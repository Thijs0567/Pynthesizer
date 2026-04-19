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

Each note plays through a wavetable oscillator with:
- **ADSR Envelope**: Fully customizable Attack, Decay, Sustain, Release times
- **Velocity-based Volume**: Dynamic response from MIDI/click (0–127)
- **Pitch Bend Support**: ±2 semitones (or custom range)
- **Voice Stealing**: Oldest-note priority when exceeding max voices
- **Smooth Retrigger**: No clicks when re-playing the same note
- **Compressor + Limiter**: 
  - RMS compressor with soft knee for e-piano character
  - Peak limiter prevents clipping while preserving dynamics
- **Wavetable Oscillator**: 16-harmonic additive synthesis with individual per-harmonic amplitude sliders and a live waveform preview
  - **Waveform Presets**: One-click buttons for sine, saw, square, triangle, and semisine — each displayed as a visual waveform icon
- **Effects Chain**:
  - **Low Pass Filter**: Variable cutoff and Q (resonance)
  - **Delay**: Configurable time, feedback, and wet/dry mix
  - **Reverb**: Freeverb-based with room size, damping, and wet/dry mix
- **Master Volume**: 0.0–1.0 scaling with no clipping

## Architecture

```
MIDI/GUI Input → Synthesizer (voice management)
    → Voice Pool (sine generation + ADSR envelope per note)
    → Voice Mixer (sum active voices)
    → Compressor (RMS stage + peak limiter)
    → Effects Chain (LPF → Delay → Reverb)
    → Master Volume
    → Audio Engine → Speakers
```

**Real-time Design**: Audio synthesis runs in callback (zero allocations). MIDI polling runs in separate thread to prevent glitches. Dynamics processor uses per-sample limiting (no staircase artifacts) and smooth block-wise gain ramps.

## Modules

- `gui_main.py` - GUI entry point
- `piano_gui.py` - Tkinter piano interface with oscillator, ADSR, filter, and effects controls
- `synthesizer.py` - Core synthesis engine & dynamics processor
- `voice.py` - Individual sine wave oscillator + ADSR
- `effects.py` - Effect chain (Master Volume, Low Pass Filter, Reverb, Delay)
- `midi_handler.py` - MIDI input handling
- `audio_engine.py` - Real-time audio output

## Configuration & API

**Synthesizer Parameters** (after instantiation):

```python
synth = Synthesizer(sample_rate=44100, max_voices=16)

# ADSR Envelope
synth.set_adsr(attack=0.01, decay=0.1, sustain=0.7, release=0.3)

# Effects
synth.set_volume(0.8)                           # 0.0–1.0
synth.set_lpf(cutoff_hz=10000, q=0.707)        # Low Pass Filter
synth.set_reverb(room_size=0.5, damping=0.5, wet=0.3)
synth.set_delay(delay_ms=250, feedback=0.4, wet=0.2)

# MIDI/Control
synth._on_note_on(note=60, velocity=100)
synth._on_note_off(note=60)
synth._on_pitch_bend(value)                     # -8192 to +8191
```

**Compressor Settings** (tweak in `src/synthesizer.py`):
- `_comp_threshold_db` - Compression knee threshold (default: -3 dB)
- `_comp_ratio` - Compression ratio (default: 4:1)
- `_comp_knee_db` - Knee width (default: 6 dB)
- `_lim_threshold` - Peak limiter ceiling (default: 0.90)

## Requirements

- Python 3.7+
- Audio output device
- Dependencies: `numpy`, `sounddevice`, `mido`, `tkinter` (included with Python)

## Known Limitations

- **Mono output** — no stereo, surround, or spatial effects
- **Fixed tuning** — A4 = 440 Hz (no alternate tuning systems)

## License

MIT