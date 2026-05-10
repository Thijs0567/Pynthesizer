"""
Main entry point for the synthesizer — GUI piano with optional MIDI input.
"""
import os
import sys
import tkinter as tk
from threading import Thread
import time
import numpy as np

from src.synthesizer import Synthesizer
from src.audio_engine import AudioEngine
from src.piano_gui import PianoGUI


def main():
    SAMPLE_RATE = 44100
    BLOCKSIZE = 2048
    MAX_VOICES = 16

    asio_device = AudioEngine.find_asio_device()
    if asio_device is not None:
        BLOCKSIZE = 256
        print(f"ASIO device found (index {asio_device}), using blocksize {BLOCKSIZE}")
    else:
        print("No ASIO device found, using default output")

    synth = Synthesizer(sample_rate=SAMPLE_RATE, max_voices=MAX_VOICES)
    audio_engine = AudioEngine(sample_rate=SAMPLE_RATE, blocksize=BLOCKSIZE, channels=2,
                               device=asio_device)

    level_info = {'current': 0.0, 'peak': 0.0, 'clipping': False}

    def audio_callback(frames):
        audio = synth.generate_audio(frames)  # (N, 2) stereo
        current = float(np.max(np.abs(audio)))
        level_info['current'] = current
        level_info['peak'] = max(level_info['peak'], current)
        level_info['clipping'] = current > 0.90
        return audio

    audio_engine.set_audio_callback(audio_callback)

    try:
        print("PythonSynth")
        print("=" * 50)

        # MIDI — optional, non-fatal
        ports = synth.list_midi_ports()
        if ports:
            print(f"MIDI ports found: {ports}")
            if synth.open_midi_port(0):
                synth.start_midi()
                print(f"MIDI input active on: {ports[0]}")
            else:
                print("Warning: could not open MIDI port, continuing without MIDI.")
        else:
            print("No MIDI ports found, continuing without MIDI.")

        print("Starting audio engine...")
        if not audio_engine.start():
            print("Error: Could not start audio engine")
            return 1

        root = tk.Tk()

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
            on_chorus_change=lambda rate, depth, wet: synth.set_chorus(rate, depth, wet),
            on_distortion_change=lambda drive, wet: synth.set_distortion(drive, wet),
            on_bitcrusher_change=lambda bits, ds, wet: synth.set_bitcrusher(bits, ds, wet),
            on_panic=synth.panic,
            lfo_bank=synth.lfo_bank,
        )

        # Wire mono/portamento callbacks
        piano._on_mono_change = synth.set_mono_mode
        piano._on_legato_change = synth.set_portamento

        # Re-wire MIDI callbacks through the GUI so keys highlight on MIDI input
        synth.midi_handler.on_note_on = piano.midi_note_on
        synth.midi_handler.on_note_off = piano.midi_note_off

        def update_gui():
            while root.winfo_exists():
                try:
                    piano.update_voice_count(len(synth.active_voices))
                    piano.update_gain_meter(level_info['current'], level_info['peak'], level_info['clipping'])
                    piano.update_lfo_visuals()
                    root.update()
                except:
                    break
                time.sleep(0.05)

        Thread(target=update_gui, daemon=True).start()

        print("GUI ready. Click or use QWERTY keys to play.")
        print("=" * 50)

        root.mainloop()

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return 1

    finally:
        print("\nShutting down...")
        audio_engine.stop()
        synth.stop()
        print("Synthesizer stopped.")


if __name__ == "__main__":
    sys.exit(main())
