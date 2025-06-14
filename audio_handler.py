# audio_handler.py

import sounddevice as sd
import numpy as np
# soundfileは不要になったため削除しました
# import soundfile as sf 

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
        # InputStreamはスレッドで動作させるため、ここではループさせません
        self.stream = sd.InputStream(samplerate=self.sample_rate, channels=self.channels, callback=self._callback)
        self.stream.start()

    def stop_recording(self):
        """
        録音を停止し、結合された音声データをNumPy配列として返す。
        ファイルへの書き込みは行わない。
        """
        if not self.is_recording:
            return None
            
        self.stream.stop()
        self.stream.close()
        self.is_recording = False
        print("Recording stopped.")

        if not self.recording_data:
            print("No audio recorded.")
            return None
        
        # NumPy配列に変換
        recording_np = np.concatenate(self.recording_data, axis=0)
        
        # Whisperが期待する1次元配列に変換して返す
        return recording_np.flatten()

    def _callback(self, indata, frames, time, status):
        """InputStreamから呼ばれるコールバック関数"""
        if status:
            print(status)
        self.recording_data.append(indata.copy())

# このファイルは直接実行せず、他のファイルから呼び出して使います。