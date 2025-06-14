# main_background.py (VS Code対応版)

import time
import threading
from pynput import keyboard
from pynput.keyboard import Key, Controller as KeyboardController

# 以前作成したファイルのインポート
from audio_handler import AudioRecorder
from transcription import TranscriptionService

# --- PyObjCのセットアップ ---
try:
    from ApplicationServices import AXUIElementCreateSystemWide, AXUIElementCopyAttributeValue
    from HIServices import kAXErrorSuccess
    PYOBJC_AVAILABLE = True
except ImportError:
    PYOBJC_AVAILABLE = False
    print("警告: PyObjCがインストールされていません。テキストボックスのフォーカスチェックは無効になります。")
    print("         次のコマンドでインストールできます: pip3 install pyobjc")


# --- 設定 ---
DOUBLE_TAP_THRESHOLD = 0.4

class BackgroundRecorder:
    def __init__(self):
        # 機能クラスのインスタンス化
        self.audio_recorder = AudioRecorder()
        # M1/M2/M3 Macでは compute_type="int8" が高速です
        self.transcription_service = TranscriptionService(model_size="large-v3-turbo", compute_type="int8")
        self.keyboard_controller = KeyboardController()

        # 状態管理用の変数
        self.last_option_press_time = 0
        self.is_recording = False
        self.recording_thread = None

        print("--- バックグラウンド録音・文字起こしツール ---")
        print("Optionキーを2回素早く押して、録音を開始/停止します。")
        print("このプログラムを終了するには、ターミナルで Ctrl+C を押してください。")

    def is_focus_on_textbox(self):
        """
        PyObjCを使用して、現在フォーカスされているUI要素がテキスト入力フィールドかどうかをチェックします。
        このスクリプトを実行するターミナル/アプリには「アクセシビリティ」の権限が必要です。
        """
        if not PYOBJC_AVAILABLE:
            return False

        try:
            system_wide_element = AXUIElementCreateSystemWide()
            err, focused_element = AXUIElementCopyAttributeValue(
                system_wide_element, "AXFocusedUIElement", None
            )
            if err != kAXErrorSuccess or not focused_element:
                return False

            # --- ★ 修正箇所 ---
            # ネイティブアプリと非ネイティブアプリ（VS Codeなど）の両方に対応するための二段階チェック

            # 1. 標準的な役割（Role）をチェック (ネイティブアプリ向け)
            err, role = AXUIElementCopyAttributeValue(focused_element, "AXRole", None)
            if err == kAXErrorSuccess and role in ["AXTextField", "AXTextArea"]:
                return True

            # 2. 役割の説明（RoleDescription）をチェック (VS CodeなどElectron製アプリ向け)
            #    役割が汎用的でも、説明に具体的な情報が含まれている場合がある
            err, role_description = AXUIElementCopyAttributeValue(focused_element, "AXRoleDescription", None)
            if err == kAXErrorSuccess and role_description:
                # VS Codeのエディタなどは説明が "text area" や "editor" になっていることがある
                # 大文字・小文字を区別しないように .lower() で比較
                if role_description.lower() in ["text area", "editor", "text editor"]:
                    return True
            
            # どちらのチェックにも当てはまらなければFalseを返す
            return False

        except Exception:
            # アクセシビリティ権限がない場合などにエラーになる可能性がある
            return False

    def on_key_press(self, key):
        """pynputリスナーがキー入力を検知した際に呼び出される関数"""
        if key == Key.alt or key == Key.alt_r:
            current_time = time.time()
            time_diff = current_time - self.last_option_press_time
            self.last_option_press_time = current_time

            if time_diff < DOUBLE_TAP_THRESHOLD:
                self.handle_double_tap()

    def handle_double_tap(self):
        """ダブルタップが検出された際の処理"""
        if not self.is_recording:
            # --- 録音開始 ---
            if not self.is_focus_on_textbox():
                if PYOBJC_AVAILABLE:
                    print("ℹ️ Recording not started: Cursor is not in a text input field.")
                else:
                    print("ℹ️ Recording not started: Cannot check focus because PyObjC is not installed.")
                self.last_option_press_time = 0
                return

            self.is_recording = True
            print("▶️ Recording started...")

            self.recording_thread = threading.Thread(target=self.audio_recorder.start_recording)
            self.recording_thread.start()
        else:
            # --- 録音停止 & 文字起こし ---
            print("⏹️ Recording stopped. Starting transcription...")
            
            processing_thread = threading.Thread(target=self.process_recording)
            processing_thread.start()
            
            self.is_recording = False

    def process_recording(self):
        """録音を停止し、文字起こしとタイピングを行う関数"""
        filepath = self.audio_recorder.stop_recording()

        if filepath:
            transcribed_text = self.transcription_service.transcribe(filepath)
            print(f"   ↳ Transcription result: {transcribed_text}")

            if transcribed_text:
                time.sleep(0.1)
                self.keyboard_controller.type(" " + transcribed_text.strip())
                print("   ↳ Text has been typed.")
        else:
            print("   ↳ Recording data was too short; processing cancelled.")

    def start_listener(self):
        """キーボード入力を監視するリスナーを開始"""
        with keyboard.Listener(on_press=self.on_key_press) as listener:
            try:
                listener.join()
            except KeyboardInterrupt:
                print("\nExiting program.")
                if self.is_recording:
                    self.audio_recorder.stop_recording()
                listener.stop()

# --- メインの実行部分 ---
if __name__ == '__main__':
    recorder_app = BackgroundRecorder()
    recorder_app.start_listener()