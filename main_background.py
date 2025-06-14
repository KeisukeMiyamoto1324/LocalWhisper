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
            is_text_field = (err == kAXErrorSuccess and role in ["AXTextField", "AXTextArea"])
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
                # マウスカーソルがどの物理スクリーン上にあるかを判定
                if AppKit.NSMouseInRect(mouse_location, screen.frame(), False):
                    active_screen = screen
                    break
            
            bounds = self.get_focused_element_bounds()
            if not bounds:
                print("ℹ️ 録音を開始できませんでした。テキスト入力欄にカーソルを合わせてください。")
                self.last_option_press_time = 0
                return

            print("▶️ Recording started...")
            # ▼▼▼ ここが修正箇所 ▼▼▼
            # UIの位置計算には、物理的なフレームではなく「可視フレーム」を渡す
            self.ui_controller.show_at(bounds, active_screen.visibleFrame())
            # ▲▲▲ ここまで ▲▲▲
            self.audio_recorder.start_recording()
        else:
            print("⏹️ Recording stopped. Starting transcription...")
            self.ui_controller.hide()
            processing_thread = threading.Thread(target=self.process_recording)
            processing_thread.start()

    def process_recording(self):
        """録音を停止し、文字起こしとタイピングを行う関数"""
        audio_data = self.audio_recorder.stop_recording()

        if audio_data is not None:
            transcribed_text = self.transcription_service.transcribe(audio_data)
            print(f"   ↳ Transcription result: {transcribed_text}")

            if transcribed_text:
                time.sleep(0.1)
                self.keyboard_controller.type(" " + transcribed_text.strip())
                print("   ↳ Text has been typed.")
        else:
            print("   ↳ Recording data was too short; processing cancelled.")

    def run(self):
        """キーボードリスナーとUIイベントループを開始します"""
        listener = keyboard.Listener(on_press=self.on_key_press)
        listener_thread = threading.Thread(target=listener.start, daemon=True)
        listener_thread.start()
        
        AppKit.NSApplication.sharedApplication().run()


if __name__ == '__main__':
    app = BackgroundRecorder()
    app.run()