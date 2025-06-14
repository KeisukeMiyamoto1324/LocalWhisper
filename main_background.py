# main_background.py

import time
import threading
import sys
import queue
from pynput import keyboard
from pynput.keyboard import Key, Controller as KeyboardController
from PyQt6.QtWidgets import QApplication

from audio_handler import AudioRecorder
from transcription import TranscriptionService
from floating_ui import FloatingUI

try:
    # シンプルなロジックに必要なインポート文に戻します
    from ApplicationServices import AXUIElementCreateSystemWide, AXUIElementCopyAttributeValue, AXValueGetValue
    from CoreFoundation import kAXValueCGPointType, kAXValueCGSizeType
    from HIServices import kAXErrorSuccess
    import ctypes
    PYOBJC_AVAILABLE = True
except ImportError:
    PYOBJC_AVAILABLE = False
    print("Warning: PyObjC is not fully available. Text box focus check will be disabled.")
    print("         Install with: pip3 install pyobjc-framework-Quartz pyobjc-framework-ApplicationServices")


DOUBLE_TAP_THRESHOLD = 0.4

class BackgroundRecorder:
    def __init__(self, app):
        self.app = app
        self.audio_recorder = AudioRecorder()
        self.transcription_service = TranscriptionService(model_size="large-v3-turbo")
        self.keyboard_controller = KeyboardController()
        
        self.last_option_press_time = 0
        
        self.waveform_queue = queue.Queue(maxsize=5)
        self.floating_ui = FloatingUI()
        
        self.ui_update_thread = threading.Thread(target=self.update_ui_from_queue, daemon=True)
        self.ui_update_thread.start()

        print("--- Background Recording and Transcription Tool ---")
        print("Press Option key twice quickly to start/stop recording.")
        print("To quit, use the menu bar icon or Ctrl+C in the terminal.")

    def get_focused_textbox_frame(self):
        """
        Gets the screen coordinates (x, y, width, height) of the focused text element.
        (Reverted to the original simple logic)
        """
        if not PYOBJC_AVAILABLE:
            return None
        try:
            system_wide_element = AXUIElementCreateSystemWide()
            err, focused_element = AXUIElementCopyAttributeValue(system_wide_element, "AXFocusedUIElement", None)
            if err != kAXErrorSuccess or not focused_element:
                return None

            # --- Original simple detection logic ---
            # 1. Check standard roles
            err, role = AXUIElementCopyAttributeValue(focused_element, "AXRole", None)
            is_text_field = err == kAXErrorSuccess and role in ["AXTextField", "AXTextArea", "AXWebArea"]

            # 2. If not found, check role descriptions
            if not is_text_field:
                err, role_desc = AXUIElementCopyAttributeValue(focused_element, "AXRoleDescription", None)
                if not (err == kAXErrorSuccess and role_desc and isinstance(role_desc, str) and role_desc.lower() in ["text area", "editor", "text editor"]):
                    return None # If this also fails, we don't recognize it.
            
            # --- Get Position and Size ---
            err, pos_ref = AXUIElementCopyAttributeValue(focused_element, "AXPosition", None)
            if err != kAXErrorSuccess: return None
            point_ptr = ctypes.c_void_p()
            AXValueGetValue(pos_ref, kAXValueCGPointType, ctypes.byref(point_ptr))
            point = ctypes.cast(point_ptr, ctypes.POINTER(ctypes.c_double * 2)).contents
            x, y = point[0], point[1]

            err, size_ref = AXUIElementCopyAttributeValue(focused_element, "AXSize", None)
            if err != kAXErrorSuccess: return None
            size_ptr = ctypes.c_void_p()
            AXValueGetValue(size_ref, kAXValueCGSizeType, ctypes.byref(size_ptr))
            size = ctypes.cast(size_ptr, ctypes.POINTER(ctypes.c_double * 2)).contents
            w, h = size[0], size[1]
            
            return (x, y, w, h)
        except Exception as e:
            print(f"Error getting focused element frame: {e}")
            return None

    def on_key_press(self, key):
        if key == Key.alt or key == Key.alt_r:
            current_time = time.time()
            time_diff = current_time - self.last_option_press_time
            self.last_option_press_time = current_time

            if time_diff < DOUBLE_TAP_THRESHOLD:
                self.handle_double_tap()

    def handle_double_tap(self):
        if not self.audio_recorder.is_recording:
            frame = self.get_focused_textbox_frame()
            if frame is None:
                print("ℹ️ Recording not started: Cursor is not in a recognized text input field.")
                self.last_option_press_time = 0
                return
            
            x, y, w, h = frame
            ui_x = x + (w / 2) - (self.floating_ui.width() / 2)
            ui_y = y + h + 5
            self.floating_ui.update_position(int(ui_x), int(ui_y))
            self.floating_ui.show()

            print("▶️ Recording started...")
            self.audio_recorder.start_recording(waveform_queue=self.waveform_queue)
        else:
            print("⏹️ Recording stopped. Starting transcription...")
            self.floating_ui.hide()
            processing_thread = threading.Thread(target=self.process_recording)
            processing_thread.start()

    def update_ui_from_queue(self):
        while True:
            try:
                audio_chunk = self.waveform_queue.get()
                if self.floating_ui.isVisible():
                    self.floating_ui.update_waveform_signal.emit(audio_chunk)
            except Exception as e:
                print(f"Error in UI update thread: {e}")

    def process_recording(self):
        audio_data = self.audio_recorder.stop_recording()

        if audio_data is not None and audio_data.size > 0:
            transcribed_text = self.transcription_service.transcribe(audio_data)
            print(f"   ↳ Transcription result: {transcribed_text}")

            if transcribed_text:
                time.sleep(0.1)
                self.keyboard_controller.type(" " + transcribed_text.strip())
                print("   ↳ Text has been typed.")
        else:
            print("   ↳ Recording data was too short; processing cancelled.")

    def start_listener(self):
        self.listener = keyboard.Listener(on_press=self.on_key_press)
        self.listener.start()

if __name__ == '__main__':
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    recorder_app = BackgroundRecorder(app)
    
    listener_thread = threading.Thread(target=recorder_app.start_listener, daemon=True)
    listener_thread.start()
    
    def on_about_to_quit():
        print("\nExiting program.")
        if recorder_app.audio_recorder.is_recording:
            recorder_app.audio_recorder.stop_recording()
        if hasattr(recorder_app, 'listener'):
             recorder_app.listener.stop()
    
    app.aboutToQuit.connect(on_about_to_quit)

    print("Application is running in the background. Press Ctrl+C in terminal to quit.")
    
    sys.exit(app.exec())