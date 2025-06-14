# main_background.py

import time
import threading
import queue
import traceback
import numpy as np  # NumPyをインポート
from pynput import keyboard
from pynput.keyboard import Key, Controller as KeyboardController

from audio_handler import AudioRecorder
from transcription import TranscriptionService
from floating_ui import FloatingUIController

import AppKit
from PyObjCTools import AppHelper

# (Accessibility API関連のインポートは変更なし)
try:
    from ApplicationServices import (
        AXUIElementCreateSystemWide,
        AXUIElementCopyAttributeValue,
        AXUIElementCopyParameterizedAttributeValue,
        AXValueGetValue,
        kAXFocusedUIElementAttribute,
        kAXSelectedTextRangeAttribute,
        kAXBoundsForRangeParameterizedAttribute,
        kAXPositionAttribute,
        kAXSizeAttribute,
        kAXValueCGPointType,
        kAXValueCGSizeType,
        kAXValueCGRectType
    )
    from HIServices import kAXErrorSuccess
    PYOBJC_AVAILABLE = True
except ImportError as e:
    print(f"警告: 必要なmacOSライブラリがインポートできませんでした: {e}")
    PYOBJC_AVAILABLE = False


DOUBLE_TAP_THRESHOLD = 0.4

class BackgroundRecorder:
    # (init, get_caret_bounds, on_key_press, handle_double_tap, finalize_transcription, paste_text_safely, run は変更なしのため、省略します)
    def __init__(self):
        self.ui_queue = queue.Queue()
        self.text_update_queue = queue.Queue()
        self.transcription_queue = queue.Queue()
        self.ui_controller = FloatingUIController(self.ui_queue, self.text_update_queue)
        self.audio_recorder = AudioRecorder(ui_queue=self.ui_queue, transcription_queue=self.transcription_queue)
        self.transcription_service = TranscriptionService(model_size="large-v3-turbo")
        self.keyboard_controller = KeyboardController()
        self.last_option_press_time = 0
        self.transcription_worker_thread = None
        self.final_transcript = ""
        print("--- バックグラウンド録音・文字起こしツール (ストリーミング対応) ---")
        print("Optionキーを2回素早く押して、録音を開始/停止します。")

    def get_caret_bounds(self):
        if not PYOBJC_AVAILABLE: return None
        try:
            system_wide_element = AXUIElementCreateSystemWide()
            err, focused_element_ref = AXUIElementCopyAttributeValue(system_wide_element, kAXFocusedUIElementAttribute, None)
            if err != kAXErrorSuccess or not focused_element_ref: return None
            err, selected_range_ref = AXUIElementCopyAttributeValue(focused_element_ref, kAXSelectedTextRangeAttribute, None)
            if err != kAXErrorSuccess or not selected_range_ref: return None
            err, bounds_for_range_ref = AXUIElementCopyParameterizedAttributeValue(focused_element_ref, kAXBoundsForRangeParameterizedAttribute, selected_range_ref, None)
            if err != kAXErrorSuccess or not bounds_for_range_ref: return None
            success, rect_value = AXValueGetValue(bounds_for_range_ref, kAXValueCGRectType, None)
            if not success: return None
            print(f"   ↳ Caret found at: [x={rect_value.origin.x}, y={rect_value.origin.y}]")
            return {'x': rect_value.origin.x, 'y': rect_value.origin.y, 'width': rect_value.size.width, 'height': rect_value.size.height}
        except Exception as e:
            print(f"\n[エラー] カーソル位置の検出中に予期せぬ例外が発生しました: {e}")
            traceback.print_exc()
            return None

    def on_key_press(self, key):
        if key == Key.alt or key == Key.alt_r:
            current_time = time.time()
            time_diff = current_time - self.last_option_press_time
            self.last_option_press_time = current_time
            if time_diff < DOUBLE_TAP_THRESHOLD:
                AppHelper.callLater(0, self.handle_double_tap)

    def handle_double_tap(self):
        if not self.audio_recorder.is_recording:
            bounds = self.get_caret_bounds()
            if not bounds:
                print("ℹ️ 録音を開始できませんでした。編集可能なテキスト入力欄にカーソルを合わせてください。")
                self.last_option_press_time = 0
                return
            mouse_location = AppKit.NSEvent.mouseLocation()
            active_screen = AppKit.NSScreen.mainScreen()
            for screen in AppKit.NSScreen.screens():
                if AppKit.NSMouseInRect(mouse_location, screen.frame(), False):
                    active_screen = screen
                    break
            print("▶️ Recording started...")
            self.ui_controller.show_at(bounds, active_screen.visibleFrame())
            self.final_transcript = ""
            self.transcription_worker_thread = threading.Thread(target=self.run_transcription_worker)
            self.transcription_worker_thread.start()
            self.audio_recorder.start_recording()
        else:
            print("⏹️ Recording stopped. Finalizing transcription...")
            self.ui_controller.hide()
            self.audio_recorder.stop_recording()
            if self.transcription_queue:
                self.transcription_queue.put(None)
            finalizing_thread = threading.Thread(target=self.finalize_transcription)
            finalizing_thread.start()

    def run_transcription_worker(self):
        """
        スライディングウィンドウ方式で、精度を維持しながら文字起こしを行うワーカースレッド
        """
        session_transcript = ""
        # 精度向上のため、音声データを保持するバッファを用意
        audio_buffer = np.array([], dtype=np.float32)
        SAMPLE_RATE = 16000  # AudioRecorderの設定と合わせる
        
        # 常に10秒分の音声コンテキストをモデルに渡す
        CONTEXT_SECONDS = 10
        MAX_BUFFER_SAMPLES = SAMPLE_RATE * CONTEXT_SECONDS
        
        # 処理とUI更新の最小間隔（頻繁すぎる更新を防ぐ）
        MIN_PROCESS_INTERVAL = 0.5 
        last_process_time = 0

        while True:
            audio_chunk = self.transcription_queue.get()
            if audio_chunk is None:
                # 録音終了時、バッファに音声が残っていれば最後の処理を行う
                if audio_buffer.any():
                     self.process_audio_buffer(audio_buffer, session_transcript)
                self.transcription_queue.task_done()
                break

            # 新しいチャンクをバッファに追加
            audio_buffer = np.concatenate([audio_buffer, audio_chunk])

            # バッファが最大長を超えたら、古い部分を削って長さを維持（スライディングウィンドウ）
            if len(audio_buffer) > MAX_BUFFER_SAMPLES:
                audio_buffer = audio_buffer[-MAX_BUFFER_SAMPLES:]

            # 頻繁に処理しすぎないように間隔をあける
            current_time = time.time()
            if current_time - last_process_time > MIN_PROCESS_INTERVAL:
                session_transcript = self.process_audio_buffer(audio_buffer, session_transcript)
                last_process_time = current_time
            
            self.transcription_queue.task_done()
            
        print("Transcription worker finished.")

    def process_audio_buffer(self, buffer, current_transcript):
        """音声バッファを文字起こしして、結果を更新するヘルパー関数"""
        
        # バッファ全体を文字起こし
        result = self.transcription_service.transcribe(
            buffer,
            prompt=current_transcript
        )

        # 結果が有効で、かつ変化があった場合のみ処理
        if result and result.strip() != current_transcript.strip():
            # プロンプトが含まれているかチェック
            if result.strip().startswith(current_transcript.strip()):
                current_transcript = result.strip()
            else:
                current_transcript += " " + result.strip()
            
            # 最終結果を更新
            self.final_transcript = current_transcript
            
            # UIに最新の全文を送る
            self.text_update_queue.put({"text": self.final_transcript, "is_final": True})
        
        return current_transcript

    def finalize_transcription(self):
        if self.transcription_worker_thread:
            self.transcription_worker_thread.join()
        print(f"   ↳ Final Transcription: {self.final_transcript}")
        if self.final_transcript:
            self.text_update_queue.put({"text": self.final_transcript, "is_final": True})
            time.sleep(0.1)
            final_text_to_paste = " " + self.final_transcript
            AppHelper.callLater(0, self.paste_text_safely, final_text_to_paste)
        self.last_option_press_time = 0

    def paste_text_safely(self, text_to_paste):
        pasteboard = AppKit.NSPasteboard.generalPasteboard()
        saved_items = []
        try:
            types = pasteboard.types()
            if types:
                for a_type in types:
                    data = pasteboard.dataForType_(a_type)
                    if data: saved_items.append({'type': a_type, 'data': data})
            print("   ↳ Clipboard content backed up.")
        except Exception as e:
            print(f"   ↳ Warning: Could not back up clipboard content: {e}")
        try:
            pasteboard.clearContents()
            pasteboard.setString_forType_(text_to_paste, AppKit.NSStringPboardType)
            time.sleep(0.1)
            with self.keyboard_controller.pressed(Key.cmd):
                self.keyboard_controller.press('v')
                self.keyboard_controller.release('v')
            print("   ↳ Paste command sent.")
        finally:
            try:
                time.sleep(0.1)
                pasteboard.clearContents()
                for item in saved_items:
                    pasteboard.setData_forType_(item['data'], item['type'])
                print("   ↳ Clipboard content restored.")
            except Exception as e:
                print(f"   ↳ Warning: Could not restore clipboard content: {e}")

    def run(self):
        listener = keyboard.Listener(on_press=self.on_key_press)
        listener_thread = threading.Thread(target=listener.start, daemon=True)
        listener_thread.start()
        AppKit.NSApplication.sharedApplication().run()

if __name__ == '__main__':
    app = BackgroundRecorder()
    app.run()