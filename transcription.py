# transcription.py

import mlx_whisper
import numpy as np
import threading
import time

class TranscriptionService:
    def __init__(self, model_size="large-v3-turbo", **kwargs):
        # Hugging Faceのmlx-communityからモデルをロードするようパスを組み立てます
        self.model_path = f"mlx-community/whisper-{model_size}"
        self.model = None
        self.model_lock = threading.Lock()
        self.last_transcription_time = 0
        self.min_transcription_interval = 1.0  # 最小間隔1秒

        print(f"TranscriptionService initialized with MLX.")
        print(f"Using model: '{self.model_path}'.")

        # モデルを事前にロード
        self._load_model()

    def _load_model(self):
        """モデルを事前にロードして初期化時間を短縮"""
        try:
            print("Loading MLX Whisper model...")
            # モデルを一度ロードしてキャッシュ
            dummy_audio = np.zeros(16000, dtype=np.float32)  # 1秒分のゼロデータ
            mlx_whisper.transcribe(
                audio=dummy_audio,
                path_or_hf_repo=self.model_path,
                word_timestamps=False
            )
            print("Model loaded successfully.")
        except Exception as e:
            print(f"Warning: Could not pre-load model: {e}")

    def transcribe(self, audio_data: np.ndarray, is_realtime=False):
        """
        与えられたNumPy配列の音声データを文字起こしする。
        """
        if audio_data is None or audio_data.size == 0:
            print("Error: Audio data is empty.")
            return ""

        # リアルタイム処理の場合、頻度制限を適用
        if is_realtime:
            current_time = time.time()
            if current_time - self.last_transcription_time < self.min_transcription_interval:
                return ""  # 頻度制限により処理をスキップ
            self.last_transcription_time = current_time

        # 音声データの前処理
        audio_data = self._preprocess_audio(audio_data)

        if audio_data is None:
            return ""

        # スレッドセーフな文字起こし実行
        with self.model_lock:
            try:
                print(f"Transcribing audio data with MLX model '{self.model_path}'...")

                result = mlx_whisper.transcribe(
                    audio=audio_data,
                    path_or_hf_repo=self.model_path,
                    word_timestamps=False,
                    verbose=False  # 詳細ログを無効化
                )

                transcribed_text = result.get("text", "")
                language = result.get("language", "unknown")

                if not is_realtime:  # リアルタイム処理以外の場合のみ詳細ログを出力
                    print(f"\nTranscription complete. Detected language: {language}")

                return transcribed_text.strip()

            except Exception as e:
                print(f"\nAn error occurred during MLX transcription: {e}")
                return ""

    def _preprocess_audio(self, audio_data):
        """音声データの前処理"""
        try:
            # データ型の確認と変換
            if audio_data.dtype != np.float32:
                audio_data = audio_data.astype(np.float32)

            # 音声レベルの確認
            rms = np.sqrt(np.mean(audio_data**2))
            if rms < 0.001:  # 非常に小さな音声レベルの場合はスキップ
                return None

            # 正規化
            max_val = np.max(np.abs(audio_data))
            if max_val > 0:
                audio_data = audio_data / max_val * 0.9

            return audio_data

        except Exception as e:
            print(f"Audio preprocessing error: {e}")
            return None

# --- Testing Block ---
if __name__ == '__main__':
    pass