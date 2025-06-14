# audio_handler.py

import sounddevice as sd
import numpy as np
import queue # Import the queue module
import sys

class AudioRecorder:
    def __init__(self, sample_rate=16000, channels=1):
        self.sample_rate = sample_rate
        self.channels = channels
        self.is_recording = False
        self.recording_data = []
        self.waveform_queue = None # Add a placeholder for the queue

    def start_recording(self, waveform_queue: queue.Queue = None):
        """
        Starts recording and optionally sends audio chunks to a queue for live visualization.
        """
        self.recording_data = []
        self.is_recording = True
        self.waveform_queue = waveform_queue # Store the queue
        print("Recording started...")
        self.stream = sd.InputStream(samplerate=self.sample_rate, channels=self.channels, callback=self._callback)
        self.stream.start()

    def stop_recording(self):
        """
        Stops recording and returns the combined audio data as a NumPy array.
        """
        if not self.is_recording:
            return None
            
        self.stream.stop()
        self.stream.close()
        self.is_recording = False
        self.waveform_queue = None # Clear the queue reference
        print("Recording stopped.")

        if not self.recording_data:
            print("No audio recorded.")
            return None
        
        recording_np = np.concatenate(self.recording_data, axis=0)
        
        return recording_np.flatten()

    def _callback(self, indata, frames, time, status):
        """InputStream callback. Appends data for storage and pushes to the waveform queue."""
        if status:
            print(status, file=sys.stderr)
        self.recording_data.append(indata.copy())
        
        # If a queue is provided, put the latest audio chunk into it.
        # Use put_nowait to avoid blocking the audio thread if the queue is full.
        if self.waveform_queue:
            try:
                # We send a flattened copy of the data
                self.waveform_queue.put_nowait(indata.copy().flatten())
            except queue.Full:
                pass # Ignore if the UI can't keep up