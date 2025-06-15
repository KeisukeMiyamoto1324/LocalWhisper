# audio_handler.py

import sounddevice as sd
import numpy as np
import threading
import time
import queue

class AudioRecorder:
    def __init__(self, sample_rate=16000, channels=1, ui_queue=None, realtime_callback=None):
        self.sample_rate = sample_rate
        self.channels = channels
        self.is_recording = False
        self.recording_data = []
        self.ui_queue = ui_queue

        # リアルタイム文字起こし用の設定
        self.realtime_callback = realtime_callback
        self.realtime_buffer = []
        self.buffer_duration = 3.0  # 3秒分のバッファ
        self.buffer_size = int(self.buffer_duration * self.sample_rate)
        self.last_transcription_time = 0
        self.transcription_interval = 2.0  # 2秒間隔に変更（負荷軽減）

        # スレッドセーフティのためのロック
        self.buffer_lock = threading.Lock()

    def start_recording(self):
        self.recording_data = []
        with self.buffer_lock:
            self.realtime_buffer = []
        self.is_recording = True
        self.last_transcription_time = time.time()
        print("Recording started...")

        self.stream = sd.InputStream(
            samplerate=self.sample_rate, 
            channels=self.channels, 
            callback=self._callback
        )
        self.stream.start()

    def stop_recording(self):
        """
        録音を停止し、結合された音声データをNumPy配列として返す。
        """
        if not self.is_recording:
            return None

        self.is_recording = False
        self.stream.stop()
        self.stream.close()
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

        if not self.is_recording:
            return

        # 録音データに追加
        self.recording_data.append(indata.copy())

        # UIキューに音声データを送信
        if self.ui_queue:
            try:
                self.ui_queue.put_nowait(indata.copy().flatten())
            except queue.Full:
                pass  # キューが満杯の場合は無視

        # リアルタイム文字起こし用のバッファ管理
        if self.realtime_callback:
            self._handle_realtime_buffer(indata.copy().flatten())

    def _handle_realtime_buffer(self, audio_chunk):
        """リアルタイム文字起こし用のバッファ管理"""
        current_time = time.time()

        with self.buffer_lock:
            # バッファに新しいデータを追加
            self.realtime_buffer.extend(audio_chunk)

            # バッファサイズを制限（古いデータを削除）
            if len(self.realtime_buffer) > self.buffer_size:
                self.realtime_buffer = self.realtime_buffer[-self.buffer_size:]

            # 定期的に文字起こしを実行（条件チェック）
            if (current_time - self.last_transcription_time >= self.transcription_interval and 
                len(self.realtime_buffer) >= self.sample_rate * 1.5):  # 最低1.5秒分のデータが必要

                self.last_transcription_time = current_time

                # バッファのコピーを作成
                buffer_copy = np.array(self.realtime_buffer[-int(self.sample_rate * 2):], dtype=np.float32)  # 最新2秒分のみ

                # 非同期で文字起こしを実行
                self.realtime_callback(buffer_copy)