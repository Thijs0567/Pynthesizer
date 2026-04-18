"""Deterministic tests for src/effects.py. No audio device required."""
import sys
import numpy as np
import pytest

sys.path.insert(0, '.')
from src.effects import MasterVolume, LowPassFilter, Reverb, Delay

SR = 44100
BLOCK = 2048


# ── MasterVolume ──────────────────────────────────────────────────────────────

def test_volume_silence():
    mv = MasterVolume(0.8)
    out = mv.process(np.zeros(BLOCK, dtype=np.float32))
    assert np.all(out == 0.0)

def test_volume_scale():
    mv = MasterVolume(0.5)
    out = mv.process(np.ones(BLOCK, dtype=np.float32))
    assert np.allclose(out, 0.5, atol=1e-6)

def test_volume_zero():
    mv = MasterVolume(0.0)
    out = mv.process(np.random.randn(BLOCK).astype(np.float32))
    assert np.all(out == 0.0)

def test_volume_clamp_high():
    mv = MasterVolume(initial_volume=2.0)
    assert mv.volume <= 1.0

def test_volume_clamp_low():
    mv = MasterVolume(initial_volume=-1.0)
    assert mv.volume >= 0.0


# ── LowPassFilter ─────────────────────────────────────────────────────────────

def test_lpf_silence():
    lpf = LowPassFilter(SR)
    out = lpf.process(np.zeros(BLOCK, dtype=np.float32))
    assert np.allclose(out, 0.0, atol=1e-9)

def test_lpf_dc_passthrough():
    lpf = LowPassFilter(SR, cutoff_hz=1000.0, q=0.707)
    dc = np.ones(BLOCK, dtype=np.float32)
    for _ in range(20):
        out = lpf.process(dc)
    # DC gain of a low-pass filter is 1.0
    assert np.allclose(out[-BLOCK // 4:], 1.0, atol=0.01)

def test_lpf_high_freq_attenuated():
    lpf = LowPassFilter(SR, cutoff_hz=500.0, q=0.707)
    t = np.arange(BLOCK) / SR
    tone = np.sin(2 * np.pi * 10000 * t).astype(np.float32)
    for _ in range(10):
        out = lpf.process(tone)
    rms_in  = float(np.sqrt(np.mean(tone ** 2)))
    rms_out = float(np.sqrt(np.mean(out ** 2)))
    assert rms_out < rms_in * 0.1, f"expected >20 dB attenuation, got {20*np.log10(rms_out/rms_in):.1f} dB"

def test_lpf_state_continuity():
    """Filter state persists between calls: split processing equals full-block."""
    lpf_full = LowPassFilter(SR, cutoff_hz=2000.0, q=1.0)
    lpf_split = LowPassFilter(SR, cutoff_hz=2000.0, q=1.0)
    t = np.arange(BLOCK * 2) / SR
    tone = np.sin(2 * np.pi * 1000 * t).astype(np.float32)

    out_full = lpf_full.process(tone).copy()
    out1 = lpf_split.process(tone[:BLOCK]).copy()
    out2 = lpf_split.process(tone[BLOCK:]).copy()
    assert np.allclose(out_full, np.concatenate([out1, out2]), atol=1e-9)

def test_lpf_reset_state():
    lpf = LowPassFilter(SR, cutoff_hz=2000.0, q=1.0)
    lpf.process(np.sin(np.arange(BLOCK) * 2 * np.pi * 1000 / SR).astype(np.float32))
    lpf.reset_state()
    assert lpf._z1 == 0.0 and lpf._z2 == 0.0

def test_lpf_returns_correct_length():
    lpf = LowPassFilter(SR)
    for n in (1, 100, BLOCK):
        out = lpf.process(np.zeros(n, dtype=np.float32))
        assert len(out) == n


# ── Reverb ────────────────────────────────────────────────────────────────────

def test_reverb_silence():
    rev = Reverb(SR, wet=1.0)
    out = rev.process(np.zeros(BLOCK, dtype=np.float32))
    assert np.all(out == 0.0)

def test_reverb_wet_zero():
    rev = Reverb(SR, wet=0.0)
    sig = (np.random.randn(BLOCK) * 0.5).astype(np.float32)
    out = rev.process(sig.copy())
    assert np.allclose(out, sig, atol=1e-5)

def test_reverb_decay():
    rev = Reverb(SR, room_size=0.5, damping=0.5, wet=1.0)
    impulse = np.zeros(BLOCK, dtype=np.float32)
    impulse[0] = 1.0
    rev.process(impulse)
    silence = np.zeros(BLOCK, dtype=np.float32)
    for _ in range(int(4 * SR / BLOCK)):
        tail = rev.process(silence)
    assert float(np.max(np.abs(tail))) < 0.01

def test_reverb_delay_lengths_scale_with_sr():
    rev_441 = Reverb(44100)
    rev_480 = Reverb(48000)
    ratio = len(rev_480._comb_bufs[0]) / len(rev_441._comb_bufs[0])
    assert abs(ratio - 48000 / 44100) < 0.02

def test_reverb_reset():
    rev = Reverb(SR, wet=1.0)
    impulse = np.zeros(BLOCK, dtype=np.float32)
    impulse[0] = 1.0
    rev.process(impulse)
    rev.reset_state()
    out = rev.process(np.zeros(BLOCK, dtype=np.float32))
    assert np.all(out == 0.0)


# ── Delay ─────────────────────────────────────────────────────────────────────

def test_delay_silence():
    dly = Delay(SR, wet=1.0)
    out = dly.process(np.zeros(BLOCK, dtype=np.float32))
    assert np.all(out == 0.0)

def test_delay_wet_zero():
    dly = Delay(SR, wet=0.0, feedback=0.0)
    sig = (np.random.randn(BLOCK) * 0.5).astype(np.float32)
    out = dly.process(sig.copy())
    assert np.allclose(out, sig, atol=1e-5)

def test_delay_timing():
    delay_ms = 100.0
    delay_samples = int(delay_ms * SR / 1000)
    dly = Delay(SR, delay_ms=delay_ms, feedback=0.0, wet=1.0)

    total = delay_samples + BLOCK
    inp = np.zeros(total, dtype=np.float32)
    inp[0] = 1.0
    result = np.zeros(total, dtype=np.float32)

    for i in range(0, total, BLOCK):
        chunk = inp[i:i + BLOCK]
        if len(chunk) < BLOCK:
            chunk = np.pad(chunk, (0, BLOCK - len(chunk)))
        out = dly.process(chunk)
        end = min(i + BLOCK, total)
        result[i:end] = out[:end - i]

    assert abs(result[delay_samples]) > 0.9
    assert np.max(np.abs(result[:delay_samples])) < 0.01

def test_delay_feedback_stability():
    dly = Delay(SR, delay_ms=50.0, feedback=0.9, wet=0.5)
    impulse = np.zeros(BLOCK, dtype=np.float32)
    impulse[0] = 1.0
    dly.process(impulse)
    silence = np.zeros(BLOCK, dtype=np.float32)
    for _ in range(int(5 * SR / BLOCK)):
        out = dly.process(silence)
    assert np.max(np.abs(out)) < 10.0

def test_delay_feedback_clamped():
    dly = Delay(SR)
    dly.set_feedback(1.5)
    assert dly._feedback <= 0.9

def test_delay_reset():
    dly = Delay(SR, delay_ms=100.0, feedback=0.5, wet=0.5)
    impulse = np.zeros(BLOCK, dtype=np.float32)
    impulse[0] = 1.0
    dly.process(impulse)
    dly.reset_state()
    out = dly.process(np.zeros(BLOCK, dtype=np.float32))
    assert np.all(out == 0.0)
