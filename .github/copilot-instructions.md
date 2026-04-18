<!-- Use this file to provide workspace-specific custom instructions to Copilot. For more details, visit https://code.visualstudio.com/docs/copilot/copilot-customization#_use-a-githubcopilotinstructionsmd-file -->

# PythonSynth - Python Polyphonic MIDI Sine Wave Synthesizer

This workspace contains a standalone polyphonic synthesizer that takes MIDI input and outputs pure sine waves.

## Project Structure

```
PythonSynth/
├── src/
│   ├── __init__.py          # Package initialization
│   ├── gui_main.py          # GUI piano entry point
│   ├── main.py              # MIDI input entry point
│   ├── piano_gui.py         # Clickable piano GUI
│   ├── synthesizer.py       # Core synthesis engine
│   ├── voice.py             # Individual voice/oscillator
│   ├── midi_handler.py      # MIDI input handling
│   └── audio_engine.py      # Real-time audio output
├── demo_gui.py             # GUI demo without audio
├── test_synthesis.py       # Synthesis test script
├── requirements.txt        # Python dependencies
├── README.md              # User documentation
└── .github/
    └── copilot-instructions.md  # This file
```

## Quick Start Options

1. **GUI Piano** (Easiest): `python -m src.gui_main` - Click keys to play
2. **MIDI Mode**: `python -m src.main` - Connect MIDI controller
3. **Test Mode**: `python test_synthesis.py` - Verify synthesis works
4. **GUI Demo**: `python demo_gui.py` - Demo without audio

## Key Technologies

- **numpy**: Numerical computing for audio synthesis
- **sounddevice**: Real-time audio output
- **mido**: Pure Python MIDI input handling (no compilation needed)
- **threading**: Non-blocking MIDI polling

## Synthesis Details

- Pure sine wave oscillators
- Up to 16 polyphonic voices
- 10ms attack, 50ms release envelope
- Velocity-based amplitude control (0-127)
- Full MIDI pitch bend support (±2 semitones by default)
- Voice stealing when max voices exceeded

## Development Notes

- All audio processing runs in real-time callback
- MIDI polling runs in separate thread to prevent audio glitches
- Normalization prevents clipping with multiple voices
- Inactive voices are cleaned up immediately
