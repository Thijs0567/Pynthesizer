"""
GUI-based main entry point for the synthesizer.
Uses a clickable piano interface instead of MIDI.
"""
import sys
import tkinter as tk
from threading import Thread
import time
import numpy as np

from src.synthesizer import Synthesizer
from src.audio_engine import AudioEngine
from src.piano_gui import PianoGUI


def main():
    """Main synthesizer application with GUI piano."""
    
    # Configuration
    SAMPLE_RATE = 44100
    BLOCKSIZE = 2048
    MAX_VOICES = 16
    
    # Create synthesizer
    synth = Synthesizer(sample_rate=SAMPLE_RATE, max_voices=MAX_VOICES)
    
    # Create audio engine
    audio_engine = AudioEngine(sample_rate=SAMPLE_RATE, blocksize=BLOCKSIZE)
    
    # Track levels for gain meter
    level_info = {'current': 0.0, 'peak': 0.0, 'clipping': False}
    
    def audio_callback(frames):
        """Generate audio and track levels."""
        audio = synth.generate_audio(frames)
        
        # Track levels
        current = np.max(np.abs(audio))
        level_info['current'] = current
        level_info['peak'] = max(level_info['peak'], current)
        level_info['clipping'] = current > 0.90  # matches meter's red zone
        
        return audio
    
    audio_engine.set_audio_callback(audio_callback)
    
    try:
        print("PythonSynth - GUI Piano Edition with ADSR")
        print("=" * 50)
        
        # Start audio engine
        print("Starting audio engine...")
        if not audio_engine.start():
            print("Error: Could not start audio engine")
            return 1
        
        # Create Tkinter root
        root = tk.Tk()
        
        # Create piano GUI
        print("Creating piano GUI...")
        piano = PianoGUI(
            root,
            on_note_on=lambda note, vel: synth._on_note_on(note, vel),
            on_note_off=lambda note: synth._on_note_off(note),
            on_adsr_change=lambda a, d, s, r: synth.set_adsr(a, d, s, r),
            on_volume_change=lambda v: synth.set_volume(v),
            on_lpf_change=lambda cutoff, q: synth.set_lpf(cutoff, q),
            on_reverb_change=lambda room, damp, wet: synth.set_reverb(room, damp, wet),
            on_delay_change=lambda ms, fb, wet: synth.set_delay(ms, fb, wet),
            on_wavetable_change=lambda wt: synth.set_wavetable(wt),
        )
        
        # Update voice count and levels in GUI periodically
        def update_gui():
            while root.winfo_exists():
                try:
                    piano.update_voice_count(len(synth.active_voices))
                    piano.update_gain_meter(level_info['current'], level_info['peak'], level_info['clipping'])
                    root.update()
                except:
                    break
                time.sleep(0.05)
        
        # Run GUI update in background thread
        gui_thread = Thread(target=update_gui, daemon=True)
        gui_thread.start()
        
        print("GUI ready. Click piano keys to play!")
        print("Adjust ADSR sliders to shape the sound.")
        print("=" * 50)
        
        # Show window and run
        root.mainloop()
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    finally:
        # Cleanup
        print("\nShutting down...")
        audio_engine.stop()
        synth.stop()
        print("Synthesizer stopped.")


if __name__ == "__main__":
    sys.exit(main())
