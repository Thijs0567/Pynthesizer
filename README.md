# PythonSynth - Polyphonic MIDI Synthesizer

A simple polyphonic sine wave synthesizer with a clickable GUI piano interface.

## Quick Start

```bash
pip install -r requirements.txt
python -m src.gui_main
```

Click keys to play. That's it.

## GUI Features

- **Clickable Piano**: Click any key to play notes (3 octaves: C4–C7)
- **Polyphony**: Play up to 16 simultaneous notes
- **Drag to Play**: Click and drag across keys for runs and chords
- **Visual Feedback**: Keys highlight when pressed
- **Voice Counter**: Real-time display of active voices

## Alternative Modes

| Mode | Command |
|------|---------|
| **GUI Piano** | `python -m src.gui_main` |
| **MIDI Controller** | `python -m src.main` |
| **Test Synthesis** | `python test_synthesis.py` |
| **GUI Demo** (no audio) | `python demo_gui.py` |

## What It Does

Each note plays as a pure sine wave with:
- Velocity-based volume (from MIDI/click)
- 10ms attack, 50ms release envelope
- Pitch bend support (±2 semitones)
- Voice stealing when exceeding 16 simultaneous notes

## Architecture

```
MIDI/GUI Input → Synthesizer (voice management) 
    → Voice (sine generation + envelope) 
    → Mixing → Audio Engine → Speakers
```

**Key Design**: Audio synthesis runs in real-time callback. MIDI polling runs in separate thread to prevent glitches.

## Modules

- `gui_main.py` - GUI entry point
- `piano_gui.py` - Tkinter piano interface
- `synthesizer.py` - Core synthesis engine
- `voice.py` - Individual sine wave oscillator
- `midi_handler.py` - MIDI input handling
- `audio_engine.py` - Real-time audio output

## Configuration

Edit `src/main.py`:
- `SAMPLE_RATE` - Default: 44100 Hz
- `BLOCKSIZE` - Default: 2048 samples
- `MAX_VOICES` - Default: 16

Edit `src/voice.py`:
- `ATTACK_TIME` - Default: 10ms
- `RELEASE_TIME` - Default: 50ms

## Requirements

- Python 3.7+
- Audio output device
- Dependencies: `numpy`, `sounddevice`, `mido`, `tkinter` (included with Python)

## Known Limitations

- Sine waves only
- No ADSR customization
- No filtering or effects

## License

MIT