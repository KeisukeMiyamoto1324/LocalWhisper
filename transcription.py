# transcription.py

import mlx_whisper
import numpy as np

class TranscriptionService:
    def __init__(self, model_size="large-v3", **kwargs):
        # Hugging Faceのmlx-communityからモデルをロードするようパスを組み立てます
        self.model_path = f"mlx-community/whisper-{model_size}"
        print(f"TranscriptionService initialized with MLX.")
        print(f"Using model: '{self.model_path}'.")

    def transcribe(self, audio_data: np.ndarray):
        """
        与えられたNumPy配列の音声データを文字起こしする。
        """
        if audio_data is None or audio_data.size == 0:
            print("Error: Audio data is empty.")
            return "Error: No audio data to transcribe."

        print(f"Transcribing audio data with MLX model '{self.model_path}'...")

        try:
            result = mlx_whisper.transcribe(
                audio=audio_data,
                path_or_hf_repo=self.model_path # 初期化時に設定したモデルパスを使用
            )

            transcribed_text = result.get("text", "")
            language = result.get("language", "unknown")

            print(f"\nTranscription complete. Detected language: {language}")
            
            return transcribed_text.strip()

        except Exception as e:
            print(f"\nAn error occurred during MLX transcription: {e}")
            return "Error during transcription."

# --- Testing Block ---
if __name__ == '__main__':
    pass