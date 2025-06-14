# transcription.py (faster-whisper版)

from faster_whisper import WhisperModel
import os

class TranscriptionService:
    def __init__(self, model_size="base.en", device="cpu", compute_type="int8"):
        """
        TranscriptionServiceを初期化します。

        Args:
            model_size (str): 使用するWhisperモデルのサイズ。
                              (例: "tiny.en", "base", "small", "medium", "large-v3")
            device (str): 推論に使用するデバイス ("cpu", "cuda", "mps")。
                          Apple Siliconでは"cpu"または"mps"が推奨されます。
            compute_type (str): 計算に使用するデータ型 ("int8", "float16", "float32")。
                                "int8"は速度とメモリ効率が良いです。
        """
        # モデルがローカルにない場合、初回実行時に自動でダウンロードされます。
        # ダウンロード先: ~/.cache/huggingface/hub/models--Systran--faster-whisper-*
        print(f"Loading model: {model_size} ({compute_type}) on {device}...")
        self.model = WhisperModel(model_size, device=device, compute_type=compute_type)
        print("Whisper model loaded.")

    def transcribe(self, audio_file_path):
        """
        指定された音声ファイルを文字起こしします。

        Args:
            audio_file_path (str): 文字起こしする音声ファイルのパス。

        Returns:
            str: 文字起こしされたテキスト全体。
        """
        if not os.path.exists(audio_file_path):
            print(f"Error: Audio file not found at {audio_file_path}")
            return "Error: Audio file not found."
            
        print(f"Transcribing {audio_file_path}...")
        
        # faster-whisperは文字起こし結果をセグメントのイテレータとして返します。
        # beam_size=5は推論の品質を向上させるための一般的な設定です。
        segments, info = self.model.transcribe(audio_file_path, beam_size=5)

        # 検出された言語と予想される文字起こしの長さを表示
        print(f"Detected language '{info.language}' with probability {info.language_probability:.2f}")
        print(f"Transcription duration: {info.duration:.2f} seconds")

        # 全てのセグメントを結合して一つのテキストにする
        transcribed_text = "".join(segment.text for segment in segments)
        
        print("Transcription finished.")
        # 余分なスペースを削除して返す
        return transcribed_text.strip()

# テスト用
if __name__ == '__main__':
    # M1/M2/M3 Macをお使いの場合、`compute_type`に`int8`を指定すると高速です。
    # `device="mps"`も試す価値がありますが、CPUの方が速い場合もあります。
    service = TranscriptionService(model_size="base.en", device="cpu", compute_type="int8")
    
    # ここにテストしたい音声ファイルのパスを記述してください。
    # 例: text = service.transcribe("path/to/your/audio.wav")
    # print("\n--- Transcription Result ---")
    # print(text)