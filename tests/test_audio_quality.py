"""
DSP property tests: clipping, RMS, phase continuity, spectral purity, effect chain.
No audio device required.
"""
import sys
import os
import pytest
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.synthesizer import Synthesizer
from src.voice import Voice
from src.effects import MasterVolume, LowPassFilter, Reverb, Delay

SR = 44100
BLOCK = 2048


# ── helpers ───────────────────────────────────────────────────────────────────

def _warm_up(synth: Synthesizer, seconds: float = 0.5) -> None:
    n = max(1, int(seconds * SR / BLOCK))
    for _ in range(n):
        synth.generate_audio(BLOCK)


def _rms(samples: np.ndarray) -> float:
    return float(np.sqrt(np.mean(samples.astype(np.float64) ** 2)))


# ── 1. Clipping: no samples exceed ±1.0 ──────────────────────────────────────

@pytest.mark.parametrize("num_voices,velocity", [
    (1,  100),
    (4,  100),
    (8,  120),
    (16, 127),
])
def test_no_clipping(num_voices, velocity):
    synth = Synthesizer(SR, max_voices=num_voices)
    for i in range(num_voices):
        synth._on_note_on(60 + (i % 12), velocity)
    _warm_up(synth, 0.5)
    for _ in range(int(SR / BLOCK)):
        samples = synth.generate_audio(BLOCK)
        peak = float(np.max(np.abs(samples)))
        assert peak <= 1.0, (
            f"Clipping: peak={peak:.4f} with {num_voices} voices @ velocity={velocity}"
        )


# ── 2. RMS level per voice ────────────────────────────────────────────────────

@pytest.mark.parametrize("velocity", [64, 100, 127])
def test_rms_scales_with_velocity(velocity):
    """RMS must scale proportionally with velocity for a single voice."""
    synth = Synthesizer(SR)
    synth._on_note_on(69, velocity)   # A4 = 440 Hz
    _warm_up(synth, 0.3)              # settle into sustain
    rms = _rms(synth.generate_audio(BLOCK * 4))

    # Predicted: (vel/127) * sustain / sqrt(2) * master_volume
    sustain = synth.sustain
    volume  = synth._volume.volume
    expected = (velocity / 127) * sustain / np.sqrt(2) * volume
    # 50 % tolerance — compressor may ride the gain slightly
    assert 0.4 * expected < rms < 2.0 * expected, (
        f"velocity={velocity}: rms={rms:.4f}, expected≈{expected:.4f}"
    )


def test_rms_increases_with_voice_count():
    """More simultaneous voices should produce higher output RMS."""
    def rms_voices(n: int) -> float:
        synth = Synthesizer(SR, max_voices=n)
        for i in range(n):
            synth._on_note_on(60 + i, 80)
        _warm_up(synth, 0.5)
        return _rms(synth.generate_audio(BLOCK * 4))

    rms1 = rms_voices(1)
    rms4 = rms_voices(4)
    assert rms4 > rms1, (
        f"4 voices not louder than 1: rms1={rms1:.4f}, rms4={rms4:.4f}"
    )


# ── 3. Phase continuity on retrigger (no click) ───────────────────────────────

def test_retrigger_no_amplitude_jump_voice():
    """Envelope must start exactly at its previous level on retrigger."""
    voice = Voice(SR, frequency=440.0, velocity=100,
                  attack=0.5, decay=0.1, sustain=0.7, release=0.3)
    voice.generate_samples(int(0.65 * SR))  # advance past attack+decay into sustain

    pre  = voice.generate_samples(BLOCK)
    last = float(pre[-1])

    voice.retrigger(velocity=100)

    post  = voice.generate_samples(BLOCK)
    first = float(post[0])

    # Per-sample oscillator variation at 440 Hz, amplitude ≈ vel/127 * sustain
    max_step = 2 * np.pi * 440.0 / SR * (100 / 127) * 0.7   # ≈ 0.035
    jump = abs(first - last)
    assert jump <= 10 * max_step, (
        f"Retrigger discontinuity: jump={jump:.5f}, 10×step={10*max_step:.5f}"
    )


def test_retrigger_no_click_via_synthesizer():
    """Synthesizer-level retrigger must not produce a click."""
    synth = Synthesizer(SR)
    synth.set_adsr(attack=0.5, decay=0.1, sustain=0.7, release=0.3)
    synth._on_note_on(69, 100)
    _warm_up(synth, 0.65)           # reach sustain

    pre  = synth.generate_audio(BLOCK)
    last = float(pre[-1])

    synth._on_note_on(69, 100)      # retrigger

    post  = synth.generate_audio(BLOCK)
    first = float(post[0])

    jump = abs(first - last)
    assert jump < 0.15, f"Synth retrigger click: jump={jump:.5f}"


# ── 4. Spectral energy: fundamental matches MIDI note ─────────────────────────

@pytest.mark.parametrize("note,expected_hz", [
    (57, 220.0),
    (69, 440.0),
    (81, 880.0),
])
def test_sine_peak_frequency(note, expected_hz):
    voice = Voice(SR, frequency=expected_hz, velocity=127,
                  attack=0.001, decay=0.001, sustain=1.0, release=0.1)
    voice.generate_samples(int(0.1 * SR))   # skip attack transient

    n       = SR
    samples = voice.generate_samples(n)
    freqs   = np.fft.rfftfreq(n, 1.0 / SR)
    peak_hz = freqs[np.argmax(np.abs(np.fft.rfft(samples)))]

    assert abs(peak_hz - expected_hz) <= 1.0, (
        f"note={note}: peak={peak_hz:.2f} Hz, expected={expected_hz:.2f} Hz"
    )


def test_sine_harmonic_suppression():
    """Pure sine oscillator must have negligible 2nd-harmonic energy."""
    freq  = 440.0
    voice = Voice(SR, frequency=freq, velocity=127,
                  attack=0.001, decay=0.001, sustain=1.0, release=0.1)
    voice.generate_samples(int(0.1 * SR))

    n       = SR
    samples = voice.generate_samples(n)
    fft_mag = np.abs(np.fft.rfft(samples))
    freqs   = np.fft.rfftfreq(n, 1.0 / SR)

    fund_energy  = fft_mag[np.argmin(np.abs(freqs - freq))]
    harm2_energy = fft_mag[np.argmin(np.abs(freqs - 2 * freq))]

    assert harm2_energy < 0.01 * fund_energy, (
        f"2nd harmonic ratio: {harm2_energy / fund_energy:.4f} (limit 0.01)"
    )


# ── 5. Effect chain: measurable, expected changes ─────────────────────────────

def test_volume_zero_produces_silence():
    synth = Synthesizer(SR)
    synth.set_volume(0.0)
    synth._on_note_on(60, 100)
    _warm_up(synth, 0.3)
    samples = synth.generate_audio(BLOCK)
    assert np.allclose(samples, 0.0, atol=1e-6), (
        f"Volume=0 not silent: max={float(np.max(np.abs(samples))):.2e}"
    )


def test_volume_louder_at_higher_setting():
    def rms_at_vol(vol: float) -> float:
        synth = Synthesizer(SR)
        synth.set_volume(vol)
        synth._on_note_on(69, 100)
        _warm_up(synth, 0.3)
        return _rms(synth.generate_audio(BLOCK * 4))

    assert rms_at_vol(0.8) > rms_at_vol(0.2) * 1.5, "Volume has no measurable effect"


def test_lpf_attenuates_above_cutoff():
    """LPF at 300 Hz must strongly attenuate a 4186 Hz (C8) note."""
    def rms_with_cutoff(cutoff: float) -> float:
        synth = Synthesizer(SR)
        synth.set_lpf(cutoff, 0.707)
        synth._on_note_on(108, 100)   # C8 ≈ 4186 Hz
        _warm_up(synth, 0.3)
        return _rms(synth.generate_audio(BLOCK * 4))

    rms_filtered = rms_with_cutoff(300.0)
    rms_open     = rms_with_cutoff(20000.0)
    assert rms_open > rms_filtered * 5.0, (
        f"LPF ineffective: filtered={rms_filtered:.4f}, open={rms_open:.4f}"
    )


def test_reverb_tail_after_silence():
    """Reverb energy must persist after source voices are removed."""
    synth = Synthesizer(SR)
    synth.set_reverb(room_size=0.8, damping=0.3, wet=0.8)
    synth._on_note_on(60, 100)
    _warm_up(synth, 0.5)

    synth.active_voices.clear()   # silence source

    tail = np.concatenate([synth.generate_audio(BLOCK)
                           for _ in range(int(0.5 * SR / BLOCK))])
    assert _rms(tail) > 1e-3, f"No reverb tail: rms={_rms(tail):.2e}"


def test_delay_echo_at_correct_position():
    """Delay echo must appear exactly delay_ms samples after the input."""
    delay_ms      = 100.0
    delay_samples = int(delay_ms * SR / 1000)   # 4410

    dly     = Delay(SR, delay_ms=delay_ms, feedback=0.0, wet=1.0)
    silence = np.zeros(BLOCK, dtype=np.float32)
    impulse = silence.copy()
    impulse[0] = 1.0

    dly.process(impulse)   # feed impulse; write ptr now at BLOCK

    # Drive silence until the block that contains the echo
    samples_until_echo = delay_samples - BLOCK
    for _ in range(samples_until_echo // BLOCK):
        dly.process(silence)

    echo_block = dly.process(silence)
    echo_offset = samples_until_echo % BLOCK
    amplitude   = abs(float(echo_block[echo_offset]))
    assert amplitude > 0.5, (
        f"No echo at offset {echo_offset}: amplitude={amplitude:.4f}"
    )


def test_delay_feedback_bounded():
    """High-feedback delay must remain bounded over many seconds."""
    dly     = Delay(SR, delay_ms=50.0, feedback=0.9, wet=0.5)
    impulse = np.zeros(BLOCK, dtype=np.float32)
    impulse[0] = 0.5
    silence = np.zeros(BLOCK, dtype=np.float32)

    dly.process(impulse)
    for _ in range(int(5 * SR / BLOCK)):
        block = dly.process(silence)
        assert np.max(np.abs(block)) < 5.0, (
            f"Delay feedback explosion: peak={np.max(np.abs(block)):.2f}"
        )


# ── 6. Note-onset artifact: LPF must not cause transient on new voice ─────────

def _onset_jump(cutoff_hz: float, voice_count: int = 3) -> float:
    """Return the sample-level jump at the exact block boundary where a new voice starts."""
    synth = Synthesizer(SR, max_voices=voice_count + 1)
    synth.set_lpf(cutoff_hz, 0.707)
    synth.set_reverb(0.5, 0.5, 0.0)
    synth.set_delay(250.0, 0.4, 0.0)

    for i in range(voice_count):
        synth._on_note_on(60 + i * 4, 80)
    _warm_up(synth, 0.5)

    pre  = synth.generate_audio(BLOCK)
    synth._on_note_on(60 + voice_count * 4, 80)   # new voice
    post = synth.generate_audio(BLOCK)

    return abs(float(post[0]) - float(pre[-1]))


@pytest.mark.parametrize("voice_count", [1, 3, 7])
def test_lpf_no_onset_artifact(voice_count):
    """LPF with mid-range cutoff must not produce a larger block-boundary jump
    than the open (bypassed) case by more than a modest factor."""
    jump_open     = _onset_jump(20000.0, voice_count)
    jump_filtered = _onset_jump(1000.0,  voice_count)

    # Allow 5× slack: the new voice contributes at most ~0.001 amplitude in
    # sample 0 (attack=0.01 s → slope ≈ vel/127/441 per sample ≈ 0.0014).
    # Any larger jump is caused by filter state discontinuity, not the oscillator.
    tolerance = max(jump_open * 5.0, 0.05)
    assert jump_filtered <= tolerance, (
        f"voices={voice_count}: LPF onset artifact jump={jump_filtered:.5f}, "
        f"open={jump_open:.5f}, tolerance={tolerance:.5f}"
    )


def test_lpf_onset_does_not_grow_with_voices():
    """The onset artifact (if any) must not grow proportionally with voice count —
    that would indicate the LPF state is accumulating cross-voice interference."""
    jump_1  = _onset_jump(1000.0, voice_count=1)
    jump_7  = _onset_jump(1000.0, voice_count=7)

    # With 7 voices the mix is louder, so a proportional increase is expected,
    # but not an order-of-magnitude blow-up.
    assert jump_7 < jump_1 * 15.0, (
        f"Onset artifact scales badly: 1 voice={jump_1:.5f}, 7 voices={jump_7:.5f}"
    )


# ── 7. Limiter staircase: per-chunk constant gain must not create 690 Hz buzz ─

def test_limiter_no_staircase_on_sustained_sine():
    """Limiter must not produce 64-sample gain steps on a sustained above-threshold
    sine.  A staircase creates a ~690 Hz amplitude-modulation artifact."""
    synth = Synthesizer(SR)

    # 200 Hz sine at 1.5 amplitude — above limiter threshold (0.90) after mixing.
    N = BLOCK
    t = np.arange(N) / SR
    signal = (np.sin(2 * np.pi * 200 * t) * 1.5).astype(np.float32)

    # Settle compressor/limiter state over 5 blocks.
    for _ in range(5):
        synth._apply_compression(signal.copy())

    out = synth._apply_compression(signal.copy())

    # Output must not clip.
    peak = float(np.max(np.abs(out)))
    assert peak <= synth._lim_threshold + 0.01, f"Limiter not working: peak={peak:.4f}"

    # Sample-to-sample difference must stay within what a smooth sine allows.
    # For 200 Hz at threshold=0.90: max natural step = 2π·200·0.90/SR ≈ 0.026.
    # A 64-sample staircase produces steps ≈ 0.20+, orders of magnitude larger.
    max_diff = float(np.max(np.abs(np.diff(out.astype(np.float64)))))
    natural_max = 2.0 * np.pi * 200.0 * synth._lim_threshold / SR
    assert max_diff < natural_max * 5.0, (
        f"Staircase artifact: max_diff={max_diff:.5f}, "
        f"natural_limit={natural_max:.5f}, 5×={natural_max*5:.5f}"
    )


def test_limiter_no_onset_buzz_with_many_voices():
    """Triggering a new voice into a busy mix must not produce a ~690 Hz buzz
    from limiter gain steps.  Detect via spectral energy in 600-780 Hz band."""
    synth = Synthesizer(SR, max_voices=9)
    synth.set_reverb(0.5, 0.5, 0.0)
    synth.set_delay(250.0, 0.4, 0.0)

    for i in range(8):
        synth._on_note_on(60 + i * 3, 100)
    _warm_up(synth, 0.5)

    synth._on_note_on(60 + 8 * 3, 100)   # trigger 9th voice

    # Collect audio starting from the onset block.
    onset_audio = np.concatenate([synth.generate_audio(BLOCK) for _ in range(4)])

    n = len(onset_audio)
    fft_mag = np.abs(np.fft.rfft(onset_audio))
    freqs   = np.fft.rfftfreq(n, 1.0 / SR)

    # Staircase at SUB=64 samples → fundamental at SR/64 = 689.1 Hz.
    # Energy in the ±100 Hz band around 689 Hz should not dominate.
    total_energy = float(np.sum(fft_mag ** 2))
    buzz_mask    = (freqs >= 600) & (freqs <= 780)
    note_mask    = np.zeros(len(freqs), dtype=bool)
    for i in range(9):
        f0 = Synthesizer.note_to_frequency(60 + i * 3)
        note_mask |= (np.abs(freqs - f0) < 5.0)

    buzz_energy = float(np.sum(fft_mag[buzz_mask & ~note_mask] ** 2))
    # Buzz energy must be less than 5 % of total spectrum energy.
    assert buzz_energy < 0.05 * total_energy, (
        f"690 Hz buzz from limiter staircase: "
        f"buzz={buzz_energy:.2e}, total={total_energy:.2e}, "
        f"ratio={buzz_energy/total_energy:.3f}"
    )
