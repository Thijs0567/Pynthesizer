# Building a Software Synthesizer in Python

*A short course in digital audio synthesis, from first principles to a working polyphonic instrument.*

---

## Table of Contents

1. [Introduction](#1-introduction)
2. [Digital Audio Foundations](#2-digital-audio-foundations)
3. [System Architecture](#3-system-architecture)
4. [The Real-Time Audio Engine](#4-the-real-time-audio-engine)
5. [The Oscillator: Additive Wavetable Synthesis](#5-the-oscillator-additive-wavetable-synthesis)
6. [The ADSR Envelope](#6-the-adsr-envelope)
7. [Polyphony and Voice Management](#7-polyphony-and-voice-management)
8. [MIDI Input](#8-midi-input)
9. [Dynamics: Compression and Limiting](#9-dynamics-compression-and-limiting)
10. [The Effects Chain](#10-the-effects-chain)
11. [Putting It Together: Signal Flow](#11-putting-it-together-signal-flow)
12. [The Graphical Interface](#12-the-graphical-interface)
13. [Testing an Audio System](#13-testing-an-audio-system)
14. [Further Reading](#14-further-reading)

---

## 1. Introduction

A **synthesizer** is an instrument that generates sound electronically rather than acoustically. A *software* synthesizer does this in code: it produces a stream of numbers that, when sent to a digital-to-analog converter (DAC), become an audible waveform.

This course walks through the design of a small but complete polyphonic synthesizer written in Python. By the end, you will understand:

- How digital audio is represented and streamed in real time.
- How to synthesize periodic waveforms from mathematical building blocks.
- How to shape a sound over time using envelopes and filters.
- How to play many notes at once without clipping or glitching.
- How classic effects (delay, reverb, chorus, bitcrusher) actually work.

The reference codebase is organised around clear boundaries: oscillator, voice, synthesizer, effects, MIDI, audio I/O, and GUI. We will treat each as a small, self-contained topic.

> **Prerequisites:** comfortable Python, basic NumPy, a willingness to think in terms of signals and time.

---

## 2. Digital Audio Foundations

### 2.1 Sampling

A continuous-time audio signal $x(t)$ is turned into a sequence of samples by measuring its amplitude at regular intervals:

$$
x[n] = x(n \cdot T_s), \qquad T_s = \frac{1}{f_s}
$$

Here $f_s$ is the **sample rate** in hertz. This project uses $f_s = 44{,}100$ Hz — the CD standard — so one second of audio is an array of $44{,}100$ floating-point numbers per channel.

### 2.2 The Nyquist Limit

The Nyquist–Shannon theorem states that a signal can be perfectly reconstructed only if every frequency it contains is below

$$
f_N = \frac{f_s}{2}.
$$

At 44.1 kHz, that upper bound is 22.05 kHz — comfortably above human hearing (~20 kHz). Frequencies above $f_N$ cause **aliasing**: they fold back into the audible band as spurious tones. This will shape several design choices later.

### 2.3 Blocks and Latency

Audio is processed in **blocks** (also called buffers) of $N$ samples. Larger blocks are safer against glitches but introduce more latency:

$$
\text{latency} \approx \frac{N}{f_s}.
$$

Our synth uses $N = 2048$, giving about 46 ms — responsive enough for playing, loose enough to run comfortably in Python.

### 2.4 Amplitude Range

Samples are stored as 32-bit floats in the range $[-1, +1]$. Anything outside that range is hard-clipped by the output driver, producing a harsh distortion. Preventing clipping is a recurring theme.

---

## 3. System Architecture

The synthesizer is split into modules with a single responsibility each:

```
┌──────────────┐    ┌───────────────┐    ┌───────────────┐
│  GUI / MIDI  │──▶│ Synthesizer   │──▶│  Audio Engine │──▶ Speakers
│  (events)    │    │ (voices+FX)   │    │  (callback)   │
└──────────────┘    └───────────────┘    └───────────────┘
                           │
                           ▼
                    ┌──────────────┐
                    │ Voice Pool   │  one Voice per note
                    │ (osc + env)  │
                    └──────────────┘
```

| Module           | Role                                                           |
|------------------|----------------------------------------------------------------|
| `audio_engine.py`| Streams samples to the sound card via `sounddevice`.           |
| `synthesizer.py` | Manages voices, mixes them, runs dynamics and effects.         |
| `voice.py`       | A single note: oscillator plus envelope.                       |
| `effects.py`     | Filter, reverb, delay, chorus, bitcrusher.                     |
| `midi_handler.py`| Polls a MIDI port in a background thread.                      |
| `piano_gui.py`   | Tkinter piano, knobs, and sliders.                             |

Design principles worth noting:

- **Pure DSP is isolated.** Nothing in `voice.py` or `effects.py` knows about Tkinter or MIDI.
- **The audio thread allocates nothing.** Every buffer is pre-created in `__init__`.
- **Data flow is explicit.** Parameter changes enter through small setter methods, never via hidden globals.

---

## 4. The Real-Time Audio Engine

### 4.1 The Callback Model

Modern audio libraries are **pull-based**: the operating system asks your code for the next block of samples at regular intervals. You register a callback; the driver calls it from a high-priority thread.

```python
stream = sd.OutputStream(
    samplerate=44100, channels=2, blocksize=2048,
    callback=self._stream_callback, latency='low',
)
```

Inside the callback, the contract is simple but strict:

1. Produce exactly `frames` samples.
2. Return quickly — if you overrun the block interval, you get an audible drop-out.
3. Never allocate, never block on I/O, never take locks if you can avoid it.

Our engine forwards the request to the synthesizer:

```python
def _stream_callback(self, outdata, frames, time, status):
    audio_data = self.audio_callback(frames)     # (frames, 2)
    outdata[:] = audio_data
```

### 4.2 Why Blocks?

Processing one sample at a time in Python is prohibitively slow because of per-sample interpreter overhead. Working on arrays of $N$ samples allows NumPy to vectorise the inner loops in C. The trick throughout this project is to **push as much work as possible into NumPy**, keeping Python loops only where per-sample state makes them unavoidable (limiters, filters, delay lines).

---

## 5. The Oscillator: Additive Wavetable Synthesis

### 5.1 The Sine Wave, Our Atom

Every periodic sound can be built from sine waves. A single sine at frequency $f$ and amplitude $A$ is

$$
x[n] = A \sin(2\pi f n / f_s).
$$

To avoid accumulating floating-point error over long notes, we track a running **phase** $\varphi$ in radians and advance it each sample by

$$
\Delta\varphi = \frac{2\pi f}{f_s}.
$$

### 5.2 Fourier's Idea: Building Any Waveform

The Fourier series tells us that a periodic waveform is a sum of harmonics — integer multiples of a fundamental:

$$
x[n] = \sum_{k=1}^{K} a_k \sin(k \cdot 2\pi f n / f_s).
$$

Here $a_k$ is the amplitude of the $k$-th harmonic. The classical waveforms correspond to specific coefficients:

| Waveform | Harmonics present | $a_k$                                       |
|----------|-------------------|---------------------------------------------|
| Sine     | 1 only            | $a_1 = 1$                                   |
| Sawtooth | all               | $a_k = 1/k$                                 |
| Square   | odd               | $a_k = 1/k$ for odd $k$, 0 otherwise        |
| Triangle | odd, alternating  | $a_k = (-1)^{(k-1)/2}/k^2$ for odd $k$      |

```
  Sine           Saw            Square          Triangle
   ∿              ⩘              ⊓⊔              △▽
```

We store 16 harmonics, so every sound is a weighted sum of up to 16 sines. This is called **additive synthesis**.

### 5.3 The Oscillator in Code

The heart of `Voice.generate_samples` is this block-vectorised sum:

```python
phase_inc = 2.0 * np.pi * self.frequency / self.sample_rate
phases    = self.phase + indices * phase_inc          # (N,)
osc[:]    = 0.0
for k in range(16):
    if wt[k] != 0.0:
        osc += wt[k] * np.sin((k + 1) * phases)
```

Each iteration adds one harmonic to the block. The `if` skips harmonics with zero amplitude, which is the common case for most presets.

### 5.4 MIDI Note to Frequency

The equal-tempered scale divides the octave into 12 equal ratios. With A4 = 440 Hz as reference (MIDI note 69):

$$
f(n) = 440 \cdot 2^{(n - 69)/12}.
$$

```python
return 440.0 * (2 ** ((note - 69) / 12.0))
```

### 5.5 Aliasing Caveat

Because we generate harmonics up to the 16th, a note at fundamental $f$ has partials as high as $16f$. For a note at 2 kHz, the 16th harmonic sits at 32 kHz — above Nyquist. In a production synth we would band-limit the sum; in this educational project we accept mild aliasing for the highest notes in exchange for simplicity.

---

## 6. The ADSR Envelope

A raw oscillator starts and stops abruptly, producing a click. Real instruments fade in and out. The classic four-stage model is **ADSR**:

```
       /\
      /  \___________
     /               \
    /                 \
   /                   \___
  A   D     S           R
```

- **Attack (A):** time to rise from 0 to 1.
- **Decay (D):** time to fall from 1 to the sustain level.
- **Sustain (S):** steady level held while the key is down (0–1, a *level*, not a time).
- **Release (R):** time to fall from the current level to 0 after key-off.

### 6.1 Mathematical Form

Let $t$ be the time since note-on and $t_{\text{off}}$ the time of note-off. Then

$$
\text{env}(t) =
\begin{cases}
\dfrac{t}{A}, & 0 \le t < A \\[4pt]
1 - (1 - S)\,\dfrac{t - A}{D}, & A \le t < A + D \\[4pt]
S, & t \ge A + D \text{ and key down} \\[4pt]
L_r \cdot \left(1 - \dfrac{t - t_{\text{off}}}{R}\right), & t > t_{\text{off}}
\end{cases}
$$

where $L_r$ is the envelope level *at the instant of key-off*. Capturing $L_r$ avoids a discontinuity if the key is released mid-attack or mid-decay.

### 6.2 Smooth Retriggering

If a key is re-pressed while its previous note is still releasing, jumping the envelope back to 0 would produce a click. We capture the current level and restart attack from there:

```python
def retrigger(self, velocity):
    self._retrigger_level = self._get_envelope_value()
    self.is_releasing = False
    self.time = 0.0
```

The attack formula is generalised so it starts from this captured level rather than from zero, eliminating the click.

### 6.3 Vectorising

The envelope is computed over the entire block using `np.where`, avoiding per-sample Python loops:

```python
env = np.where(
    t < atk_end,
    rl + (1 - rl) * t / atk_end,
    np.where(t < dec_end,
             1 - (1 - S) * (t - atk_end) / D,
             S),
)
```

---

## 7. Polyphony and Voice Management

### 7.1 What Is a Voice?

A **voice** is one playing note: its own oscillator phase, envelope state, and frequency. Polyphony means running many voices in parallel and summing their outputs. Our synth allows up to 16 simultaneous voices.

```python
self.active_voices: Dict[int, Voice] = {}   # MIDI note → Voice
```

### 7.2 Voice Stealing

When a 17th note arrives, one voice must go. We use the simplest fair policy — **oldest first**:

```python
if len(self.active_voices) >= self.max_voices:
    oldest = min(self.active_voices,
                 key=lambda n: self.active_voices[n].creation_time)
    del self.active_voices[oldest]
```

### 7.3 Summing Voices Without Clipping

Naively adding $V$ voices of amplitude 1 gives a signal up to amplitude $V$ — catastrophic clipping. Dividing by $V$ is wrong too: a single loud note would sound quiet. The perceptual fix is to scale by the **square root of the number of active voices**, which matches the way uncorrelated signals add in energy rather than amplitude:

$$
g = \frac{1}{\sqrt{\max(1, \sum_i \text{env}_i(t))}}.
$$

This produces constant perceived loudness whether one or sixteen notes are active. The scale is smoothed with a 50 ms time constant so that voices fading through release do not pump the gain.

```python
target = 1.0 / np.sqrt(max(env_sum, 1.0))
self._mix_scale = smooth * self._mix_scale + (1 - smooth) * target
output *= self._mix_scale
```

### 7.4 Pitch Bend

A pitch bend wheel sends a 14-bit value in $[-8192, +8191]$. For a bend range of $B$ semitones,

$$
f' = f \cdot 2^{(v/8192)\,B/12}.
$$

Every active voice has its frequency re-computed on each bend message.

---

## 8. MIDI Input

MIDI is a compact byte-stream protocol originating in 1983. We care about three message types:

| Message        | Payload                      | Action                       |
|----------------|------------------------------|------------------------------|
| `note_on`      | note (0–127), velocity (0–127)| Start a voice               |
| `note_off`     | note                         | Trigger release              |
| `pitchwheel`   | value $\in [-8192, 8191]$    | Retune all active voices     |

A `note_on` with velocity 0 is, by historical convention, a `note_off` in disguise — we handle that.

MIDI polling runs in a **separate thread** so that audio is never stalled waiting for a message:

```python
self.thread = threading.Thread(target=self._poll_midi, daemon=True)
```

The callbacks themselves just mutate the dictionary of active voices — a tiny critical section that is safe in practice at the scale of a single user playing.

---

## 9. Dynamics: Compression and Limiting

Sixteen voices produce a much larger peak than one. Even with $\sqrt{N}$ scaling the occasional chord stack can still reach the ceiling. We protect the output with a two-stage dynamics processor.

### 9.1 Stage 1: RMS Compressor

A compressor reduces gain when the signal is loud. The metric is the **root-mean-square** level over a short window,

$$
\text{RMS} = \sqrt{\frac{1}{N}\sum_{n=0}^{N-1} x[n]^2},
$$

converted to decibels $L_{\text{dB}} = 20 \log_{10}(\text{RMS})$. With threshold $T$, ratio $R$, and a soft-knee width $W$, the gain reduction is:

$$
G_{\text{dB}}(L) =
\begin{cases}
0, & L < T - W/2 \\[4pt]
\dfrac{(1/R - 1)\,(L - T + W/2)^2}{2W}, & |L - T| \le W/2 \\[4pt]
(1/R - 1)\,(L - T), & L > T + W/2
\end{cases}
$$

Our defaults: $T = -3$ dB, $R = 4{:}1$, $W = 6$ dB. The quadratic middle branch is the **soft knee** — it curves smoothly between "no compression" and "full compression" instead of kinking sharply.

A first-order smoother tracks both the RMS envelope and the gain so that the compressor does not flap on every transient. Attack and release time constants are converted to one-pole coefficients:

$$
\alpha = \exp\!\left(-\frac{1}{\tau\,f_s}\right),
$$

with $\tau_{\text{att}} = 30$ ms and $\tau_{\text{rel}} = 200$ ms.

### 9.2 Stage 2: Peak Limiter

The RMS compressor reacts to *average* level, not to instantaneous peaks. A sine wave has a 3 dB crest factor; chords have more. A separate per-sample **brickwall limiter** ensures nothing exceeds a hard ceiling of 0.90:

```python
for i in range(N):
    x = compressed[i]
    if abs(x) * lim_gain > thresh:
        lim_gain = thresh / (abs(x) + 1e-30)   # instant attack
    else:
        lim_gain = rel * lim_gain + (1 - rel)   # exponential release
    out[i] = x * lim_gain
```

The attack is instantaneous (gain is set to exactly the ratio that would bring this sample to the threshold); the release is a one-pole smoother. An earlier block-based version produced a ~690 Hz buzz on note onset because the gain changed in steps; going per-sample fixed it.

---

## 10. The Effects Chain

All effects share the same interface: a `process(signal) → signal` method and setter methods for their parameters. Buffers are pre-allocated; no per-block allocations.

### 10.1 Biquad Low-Pass Filter

A **biquad** is a second-order IIR filter, the workhorse of audio DSP:

$$
y[n] = b_0\,x[n] + b_1\,x[n{-}1] + b_2\,x[n{-}2] - a_1\,y[n{-}1] - a_2\,y[n{-}2].
$$

For a low-pass at cutoff $f_c$ with quality $Q$, the Robert Bristow-Johnson cookbook gives:

$$
\omega_0 = 2\pi f_c / f_s, \qquad \alpha = \sin(\omega_0)/(2Q)
$$

$$
b_0 = b_2 = \frac{1 - \cos\omega_0}{2}, \quad b_1 = 1 - \cos\omega_0
$$

$$
a_0 = 1 + \alpha, \quad a_1 = -2\cos\omega_0, \quad a_2 = 1 - \alpha
$$

and all coefficients are divided by $a_0$ to normalise. The filter implementation uses the **Direct Form II Transposed** structure, which carries two state variables $z_1, z_2$ across blocks.

Visually, the magnitude response looks like:

```
|H(f)|
  1 ─┐_____________
      \
       \  ← resonance hump when Q > 0.707
        \______
              ‾‾‾‾ ─── (−12 dB/octave slope above f_c)
       f_c                               f
```

### 10.2 Digital Delay

A delay line is a circular buffer. A write pointer moves forward; a read pointer lags behind by $D$ samples.

$$
y[n] = (1 - w)\,x[n] + w \cdot d[n], \qquad d[n] = x[n - D] + f \cdot d[n - D]
$$

where $f$ is the **feedback** (echoes feeding back into themselves) and $w$ the **wet/dry mix**. With $f = 0.4$ and a 250 ms delay, you get classic slap-back echoes.

```
 input ──┬────────────────────────────▶ dry
         │
         ▼
      [delay buffer, D samples] ──┬──▶ wet
         ▲                        │
         └──── × f ◀───────────────┘
```

### 10.3 Reverb (Freeverb Topology)

A reverb simulates the dense, diffuse echoes of a room. Freeverb, by Jezar at Dreampoint, uses the classic Schroeder architecture:

- **Four parallel comb filters** give the long decay.
- **Two series all-pass filters** smear echoes into a dense tail.
- **Damping** attenuates high frequencies inside each comb's feedback loop, modelling air absorption.

Comb lengths (1116, 1188, 1277, 1356 samples at 44.1 kHz) are deliberately co-prime, so the echoes do not line up and you avoid metallic ringing.

Per comb, the update is:

$$
y[n] = \text{buf}[p], \quad \text{filt}[n] = y[n]\,(1-d) + \text{filt}[n-1]\,d, \quad \text{buf}[p] = x[n] + f\cdot\text{filt}[n]
$$

### 10.4 Chorus

Chorus thickens a sound by mixing in a copy through a **slowly time-varying delay line**. A low-frequency oscillator (LFO, 0.05–8 Hz) modulates the delay around a 20 ms centre:

$$
D(t) = D_0 + d \cdot \sin(2\pi f_{\text{lfo}} t).
$$

The fractional delay is read with linear interpolation between adjacent buffer samples. To create stereo width, the left and right channels use LFOs that are 180° out of phase: one is getting longer while the other is getting shorter. The output is stereo.

### 10.5 Bitcrusher

The bitcrusher simulates the grit of early samplers by degrading the signal in two ways:

**Bit-depth reduction.** With $B$ bits there are $2^{B-1}$ positive levels. Quantise each sample to the nearest level:

$$
\hat x = \Delta \cdot \left\lfloor \frac{x}{\Delta} + 0.5 \right\rfloor, \qquad \Delta = \frac{1}{2^{B-1}}.
$$

**Sample-rate reduction.** Hold every input sample for $M$ output samples (sample-and-hold). This creates aliased harmonics that give the classic "lo-fi" crunch.

---

## 11. Putting It Together: Signal Flow

Every audio block traverses this chain:

```
MIDI / GUI / QWERTY
        │
        ▼
   ┌─────────────┐
   │  Voice 1    │──┐
   │  Voice 2    │──┤
   │    ...      │──┼─ Σ ─▶ √N normalise ─▶ Master Volume ─▶ LPF
   │  Voice 16   │──┘                                          │
   └─────────────┘                                              ▼
                                                          Reverb ─▶ Delay
                                                                     │
                                                                     ▼
                                                         Compressor + Limiter
                                                                     │
                                                                     ▼
                                                                Bitcrusher
                                                                     │
                                                                     ▼
                                                        Chorus (mono → stereo)
                                                                     │
                                                                     ▼
                                                                 Speakers
```

The order is musically motivated:

- **LPF before reverb/delay** so the room response follows a tone-shaped signal.
- **Compressor after the ambience effects** so chord build-ups from reverb tails are caught.
- **Chorus last** because it produces the final stereo image; upstream effects remain mono.

In code, the full chain is just a sequence of method calls:

```python
output = self._volume.process(output)
output = self._lpf.process(output)
output = self._reverb.process(output)
output = self._delay.process(output)
output = self._apply_compression(output)
output = self._bitcrusher.process(output)
stereo = self._chorus.process(output)
```

---

## 12. The Graphical Interface

The GUI is a thin controller layer on top of the synth engine. It uses Tkinter for portability. The critical design rule: the GUI **never** touches the audio thread directly. It calls setter methods on the synth, which mutate small values read by the next audio block.

Main GUI elements:

- **Piano keyboard.** Three octaves, mouse + QWERTY + MIDI input, with visual highlight on pressed keys.
- **Harmonic sliders.** Sixteen vertical sliders, one per harmonic — a direct UI for the additive engine. Clicking anywhere on a track jumps to that value.
- **Waveform presets.** Buttons for sine, saw, square, triangle, semisine. Each generates its slider configuration from the mathematical formula in the table above:

```python
WAVE_PRESETS = {
    'sine':     lambda k: 1.0 if k == 0 else 0.0,
    'saw':      lambda k: 1.0 / (k + 1),
    'square':   lambda k: (1.0 / (k + 1)) if (k % 2 == 0) else 0.0,
    'triangle': lambda k: ((-1) ** (k // 2) / (k + 1) ** 2) if (k % 2 == 0) else 0.0,
    'semisine': lambda k: (1.0 / (k + 1)) if (k % 2 == 1) else (1.0 if k == 0 else 0.0),
}
```

- **Knobs for every effect parameter**, and ADSR sliders.
- **Level meter.** Logarithmic dB readout, updated at 20 Hz in a daemon thread that reads a shared dictionary populated by the audio callback. Displaying audio state never stalls audio generation.

---

## 13. Testing an Audio System

Audio code is famously tricky because the ground truth is perceptual. A few principles keep tests tractable:

**Determinism.** Set a known sample rate, a known block size, and a known waveform. Anything stochastic in the DSP should be seeded.

**Unit tests for pure functions.**
- `note_to_frequency(69) == 440.0`.
- A 440 Hz sine played for 1 s has RMS close to $1/\sqrt{2}$.
- ADSR at $t = A$ is exactly 1.0; at $t = A + D$ is exactly $S$.

**Property tests for invariants.**
- Envelope is never negative and never exceeds 1.
- Limiter output magnitude never exceeds threshold.
- Delay buffer wraps correctly across block boundaries.

**Golden checks for effects.**
- Send a click through the reverb; the energy of the tail decays monotonically.
- Send a sine through the LPF above cutoff; output amplitude is reduced by the expected dB.

The project's `tests/` directory contains `test_synthesis.py`, `test_effects.py`, and `test_audio_quality.py` following this pattern.

---

## 14. Further Reading

- **Julius O. Smith — *Introduction to Digital Filters*.** The canonical introduction to biquads, state-variable filters, and everything IIR.
- **Will Pirkle — *Designing Software Synthesizer Plug-Ins in C++*.** Practical, exhaustive, closest in spirit to this project.
- **Robert Bristow-Johnson — *Audio EQ Cookbook*.** The one-page reference for biquad coefficients.
- **Jezar at Dreampoint — *Freeverb* source.** Short, public-domain, and the basis of nearly every small reverb in use today.
- **The MIDI 1.0 Specification.** Still the baseline for nearly all controllers.

### Extensions to try

1. A **band-limited oscillator** using polyBLEP or wavetables for aliasing-free saws.
2. A **state-variable filter** with simultaneous low-, band-, and high-pass outputs.
3. **Modulation routing**: an LFO that can be assigned to pitch, filter cutoff, or amplitude.
4. **Preset save/load** using a JSON file.
5. **Unison** per voice: multiple detuned oscillators stacked into one note.

---

*End of course. Every concept above is implemented in under 3,000 lines of Python — proof that a rich, playable instrument can be built from a small set of clear mathematical ideas.*
