#!/usr/bin/env python3
"""
Demo/test script for the GUI piano without audio output.
Useful for testing the GUI without needing audio devices.
"""
import sys
import tkinter as tk
from src.piano_gui import PianoGUI


def demo_gui():
    """Demo the piano GUI without audio."""
    
    print("PythonSynth - GUI Piano Demo with ADSR")
    print("=" * 50)
    print("This demo shows the piano GUI without audio output.")
    print("Click on keys to see note numbers in the console.")
    print("Adjust ADSR sliders to see the envelope graph update.")
    print("=" * 50 + "\n")
    
    # Map MIDI notes to note names
    note_names = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
    
    def midi_to_note_name(midi_note):
        note_in_octave = midi_note % 12
        octave = midi_note // 12
        return f"{note_names[note_in_octave]}{octave}"
    
    # Track active notes
    active_notes = []
    
    def on_note_on(note, velocity):
        active_notes.append(note)
        note_name = midi_to_note_name(note)
        print(f"Note ON:  {note_name:>3} (MIDI {note:3d})")
    
    def on_note_off(note):
        if note in active_notes:
            active_notes.remove(note)
        note_name = midi_to_note_name(note)
        print(f"Note OFF: {note_name:>3} (MIDI {note:3d})")
    
    def on_adsr_changed(attack, decay, sustain, release):
        print(f"ADSR: A={attack*1000:.0f}ms D={decay*1000:.0f}ms S={sustain*100:.0f}% R={release*1000:.0f}ms")
    
    # Create and run GUI
    root = tk.Tk()
    piano = PianoGUI(root, on_note_on, on_note_off, on_adsr_changed)
    
    print("Piano GUI opened. Click keys to test, adjust sliders.\n")
    
    root.mainloop()


if __name__ == "__main__":
    try:
        demo_gui()
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
