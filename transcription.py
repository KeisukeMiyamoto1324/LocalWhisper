# transcription.py

import mlx_whisper
import numpy as np
import queue
import threading
import time

# A special object used as a signal to end the transcription stream gracefully.
_END_STREAM_SIGNAL = object()

class TranscriptionService:
    def __init__(self, model_size="large-v3", ui_queue=None, **kwargs):
        """
        Initializes the streaming transcription service.
        """
        self.model_path = f"mlx-community/whisper-{model_size}"
        self.ui_queue = ui_queue
        
        self.audio_queue = queue.Queue()
        self.transcription_thread = None
        self.is_running = False
        
        self.full_transcription = ""
        self.sample_rate = 16000
        self.transcribe_threshold_sec = 2.0
        self.silence_threshold_sec = 1.0

        print(f"TranscriptionService initialized for streaming with MLX.")
        print(f"Using model: '{self.model_path}'.")

    def _process_loop(self):
        """
        The main loop for transcription, running in a background thread.
        """
        audio_buffer = []
        
        while self.is_running:
            try:
                # Get an item from the queue with a timeout.
                item = self.audio_queue.get(timeout=self.silence_threshold_sec)

                if item is _END_STREAM_SIGNAL:
                    print("  [T-Thread] End signal received. Processing final audio buffer.")
                    # If there's remaining audio, process it one last time.
                    if audio_buffer:
                        self.transcribe_and_update(audio_buffer)
                    break # Exit the loop.
                
                audio_buffer.append(item)
                
                buffer_duration = sum(len(chunk) for chunk in audio_buffer) / self.sample_rate
                if buffer_duration < self.transcribe_threshold_sec:
                    continue

            except queue.Empty:
                if not audio_buffer:
                    continue
                print("  [T-Thread] Silence detected, processing buffered audio.")
            
            # Transcribe the current buffer and then clear it.
            audio_buffer = self.transcribe_and_update(audio_buffer)
        
        print("  [T-Thread] Transcription thread finished.")

    def transcribe_and_update(self, buffer_to_process: list) -> list:
        """
        Helper function to transcribe an audio buffer and update the full transcription.
        Returns an empty list to clear the buffer.
        """
        combined_audio = np.concatenate(buffer_to_process)
        print(f"  [T-Thread] Transcribing {len(combined_audio) / self.sample_rate:.2f}s of audio...")

        try:
            # ▼▼▼ CORE CHANGE ▼▼▼
            # Use the previous full transcription as a prompt for the new one.
            # This helps Whisper maintain context.
            result = mlx_whisper.transcribe(
                audio=combined_audio,
                path_or_hf_repo=self.model_path,
                initial_prompt=self.full_transcription
            )
            
            transcribed_text = result.get("text", "").strip()
            
            # Whisper typically returns the entire text including the prompt's content.
            # We replace our stored text if the new result is different.
            if transcribed_text and transcribed_text != self.full_transcription:
                print(f"  [T-Thread] Transcription UPDATED: '{transcribed_text}'")
                self.full_transcription = transcribed_text # Update the full text
                
                if self.ui_queue:
                    self.ui_queue.put(self.full_transcription)
            else:
                print("  [T-Thread] Transcription UNCHANGED or empty.")

        except Exception as e:
            print(f"\n[ERROR] mlx_whisper.transcribe failed: {e}")
        
        # Return an empty list to clear the buffer after processing.
        return []

    def start_stream(self):
        """Starts the transcription stream and worker thread."""
        if self.is_running:
            return
        print("Starting transcription stream...")
        self.is_running = True
        self.full_transcription = ""
        # Clear any old data from the queue.
        while not self.audio_queue.empty():
            self.audio_queue.get()
        
        self.transcription_thread = threading.Thread(target=self._process_loop)
        self.transcription_thread.daemon = True
        self.transcription_thread.start()

    def stop_stream(self) -> str:
        """Stops the stream, waits for the thread to finish, and returns the final text."""
        if not self.is_running:
            return self.full_transcription
            
        print("Stopping transcription stream...")
        self.is_running = False
        
        # Send the end signal to the queue to notify the thread to exit.
        self.audio_queue.put(_END_STREAM_SIGNAL)
        
        # Wait for the thread to terminate.
        if self.transcription_thread:
            self.transcription_thread.join(timeout=5.0) # Add a timeout for safety.
            if self.transcription_thread.is_alive():
                print("[WARNING] Transcription thread did not terminate gracefully.")

        print(f"Transcription stream stopped. Final text: '{self.full_transcription}'")
        # Return the final, complete transcription.
        return self.full_transcription

    def add_audio_chunk(self, chunk: np.ndarray):
        """Adds an audio chunk from the recorder to the processing queue."""
        if self.is_running:
            self.audio_queue.put(chunk)