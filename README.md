# PythonSynth - Polyphonic Synthesizer

A polyphonic/monophonic wavetable synthesizer with a clickable GUI piano, QWERTY keyboard playability, ADSR, stereo effects, mono mode with portamento/legato, and optional MIDI input.

## Quick Start

```bash
pip install -r requirements.txt
python -m src.main
```

MIDI input is opened automatically if a device is connected. The GUI always launches.

## GUI Features

- **Clickable Piano**: 3 octaves + 1 key (C4–C7), click or drag to play
- **QWERTY Keyboard**: Play notes from your computer keyboard
- **Polyphony**: Up to 96 simultaneous voices
- **Mono Mode**: Toggle button switches to single-voice mode with true legato (envelope continues across note changes) and portamento glide
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

- **Unison**: stack 1–8 sub-voices per note, each slightly detuned; Voices knob sets count, Detune knob sets total spread in cents (0–100 ¢); sub-voices are evenly distributed around the base pitch; state is saved in presets
- **Dual wavetable slots (A / B)**: each slot has 16 independent harmonic amplitude sliders and a live waveform preview
- **Morph knob**: continuously interpolates between slot A and slot B (32 steps); LFO-assignable
- **Edit slot toggle**: switch which slot (A or B) the harmonic sliders currently edit
- **Waveform presets** — click a button to load a classic shape into the active slot:
  - Sine, Saw, Square, Triangle, Semisine
  - Each button shows the actual waveform shape as its icon

## LFO Modulation

- **3 independent LFOs** (sine wave), each with rate (0.05–8 Hz) and amplitude knobs
- **Per-knob LFO routing**: right-click any assignable knob to assign it to one of the 3 LFOs
- **Assignable targets**: ADSR knobs, LPF cutoff/Q, reverb/delay/chorus/bitcrusher knobs, wavetable morph
- LFO panel selects which LFO to configure via a dropdown; each LFO retains its settings independently

## Presets

- **Save / Load**: full synth state (ADSR, effects, wavetable A/B, morph, LFO routing, mono mode, portamento) stored as JSON in `presets/`
- **Preset browser**: scan and load any `.json` preset from the `presets/` folder directly from the GUI; the preset menu button shows the currently loaded preset name

## What It Does

Each note plays through the wavetable oscillator with:
- **ADSR Envelope**: Fully customizable Attack, Decay, Sustain, Release; Attack/Decay/Release knobs use a logarithmic scale for finer control at short times
- **Velocity-based Volume**: Dynamic response from MIDI/click (0–127)
- **Pitch Bend Support**: ±2 semitones (or custom range)
- **Voice Stealing**: Oldest-note priority when exceeding max voices
- **Smooth Retrigger**: No clicks when re-playing the same note
- **Mono Mode + Legato/Portamento**: Single-voice mode with a note stack (most-recently-held note resumes on release), true legato (envelope never resets on note change), and a portamento glide with 0–2 s range controlled by the Portamento knob
- **Polyphony Gain Scaling**: Output is normalised by √(sum of active envelope amplitudes), keeping perceived loudness constant whether 1 or 16 voices are playing. The scaling is smoothed (50 ms) so voices fading through release cause no pumping or level jumps.
- **Compressor + Limiter**:
  - RMS compressor with soft knee
  - Peak limiter prevents clipping while preserving dynamics
- **Effects Chain** (stereo output, in signal order):
  - **Tube Distortion**: tanh soft-clip waveshaper with drive (1–20×) and wet/dry mix; output is gain-compensated so unity drive is transparent
  - **Reverb**: Freeverb-based with room size, damping, and wet/dry mix
  - **Delay**: Configurable time, feedback, and wet/dry mix
  - **Bitcrusher**: Bit-depth reduction (1–24 bits) + sample-rate reduction via sample-and-hold downsampling (factor 1–32); wet/dry mix
  - **Low-Pass Filter**: Variable cutoff and Q (resonance); **Key Track** toggle scales each note's filter cutoff proportionally to its frequency (centred on C4), so higher notes stay open and lower notes close more — the same effect as key tracking in Serum
  - **Chorus**: Stereo LFO-modulated delay (L/R phases offset by 180°); rate 0.05–8 Hz, depth, and wet/dry mix (mono → stereo)
- **Master Volume**: knob range mapped to 0–43% linear; defaults to 70% knob (0.3 linear) for comfortable headroom
- **Portamento**: knob in the Master section; only active in mono mode; 0% = instant, 100% = 2 s glide

## Architecture

```
MIDI / GUI click / QWERTY keyboard
    → Synthesizer (voice management)
    → Voice Pool (wavetable oscillator + ADSR per note)
    → Voice Mixer (sum active voices, √N envelope scaling)
    → Compressor (RMS stage + peak limiter)
    → Effects Chain (Distortion → Reverb → Delay → Bitcrusher → LPF → Chorus)
    → Master Volume
    → Audio Engine (stereo) → Speakers

LFO Bank (3 × sine LFO) → knob routing → modulates assignable parameters each block
```

**Real-time Design**: Audio synthesis runs in callback (zero allocations). MIDI polling runs in a separate thread. GUI updates at 20 Hz in a daemon thread.

## Modules

- `main.py` — Entry point: GUI piano with optional MIDI input
- `piano_gui.py` — Tkinter piano interface with all controls
- `synthesizer.py` — Core synthesis engine & dynamics processor
- `voice.py` — Individual wavetable oscillator + ADSR
- `effects.py` — Effect chain (TubeDistortion, LPF, Reverb, Delay, Chorus, Bitcrusher)
- `lfo.py` — LFO bank (3 sine LFOs) with knob routing registry
- `presets.py` — Preset capture, apply, save (JSON), and folder scan
- `midi_handler.py` — MIDI input handling
- `audio_engine.py` — Real-time audio output
- `widgets/` — Knob and HarmonicSlider custom widgets

## Configuration & API

```python
synth = Synthesizer(sample_rate=44100, max_voices=96)

synth.set_adsr(attack=0.01, decay=0.1, sustain=0.7, release=0.3)
synth.set_volume(0.8)
synth.set_lpf(cutoff_hz=10000, q=0.707)
synth.set_reverb(room_size=0.5, damping=0.5, wet=0.3)
synth.set_delay(delay_ms=250, feedback=0.4, wet=0.2)
synth.set_bitcrusher(bits=8.0, downsample=4, wet=0.5)
synth.set_wavetable(np.array([1.0, 0.5, 0.0, ...], dtype=np.float32))  # 16 harmonics
synth.set_mono_mode(True)          # enable mono/legato mode
synth.set_portamento(0.5)          # 0.0–1.0 → 0–2 s glide time
synth.set_unison(4, 20.0)          # 4 sub-voices, 20 cents total spread (0–100 ct)
synth.set_lpf_key_track(1.0)      # 0.0 = off, 1.0 = full key tracking
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
- **Fixed tuning** — A4 = 440 Hz
- **Key rollover**: simultaneous QWERTY notes are limited by keyboard hardware (N-key rollover keyboard recommended for full chords)

## License

MIT
