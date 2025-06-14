# main.py (修正版)

import toga
from toga.style import Pack
from toga.style.pack import COLUMN, ROW, CENTER
import threading

from audio_handler import AudioRecorder
from transcription import TranscriptionService

class OpenSuperWhisper(toga.App):
    def startup(self):
        # 機能クラスのインスタンス化
        self.audio_recorder = AudioRecorder()
        self.transcription_service = TranscriptionService()

        # UI要素の作成
        # --- 修正点1: DeprecationWarningを解消するため、paddingをmarginに変更 ---
        self.main_box = toga.Box(style=Pack(direction=COLUMN, margin=10))

        self.record_button = toga.Button(
            "Record", on_press=self.toggle_recording, style=Pack(margin=5, width=200)
        )
        self.status_label = toga.Label("Press 'Record' to start.", style=Pack(text_align=CENTER, margin=5))
        self.result_box = toga.MultilineTextInput(readonly=True, style=Pack(flex=1, margin_top=10))
        
        # UIの配置
        self.main_box.add(self.record_button)
        self.main_box.add(self.status_label)
        self.main_box.add(self.result_box)

        self.main_window = toga.MainWindow(title=self.formal_name)
        self.main_window.content = self.main_box
        self.main_window.show()

    def toggle_recording(self, widget):
        if self.audio_recorder.is_recording:
            # 録音停止と文字起こし
            self.status_label.text = "Stopping and transcribing..."
            self.record_button.enabled = False
            
            # 新しいスレッドで停止と文字起こしを実行
            threading.Thread(target=self.stop_and_transcribe).start()

        else:
            # 録音開始
            self.record_button.label = "Stop Recording"
            self.status_label.text = "Recording..."
            
            # 録音処理を別スレッドで開始
            self.recording_thread = threading.Thread(target=self.audio_recorder.start_recording)
            self.recording_thread.start()

    def stop_and_transcribe(self):
        """バックグラウンドスレッドで実行される関数"""
        filepath = self.audio_recorder.stop_recording()
        if filepath:
            transcribed_text = self.transcription_service.transcribe(filepath)
            
            # GUIの更新はメインスレッドで行う
            def update_ui():
                self.result_box.value = transcribed_text
                self.status_label.text = "Transcription complete. Press 'Record' to start."
                self.record_button.label = "Record"
                self.record_button.enabled = True
                
            # --- 修正点2: スレッドセーフな方法でGUI更新を呼び出す ---
            self.loop.call_soon_threadsafe(update_ui)
        else:
            def update_ui_for_empty():
                self.status_label.text = "Recording was too short."
                self.record_button.label = "Record"
                self.record_button.enabled = True
            
            # --- 修正点2: こちらも同様に修正 ---
            self.loop.call_soon_threadsafe(update_ui_for_empty)


def main():
    return OpenSuperWhisper('OpenSuperWhisper', 'ru.starmel.OpenSuperWhisper.py')

if __name__ == '__main__':
    main().main_loop()