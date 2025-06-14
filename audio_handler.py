# audio_handler.py

import sounddevice as sd
import numpy as np
import queue

class AudioRecorder:
    def __init__(self, sample_rate=16000, channels=1, ui_queue=None, transcription_queue=None):
        self.sample_rate = sample_rate
        self.channels = channels
        self.is_recording = False
        
        self.ui_queue = ui_queue
        self.transcription_queue = transcription_queue
        
        # チャンク間隔を短くし、よりスムーズにデータを送る
        self.chunk_duration_seconds = 1  # 1秒ごとにチャンクを生成
        self.chunk_frames = int(self.sample_rate * self.chunk_duration_seconds)
        self.transcription_buffer = []

    def start_recording(self):
        self.transcription_buffer = []
        self.is_recording = True
        print("Streaming recording started...")
        self.stream = sd.InputStream(samplerate=self.sample_rate, channels=self.channels, callback=self._callback)
        self.stream.start()

    def stop_recording(self):
        if not self.is_recording:
            return
            
        self.stream.stop()
        self.stream.close()
        self.is_recording = False
        print("Streaming recording stopped.")

        if self.transcription_buffer:
            final_chunk = np.concatenate(self.transcription_buffer)
            if self.transcription_queue:
                self.transcription_queue.put(final_chunk.flatten())
            self.transcription_buffer = []

    def _callback(self, indata, frames, time, status):
        if status:
            print(status)
        
        if self.ui_queue:
            self.ui_queue.put(indata.copy().flatten())
            
        self.transcription_buffer.append(indata.copy())
        
        buffered_frames = sum(len(chunk) for chunk in self.transcription_buffer)

        if buffered_frames >= self.chunk_frames:
            chunk_to_process = np.concatenate(self.transcription_buffer)
            self.transcription_buffer = []
            
            if self.transcription_queue:
                self.transcription_queue.put(chunk_to_process.flatten())