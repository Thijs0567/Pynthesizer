# PythonSynth - Polyphonic Synthesizer

A polyphonic wavetable synthesizer with a clickable GUI piano, QWERTY keyboard playability, ADSR, effects, and optional MIDI input.

## Quick Start

```bash
pip install -r requirements.txt
python -m src.main
```

MIDI input is opened automatically if a device is connected. The GUI always launches.

## GUI Features

- **Clickable Piano**: 3 octaves + 1 key (C4–C7), click or drag to play
- **QWERTY Keyboard**: Play notes from your computer keyboard
- **Polyphony**: Up to 16 simultaneous voices
- **Visual Feedback**: Keys highlight when pressed (mouse, keyboard, and MIDI); panic button clears all highlights
- **Voice Counter**: Real-time display of active voices
- **Level Meter**: Logarithmic dB scale (-60 dB to 0 dB), reads post-compressor
- **Transpose Slider**: ±24 semitones

## QWERTY Keyboard Layout

| Row | Keys | Notes |
|-----|------|-------|
| White keys | `A S D F G H J K L` | C D E F G A B C D |
| Black keys | `W E - T Y U - O` | C# D# — F# G# A# — C# |
| Octave down | `Z` | Shift hotkeys one octave down |
| Octave up | `X` | Shift hotkeys one octave up |

- Default position: C5 (centered on the displayed range)
- **Octave + Transpose chaining**: when `Z`/`X` hits the display limit, it automatically transposes by ±12 semitones (up to the ±24 transpose limit), allowing play across a wide range with visual feedback

## Oscillator

- **16-harmonic additive wavetable** with individual amplitude sliders and a live waveform preview
- **Waveform presets** — click a button to load a classic shape:
  - Sine, Saw, Square, Triangle, Semisine
  - Each button shows the actual waveform shape as its icon

## What It Does

Each note plays through the wavetable oscillator with:
- **ADSR Envelope**: Fully customizable Attack, Decay, Sustain, Release
- **Velocity-based Volume**: Dynamic response from MIDI/click (0–127)
- **Pitch Bend Support**: ±2 semitones (or custom range)
- **Voice Stealing**: Oldest-note priority when exceeding max voices
- **Smooth Retrigger**: No clicks when re-playing the same note
- **Polyphony Gain Scaling**: Output is normalised by √(sum of active envelope amplitudes), keeping perceived loudness constant whether 1 or 16 voices are playing. The scaling is smoothed (50 ms) so voices fading through release cause no pumping or level jumps.
- **Compressor + Limiter**:
  - RMS compressor with soft knee
  - Peak limiter prevents clipping while preserving dynamics
- **Effects Chain**:
  - **Low-Pass Filter**: Variable cutoff and Q (resonance)
  - **Delay**: Configurable time, feedback, and wet/dry mix
  - **Reverb**: Freeverb-based with room size, damping, and wet/dry mix
- **Master Volume**: knob range mapped to 0–43% linear; defaults to 70% knob (0.3 linear) for comfortable headroom

## Architecture

```
MIDI / GUI click / QWERTY keyboard
    → Synthesizer (voice management)
    → Voice Pool (wavetable oscillator + ADSR per note)
    → Voice Mixer (sum active voices)
    → Compressor (RMS stage + peak limiter)
    → Effects Chain (LPF → Delay → Reverb)
    → Master Volume
    → Audio Engine → Speakers
```

**Real-time Design**: Audio synthesis runs in callback (zero allocations). MIDI polling runs in a separate thread. GUI updates at 20 Hz in a daemon thread.

## Modules

- `main.py` - Entry point: GUI piano with optional MIDI input
- `piano_gui.py` - Tkinter piano interface with all controls
- `synthesizer.py` - Core synthesis engine & dynamics processor
- `voice.py` - Individual wavetable oscillator + ADSR
- `effects.py` - Effect chain (LPF, Reverb, Delay)
- `midi_handler.py` - MIDI input handling
- `audio_engine.py` - Real-time audio output
- `widgets/` - Knob and HarmonicSlider custom widgets

## Configuration & API

```python
synth = Synthesizer(sample_rate=44100, max_voices=16)

synth.set_adsr(attack=0.01, decay=0.1, sustain=0.7, release=0.3)
synth.set_volume(0.8)
synth.set_lpf(cutoff_hz=10000, q=0.707)
synth.set_reverb(room_size=0.5, damping=0.5, wet=0.3)
synth.set_delay(delay_ms=250, feedback=0.4, wet=0.2)
synth.set_wavetable(np.array([1.0, 0.5, 0.0, ...], dtype=np.float32))  # 16 harmonics
```

**Compressor Settings** (tweak in `src/synthesizer.py`):
- `_comp_threshold_db` — default: -3 dB
- `_comp_ratio` — default: 4:1
- `_comp_knee_db` — default: 6 dB
- `_lim_threshold` — default: 0.90

## Requirements

- Python 3.7+
- Audio output device
- Dependencies: `numpy`, `sounddevice`, `mido`, `tkinter` (included with Python)
- MIDI device: optional

## Known Limitations

- **Mono output** — no stereo or spatial effects
- **Fixed tuning** — A4 = 440 Hz
- **Key rollover**: simultaneous QWERTY notes are limited by keyboard hardware (N-key rollover keyboard recommended for full chords)

## License

MIT
