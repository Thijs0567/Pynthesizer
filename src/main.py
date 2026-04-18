"""
Main entry point for the polyphonic MIDI sine wave synthesizer.
"""
import sys
import time
from src.synthesizer import Synthesizer
from src.audio_engine import AudioEngine


def main():
    """Main synthesizer application."""
    
    print("Python Polyphonic MIDI Sine Wave Synthesizer")
    print("=" * 50)
    
    # Configuration
    SAMPLE_RATE = 44100
    BLOCKSIZE = 2048
    MAX_VOICES = 16
    
    # Create synthesizer
    synth = Synthesizer(sample_rate=SAMPLE_RATE, max_voices=MAX_VOICES)
    
    # Create audio engine
    audio_engine = AudioEngine(sample_rate=SAMPLE_RATE, blocksize=BLOCKSIZE)
    audio_engine.set_audio_callback(lambda frames: synth.generate_audio(frames))
    
    try:
        # List MIDI ports
        print("\nAvailable MIDI input ports:")
        ports = synth.list_midi_ports()
        for i, port in enumerate(ports):
            print(f"  {i}: {port}")
        
        # Open default MIDI port
        print("\nOpening MIDI port 0...")
        if not synth.open_midi_port(0):
            print("Warning: Could not open MIDI port. Continuing with virtual port...")
        
        # Start MIDI input
        print("Starting MIDI input...")
        synth.start_midi()
        
        # List audio devices
        print("\n")
        AudioEngine.list_devices()
        
        # Start audio engine
        print("\nStarting audio engine...")
        if not audio_engine.start():
            print("Error: Could not start audio engine")
            return 1
        
        print("\n" + "=" * 50)
        print("Synthesizer running. Play MIDI notes to hear sine waves.")
        print("Press Ctrl+C to exit.")
        print("=" * 50 + "\n")
        
        # Main loop
        try:
            while True:
                active_voices = len(synth.active_voices)
                print(f"\rActive voices: {active_voices}/{MAX_VOICES}", end="", flush=True)
                time.sleep(0.1)
        
        except KeyboardInterrupt:
            print("\n\nShutting down...")
    
    finally:
        # Cleanup
        audio_engine.stop()
        synth.stop()
        print("Synthesizer stopped.")


if __name__ == "__main__":
    sys.exit(main())
