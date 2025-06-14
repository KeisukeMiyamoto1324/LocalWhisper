# main_background.py

import time
import threading
from pynput import keyboard
from pynput.keyboard import Key, Controller as KeyboardController

from audio_handler import AudioRecorder
from transcription import TranscriptionService

try:
    from ApplicationServices import AXUIElementCreateSystemWide, AXUIElementCopyAttributeValue
    from HIServices import kAXErrorSuccess
    PYOBJC_AVAILABLE = True
except ImportError:
    PYOBJC_AVAILABLE = False
    print("警告: PyObjCがインストールされていません。テキストボックスのフォーカスチェックは無効になります。")
    print("       次のコマンドでインストールできます: pip3 install pyobjc")


DOUBLE_TAP_THRESHOLD = 0.4

class BackgroundRecorder:
    # __init__にstatus_update_callback引数を追加
    def __init__(self, status_update_callback=None):
        self.audio_recorder = AudioRecorder()
        self.transcription_service = TranscriptionService(model_size="large-v3-turbo")
        self.keyboard_controller = KeyboardController()
        
        # UIの状態を更新するためのコールバック関数を保持
        self.status_update_callback = status_update_callback
        
        self.last_option_press_time = 0
        
        print("--- バックグラウンド録音・文字起こしツール ---")
        print("Optionキーを2回素早く押して、録音を開始/停止します。")
        print("アプリケーションを終了するには、メニューバーのQuitを選択してください。")

    def is_focus_on_textbox(self):
        if not PYOBJC_AVAILABLE:
            return False
        try:
            system_wide_element = AXUIElementCreateSystemWide()
            err, focused_element = AXUIElementCopyAttributeValue(
                system_wide_element, "AXFocusedUIElement", None
            )
            if err != kAXErrorSuccess or not focused_element:
                return False

            err, role = AXUIElementCopyAttributeValue(focused_element, "AXRole", None)
            if err == kAXErrorSuccess and role in ["AXTextField", "AXTextArea"]:
                return True

            err, role_description = AXUIElementCopyAttributeValue(focused_element, "AXRoleDescription", None)
            if err == kAXErrorSuccess and role_description:
                if role_description.lower() in ["text area", "editor", "text editor"]:
                    return True
            
            return False
        except Exception:
            return False

    def on_key_press(self, key):
        if key == Key.alt or key == Key.alt_r:
            current_time = time.time()
            time_diff = current_time - self.last_option_press_time
            self.last_option_press_time = current_time

            if time_diff < DOUBLE_TAP_THRESHOLD:
                self.handle_double_tap()

    def handle_double_tap(self):
        if not self.audio_recorder.is_recording:
            if not self.is_focus_on_textbox():
                if PYOBJC_AVAILABLE:
                    print("ℹ️ Recording not started: Cursor is not in a text input field.")
                else:
                    print("ℹ️ Recording not started: Cannot check focus because PyObjC is not installed.")
                self.last_option_press_time = 0
                return

            print("▶️ Recording started...")
            self.audio_recorder.start_recording()
            # 【変更点】録音開始をUIに通知するためのコールバックを呼び出す
            if self.status_update_callback:
                self.status_update_callback(True)
        else:
            print("⏹️ Recording stopped. Starting transcription...")
            # 【変更点】録音停止をUIに通知するためのコールバックを呼び出す
            if self.status_update_callback:
                self.status_update_callback(False)
            
            processing_thread = threading.Thread(target=self.process_recording)
            processing_thread.start()

    def process_recording(self):
        audio_data = self.audio_recorder.stop_recording()

        if audio_data is not None:
            transcribed_text = self.transcription_service.transcribe(audio_data)
            print(f"   ↳ Transcription result: {transcribed_text}")

            if transcribed_text:
                time.sleep(0.1)
                self.keyboard_controller.type(" " + transcribed_text.strip())
                print("   ↳ Text has been typed.")
        else:
            print("   ↳ Recording data was too short; processing cancelled.")

    def start_listener(self):
        # このメソッドはスレッドから呼び出される
        self.listener = keyboard.Listener(on_press=self.on_key_press)
        self.listener.start()
        print("Keyboard listener started in a separate thread.")

    def stop_listener(self):
        # アプリケーション終了時にリスナーを停止させる
        if hasattr(self, 'listener') and self.listener.is_alive():
            self.listener.stop()
            print("Keyboard listener stopped.")
        if self.audio_recorder.is_recording:
            # 念のため録音も停止
            self.audio_recorder.stop_recording()