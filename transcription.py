# transcription.py

import mlx_whisper
import numpy as np

class TranscriptionService:
    def __init__(self, model_size="large-v3-turbo", **kwargs):
        # Hugging Faceのmlx-communityからモデルをロード
        self.model_path = f"mlx-community/whisper-{model_size}"
        print(f"TranscriptionService initialized with MLX.")
        print(f"Using model: '{self.model_path}'.")

    def transcribe(self, audio_data: np.ndarray, prompt: str = None, language: str = "ja"):
        """
        与えられた音声データを文字起こしする。
        prompt: 前のチャンクの文字起こし結果。文脈維持に使う。
        language: 言語を固定して高速化。
        """
        if audio_data is None or audio_data.size == 0:
            return ""

        print(f"Transcribing audio chunk... (prompt: '{prompt[:20]}...')")

        try:
            # mlx_whisper.transcribeに関心のある引数を渡す
            result = mlx_whisper.transcribe(
                audio=audio_data,
                path_or_hf_repo=self.model_path,
                initial_prompt=prompt, # initial_promptとして渡す
                language=language,
                # beam_size=1 # さらなる高速化のためにGreedy Searchにする場合はコメントを外す
            )

            transcribed_text = result.get("text", "")
            print(f" -> Chunk result: '{transcribed_text}'")
            return transcribed_text.strip()

        except Exception as e:
            print(f"\nAn error occurred during MLX transcription: {e}")
            return "Error during transcription."

# --- Testing Block ---
if __name__ == '__main__':
    pass