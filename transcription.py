# transcription.py

import mlx_whisper
import os
import numpy as np # NumPyをインポート

class TranscriptionService:
    def __init__(self, model_size="large-v3", **kwargs):
        self.model_size = model_size
        # 引数を吸収するための**kwargsはそのままにしておきます
        print(f"TranscriptionService initialized with MLX.")
        print(f"Using model: '{self.model_size}'.")

    def transcribe(self, audio_data: np.ndarray):
        """
        与えられたNumPy配列の音声データを文字起こしする。

        Args:
            audio_data (np.ndarray): 文字起こしする音声データ。

        Returns:
            str: 文字起こしされたテキスト。
        """
        if audio_data is None or audio_data.size == 0:
            print("Error: Audio data is empty.")
            return "Error: No audio data to transcribe."

        print(f"Transcribing audio data with MLX model '{self.model_size}'...")

        try:
            # audio引数にファイルパスの代わりにNumPy配列を渡す
            result = mlx_whisper.transcribe(
                audio=audio_data,
                path_or_hf_repo="mlx-community/whisper-large-v3-turbo"
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
    # このテストブロックは直接実行しない限り動作しません
    pass