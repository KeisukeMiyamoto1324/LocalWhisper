# main_background.py

import time
import threading
import queue
import traceback
from pynput import keyboard
from pynput.keyboard import Key, Controller as KeyboardController

from audio_handler import AudioRecorder
from transcription import TranscriptionService
from floating_ui import FloatingUIController # 修正されたUIをインポート

import AppKit
from PyObjCTools import AppHelper

try:
    from ApplicationServices import (
        AXUIElementCreateSystemWide,
        AXUIElementCopyAttributeValue,
        AXUIElementCopyParameterizedAttributeValue,
        AXValueGetValue,
        kAXFocusedUIElementAttribute,
        kAXSelectedTextRangeAttribute,
        kAXBoundsForRangeParameterizedAttribute,
        kAXValueCGRectType
    )
    from HIServices import kAXErrorSuccess
    PYOBJC_AVAILABLE = True
except ImportError as e:
    print(f"警告: 必要なmacOSライブラリがインポートできませんでした: {e}")
    PYOBJC_AVAILABLE = False


DOUBLE_TAP_THRESHOLD = 0.4

class BackgroundRecorder:
    def __init__(self):
        # ▼▼▼ 変更点 1: キューを2つ作成 ▼▼▼
        self.waveform_ui_queue = queue.Queue() # 波形表示用
        self.transcription_to_ui_queue = queue.Queue() # 文字起こしテキスト表示用

        # ▼▼▼ 変更点 2: 各コンポーネントを新しいキューで初期化 ▼▼▼
        self.transcription_service = TranscriptionService(
            model_size="large-v3-turbo", 
            ui_queue=self.transcription_to_ui_queue
        )
        self.ui_controller = FloatingUIController(
            self.waveform_ui_queue, 
            self.transcription_to_ui_queue
        )
        self.audio_recorder = AudioRecorder(
            ui_queue=self.waveform_ui_queue, 
            transcription_service=self.transcription_service
        )
        
        self.keyboard_controller = KeyboardController()
        self.last_option_press_time = 0
        
        print("--- バックグラウンド録音・文字起こしツール (ストリーミング対応版) ---")
        print("Optionキーを2回素早く押して、録音を開始/停止します。")
        print("このプログラムを終了するには、ターミナルで Ctrl+C を押してください。")

    def get_caret_bounds(self):
        if not PYOBJC_AVAILABLE:
            return None
        try:
            system_wide_element = AXUIElementCreateSystemWide()
            err, focused_element_ref = AXUIElementCopyAttributeValue(system_wide_element, kAXFocusedUIElementAttribute, None)
            if err != kAXErrorSuccess or not focused_element_ref:
                return None
            err, selected_range_ref = AXUIElementCopyAttributeValue(focused_element_ref, kAXSelectedTextRangeAttribute, None)
            if err != kAXErrorSuccess or not selected_range_ref:
                return None
            err, bounds_for_range_ref = AXUIElementCopyParameterizedAttributeValue(
                focused_element_ref,
                kAXBoundsForRangeParameterizedAttribute,
                selected_range_ref,
                None
            )
            if err != kAXErrorSuccess or not bounds_for_range_ref:
                return None
            success, rect_value = AXValueGetValue(bounds_for_range_ref, kAXValueCGRectType, None)
            if not success:
                return None
            
            print(f" ↳ Caret found at: [x={rect_value.origin.x}, y={rect_value.origin.y}]")
            return {
                'x': rect_value.origin.x,
                'y': rect_value.origin.y,
                'width': rect_value.size.width,
                'height': rect_value.size.height
            }
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
            mouse_location = AppKit.NSEvent.mouseLocation()
            active_screen = AppKit.NSScreen.mainScreen()
            for screen in AppKit.NSScreen.screens():
                if AppKit.NSMouseInRect(mouse_location, screen.frame(), False):
                    active_screen = screen
                    break
            
            bounds = self.get_caret_bounds()
            
            if not bounds:
                print("ℹ️ 録音を開始できませんでした。編集可能なテキスト入力欄にカーソルを合わせてください。")
                self.last_option_press_time = 0
                return

            print("▶️ Recording started...")
            self.ui_controller.show_at(bounds, active_screen.visibleFrame())
            # ▼▼▼ 変更点 3: ストリーミング処理を開始 ▼▼▼
            self.transcription_service.start_stream()
            self.audio_recorder.start_recording()
        else:
            print("⏹️ Recording stopped. Finalizing transcription...")
            self.ui_controller.hide()
            # ▼▼▼ 変更点 4: 録音停止と最終処理をバックグラウンドで実行 ▼▼▼
            processing_thread = threading.Thread(target=self.process_recording)
            processing_thread.start()

    def paste_text_safely(self, text_to_paste):
        """
        現在のクリップボードの内容をバックアップ・復元しながら、安全にテキストをペーストする。
        """
        pasteboard = AppKit.NSPasteboard.generalPasteboard()
        saved_items = []
        try:
            types = pasteboard.types()
            if types:
                for a_type in types:
                    data = pasteboard.dataForType_(a_type)
                    if data:
                        saved_items.append({'type': a_type, 'data': data})
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

    def process_recording(self):
        """
        録音を停止し、最終的な文字起こし結果を取得してテキストをペーストする。
        """
        # ▼▼▼ 変更点 5: ストリーミングを停止し、最終テキストを取得 ▼▼▼
        self.audio_recorder.stop_recording() # まずはマイク入力を止める
        transcribed_text = self.transcription_service.stop_stream()

        if transcribed_text:
            print(f"   ↳ Final transcription result: {transcribed_text}")
            final_text = " " + transcribed_text.strip()
            AppHelper.callLater(0, self.paste_text_safely, final_text)
        else:
            print("   ↳ Recording was empty or transcription failed; nothing to paste.")

    def run(self):
        """キーボードリスナーとUIイベントループを開始します"""
        listener = keyboard.Listener(on_press=self.on_key_press)
        listener_thread = threading.Thread(target=listener.start, daemon=True)
        listener_thread.start()
        
        AppKit.NSApplication.sharedApplication().run()


if __name__ == '__main__':
    app = BackgroundRecorder()
    app.run()