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
    def __init__(self):
        self.audio_recorder = AudioRecorder()
        self.transcription_service = TranscriptionService(model_size="large-v3-turbo") # compute_typeはMLXでは不要
        self.keyboard_controller = KeyboardController()
        
        self.last_option_press_time = 0
        # is_recordingの状態はAudioRecorderインスタンスが持つので、そちらを参照する
        
        print("--- バックグラウンド録音・文字起こしツール ---")
        print("Optionキーを2回素早く押して、録音を開始/停止します。")
        print("このプログラムを終了するには、ターミナルで Ctrl+C を押してください。")
    
    # is_focus_on_textboxメソッドは変更なし...
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
        else:
            print("⏹️ Recording stopped. Starting transcription...")
            processing_thread = threading.Thread(target=self.process_recording)
            processing_thread.start()

    def process_recording(self):
        """録音を停止し、文字起こしとタイピングを行う関数"""
        # stop_recordingはファイルパスではなくNumpy配列を返す
        audio_data = self.audio_recorder.stop_recording()

        if audio_data is not None:
            # transcribeメソッドにNumpy配列を渡す
            transcribed_text = self.transcription_service.transcribe(audio_data)
            print(f"   ↳ Transcription result: {transcribed_text}")

            if transcribed_text:
                time.sleep(0.1)
                self.keyboard_controller.type(" " + transcribed_text.strip())
                print("   ↳ Text has been typed.")
        else:
            print("   ↳ Recording data was too short; processing cancelled.")

    def start_listener(self):
        with keyboard.Listener(on_press=self.on_key_press) as listener:
            try:
                listener.join()
            except KeyboardInterrupt:
                print("\nExiting program.")
                if self.audio_recorder.is_recording:
                    self.audio_recorder.stop_recording()
                listener.stop()

if __name__ == '__main__':
    recorder_app = BackgroundRecorder()
    recorder_app.start_listener()