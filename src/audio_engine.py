"""
Audio output engine.
Handles audio streaming to speakers.
"""
import sounddevice as sd
import numpy as np
from typing import Callable


class AudioEngine:
    """Manages audio output via sounddevice."""
    
    def __init__(self, sample_rate: int = 44100, channels: int = 1, 
                 blocksize: int = 2048, device: int = None):
        """
        Initialize the audio engine.
        
        Args:
            sample_rate: Sample rate in Hz
            channels: Number of audio channels (1 for mono, 2 for stereo)
            blocksize: Size of audio blocks to process
            device: Audio device index (None for default)
        """
        self.sample_rate = sample_rate
        self.channels = channels
        self.blocksize = blocksize
        self.device = device
        self.stream = None
        self.audio_callback: Callable[[int], np.ndarray] = None
        
    def set_audio_callback(self, callback: Callable[[int], np.ndarray]):
        """
        Set the callback function that generates audio.
        
        Args:
            callback: Function that takes num_samples and returns np.ndarray
        """
        self.audio_callback = callback
    
    def start(self) -> bool:
        """
        Start audio streaming.
        
        Returns:
            True if successful
        """
        try:
            self.stream = sd.OutputStream(
                channels=self.channels,
                samplerate=self.sample_rate,
                blocksize=self.blocksize,
                device=self.device,
                callback=self._stream_callback,
                latency='low'
            )
            self.stream.start()
            print(f"Audio stream started: {self.sample_rate}Hz, {self.channels} channels, blocksize {self.blocksize}")
            return True
        except Exception as e:
            print(f"Error starting audio stream: {e}")
            return False
    
    def stop(self):
        """Stop audio streaming."""
        if self.stream:
            self.stream.stop()
            self.stream.close()
            self.stream = None
            print("Audio stream stopped")
    
    def _stream_callback(self, outdata, frames, time, status):
        """Internal callback for the audio stream."""
        if status:
            print(f"Audio stream status: {status}")
        
        if self.audio_callback:
            try:
                audio_data = self.audio_callback(frames)

                if audio_data.ndim == 2 and audio_data.shape[1] == self.channels:
                    outdata[:] = audio_data
                elif self.channels == 1:
                    outdata[:, 0] = audio_data
                else:
                    for ch in range(self.channels):
                        outdata[:, ch] = audio_data
                        
            except Exception as e:
                print(f"Error in audio callback: {type(e).__name__}: {e}")
                import traceback
                traceback.print_exc()
                outdata.fill(0)
        else:
            outdata.fill(0)
    
    @staticmethod
    def list_devices():
        """List available audio output devices."""
        print("\nAvailable audio devices:")
        devices = sd.query_devices()
        for i, device in enumerate(devices):
            print(f"  {i}: {device['name']} ({device['max_output_channels']} out)")
