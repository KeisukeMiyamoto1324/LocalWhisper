import sounddevice as sd
import soundfile as sf
import numpy as np

class AudioRecorder:
    def __init__(self, sample_rate=16000, channels=1):
        self.sample_rate = sample_rate
        self.channels = channels
        self.is_recording = False
        self.recording_data = []

    def start_recording(self):
        self.recording_data = []
        self.is_recording = True
        print("Recording started...")
        with sd.InputStream(samplerate=self.sample_rate, channels=self.channels, callback=self._callback):
            while self.is_recording:
                sd.sleep(100)

    def stop_recording(self, output_filename="temp_recording.wav"):
        self.is_recording = False
        print("Recording stopped.")
        if not self.recording_data:
            print("No audio recorded.")
            return None
        
        # NumPy配列に変換
        recording_np = np.concatenate(self.recording_data, axis=0)
        
        # .wavファイルとして保存
        sf.write(output_filename, recording_np, self.sample_rate)
        print(f"Recording saved to {output_filename}")
        return output_filename

    def _callback(self, indata, frames, time, status):
        """InputStreamから呼ばれるコールバック関数"""
        if status:
            print(status)
        self.recording_data.append(indata.copy())

# このファイルは直接実行せず、他のファイルから呼び出して使います。