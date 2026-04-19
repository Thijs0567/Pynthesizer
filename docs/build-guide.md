# Build a Software Synthesizer in Python
### A Beginner's Course — From Sine Wave to Polyphonic Synth

---

> **Course overview**  
> You will build a fully working, polyphonic software synthesizer step by step. By the end you will have real-time audio output, a MIDI-capable voice engine, a DSP effects chain, and a graphical piano keyboard.  
>
> **Estimated time:** 8–10 hours  
> **Prerequisites:** Python basics (functions, classes, lists). No audio or DSP knowledge required.  
> **Tools:** Python 3.10+, pip, a text editor.

---

## Table of Contents

1. [How Sound Works in a Computer](#1-how-sound-works-in-a-computer)
2. [Project Setup](#2-project-setup)
3. [Generating Your First Tone](#3-generating-your-first-tone)
4. [The ADSR Envelope](#4-the-adsr-envelope)
5. [Additive Synthesis and Wavetables](#5-additive-synthesis-and-wavetables)
6. [The Voice Class](#6-the-voice-class)
7. [Polyphony and the Synthesizer Engine](#7-polyphony-and-the-synthesizer-engine)
8. [Real-Time Audio Output](#8-real-time-audio-output)
9. [DSP Effects Chain](#9-dsp-effects-chain)
10. [MIDI Input](#10-midi-input)
11. [Building the GUI](#11-building-the-gui)
12. [Wiring It All Together](#12-wiring-it-all-together)
13. [Testing Your Synthesizer](#13-testing-your-synthesizer)
14. [Where to Go Next](#14-where-to-go-next)

---

\newpage

## 1. How Sound Works in a Computer

### 1.1 Sound as Pressure Waves

Sound is rapid variation in air pressure. A speaker cone moves back and forth, pushing the air in a pattern that your ear detects as pitch and timbre. A computer represents that movement as a sequence of numbers called **samples**.

```
Pressure
  |   /\      /\      /\
  |  /  \    /  \    /  \
  | /    \  /    \  /    \
  |/      \/      \/      \___  time →
```

Each number in the sequence tells the speaker: *push this far at this moment.*

### 1.2 Sample Rate and Nyquist Theorem

The **sample rate** (SR) is how many samples per second you send to the speaker. The standard for audio is **44 100 Hz** (44.1 kHz) — that is, 44 100 numbers every second.

**Why 44.1 kHz?** The Nyquist–Shannon theorem states:

> To reproduce a frequency *f*, you need at least *2f* samples per second.

Human hearing tops out around 20 000 Hz, so you need at least 40 000 samples per second. 44 100 Hz became the standard because it was used by early digital recording equipment.

```
SR = 44100  # samples per second
```

### 1.3 Amplitude and Clipping

Each sample is a floating-point number in the range **−1.0 to +1.0**. Values outside this range cause **clipping** — a harsh distortion where the speaker cannot move any further.

```
+1.0 ─────────────────────────  ← hard limit
      /\         /\
     /  \       /  \
    /    \     /    \
───/──────\───/──────\───────── → time
           \  /       \  /
            \/         \/
−1.0 ─────────────────────────
```

### 1.4 Audio Callbacks and Buffers

Real-time audio works in **blocks** (also called buffers or frames). The audio driver asks your program: *"Give me the next 512 samples."* Your code must return those samples before the driver runs out, or you get a dropout (an audible click or gap). This time constraint is called the **real-time deadline**.

A typical block size is **512–2048 samples**. At 44 100 Hz and 2048 samples, you have about **46 ms** to compute each block.

---

\newpage

## 2. Project Setup

### 2.1 Folder Structure

Create the following layout. We will fill in each file as we go.

```
pythonsynth/
├── src/
│   ├── __init__.py
│   ├── voice.py          # single oscillator note
│   ├── synthesizer.py    # voice manager + effects glue
│   ├── effects.py        # DSP effects (filter, reverb, etc.)
│   ├── audio_engine.py   # sounddevice wrapper
│   ├── midi_handler.py   # MIDI input
│   └── piano_gui.py      # Tkinter GUI
├── tests/
│   ├── test_synthesis.py
│   └── test_effects.py
├── main.py
└── requirements.txt
```

### 2.2 Install Dependencies

```
pip install numpy sounddevice mido
```

| Package | Purpose |
|---|---|
| `numpy` | Fast array math for audio buffers |
| `sounddevice` | Send audio samples to the system audio driver |
| `mido` | Read MIDI messages from a keyboard or port |

`tkinter` comes with Python on Windows and macOS; on Linux install `python3-tk` with your package manager.

### 2.3 Verify Everything Works

```python
# check.py
import numpy as np
import sounddevice as sd
import mido
import tkinter

print("numpy:", np.__version__)
print("sounddevice:", sd.__version__)
print("All good.")
```

Run `python check.py`. If no errors appear you are ready.

---

\newpage

## 3. Generating Your First Tone

### 3.1 The Sine Wave

The simplest possible sound is a **sine wave** — a pure, single-frequency tone. Its formula is:

```
sample(t) = sin(2π · f · t)
```

Where:
- `f` is the frequency in Hz (e.g. 440 Hz = concert A)
- `t` is time in seconds

In code, we don't track continuous time — we track a **phase angle** that accumulates sample by sample.

```python
import numpy as np

SR = 44100   # sample rate
freq = 440   # A4

# Generate one second of a 440 Hz sine wave
num_samples = SR
t = np.arange(num_samples) / SR          # time array: [0, 1/SR, 2/SR, ...]
samples = np.sin(2 * np.pi * freq * t)   # sine values at each time point
```

### 3.2 Phase Accumulation (the Real-Time Way)

The time-array approach recalculates `t` from scratch every block, which breaks phase continuity between blocks (you'd hear a click at every block boundary). Instead, maintain a running **phase** variable:

```python
phase = 0.0
phase_increment = 2 * np.pi * freq / SR  # angle to advance per sample

def generate_block(num_samples: int) -> np.ndarray:
    global phase
    # Build an array of phase values for this block
    phases = phase + np.arange(num_samples) * phase_increment
    samples = np.sin(phases)
    # Save phase for next block (wrap to avoid float precision drift)
    phase = phases[-1] % (2 * np.pi)
    return samples
```

This guarantees the wave continues seamlessly across block boundaries.

### 3.3 Play It!

```python
import sounddevice as sd
import numpy as np

SR = 44100
freq = 440
phase = 0.0
phase_increment = 2 * np.pi * freq / SR

def callback(outdata, frames, time, status):
    global phase
    phases = phase + np.arange(frames) * phase_increment
    outdata[:, 0] = np.sin(phases) * 0.3  # 0.3 = quiet volume
    phase = phases[-1] % (2 * np.pi)

with sd.OutputStream(samplerate=SR, channels=1,
                     blocksize=512, callback=callback):
    input("Press Enter to stop...")
```

Run this. You should hear a steady A440 tone. Congratulations — you just built an oscillator.

> **Key concept:** The audio callback runs on a separate high-priority thread. Keep it fast. No file I/O, no network calls, and no dynamic memory allocation inside the callback.

---

\newpage

## 4. The ADSR Envelope

### 4.1 What Is an Envelope?

A raw sine wave plays at full volume the instant a key is pressed and cuts off instantly when released. Real instruments fade in, fade out, and sustain. An **ADSR envelope** shapes volume over time:

```
Volume
  1.0 ─────╮
           │╲  ← Decay
  Sus  ─── │ ╰─────────────╮  ← Sustain level
           │  Attack       │╲
           │               │  ╲  ← Release
  0.0 ─────┴───────────────┴────╯─────  time
           ↑               ↑
         key on          key off
```

| Stage | What happens |
|---|---|
| **Attack** | Volume ramps from 0 → 1 over `attack` seconds |
| **Decay** | Volume ramps from 1 → sustain level over `decay` seconds |
| **Sustain** | Volume stays at sustain level while key is held |
| **Release** | After key release, volume ramps from sustain → 0 over `release` seconds |

### 4.2 Computing Envelope Values

The envelope is just a scalar multiplied by the oscillator output. For each sample we compute how far along the ADSR we are, based on elapsed time.

```python
def get_envelope_value(t, key_off_time, attack, decay, sustain, release,
                       is_releasing, release_level):
    if is_releasing:
        elapsed = t - key_off_time
        return max(0.0, release_level * (1.0 - elapsed / release))

    if t < attack:
        return t / attack                                   # 0 → 1
    elif t < attack + decay:
        return 1.0 - (1.0 - sustain) * (t - attack) / decay  # 1 → sustain
    else:
        return sustain                                      # flat
```

### 4.3 Vectorizing the Envelope

Computing the envelope sample-by-sample in a Python loop is slow. NumPy's `np.where` lets us compute the whole block at once:

```python
import numpy as np

def compute_envelope(times, key_off_time, attack, decay, sustain, release,
                     is_releasing, release_level):
    if is_releasing:
        elapsed = times - key_off_time
        return np.maximum(0.0, release_level * (1.0 - elapsed / release))

    in_attack  = times < attack
    in_decay   = (times >= attack) & (times < attack + decay)

    env = np.where(in_attack,
                   times / attack,
            np.where(in_decay,
                     1.0 - (1.0 - sustain) * (times - attack) / decay,
                     sustain))
    return env
```

### 4.4 Detecting When a Voice Is Done

A voice is **finished** and can be removed when it is releasing and the envelope has reached zero:

```python
def is_done(t, key_off_time, release, is_releasing):
    return is_releasing and (t - key_off_time) >= release
```

---

\newpage

## 5. Additive Synthesis and Wavetables

### 5.1 Why Pure Sine Waves Sound Thin

A sine wave is the simplest sound, but most musical instruments produce many frequencies at once. A violin A440 also radiates 880 Hz (2nd harmonic), 1320 Hz (3rd harmonic), and so on. The mix of these harmonics is what gives an instrument its characteristic **timbre** (tone color).

### 5.2 Fourier's Insight

Jean-Baptiste Joseph Fourier proved that **any periodic waveform can be decomposed into a sum of sine waves** at integer multiples of a fundamental frequency.

```
f(t) = a₁·sin(1·ωt) + a₂·sin(2·ωt) + a₃·sin(3·ωt) + ...

where ω = 2π·freq
```

The coefficients `a₁, a₂, a₃, ...` are called **amplitudes** or **partial strengths**. By choosing different amplitudes you can build any timbre.

### 5.3 Classic Waveforms as Fourier Series

| Waveform | Harmonics | Amplitude formula |
|---|---|---|
| Sine | Fundamental only | `a₁ = 1`, rest = 0 |
| Sawtooth | All harmonics | `aₙ = 1/n` |
| Square | Odd harmonics only | `aₙ = 1/n` for odd n, 0 for even |
| Triangle | Odd harmonics | `aₙ = 1/n²` for odd n, alternating sign |

```python
def make_sawtooth_wavetable(num_harmonics=16):
    wt = np.zeros(num_harmonics)
    for n in range(1, num_harmonics + 1):
        wt[n - 1] = 1.0 / n   # amplitude of nth harmonic
    return wt

def make_square_wavetable(num_harmonics=16):
    wt = np.zeros(num_harmonics)
    for n in range(1, num_harmonics + 1, 2):   # odd harmonics
        wt[n - 1] = 1.0 / n
    return wt
```

### 5.4 Additive Synthesis in Code

Given a **wavetable** (array of 16 harmonic amplitudes) and a phase value, the oscillator output is:

```python
def oscillate(phase_array, wavetable):
    """
    phase_array: shape (N,) — phase value at each sample
    wavetable:   shape (16,) — amplitude of each harmonic
    returns:     shape (N,) — summed waveform
    """
    output = np.zeros(len(phase_array))
    for k, amp in enumerate(wavetable):
        if amp > 0:
            output += amp * np.sin((k + 1) * phase_array)
    return output
```

Harmonic index `k=0` is the **fundamental** (frequency = freq × 1). `k=1` is the **second harmonic** (freq × 2), and so on.

> **Aliasing warning:** If a harmonic exceeds half the sample rate (SR/2 = 22 050 Hz), it "folds back" and sounds wrong. For a 2000 Hz note, the 11th harmonic lands at 22 000 Hz — safe. For a 4000 Hz note, the 6th harmonic lands at 24 000 Hz — aliased. In practice, at MIDI note range this is rarely audible.

---

\newpage

## 6. The Voice Class

A **Voice** represents a single key being held. It combines the oscillator, phase accumulator, and envelope into one object. We create a new Voice every time a key is pressed and remove it when the envelope reaches zero.

### 6.1 Skeleton

```python
# src/voice.py
import numpy as np
import math

class Voice:
    def __init__(self, sample_rate: int, frequency: float, velocity: int,
                 attack: float, decay: float, sustain: float, release: float,
                 creation_time: float = 0.0, wavetable=None):

        self.sample_rate   = sample_rate
        self.frequency     = max(20.0, min(20000.0, frequency))
        self.velocity      = velocity / 127.0   # normalise to 0–1
        self.attack        = attack
        self.decay         = decay
        self.sustain       = sustain
        self.release       = release
        self.creation_time = creation_time

        self.phase          = 0.0
        self._time          = 0.0     # seconds since key-on
        self.is_releasing   = False
        self._key_off_time  = 0.0
        self._release_level = 0.0    # envelope value at the moment of release

        # 16-harmonic wavetable; default to pure sine
        if wavetable is None:
            self.wavetable = np.zeros(16)
            self.wavetable[0] = 1.0
        else:
            self.wavetable = np.array(wavetable, dtype=float)
```

### 6.2 Generating Samples

```python
    def generate_samples(self, num_samples: int) -> np.ndarray:
        SR   = self.sample_rate
        freq = self.frequency
        dt   = 1.0 / SR

        # Phase array for this block
        phase_inc  = 2.0 * math.pi * freq / SR
        phases     = self.phase + np.arange(num_samples) * phase_inc
        self.phase = phases[-1] % (2.0 * math.pi)

        # Oscillator: sum of harmonics
        osc = np.zeros(num_samples)
        for k, amp in enumerate(self.wavetable):
            if amp > 0.0:
                osc += amp * np.sin((k + 1) * phases)

        # Envelope time array
        times = self._time + np.arange(num_samples) * dt
        env   = self._compute_envelope(times)
        self._time += num_samples * dt

        return osc * env * self.velocity

    def _compute_envelope(self, times):
        if self.is_releasing:
            elapsed = times - self._key_off_time
            return np.maximum(0.0, self._release_level * (1.0 - elapsed / self.release))

        in_attack = times < self.attack
        in_decay  = (times >= self.attack) & (times < self.attack + self.decay)
        return np.where(in_attack,
                        times / self.attack,
                np.where(in_decay,
                         1.0 - (1.0 - self.sustain) * (times - self.attack) / self.decay,
                         self.sustain))
```

### 6.3 Note Off and Retrigger

```python
    def note_off(self):
        """Key released — begin release stage."""
        self._release_level = self._get_envelope_value()
        self._key_off_time  = self._time
        self.is_releasing   = True

    def retrigger(self, velocity: int):
        """Same note pressed again before it finished releasing."""
        # Restart from the current envelope level to avoid a volume jump
        self._retrigger_level = self._get_envelope_value()
        self.velocity         = velocity / 127.0
        self.is_releasing     = False
        self._time            = 0.0

    def _get_envelope_value(self) -> float:
        t = self._time
        if self.is_releasing:
            elapsed = t - self._key_off_time
            return max(0.0, self._release_level * (1.0 - elapsed / self.release))
        if t < self.attack:
            return t / self.attack
        elif t < self.attack + self.decay:
            return 1.0 - (1.0 - self.sustain) * (t - self.attack) / self.decay
        return self.sustain

    def is_done(self) -> bool:
        return self.is_releasing and (self._time - self._key_off_time) >= self.release
```

### 6.4 Quick Smoke Test

```python
# Run from project root: python -c "exec(open('src/voice.py').read()); ..."
voice = Voice(sample_rate=44100, frequency=440, velocity=100,
              attack=0.01, decay=0.1, sustain=0.7, release=0.2)
block = voice.generate_samples(2048)
print("max amplitude:", block.max())   # should be around 0.7 × (100/127)
```

---

\newpage

## 7. Polyphony and the Synthesizer Engine

### 7.1 Managing Multiple Voices

When multiple keys are pressed at once you need multiple Voices running simultaneously. The **Synthesizer** class is the manager: it holds a dictionary of active voices, creates voices on note-on, releases them on note-off, and mixes all voice outputs together.

```python
# src/synthesizer.py
import numpy as np
import time
from src.voice import Voice

class Synthesizer:
    MAX_VOICES = 16

    def __init__(self, sample_rate: int = 44100, max_voices: int = 16):
        self.sample_rate = sample_rate
        self.max_voices  = max_voices
        self.active_voices: dict[int, Voice] = {}  # note → Voice
        self._voice_time = 0.0   # monotonic clock for voice-stealing

        # ADSR defaults
        self.attack  = 0.01
        self.decay   = 0.1
        self.sustain = 0.7
        self.release = 0.2

        self.wavetable = np.zeros(16)
        self.wavetable[0] = 1.0
```

### 7.2 MIDI Note to Frequency

MIDI notes are integers from 0 to 127. The formula that converts a MIDI note number to Hz is:

```
frequency = 440 × 2^((note − 69) / 12)
```

MIDI note 69 = A4 = 440 Hz. Every 12 notes up is one octave (×2). Every 12 down is one octave (÷2).

```python
    @staticmethod
    def note_to_frequency(note: int) -> float:
        return 440.0 * (2.0 ** ((note - 69) / 12.0))
```

Some reference values to check your formula:

| MIDI note | Note name | Expected Hz |
|---|---|---|
| 21 | A0 | 27.5 |
| 60 | C4 (middle C) | 261.6 |
| 69 | A4 | 440.0 |
| 81 | A5 | 880.0 |
| 108 | C8 | 4186.0 |

### 7.3 Note On and Note Off

```python
    def _on_note_on(self, note: int, velocity: int):
        if note in self.active_voices:
            # Key repeated — retrigger smoothly
            self.active_voices[note].retrigger(velocity)
            return

        # Voice stealing: remove oldest voice if at the limit
        if len(self.active_voices) >= self.max_voices:
            oldest_note = min(self.active_voices,
                              key=lambda n: self.active_voices[n].creation_time)
            del self.active_voices[oldest_note]

        self.active_voices[note] = Voice(
            sample_rate   = self.sample_rate,
            frequency     = self.note_to_frequency(note),
            velocity      = velocity,
            attack        = self.attack,
            decay         = self.decay,
            sustain       = self.sustain,
            release       = self.release,
            creation_time = self._voice_time,
            wavetable     = self.wavetable,
        )
        self._voice_time += 1

    def _on_note_off(self, note: int):
        if note in self.active_voices:
            self.active_voices[note].note_off()
```

### 7.4 Mixing Voices

```python
    def generate_audio(self, num_samples: int) -> np.ndarray:
        # Collect samples from all active voices
        mixed = np.zeros(num_samples)
        finished = []

        for note, voice in self.active_voices.items():
            mixed += voice.generate_samples(num_samples)
            if voice.is_done():
                finished.append(note)

        # Remove finished voices
        for note in finished:
            del self.active_voices[note]

        return mixed
```

### 7.5 The Loudness Problem

When you press 8 keys at once, the mixed signal can be 8× louder than a single note — causing clipping. A naive fix is to divide by the number of voices, but that makes single notes sound quieter.

A better approach is to scale by the **square root of the number of active voices**. This models how perceived loudness grows with uncorrelated sound sources (like an orchestra):

```
scale = 1 / sqrt(num_voices)
```

For one voice: scale = 1.0 (full volume)  
For four voices: scale = 0.5  
For sixteen voices: scale = 0.25  

```python
    def generate_audio(self, num_samples: int) -> np.ndarray:
        mixed = np.zeros(num_samples)
        finished = []

        for note, voice in self.active_voices.items():
            mixed += voice.generate_samples(num_samples)
            if voice.is_done():
                finished.append(note)

        for note in finished:
            del self.active_voices[note]

        # Scale to prevent clipping
        n = max(1, len(self.active_voices))
        mixed *= 1.0 / np.sqrt(n)

        # Hard safety clip
        mixed = np.clip(mixed, -1.0, 1.0)
        return mixed
```

### 7.6 Settings Methods

Add simple setters so the GUI can update parameters at any time:

```python
    def set_adsr(self, attack, decay, sustain, release):
        self.attack  = attack
        self.decay   = decay
        self.sustain = sustain
        self.release = release

    def set_wavetable(self, amplitudes: np.ndarray):
        self.wavetable = np.array(amplitudes, dtype=float)

    def panic(self):
        """Silence everything immediately."""
        self.active_voices.clear()
```

---

\newpage

## 8. Real-Time Audio Output

### 8.1 How sounddevice Works

`sounddevice` opens a stream to your system audio driver. You provide a **callback function** that is called once per audio block. The callback receives:

- `outdata` — a NumPy array of shape `(frames, channels)` that you must fill
- `frames` — how many samples to fill
- `time` — timing information (rarely needed)
- `status` — flags for underruns/overruns

```python
# src/audio_engine.py
import sounddevice as sd
import numpy as np
from typing import Callable, Optional

class AudioEngine:
    def __init__(self, sample_rate: int = 44100,
                 channels: int = 2,
                 blocksize: int = 2048):
        self.sample_rate = sample_rate
        self.channels    = channels
        self.blocksize   = blocksize
        self._stream     = None
        self._callback: Optional[Callable] = None

    def set_audio_callback(self, callback: Callable):
        self._callback = callback

    def _stream_callback(self, outdata, frames, time, status):
        if status:
            print("Audio status:", status)

        if self._callback is None:
            outdata[:] = 0
            return

        audio = self._callback(frames)   # call synthesizer

        # Handle mono (N,) or stereo (N, 2)
        if audio.ndim == 1:
            # Mono → duplicate to all channels
            for ch in range(self.channels):
                outdata[:, ch] = audio
        else:
            outdata[:] = audio

    def start(self) -> bool:
        try:
            self._stream = sd.OutputStream(
                samplerate = self.sample_rate,
                channels   = self.channels,
                blocksize  = self.blocksize,
                callback   = self._stream_callback,
                dtype      = 'float32',
            )
            self._stream.start()
            return True
        except Exception as e:
            print("Audio engine failed to start:", e)
            return False

    def stop(self):
        if self._stream:
            self._stream.stop()
            self._stream.close()
            self._stream = None
```

### 8.2 Audio Callback Safety Rules

The audio callback runs on a **high-priority real-time thread**. Breaking any of these rules causes audio dropouts:

| Rule | Reason |
|---|---|
| No `print()` | Blocking I/O |
| No file reads/writes | Blocking I/O |
| No `time.sleep()` | Blocking |
| No Python `list.append()` in a loop | Memory allocation |
| No acquiring a Python `Lock` that another thread holds | Deadlock risk |
| Allocate buffers once in `__init__`, reuse them | Allocation-free path |

### 8.3 Testing Audio Output

```python
# Minimal end-to-end test — save as test_audio.py
from src.synthesizer import Synthesizer
from src.audio_engine import AudioEngine

synth  = Synthesizer(sample_rate=44100)
engine = AudioEngine(sample_rate=44100, channels=1, blocksize=2048)

engine.set_audio_callback(synth.generate_audio)
engine.start()

synth._on_note_on(69, 100)   # A4
input("Press Enter to stop...")
synth._on_note_off(69)
input("Press Enter to exit...")
engine.stop()
```

---

\newpage

## 9. DSP Effects Chain

Effects are applied to the mixed mono signal **after** all voices are summed, and before the output is sent to the speakers. We implement each effect as its own class with a `.process(signal)` method.

```
[voices summed] → Volume → LPF → Reverb → Delay → Compressor → Bitcrusher → Chorus → [speakers]
```

### 9.1 Master Volume

The simplest effect — just multiply by a scalar:

```python
# src/effects.py
import numpy as np
import math

class MasterVolume:
    def __init__(self):
        self.volume = 0.8

    def set_volume(self, volume: float):
        self.volume = max(0.0, min(1.0, volume))

    def process(self, signal: np.ndarray) -> np.ndarray:
        return signal * self.volume
```

### 9.2 Low-Pass Filter (Biquad IIR)

A **low-pass filter** lets low frequencies through and attenuates high frequencies. The cutoff frequency determines where this transition happens. **Resonance** (Q) controls a peak just below the cutoff — high Q gives a characteristic "wah" sound.

**Why a biquad filter?** It is a 2nd-order IIR (Infinite Impulse Response) filter: cheap to compute, numerically stable, and sounds musical.

The transfer function is:

```
H(z) = (b0 + b1·z⁻¹ + b2·z⁻²) / (1 + a1·z⁻¹ + a2·z⁻²)
```

The coefficients for a low-pass filter are derived from the cutoff frequency `f₀` and Q:

```
ω₀ = 2π·f₀/SR
α  = sin(ω₀) / (2·Q)

b0 = (1 - cos(ω₀)) / 2
b1 =  1 - cos(ω₀)
b2 = (1 - cos(ω₀)) / 2
a0 =  1 + α
a1 = -2·cos(ω₀)
a2 =  1 - α

(all values normalised by dividing by a0)
```

```python
class LowPassFilter:
    def __init__(self, sample_rate: int = 44100):
        self.sample_rate = sample_rate
        self.cutoff = 20000.0
        self.q      = 0.707   # Butterworth (maximally flat)
        self._z1    = 0.0     # filter state (two delay elements)
        self._z2    = 0.0
        self._compute_coefficients()

    def set_cutoff(self, cutoff_hz: float, q: float = None):
        self.cutoff = max(20.0, min(cutoff_hz, self.sample_rate / 2.1))
        if q is not None:
            self.q = max(0.1, q)
        self._compute_coefficients()

    def _compute_coefficients(self):
        w0    = 2.0 * math.pi * self.cutoff / self.sample_rate
        alpha = math.sin(w0) / (2.0 * self.q)
        cos_w = math.cos(w0)

        b0 = (1.0 - cos_w) / 2.0
        b1 =  1.0 - cos_w
        b2 = (1.0 - cos_w) / 2.0
        a0 =  1.0 + alpha
        a1 = -2.0 * cos_w
        a2 =  1.0 - alpha

        self._b0 = b0 / a0
        self._b1 = b1 / a0
        self._b2 = b2 / a0
        self._a1 = a1 / a0
        self._a2 = a2 / a0

    def process(self, signal: np.ndarray) -> np.ndarray:
        out = np.empty_like(signal)
        z1, z2 = self._z1, self._z2
        # Transposed Direct Form II — numerically stable
        for i, x in enumerate(signal):
            y    = self._b0 * x + z1
            z1   = self._b1 * x - self._a1 * y + z2
            z2   = self._b2 * x - self._a2 * y
            out[i] = y
        self._z1, self._z2 = z1, z2
        return out
```

> **Why process per-sample in a loop?** Each sample's output depends on the previous sample's output (that is what IIR means). NumPy cannot vectorize this automatically. For a production synth in C++ you would SIMD-vectorize this, but in Python the per-sample loop is fine for block sizes up to ~4096.

### 9.3 Delay Effect

A delay records the audio into a circular buffer and mixes a delayed copy back into the signal. Adding feedback (feeding the output back into the input) creates echoes that fade out over time.

```
[input] ──┬────────────────────────────────→ [dry output]
          │                                        ↑
          └→ [circular buffer] → (delay time) ─→ × wet → mix
                   ↑ feedback ──────────────────────┘
```

```python
class Delay:
    def __init__(self, sample_rate: int = 44100):
        self.sample_rate = sample_rate
        self.delay_ms    = 300.0
        self.feedback    = 0.4
        self.wet         = 0.0

        max_delay_samples = int(sample_rate * 1.0)   # 1 second max
        self._buffer      = np.zeros(max_delay_samples)
        self._write_ptr   = 0

    def set_delay(self, delay_ms: float, feedback: float, wet: float):
        self.delay_ms = max(10.0, min(1000.0, delay_ms))
        self.feedback = max(0.0, min(0.9, feedback))   # cap at 0.9 to prevent blowup
        self.wet      = max(0.0, min(1.0, wet))

    def process(self, signal: np.ndarray) -> np.ndarray:
        out     = np.empty_like(signal)
        buf     = self._buffer
        buf_len = len(buf)
        delay_s = int(self.delay_ms * self.sample_rate / 1000.0)
        wp      = self._write_ptr

        for i, x in enumerate(signal):
            read_ptr    = (wp - delay_s) % buf_len
            delayed     = buf[read_ptr]
            buf[wp]     = x + delayed * self.feedback
            out[i]      = x + delayed * self.wet
            wp          = (wp + 1) % buf_len

        self._write_ptr = wp
        return out
```

### 9.4 Reverb (Freeverb Topology)

Reverb simulates how sound bounces off the walls of a room. The Freeverb algorithm (Jezar at Dreampoint, 1999) uses:

- **4 comb filters** in parallel — each adds a series of echoes
- **2 allpass filters** in series — randomize the echo timing to sound less metallic

A **comb filter** is a delay line with feedback:

```
output[n] = input[n] + feedback × output[n − delay_length]
```

```python
class _CombFilter:
    def __init__(self, delay_samples: int, feedback: float, damping: float):
        self._buf      = np.zeros(delay_samples)
        self._ptr      = 0
        self.feedback  = feedback
        self.damping   = damping
        self._store    = 0.0    # damping low-pass state

    def process_sample(self, x: float) -> float:
        output       = self._buf[self._ptr]
        self._store  = output * (1.0 - self.damping) + self._store * self.damping
        self._buf[self._ptr] = x + self._store * self.feedback
        self._ptr    = (self._ptr + 1) % len(self._buf)
        return output
```

An **allpass filter** preserves spectral energy while scattering phase:

```python
class _AllpassFilter:
    def __init__(self, delay_samples: int):
        self._buf  = np.zeros(delay_samples)
        self._ptr  = 0

    def process_sample(self, x: float) -> float:
        buf_out           = self._buf[self._ptr]
        output            = -x + buf_out
        self._buf[self._ptr] = x + buf_out * 0.5
        self._ptr         = (self._ptr + 1) % len(self._buf)
        return output
```

```python
class Reverb:
    # Freeverb comb delay lengths (at 44.1 kHz)
    COMB_LENGTHS    = [1116, 1188, 1277, 1356]
    ALLPASS_LENGTHS = [556, 441]

    def __init__(self, sample_rate: int = 44100):
        scale = sample_rate / 44100.0
        self.wet      = 0.0
        self.room     = 0.5   # 0–1 → feedback 0.70–0.98
        self.damping  = 0.5

        self._combs   = [_CombFilter(int(l * scale), 0.84, 0.5)
                         for l in self.COMB_LENGTHS]
        self._allpass = [_AllpassFilter(int(l * scale))
                         for l in self.ALLPASS_LENGTHS]

    def set_reverb(self, room_size: float, damping: float, wet: float):
        self.room    = max(0.0, min(1.0, room_size))
        self.damping = max(0.0, min(1.0, damping))
        self.wet     = max(0.0, min(1.0, wet))
        feedback = 0.70 + self.room * 0.28
        for c in self._combs:
            c.feedback = feedback
            c.damping  = damping

    def process(self, signal: np.ndarray) -> np.ndarray:
        out = np.empty_like(signal)
        for i, x in enumerate(signal):
            # Sum all comb filters in parallel
            verb = sum(c.process_sample(x) for c in self._combs)
            # Pass through allpass filters in series
            for ap in self._allpass:
                verb = ap.process_sample(verb)
            out[i] = x + verb * self.wet
        return out
```

### 9.5 Bitcrusher

The bitcrusher reduces **bit depth** (quantizes the signal to fewer discrete levels) and optionally reduces **sample rate** (sample-and-hold). Both effects give a retro lo-fi character.

**Bit depth reduction:**

```
step   = 1 / 2^(bits − 1)
output = round(input / step) × step
```

With 8 bits, `step = 1/128 ≈ 0.0078`. Each sample snaps to the nearest multiple of 0.0078.

**Sample-rate reduction:** Hold each sample for `factor` samples before advancing to the next. A factor of 4 gives an effective rate of 44100/4 = 11025 Hz.

```python
class Bitcrusher:
    def __init__(self):
        self.bits        = 24    # effectively bypassed at 24 bits
        self.downsample  = 1
        self.wet         = 0.0
        self._hold_val   = 0.0
        self._hold_count = 0

    def set_bitcrusher(self, bits: int, downsample: int, wet: float):
        self.bits       = max(1, min(24, bits))
        self.downsample = max(1, min(32, downsample))
        self.wet        = max(0.0, min(1.0, wet))

    def process(self, signal: np.ndarray) -> np.ndarray:
        step = 1.0 / (2 ** (self.bits - 1))
        out  = np.empty_like(signal)

        for i, x in enumerate(signal):
            # Sample-rate reduction
            if self._hold_count == 0:
                self._hold_val = x
            self._hold_count = (self._hold_count + 1) % self.downsample

            # Quantize
            crushed = np.round(self._hold_val / step) * step
            out[i]  = x + (crushed - x) * self.wet

        return out
```

### 9.6 Chorus (Stereo Widener)

The chorus doubles the signal with a slightly pitch-shifted copy, creating a lush, wide stereo image. The pitch shift is achieved by modulating the delay time with a **Low Frequency Oscillator (LFO)** — a slow sine wave (0.1–8 Hz).

The left and right channels use LFOs that are 180° out of phase, pushing the stereo image wide.

```python
class Chorus:
    def __init__(self, sample_rate: int = 44100):
        self.sample_rate = sample_rate
        self.rate        = 0.5     # LFO Hz
        self.depth       = 0.003   # seconds (3 ms)
        self.wet         = 0.0
        self._lfo_phase  = 0.0

        center_ms    = 0.020       # 20 ms center delay
        max_delay    = int(sample_rate * (center_ms + self.depth + 0.001))
        self._buffer = np.zeros(max_delay + 16)
        self._ptr    = 0

    def set_chorus(self, rate_hz: float, depth: float, wet: float):
        self.rate  = max(0.05, min(8.0, rate_hz))
        self.depth = max(0.0, min(0.020, depth))
        self.wet   = max(0.0, min(1.0, wet))

    def process(self, signal: np.ndarray) -> np.ndarray:
        SR          = self.sample_rate
        center      = int(0.020 * SR)
        depth_samp  = self.depth * SR
        lfo_inc     = 2.0 * math.pi * self.rate / SR
        buf         = self._buffer
        buf_len     = len(buf)
        out         = np.zeros((len(signal), 2))   # stereo output
        lfo_phase   = self._lfo_phase
        ptr         = self._ptr

        for i, x in enumerate(signal):
            buf[ptr] = x

            # Left channel: LFO at 0°
            delay_l = center + depth_samp * math.sin(lfo_phase)
            # Right channel: LFO at 180°
            delay_r = center + depth_samp * math.sin(lfo_phase + math.pi)

            # Linear interpolation for fractional delay
            def read_delayed(delay):
                d0 = int(delay)
                frac = delay - d0
                s0 = buf[(ptr - d0) % buf_len]
                s1 = buf[(ptr - d0 - 1) % buf_len]
                return s0 + frac * (s1 - s0)

            wet_l = read_delayed(delay_l)
            wet_r = read_delayed(delay_r)

            out[i, 0] = x + wet_l * self.wet
            out[i, 1] = x + wet_r * self.wet

            lfo_phase = (lfo_phase + lfo_inc) % (2.0 * math.pi)
            ptr = (ptr + 1) % buf_len

        self._lfo_phase = lfo_phase
        self._ptr       = ptr
        return out
```

### 9.7 Wiring the Effects Chain

Add the effects to the Synthesizer:

```python
# Inside Synthesizer.__init__
from src.effects import MasterVolume, LowPassFilter, Reverb, Delay, Bitcrusher, Chorus

self._volume    = MasterVolume()
self._lpf       = LowPassFilter(sample_rate)
self._reverb    = Reverb(sample_rate)
self._delay     = Delay(sample_rate)
self._bitcrusher = Bitcrusher()
self._chorus    = Chorus(sample_rate)
```

```python
# Replace the return statement in generate_audio
def generate_audio(self, num_samples: int) -> np.ndarray:
    # ... (voice mixing code from section 7.4) ...

    # Effects chain
    signal = self._volume.process(signal)
    signal = self._lpf.process(signal)
    signal = self._reverb.process(signal)
    signal = self._delay.process(signal)
    signal = np.clip(signal, -1.0, 1.0)          # safety clip before chorus
    signal = self._bitcrusher.process(signal)
    stereo = self._chorus.process(signal)         # mono → stereo (N, 2)

    return stereo.astype(np.float32)
```

And add the setter methods:

```python
def set_volume(self, v): self._volume.set_volume(v)
def set_lpf(self, cutoff, q): self._lpf.set_cutoff(cutoff, q)
def set_reverb(self, room, damp, wet): self._reverb.set_reverb(room, damp, wet)
def set_delay(self, ms, fb, wet): self._delay.set_delay(ms, fb, wet)
def set_bitcrusher(self, bits, ds, wet): self._bitcrusher.set_bitcrusher(bits, ds, wet)
def set_chorus(self, rate, depth, wet): self._chorus.set_chorus(rate, depth, wet)
```

---

\newpage

## 10. MIDI Input

### 10.1 What Is MIDI?

MIDI (Musical Instrument Digital Interface) is a protocol for sending musical control messages. A MIDI keyboard sends **note on** (key pressed, with velocity 0–127) and **note off** (key released) messages. Other messages include pitch bend, control changes (knobs/sliders), and program change.

MIDI messages are 2–3 bytes:

| Message type | Byte 1 | Byte 2 | Byte 3 |
|---|---|---|---|
| Note on | `0x90 + channel` | note (0–127) | velocity (0–127) |
| Note off | `0x80 + channel` | note (0–127) | velocity (always 0) |
| Pitch bend | `0xE0 + channel` | LSB | MSB |
| Control change | `0xB0 + channel` | controller (0–127) | value (0–127) |

### 10.2 The MIDIHandler Class

```python
# src/midi_handler.py
import threading
import time
from typing import Callable, Optional, List

try:
    import mido
    MIDO_AVAILABLE = True
except ImportError:
    MIDO_AVAILABLE = False

class MIDIHandler:
    def __init__(self):
        self.on_note_on:       Callable[[int, int], None]  = lambda n, v: None
        self.on_note_off:      Callable[[int], None]        = lambda n: None
        self.on_pitch_bend:    Callable[[float], None]      = lambda v: None
        self.on_control_change: Callable[[int, int], None] = lambda c, v: None

        self._port   = None
        self._thread = None
        self._running = False

    def list_input_ports(self) -> List[str]:
        if not MIDO_AVAILABLE:
            return []
        return mido.get_input_names()

    def open_port(self, port_index: int = 0) -> bool:
        if not MIDO_AVAILABLE:
            return False
        ports = self.list_input_ports()
        if not ports or port_index >= len(ports):
            return False
        try:
            self._port = mido.open_input(ports[port_index])
            return True
        except Exception as e:
            print("MIDI port error:", e)
            return False

    def start(self) -> bool:
        if self._port is None:
            return False
        self._running = True
        self._thread  = threading.Thread(target=self._poll, daemon=True)
        self._thread.start()
        return True

    def _poll(self):
        while self._running:
            if self._port:
                for msg in self._port.iter_pending():
                    self._dispatch(msg)
            time.sleep(0.001)   # 1 ms polling interval

    def _dispatch(self, msg):
        t = msg.type
        if t == 'note_on' and msg.velocity > 0:
            self.on_note_on(msg.note, msg.velocity)
        elif t == 'note_off' or (t == 'note_on' and msg.velocity == 0):
            self.on_note_off(msg.note)
        elif t == 'pitchwheel':
            # mido gives -8192 to +8191; normalise to -1.0 to +1.0
            self.on_pitch_bend(msg.pitch / 8191.0)
        elif t == 'control_change':
            self.on_control_change(msg.control, msg.value)

    def stop(self):
        self._running = False
        if self._port:
            self._port.close()
            self._port = None
```

### 10.3 Connecting MIDI to the Synthesizer

```python
# In main.py
from src.midi_handler import MIDIHandler
from src.synthesizer  import Synthesizer

synth = Synthesizer()
midi  = MIDIHandler()

# Wire callbacks
midi.on_note_on    = synth._on_note_on
midi.on_note_off   = synth._on_note_off
midi.on_pitch_bend = synth._on_pitch_bend

# Try to open the first available MIDI port
ports = midi.list_input_ports()
if ports:
    print("MIDI ports:", ports)
    midi.open_port(0)
    midi.start()
    print("MIDI active:", ports[0])
else:
    print("No MIDI input found — using keyboard/mouse only.")
```

### 10.4 Pitch Bend

Pitch bend is a continuous value that shifts the frequency of all active voices up or down. The standard range is ±2 semitones. The frequency shift in Hz is:

```
shifted_freq = base_freq × 2^(bend × semitones / 12)
```

```python
# In Synthesizer
def _on_pitch_bend(self, value: float):
    """value: -1.0 to +1.0"""
    semitones = 2.0   # ±2 semitone range
    ratio = 2.0 ** (value * semitones / 12.0)
    for voice in self.active_voices.values():
        base_freq = self.note_to_frequency(
            [n for n, v in self.active_voices.items() if v is voice][0])
        voice.set_frequency(base_freq * ratio)
```

---

\newpage

## 11. Building the GUI

### 11.1 Tkinter Overview

`tkinter` is Python's built-in GUI library. A Tkinter app has a **root window** (`Tk()`), into which you place **widgets** (buttons, canvases, sliders). Event handlers connect user actions (clicks, drags, key presses) to your code.

Key concepts:
- `root.mainloop()` runs the event loop (blocking)
- `canvas.create_rectangle(x0, y0, x1, y1)` draws a filled rectangle
- `canvas.tag_bind(tag, "<ButtonPress-1>", handler)` catches mouse events
- `root.after(ms, function)` schedules a callback on the GUI thread

### 11.2 Drawing Piano Keys

We represent white keys as rectangles and black keys as narrower, shorter rectangles drawn on top. The piano is built from a `Canvas` widget.

```python
import tkinter as tk

WHITE_KEY_W = 36
WHITE_KEY_H = 140
BLACK_KEY_W = 22
BLACK_KEY_H = 90
BLACK_KEY_OFFSETS = {1: 0.6, 3: 1.6, 6: 3.6, 8: 4.6, 10: 5.6}  # semitone → x offset

def build_piano_canvas(root, start_note=48, num_octaves=2):
    """Draw piano keys; return canvas and key→note mapping."""
    white_notes = [n for n in range(start_note, start_note + num_octaves * 12 + 1)
                   if (n % 12) not in (1, 3, 6, 8, 10)]
    width  = len(white_notes) * WHITE_KEY_W
    canvas = tk.Canvas(root, width=width, height=WHITE_KEY_H, bg="white")
    canvas.pack()

    key_items = {}   # item_id → note

    # Draw white keys first
    for i, note in enumerate(white_notes):
        x0 = i * WHITE_KEY_W
        item = canvas.create_rectangle(x0, 0, x0 + WHITE_KEY_W, WHITE_KEY_H,
                                       fill="white", outline="black", tags=f"key_{note}")
        key_items[item] = note

    # Draw black keys on top
    white_index = 0
    for note in range(start_note, start_note + num_octaves * 12 + 1):
        semitone = note % 12
        if semitone in BLACK_KEY_OFFSETS:
            x0 = (white_index + BLACK_KEY_OFFSETS[semitone] - 0.6) * WHITE_KEY_W
            item = canvas.create_rectangle(x0, 0, x0 + BLACK_KEY_W, BLACK_KEY_H,
                                           fill="black", tags=f"key_{note}")
            key_items[item] = note
        else:
            white_index += 1

    return canvas, key_items
```

### 11.3 Handling Key Press and Release

```python
def add_piano_callbacks(canvas, key_items, on_note_on, on_note_off):
    active_key = [None]   # mutable container for closure

    def press(event):
        # Find which key was clicked
        items = canvas.find_overlapping(event.x, event.y, event.x, event.y)
        if not items:
            return
        # Topmost item (last in list) is the black key if overlapping
        for item in reversed(items):
            if item in key_items:
                note = key_items[item]
                if active_key[0] != note:
                    if active_key[0] is not None:
                        on_note_off(active_key[0])
                    on_note_on(note, 90)
                    active_key[0] = note
                    # Highlight key
                    fill = "#aaa" if canvas.itemcget(item, "fill") == "white" else "#555"
                    canvas.itemconfig(item, fill=fill)
                break

    def release(event):
        if active_key[0] is not None:
            on_note_off(active_key[0])
            # Restore key color
            for item, note in key_items.items():
                if note == active_key[0]:
                    orig = "black" if canvas.itemcget(item, "fill") == "#555" else "white"
                    canvas.itemconfig(item, fill=orig)
            active_key[0] = None

    canvas.bind("<ButtonPress-1>",   press)
    canvas.bind("<ButtonRelease-1>", release)
    canvas.bind("<B1-Motion>",       press)
```

### 11.4 ADSR Knobs

A **knob** is a rotary control — a canvas circle you drag vertically to change its value. Tkinter has no built-in knob, so we draw one:

```python
class Knob(tk.Canvas):
    def __init__(self, parent, from_=0.0, to=1.0, initial=0.5,
                 label="", command=None, **kwargs):
        super().__init__(parent, width=60, height=70, **kwargs)
        self.from_   = from_
        self.to      = to
        self.value   = initial
        self.label   = label
        self.command = command
        self._drag_y = None
        self._draw()
        self.bind("<ButtonPress-1>",   self._on_press)
        self.bind("<B1-Motion>",       self._on_drag)
        self.bind("<ButtonRelease-1>", self._on_release)

    def _norm(self):
        return (self.value - self.from_) / (self.to - self.from_)

    def _draw(self):
        self.delete("all")
        cx, cy, r = 30, 30, 22
        # Background arc (gray track)
        self.create_arc(cx-r, cy-r, cx+r, cy+r, start=-220, extent=260,
                        style="arc", outline="#555", width=4)
        # Value arc (green)
        extent = int(self._norm() * 260)
        self.create_arc(cx-r, cy-r, cx+r, cy+r, start=-220, extent=extent,
                        style="arc", outline="#4caf50", width=4)
        # Pointer
        angle = math.radians(-220 + self._norm() * 260)
        px = cx + (r - 5) * math.cos(angle)
        py = cy - (r - 5) * math.sin(angle)
        self.create_line(cx, cy, px, py, fill="white", width=2)
        # Label
        self.create_text(30, 58, text=self.label, fill="white", font=("Arial", 8))

    def _on_press(self, event): self._drag_y = event.y
    def _on_release(self, event): self._drag_y = None

    def _on_drag(self, event):
        if self._drag_y is None:
            return
        dy    = self._drag_y - event.y   # positive = upward = increase
        delta = dy / 100.0 * (self.to - self.from_)
        self.value = max(self.from_, min(self.to, self.value + delta))
        self._drag_y = event.y
        self._draw()
        if self.command:
            self.command(self.value)

    def get(self): return self.value
    def set(self, value):
        self.value = max(self.from_, min(self.to, value))
        self._draw()
```

### 11.5 Connecting Knobs to the Synthesizer

```python
# In your GUI setup code
def make_adsr_section(parent, synth):
    frame = tk.LabelFrame(parent, text="ADSR", bg="#222", fg="white")
    frame.pack(side="left", padx=10)

    def on_change(*_):
        synth.set_adsr(
            attack  = atk.get() / 1000.0,   # ms → seconds
            decay   = dec.get() / 1000.0,
            sustain = sus.get() / 100.0,     # % → 0–1
            release = rel.get() / 1000.0,
        )

    atk = Knob(frame, from_=1, to=500, initial=10,   label="Atk ms", command=on_change)
    dec = Knob(frame, from_=1, to=500, initial=100,  label="Dec ms", command=on_change)
    sus = Knob(frame, from_=0, to=100, initial=70,   label="Sus %",  command=on_change)
    rel = Knob(frame, from_=1, to=2000, initial=200, label="Rel ms", command=on_change)

    for k in (atk, dec, sus, rel):
        k.pack(side="left", padx=4)
```

### 11.6 Harmonic Sliders

Each harmonic slider is a vertical fader from 0.0 to 1.0. Draw it on a small Canvas and respond to mouse events:

```python
class HarmonicSlider(tk.Canvas):
    def __init__(self, parent, index, command=None, **kwargs):
        super().__init__(parent, width=24, height=80, bg="#1a1a1a", **kwargs)
        self.value   = 0.0
        self.index   = index
        self.command = command
        self._draw()
        self.bind("<ButtonPress-1>",   self._on_click)
        self.bind("<B1-Motion>",       self._on_drag)

    def _draw(self):
        self.delete("all")
        h = 80
        fill_h = int(self.value * (h - 4))
        self.create_rectangle(2, h - 2 - fill_h, 22, h - 2,
                               fill="#4caf50", outline="")
        label = "F" if self.index == 0 else str(self.index + 1)
        self.create_text(12, 6, text=label, fill="#aaa", font=("Arial", 7))

    def _set_from_y(self, y):
        self.value = max(0.0, min(1.0, 1.0 - (y - 2) / 76.0))
        self._draw()
        if self.command:
            self.command(self.index, self.value)

    def _on_click(self, event): self._set_from_y(event.y)
    def _on_drag(self, event):  self._set_from_y(event.y)
```

### 11.7 Level Meter

A level meter shows the current audio output level. We read the peak from the audio callback and display it as a vertical bar:

```python
def draw_level_meter(canvas, level_db):
    """level_db: 0 = full, -60 = silence"""
    canvas.delete("all")
    canvas.create_rectangle(0, 0, 20, 120, fill="#111")
    bar_h = int((level_db + 60) / 60 * 120)
    bar_h = max(0, min(120, bar_h))
    if level_db > -6:
        color = "red"
    elif level_db > -18:
        color = "yellow"
    else:
        color = "#4caf50"
    canvas.create_rectangle(2, 120 - bar_h, 18, 120, fill=color)
```

Update this from the GUI thread every 50 ms:

```python
def schedule_meter_update(root, canvas, get_level_db):
    def update():
        draw_level_meter(canvas, get_level_db())
        root.after(50, update)
    root.after(50, update)
```

---

\newpage

## 12. Wiring It All Together

### 12.1 The Main Entry Point

```python
# main.py
import threading
import numpy as np
import tkinter as tk

from src.synthesizer  import Synthesizer
from src.audio_engine import AudioEngine
from src.midi_handler import MIDIHandler
from src.piano_gui    import PianoGUI

SR         = 44100
BLOCKSIZE  = 2048
MAX_VOICES = 16

# ── Core objects ─────────────────────────────────────────────────────────────
synth  = Synthesizer(sample_rate=SR, max_voices=MAX_VOICES)
engine = AudioEngine(sample_rate=SR, channels=2, blocksize=BLOCKSIZE)
midi   = MIDIHandler()

# ── Shared state for the meter ────────────────────────────────────────────────
_level_info = {"peak": 0.0}   # written by audio thread, read by GUI thread

def audio_callback(frames: int) -> np.ndarray:
    audio = synth.generate_audio(frames)
    _level_info["peak"] = float(np.max(np.abs(audio)))
    return audio

engine.set_audio_callback(audio_callback)
engine.start()

# ── MIDI setup ───────────────────────────────────────────────────────────────
midi.on_note_on    = synth._on_note_on
midi.on_note_off   = synth._on_note_off
midi.on_pitch_bend = synth._on_pitch_bend

ports = midi.list_input_ports()
if ports:
    midi.open_port(0)
    midi.start()
    print("MIDI:", ports[0])
else:
    print("No MIDI found.")

# ── GUI ──────────────────────────────────────────────────────────────────────
root = tk.Tk()
root.title("PythonSynth")
root.configure(bg="#1a1a1a")

gui = PianoGUI(root, synth)   # PianoGUI connects note on/off to synth

def get_level_db():
    peak = _level_info["peak"]
    if peak < 1e-7:
        return -60.0
    return max(-60.0, 20 * np.log10(peak))

# Schedule GUI update at 20 Hz
def gui_update():
    gui.update_meter(get_level_db())
    gui.update_voice_count(len(synth.active_voices))
    root.after(50, gui_update)

root.after(50, gui_update)

def on_close():
    engine.stop()
    midi.stop()
    root.destroy()

root.protocol("WM_DELETE_WINDOW", on_close)
root.mainloop()
```

### 12.2 PianoGUI Skeleton

```python
# src/piano_gui.py
import tkinter as tk

class PianoGUI:
    def __init__(self, root: tk.Tk, synth):
        self.root  = root
        self.synth = synth
        self._build()

    def _build(self):
        # Top row: ADSR, oscillator, effects
        controls = tk.Frame(self.root, bg="#1a1a1a")
        controls.pack(fill="x", padx=10, pady=5)
        self._build_adsr(controls)
        self._build_oscillator(controls)
        self._build_effects(controls)

        # Middle: piano keys
        piano_frame = tk.Frame(self.root, bg="#1a1a1a")
        piano_frame.pack(pady=10)
        self._build_piano(piano_frame)

        # Bottom: master volume, meter
        bottom = tk.Frame(self.root, bg="#1a1a1a")
        bottom.pack(fill="x", padx=10)
        self._build_master(bottom)

    # ... (individual _build_* methods as shown in section 11) ...

    def update_meter(self, level_db: float):
        # Redraw level meter
        pass

    def update_voice_count(self, count: int):
        # Update voice counter label
        pass
```

### 12.3 Thread Safety Notes

You have three threads in this application:

| Thread | Runs | Rule |
|---|---|---|
| **Main/GUI thread** | `root.mainloop()` | All tkinter calls must be here |
| **Audio thread** | `engine._stream_callback()` | No allocation, no blocking |
| **MIDI thread** | `midi._poll()` | 1 ms loop; calls synth callbacks |

The MIDI thread calls `synth._on_note_on()` and `synth._on_note_off()`, which modify the `active_voices` dictionary — the same dictionary the audio thread reads in `generate_audio()`. This is a **race condition** in principle.

For a production app you would use a lock-free queue (e.g. `queue.Queue`) to pass events from the MIDI thread to the audio thread. For our purposes, CPython's Global Interpreter Lock (GIL) prevents the most dangerous memory corruption, so the app works reliably in practice. But keep it in mind.

---

\newpage

## 13. Testing Your Synthesizer

### 13.1 Why Test DSP Code?

DSP bugs are subtle. A filter with the wrong coefficient sounds similar to the correct one until you compare them. A voice that slightly clips may not be audible until 8 voices play together. Tests catch these problems automatically.

Good DSP tests are:
- **Deterministic** — same input always gives same output
- **Offline** — no audio device required
- **Property-based** — test invariants ("output must never exceed 1.0") not exact values

### 13.2 Testing the Voice

```python
# tests/test_synthesis.py
import numpy as np
import sys; sys.path.insert(0, ".")
from src.voice import Voice

SR = 44100

def make_voice(**kwargs):
    defaults = dict(sample_rate=SR, frequency=440, velocity=100,
                    attack=0.01, decay=0.1, sustain=0.7, release=0.3)
    defaults.update(kwargs)
    return Voice(**defaults)

def test_voice_no_clip():
    """16 voices in unison must not clip."""
    voices  = [make_voice() for _ in range(16)]
    mixed   = sum(v.generate_samples(2048) for v in voices)
    scale   = 1.0 / np.sqrt(len(voices))
    assert np.max(np.abs(mixed * scale)) <= 1.0, "Clipping detected"

def test_note_off_silences():
    """Voice must reach zero within release time."""
    v = make_voice(release=0.1, sustain=0.7)
    v.generate_samples(int(SR * 0.15))   # past sustain
    v.note_off()
    v.generate_samples(int(SR * 0.12))   # through release
    assert v.is_done()

def test_frequency_conversion():
    from src.synthesizer import Synthesizer
    assert abs(Synthesizer.note_to_frequency(69) - 440.0) < 0.01
    assert abs(Synthesizer.note_to_frequency(81) - 880.0) < 0.01
    assert abs(Synthesizer.note_to_frequency(57) - 220.0) < 0.01
```

### 13.3 Testing the Effects

```python
# tests/test_effects.py
import numpy as np
import sys; sys.path.insert(0, ".")
from src.effects import LowPassFilter, Delay, Reverb, MasterVolume

SR = 44100

def test_lpf_attenuates_high_freq():
    """A 10 kHz sine should be attenuated with cutoff at 1 kHz."""
    lpf  = LowPassFilter(SR)
    lpf.set_cutoff(1000.0)
    t    = np.arange(SR) / SR
    high = np.sin(2 * np.pi * 10000 * t).astype(np.float64)
    out  = lpf.process(high)
    assert out.std() < high.std() * 0.5, "High freq not attenuated"

def test_lpf_state_continuity():
    """Filter output must not jump at block boundaries."""
    lpf = LowPassFilter(SR)
    lpf.set_cutoff(1000.0)
    t = np.arange(SR * 2) / SR
    sig = np.sin(2 * np.pi * 500 * t)
    # Process in two blocks
    out1 = lpf.process(sig[:SR])
    out2 = lpf.process(sig[SR:])
    # No discontinuity at boundary
    jump = abs(float(out1[-1]) - float(out2[0]))
    assert jump < 0.1, f"Filter state jump too large: {jump}"

def test_delay_timing():
    """A pulse input should appear delayed by the set delay time."""
    d = Delay(SR)
    d.set_delay(100.0, 0.0, 1.0)   # 100 ms delay, no feedback, full wet
    impulse = np.zeros(SR)
    impulse[0] = 1.0
    out = d.process(impulse)
    expected_idx = int(0.1 * SR)   # 100 ms
    assert out[expected_idx] > 0.5, "Delayed pulse not found at expected position"

def test_volume_scale():
    sig = np.ones(100)
    mv  = MasterVolume()
    mv.set_volume(0.5)
    out = mv.process(sig)
    assert np.allclose(out, 0.5)
```

### 13.4 Running Tests

```bash
# Run all tests
python -m pytest tests/ -v

# Run a specific file
python -m pytest tests/test_effects.py -v

# Run one test
python -m pytest tests/test_effects.py::test_lpf_attenuates_high_freq -v
```

### 13.5 A Golden-Check Test

A golden check generates a block of audio and verifies its statistical properties fall within expected bounds. This catches accidental regressions — for example if you change the wavetable normalization and the RMS level changes.

```python
def test_rms_level_reasonable():
    """Single sine voice should have RMS around 0.35 during sustain."""
    from src.voice import Voice
    v   = Voice(sample_rate=SR, frequency=440, velocity=127,
                attack=0.001, decay=0.001, sustain=1.0, release=0.3)
    v.generate_samples(int(SR * 0.01))   # skip attack/decay
    block = v.generate_samples(2048)
    rms   = np.sqrt(np.mean(block ** 2))
    # Sine wave RMS = amplitude × 1/√2 ≈ 0.707
    assert 0.3 < rms < 0.8, f"Unexpected RMS: {rms:.3f}"
```

---

\newpage

## 14. Where to Go Next

You have now built a complete polyphonic software synthesizer with:

- **Additive synthesis** (16-harmonic wavetable oscillators)
- **ADSR envelopes** with smooth retrigger
- **Voice management** with polyphony up to 16 voices
- **DSP effects chain** (LPF, reverb, delay, bitcrusher, chorus)
- **Real-time audio output** via sounddevice callbacks
- **MIDI input** support
- **Tkinter GUI** with piano keyboard, knobs, and sliders
- **Automated tests** covering clipping, spectral purity, and effect timing

---

### Ideas to Explore

#### Sound Design
- **FM synthesis** — modulate one oscillator's frequency with another for metallic, bell-like tones
- **Subtractive synthesis** — start with a harmonically rich waveform (saw/square) and filter it
- **Noise oscillator** — add white noise to simulate breath, percussion, or pad textures
- **Unison detune** — spawn 2–8 slightly detuned copies of each voice for a thick "super saw" sound

#### DSP
- **High-pass filter** — use the same biquad math, changing coefficient formulas
- **Band-pass / notch filters** — for wah, telephone, or resonant effects
- **Envelope follower** — measure the RMS level and use it as a modulation source
- **LFO modulation** — route the LFO to filter cutoff, pitch, or amplitude (tremolo/vibrato)
- **Stereo panning per voice** — pan voices left/right based on pitch or oscillator index

#### Performance
- **C extension for inner loops** — the per-sample filter and reverb loops are the main bottleneck; rewrite in Cython or use `numba.njit`
- **Pre-allocated voice pool** — recycle Voice objects instead of allocating new ones on note-on
- **Lock-free event queue** — use `collections.deque` for MIDI events instead of relying on the GIL

#### Features
- **Preset save/load** — serialize ADSR and wavetable as JSON; load on startup
- **Polyphonic aftertouch** — vary vibrato or volume per note while held
- **MIDI learn** — map any MIDI CC to any synth parameter by entering "learn mode"
- **Arpeggiator** — cycle through held notes at a fixed BPM, synced to MIDI clock
- **Step sequencer** — store a pattern of notes and play them back automatically

#### Architecture
- **Plugin format** — wrap the synthesizer as a VST3 or CLAP plugin using the `dawdreamer` or `pedalboard` libraries
- **Web frontend** — expose the synthesizer over WebSockets and build a browser GUI

---

### Further Reading

| Topic | Resource |
|---|---|
| DSP fundamentals | *The Scientist and Engineer's Guide to Digital Signal Processing* — Steven Smith (free online) |
| Filter design | *Audio EQ Cookbook* — Robert Bristow-Johnson (1994, widely available) |
| Freeverb algorithm | Jezar at Dreampoint, 1999 (search "Freeverb source code") |
| MIDI specification | MIDI Association official spec at midi.org |
| Python audio | `sounddevice` documentation: python-sounddevice.readthedocs.io |
| Synth architecture | *Designing Software Synthesizer Plug-Ins in C++* — Will Pirkle |

---

### Module Reference (Quick Lookup)

| Module | Class | Key method |
|---|---|---|
| `voice.py` | `Voice` | `generate_samples(n)` |
| `synthesizer.py` | `Synthesizer` | `generate_audio(n)` |
| `effects.py` | `LowPassFilter` | `process(signal)` |
| `effects.py` | `Reverb` | `process(signal)` |
| `effects.py` | `Delay` | `process(signal)` |
| `effects.py` | `Bitcrusher` | `process(signal)` |
| `effects.py` | `Chorus` | `process(signal)` → stereo |
| `audio_engine.py` | `AudioEngine` | `start()`, `stop()` |
| `midi_handler.py` | `MIDIHandler` | `open_port()`, `start()` |
| `piano_gui.py` | `PianoGUI` | `update_meter(db)` |

---

*End of course — happy synthesizing.*
