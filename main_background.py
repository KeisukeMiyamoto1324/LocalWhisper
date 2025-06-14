# main_background.py

import time
import threading
import queue
import traceback
from pynput import keyboard
from pynput.keyboard import Key, Controller as KeyboardController

from audio_handler import AudioRecorder
from transcription import TranscriptionService
from floating_ui import FloatingUIController

import AppKit
from PyObjCTools import AppHelper

# ApplicationServicesはキー入力のシミュレーションには直接不要だが、
# UI要素の取得のために残しておく
try:
    from ApplicationServices import (
        AXUIElementCreateSystemWide,
        AXUIElementCopyAttributeValue,
        AXValueGetValue,
        kAXFocusedUIElementAttribute,
        kAXRoleAttribute,
        kAXPositionAttribute,
        kAXSizeAttribute,
        kAXValueCGPointType,
        kAXValueCGSizeType
    )
    from HIServices import kAXErrorSuccess
    PYOBJC_AVAILABLE = True
except ImportError as e:
    print(f"警告: 必要なmacOSライブラリがインポートできませんでした: {e}")
    PYOBJC_AVAILABLE = False


DOUBLE_TAP_THRESHOLD = 0.4

class BackgroundRecorder:
    def __init__(self):
        self.ui_queue = queue.Queue()
        self.ui_controller = FloatingUIController(self.ui_queue)
        
        self.audio_recorder = AudioRecorder(ui_queue=self.ui_queue)
        self.transcription_service = TranscriptionService(model_size="large-v3-turbo")
        self.keyboard_controller = KeyboardController()
        
        self.last_option_press_time = 0
        
        print("--- バックグラウンド録音・文字起こしツール ---")
        print("Optionキーを2回素早く押して、録音を開始/停止します。")
        print("このプログラムを終了するには、ターミナルで Ctrl+C を押してください。")

    def get_focused_element_bounds(self):
        """現在フォーカスされているUI要素の位置とサイズを取得します"""
        if not PYOBJC_AVAILABLE:
            return None
        
        try:
            system_wide_element = AXUIElementCreateSystemWide()
            err, focused_element = AXUIElementCopyAttributeValue(system_wide_element, kAXFocusedUIElementAttribute, None)
            if err != kAXErrorSuccess or not focused_element:
                return None

            err, role = AXUIElementCopyAttributeValue(focused_element, kAXRoleAttribute, None)
            is_text_field = (err == kAXErrorSuccess and role in ["AXTextField", "AXTextArea", "AXSecureTextField"])
            if not is_text_field:
                 return None

            err_pos, pos_ref = AXUIElementCopyAttributeValue(focused_element, kAXPositionAttribute, None)
            err_size, size_ref = AXUIElementCopyAttributeValue(focused_element, kAXSizeAttribute, None)

            if err_pos == kAXErrorSuccess and err_size == kAXErrorSuccess and pos_ref and size_ref:
                success_pos, pos = AXValueGetValue(pos_ref, kAXValueCGPointType, None)
                success_size, size = AXValueGetValue(size_ref, kAXValueCGSizeType, None)
                if success_pos and success_size:
                    return {'x': pos.x, 'y': pos.y, 'width': size.width, 'height': size.height}
            return None

        except Exception as e:
            print(f"\n[エラー] UI要素の位置取得中に予期せぬ例外が発生しました: {e}")
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
            
            bounds = self.get_focused_element_bounds()
            if not bounds:
                print("ℹ️ 録音を開始できませんでした。テキスト入力欄にカーソルを合わせてください。")
                self.last_option_press_time = 0
                return

            print("▶️ Recording started...")
            self.ui_controller.show_at(bounds, active_screen.visibleFrame())
            self.audio_recorder.start_recording()
        else:
            print("⏹️ Recording stopped. Starting transcription...")
            self.ui_controller.hide()
            processing_thread = threading.Thread(target=self.process_recording)
            processing_thread.start()

    # ▼▼▼ ここからが新しいメソッドです ▼▼▼
    def paste_text_safely(self, text_to_paste):
        """
        現在のクリップボードの内容をバックアップ・復元しながら、安全にテキストをペーストする。
        """
        pasteboard = AppKit.NSPasteboard.generalPasteboard()
        
        # 1. 現在のクリップボードの内容を型情報と一緒にバックアップ
        saved_items = []
        try:
            types = pasteboard.types()
            if types:
                for a_type in types:
                    data = pasteboard.dataForType_(a_type)
                    if data:
                        saved_items.append({'type': a_type, 'data': data})
            print("   ↳ Clipboard content backed up.")
        except Exception as e:
            print(f"   ↳ Warning: Could not back up clipboard content: {e}")

        try:
            # 2. 文字起こしテキストをクリップボードに設定
            pasteboard.clearContents()
            pasteboard.setString_forType_(text_to_paste, AppKit.NSStringPboardType)
            
            # 3. Command + V (ペースト) を実行
            time.sleep(0.1) # OSがクリップボードを認識するのを待つ
            with self.keyboard_controller.pressed(Key.cmd):
                self.keyboard_controller.press('v')
                self.keyboard_controller.release('v')
            print("   ↳ Paste command sent.")

        finally:
            # 4. バックアップした内容をクリップボードに復元
            # 処理の成功・失敗に関わらず、必ず実行される
            try:
                # ペースト処理が完了するのを少し待ってから復元する
                time.sleep(0.1)
                pasteboard.clearContents()
                for item in saved_items:
                    pasteboard.setData_forType_(item['data'], item['type'])
                print("   ↳ Clipboard content restored.")
            except Exception as e:
                print(f"   ↳ Warning: Could not restore clipboard content: {e}")

    def process_recording(self):
        """録音を停止し、文字起こしとテキスト設定を行う関数"""
        audio_data = self.audio_recorder.stop_recording()

        if audio_data is not None:
            transcribed_text = self.transcription_service.transcribe(audio_data)
            print(f"   ↳ Transcription result: {transcribed_text}")

            if transcribed_text:
                final_text = " " + transcribed_text.strip()
                
                # 新しい安全なペーストメソッドをメインスレッドで呼び出す
                AppHelper.callLater(0, self.paste_text_safely, final_text)
        else:
            print("   ↳ Recording data was too short; processing cancelled.")
    # ▲▲▲ ここまでが変更箇所です ▲▲▲

    def run(self):
        """キーボードリスナーとUIイベントループを開始します"""
        listener = keyboard.Listener(on_press=self.on_key_press)
        listener_thread = threading.Thread(target=listener.start, daemon=True)
        listener_thread.start()
        
        AppKit.NSApplication.sharedApplication().run()


if __name__ == '__main__':
    app = BackgroundRecorder()
    app.run()