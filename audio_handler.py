# audio_handler.py

import sounddevice as sd
import numpy as np

class AudioRecorder:
    def __init__(self, sample_rate=16000, channels=1, ui_queue=None, transcription_service=None):
        self.sample_rate = sample_rate
        self.channels = channels
        self.is_recording = False
        self.recording_data = []
        self.ui_queue = ui_queue
        # ▼▼▼ 変更点 1: TranscriptionServiceのインスタンスを受け取る ▼▼▼
        self.transcription_service = transcription_service

    def start_recording(self):
        self.recording_data = []
        self.is_recording = True
        print("Recording started...")
        self.stream = sd.InputStream(samplerate=self.sample_rate, channels=self.channels, callback=self._callback)
        self.stream.start()

    def stop_recording(self):
        """
        録音を停止し、結合された音声データをNumPy配列として返す。
        ストリーミングモードでは、主にストリームの停止に使われる。
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
        
        recording_np = np.concatenate(self.recording_data, axis=0)
        return recording_np.flatten()

    def _callback(self, indata, frames, time, status):
        """InputStreamから呼ばれるコールバック関数"""
        if status:
            print(status)
        
        audio_chunk = indata.copy()
        self.recording_data.append(audio_chunk)
        
        # UIキューには波形用のデータを送ります
        if self.ui_queue:
            self.ui_queue.put(audio_chunk.flatten())
            
        # ▼▼▼ 変更点 2: TranscriptionServiceに音声チャンクを送る ▼▼▼
        if self.transcription_service:
            self.transcription_service.add_audio_chunk(audio_chunk.flatten())