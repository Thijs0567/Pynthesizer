#!/usr/bin/env python3
"""
Test script for the polyphonic synthesizer.
Demonstrates note playback and basic functionality.
"""
import sys
import time
sys.path.insert(0, '.')

from src.synthesizer import Synthesizer
from src.audio_engine import AudioEngine


def test_synthesizer():
    """Test the synthesizer without MIDI."""
    
    print("Testing PythonSynth - Polyphonic Sine Wave Synthesizer")
    print("=" * 60)
    
    # Create synthesizer
    print("\n1. Creating synthesizer...")
    synth = Synthesizer(sample_rate=44100, max_voices=16)
    print("   ✓ Synthesizer created")
    
    # Create audio engine
    print("\n2. Creating audio engine...")
    audio_engine = AudioEngine(sample_rate=44100, blocksize=2048)
    audio_engine.set_audio_callback(lambda frames: synth.generate_audio(frames))
    print("   ✓ Audio engine created")
    
    # Test note synthesis
    print("\n3. Testing note synthesis (no audio output)...")
    print("   Playing a C major chord (C4, E4, G4)")
    
    # Simulate MIDI note on events
    synth._on_note_on(60, 100)  # C4
    time.sleep(0.1)
    synth._on_note_on(64, 100)  # E4
    time.sleep(0.1)
    synth._on_note_on(67, 100)  # G4
    time.sleep(0.1)
    
    print(f"   Active voices: {len(synth.active_voices)}")
    
    # Generate some audio samples to verify synthesis
    print("\n4. Generating test audio samples...")
    samples = synth.generate_audio(44100)  # 1 second of audio
    print(f"   Generated {len(samples)} samples")
    print(f"   Min: {samples.min():.4f}, Max: {samples.max():.4f}")
    print(f"   Mean: {samples.mean():.4f}")
    
    # Test note off
    print("\n5. Testing note release...")
    synth._on_note_off(60)  # C4 off
    synth._on_note_off(64)  # E4 off
    synth._on_note_off(67)  # G4 off
    print(f"   Active voices: {len(synth.active_voices)}")
    
    # Generate more samples to let voices decay
    samples = synth.generate_audio(44100 * 2)  # 2 seconds for release
    print(f"   Generated {len(samples)} samples during release")
    print(f"   Active voices after release: {len(synth.active_voices)}")
    
    # Test frequency conversion
    print("\n6. Testing MIDI to frequency conversion...")
    for note_num in [60, 64, 67]:
        freq = Synthesizer.note_to_frequency(note_num)
        print(f"   MIDI Note {note_num}: {freq:.2f} Hz")
    
    # Cleanup
    synth.stop()
    
    print("\n" + "=" * 60)
    print("✓ All tests passed!")
    print("\nTo use with MIDI and hear audio output:")
    print("  python src/main.py")
    print("=" * 60)


if __name__ == "__main__":
    try:
        test_synthesizer()
    except Exception as e:
        print(f"\n✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
