# transcription.py (Corrected MLX version)

import mlx_whisper
import os

class TranscriptionService:
    def __init__(self, model_size="large-v3", **kwargs):
        """
        Initializes the TranscriptionService using MLX.
        MLX is a framework from Apple optimized for Apple Silicon. It automatically
        handles device placement (CPU/GPU) and uses optimized computation paths.

        Args:
            model_size (str): The name of the Whisper model to use.
                              (e.g., "tiny.en", "base", "small", "medium", "large-v3")
            **kwargs: Absorbs other arguments like 'device' and 'compute_type' for
                      backward compatibility with how the class was called before,
                      even though they are not used by MLX.
        """
        self.model_size = model_size
        print(f"TranscriptionService initialized with MLX.")
        print(f"Using model: '{self.model_size}'. Model will be automatically downloaded and optimized on first use.")

    def transcribe(self, audio_file_path):
        """
        Transcribes the given audio file using the whisper model on MLX.

        Args:
            audio_file_path (str): The path to the audio file to transcribe.

        Returns:
            str: The transcribed text.
        """
        if not os.path.exists(audio_file_path):
            print(f"Error: Audio file not found at {audio_file_path}")
            return "Error: Audio file not found."

        print(f"Transcribing {audio_file_path} with MLX model '{self.model_size}'...")

        try:
            # --- FIX ---
            # The keyword argument for specifying the model is 'path_or_model', not 'model'.
            # This was the cause of the error.
            result = mlx_whisper.transcribe(
                audio=audio_file_path,
                # path_or_model=self.model_size, # Corrected this line
                # verbose=True
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
    service = TranscriptionService(model_size="base.en")
    pass