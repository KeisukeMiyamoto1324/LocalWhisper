# main_background.py

import time
import threading
from pynput import keyboard
from pynput.keyboard import Key, Controller as KeyboardController

# 以前作成したファイルをインポート
from audio_handler import AudioRecorder 
from transcription import TranscriptionService

# --- 設定 ---
# ダブルタップと判定するキー入力の間隔（秒）
DOUBLE_TAP_THRESHOLD = 0.4

class BackgroundRecorder:
    def __init__(self):
        # 各機能のインスタンスを作成
        self.audio_recorder = AudioRecorder()
        # M1/M2/M3 Macでは compute_type="int8" が高速です
        self.transcription_service = TranscriptionService(model_size="base", compute_type="int8")
        self.keyboard_controller = KeyboardController()

        # 状態管理用の変数
        self.last_option_press_time = 0
        self.is_recording = False
        self.recording_thread = None

        print("--- バックグラウンド録音・文字起こしツール ---")
        print("Optionキーを2回素早く押して、録音を開始/停止します。")
        print("このプログラムを終了するには、ターミナルで Ctrl+C を押してください。")

    def on_key_press(self, key):
        """pynputリスナーがキー入力を検知した際に呼び出される関数"""
        # Optionキー（左: Key.alt, 右: Key.alt_r）か判定
        if key == Key.alt or key == Key.alt_r:
            current_time = time.time()
            # 前回Optionキーが押されてからの時間を計算
            time_diff = current_time - self.last_option_press_time
            self.last_option_press_time = current_time

            # ダブルタップを検出
            if time_diff < DOUBLE_TAP_THRESHOLD:
                self.handle_double_tap()

    def handle_double_tap(self):
        """ダブルタップが検出された際の処理"""
        if not self.is_recording:
            # --- 録音開始 ---
            self.is_recording = True
            print("▶️ 録音を開始しました...")
            
            # 録音処理はメインのキー監視を邪魔しないよう、別スレッドで実行
            self.recording_thread = threading.Thread(target=self.audio_recorder.start_recording)
            self.recording_thread.start()
        else:
            # --- 録音停止 & 文字起こし ---
            print("⏹️ 録音を停止しました。文字起こしを開始します...")
            
            # 録音停止後の処理（ファイル保存、文字起こし、タイピング）も別スレッドで実行
            # これにより、重い処理中でも次のキー入力を受け付けることができる
            processing_thread = threading.Thread(target=self.process_recording)
            processing_thread.start()
            
            self.is_recording = False

    def process_recording(self):
        """録音を停止し、文字起こしとタイピングを行う関数"""
        # 録音ループを停止し、保存したファイルパスを受け取る
        filepath = self.audio_recorder.stop_recording()
        
        if filepath:
            # 文字起こしを実行
            transcribed_text = self.transcription_service.transcribe(filepath)
            print(f"   ↳ 文字起こし結果: {transcribed_text}")
            
            # 結果をタイピング
            if transcribed_text:
                # 少し待機してから入力すると、入力が漏れにくい
                time.sleep(0.1)
                self.keyboard_controller.type(" " + transcribed_text.strip())
                print("   ↳ テキストを入力しました。")
        else:
            print("   ↳ 録音データが短すぎるため、処理を中断しました。")

    def start_listener(self):
        """キーボード入力を監視するリスナーを開始"""
        # 'with'構文を使うと、プログラム終了時にリスナーが自動的にクリーンアップされる
        with keyboard.Listener(on_press=self.on_key_press) as listener:
            try:
                # リスナーが停止するまでメインスレッドをブロック
                listener.join()
            except KeyboardInterrupt:
                print("\nプログラムを終了します。")
                if self.is_recording:
                    # 録音中だった場合は、安全に停止させる
                    self.audio_recorder.stop_recording()
                listener.stop()

# --- メインの実行部分 ---
if __name__ == '__main__':
    recorder_app = BackgroundRecorder()
    recorder_app.start_listener()