<!-- Use this file to provide workspace-specific custom instructions to Copilot. For more details, visit https://code.visualstudio.com/docs/copilot/copilot-customization#_use-a-githubcopilotinstructionsmd-file -->

# PythonSynth - Python Polyphonic Synthesizer

This workspace contains a standalone polyphonic synthesizer with a GUI piano, wavetable oscillator, ADSR, effects, MIDI input, and QWERTY keyboard playability.

## Project Structure

```
PythonSynth/
├── src/
│   ├── __init__.py          # Package initialization
│   ├── main.py              # Entry point: GUI piano + optional MIDI input
│   ├── piano_gui.py         # Clickable piano GUI with all controls
│   ├── synthesizer.py       # Core synthesis engine & dynamics processor
│   ├── voice.py             # Individual voice/oscillator + ADSR
│   ├── midi_handler.py      # MIDI input handling
│   ├── audio_engine.py      # Real-time audio output
│   ├── effects.py           # Effect chain (LPF, Reverb, Delay)
│   └── widgets/
│       ├── __init__.py      # Knob widget
│       └── harmonic_slider.py  # Per-harmonic amplitude slider
├── test_synthesis.py       # Synthesis test script
├── requirements.txt        # Python dependencies
├── README.md               # User documentation
└── .github/
    └── copilot-instructions.md  # This file
```

## Quick Start

```
python -m src.main
```

MIDI input is detected and opened automatically if a port is available. The GUI launches regardless.

## Key Technologies

- **numpy**: Audio synthesis and wavetable generation
- **sounddevice**: Real-time audio output
- **mido**: Pure Python MIDI input handling
- **tkinter**: GUI (included with Python)
- **threading**: Non-blocking MIDI polling and GUI update loop

## Synthesis Details

- 16-harmonic additive wavetable oscillator (per-harmonic amplitude sliders)
- Waveform presets: sine, saw, square, triangle, semisine
- Up to 16 polyphonic voices with voice stealing
- Full ADSR envelope per voice
- RMS compressor + peak limiter
- Effects chain: Low-Pass Filter → Delay → Reverb
- MIDI pitch bend support (±2 semitones by default)

## GUI Controls

- **Oscillator**: harmonic sliders, live waveform preview, waveform preset buttons
- **ADSR**: Attack, Decay, Sustain, Release knobs with envelope graph
- **Filter**: Cutoff and Resonance knobs
- **Effects**: Reverb (Room, Damp, Wet) and Delay (Time, Feedback, Wet)
- **Master**: Volume knob and vertical level meter
- **Transpose**: Vertical slider (±24 semitones)
- **QWERTY keyboard**: A–L = white keys, W E T Y U O = black keys; Z/X shift octave

## Development Notes

- Audio callback is allocation-free and runs on the sounddevice thread
- MIDI polling runs in a separate thread to prevent audio glitches
- GUI update loop runs in a daemon thread, polling at 20 Hz
- Keep audio-thread code deterministic; avoid Python object churn per sample
