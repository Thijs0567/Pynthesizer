# Python Polyphonic MIDI Sine Wave Synthesizer

A standalone polyphonic synthesizer written in Python that takes MIDI input and outputs pure sine waves. Perfect for learning about digital audio synthesis and MIDI programming.

## Features

- **Polyphonic synthesis**: Play up to 16 simultaneous sine wave notes
- **MIDI input**: Connect any MIDI controller or sequencer
- **Real-time audio output**: Low-latency audio streaming
- **Pitch bend support**: Full MIDI pitch bend implementation
- **Control Change support**: Extensible control handling
- **Simple envelope**: Attack and release phases for each note
- **Pure Python**: No C++ compilation needed (uses pre-built wheels)

## Requirements

- Python 3.7+
- Audio device with output capability
- MIDI input device (optional - can test without MIDI)

## Installation

### 1. Clone or download the repository

```bash
cd PythonSynth
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

Or manually:
```bash
pip install numpy sounddevice mido
```

## GUI Piano Interface

The easiest way to play the synthesizer is with the clickable piano GUI:

```bash
python -m src.gui_main
```

### Features

- **Clickable Keys**: Click on white or black keys to play notes
- **Drag to Play**: Click and drag across keys to play multiple notes
- **Visual Feedback**: Keys highlight when pressed
- **Voice Counter**: Shows active voices in real-time
- **3 Octaves**: C4 to C7 (middle C to high C)

### How to Use

1. Run the GUI: `python -m src.gui_main`
2. Click any key to play a note
3. Click and hold multiple keys for polyphonic chords
4. Click and drag across keys for scales and runs
5. Watch the active voice counter
6. Close the window to exit

### Option 1: GUI Piano (Easiest)

Click to play on a virtual piano keyboard:

```bash
python -m src.gui_main
```

Then simply click on the piano keys to play notes. The active voice count is displayed at the top.

### Option 2: Test the Synthesizer (No MIDI/Audio Required)

Run the test script to verify the synthesizer works:
```bash
python test_synthesis.py
```

This will test note synthesis and display audio statistics without requiring a MIDI device or audio output.

### Option 3: MIDI Controller

Connect a MIDI device and run:

```bash
python -m src.main
```

## Troubleshooting

### GUI Piano Issues

**"Tkinter not found" error**
- Tkinter comes with Python but may not be installed on Linux
- Linux: `sudo apt install python3-tk`
- Should work out-of-the-box on Windows and macOS

**"No audio output" / "Can't find audio device"**
- Check that your speakers/headphones are properly connected
- Run `python -c "import sounddevice; sounddevice.query_devices()"` to see available devices

### MIDI Device Issues

**"No MIDI device found"**
- Run `python -c "import mido; print(mido.get_input_names())"` to see available MIDI ports
- Connect your MIDI controller and try again
- You can use virtual MIDI ports like loopMIDI on Windows

### Import errors
- Ensure dependencies are installed: `pip install -r requirements.txt`
- Check Python version: `python --version` (3.7+ required)

## Architecture

### Modules

- **`gui_main.py`**: Entry point for GUI piano mode
- **`main.py`**: Entry point for MIDI mode
- **`piano_gui.py`**: Clickable piano GUI interface
- **`synthesizer.py`**: Core synthesis engine managing voices and MIDI
- **`voice.py`**: Individual oscillator voice with sine wave generation and envelope
- **`midi_handler.py`**: MIDI input handling with threaded polling
- **`audio_engine.py`**: Real-time audio output via sounddevice

### Voice Management

Each MIDI note creates a voice that:
- Generates a pure sine wave at the note's frequency
- Applies velocity-based amplitude (0-127 from MIDI)
- Has a 10ms attack phase and 50ms release phase
- Supports pitch bend modulation

### Audio Processing Pipeline

```
MIDI Input → Synthesizer (voice management) → Voice (sine generation) 
   → Mixing → Normalization → Audio Engine → Speakers
```

### Real-Time Design

- **Audio callback**: Synthesis runs in real-time audio stream callback
- **MIDI polling**: MIDI runs in separate background thread to prevent audio glitches
- **Thread-safe**: Voice management uses dict lookups (thread-safe in Python)
- **Normalization**: Multi-voice output normalized to prevent clipping

## Configuration

Edit `src/main.py` to adjust:
- `SAMPLE_RATE`: Audio sample rate (default: 44100 Hz)
- `BLOCKSIZE`: Audio block size (default: 2048 samples)
- `MAX_VOICES`: Maximum simultaneous voices (default: 16)

Edit `src/voice.py` to customize:
- Attack time (default: 10ms)
- Release time (default: 50ms)

## Supported MIDI Events

- **Note On / Note Off**: Play and stop notes
- **Velocity**: Control amplitude (0-127)
- **Pitch Bend**: Pitch modulation (±2 semitones)
- **Control Change**: Ready for ADSR, filter cutoff, etc.

## Performance

- Minimal CPU usage for basic sine wave synthesis
- Designed for real-time low-latency operation
- Tested with up to 16 simultaneous voices
- Voice stealing implemented (oldest note removed when exceeding max voices)

## Examples

### Playing a C Major Scale

```python
from src.synthesizer import Synthesizer
from src.audio_engine import AudioEngine
import time

synth = Synthesizer()
audio_engine = AudioEngine()
audio_engine.set_audio_callback(lambda frames: synth.generate_audio(frames))
audio_engine.start()

# C major scale (C4 to C5)
notes = [60, 62, 64, 65, 67, 69, 71, 72]

for note in notes:
    synth._on_note_on(note, 100)
    time.sleep(0.5)
    synth._on_note_off(note)
    time.sleep(0.5)

audio_engine.stop()
```

## Known Limitations

- Mono sine waves only
- No ADSR customization via CC
- No waveform selection
- No filtering
- Limited effects

## Future Enhancements

- ADSR envelope control via MIDI CC
- Waveform selection (square, sawtooth, triangle, etc.)
- Low-pass filter
- Effects (reverb, delay, chorus, etc.)
- Preset management
- GUI interface
- Stereo output
- Oscillator detuning
- LFO modulation

## Development

To contribute:
1. Test changes with `python test_synthesis.py`
2. Verify MIDI with `python -m src.main`
3. Check code follows the existing style

## License

MIT
