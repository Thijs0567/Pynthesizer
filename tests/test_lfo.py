"""Tests for the LFO / LFOBank modulation module."""
import math
import pytest

from src.lfo import LFO, LFOBank


def test_lfo_sine_phase_after_one_full_cycle():
    """Advancing an LFO at rate R for sample_rate/R samples returns to near sin(0)."""
    sr = 44100
    lfo = LFO(rate_hz=1.0, amplitude=1.0)
    # Advance by exactly one full cycle (sample-rate samples at 1 Hz).
    lfo.advance(sr, sr)
    assert abs(lfo.value) < 1e-6


def test_lfo_quarter_cycle_at_peak():
    """1 Hz LFO advanced sr/4 samples -> phase = pi/2 -> value ≈ 1.0."""
    sr = 44100
    lfo = LFO(rate_hz=1.0, amplitude=1.0)
    lfo.advance(sr // 4, sr)
    assert lfo.value == pytest.approx(1.0, abs=5e-4)


def test_bank_unrouted_returns_raw():
    bank = LFOBank()
    # No routes -> effective_value is the raw value.
    assert bank.effective_value("lpf_cutoff", 50.0, 0.0, 100.0) == 50.0


def test_bank_bipolar_offset_at_mid_knob():
    """Bipolar: amp=0.5 at sin(phase)=1 -> effective = raw + 0.5*span."""
    bank = LFOBank()
    bank.assign("k", 0)
    bank.lfos[0].amplitude = 0.5
    bank.lfos[0]._phase = math.pi / 2  # sin = 1
    bank.lfos[0].value = 1.0
    bank.tick(num_samples=0, sample_rate=44100)  # recompute offsets
    # Raw=50 on 0..100 range, span=100, amp=0.5, sin≈1 -> offset=50 -> eff≈100
    eff = bank.effective_value("k", 50.0, 0.0, 100.0)
    assert eff == pytest.approx(100.0, abs=0.5)


def test_bank_clamps_at_knob_max():
    bank = LFOBank()
    bank.assign("k", 0)
    bank.lfos[0].amplitude = 1.0
    bank.lfos[0]._phase = math.pi / 2
    bank.lfos[0].value = 1.0
    bank.tick(0, 44100)
    # Raw=90 on 0..100, +100% amp -> would be 190, clamped to 100.
    eff = bank.effective_value("k", 90.0, 0.0, 100.0)
    assert eff == 100.0


def test_bank_clamps_at_knob_min():
    bank = LFOBank()
    bank.assign("k", 0)
    bank.lfos[0].amplitude = 1.0
    bank.lfos[0]._phase = -math.pi / 2
    bank.lfos[0].value = -1.0
    bank.tick(0, 44100)
    eff = bank.effective_value("k", 10.0, 0.0, 100.0)
    assert eff == 0.0


def test_unassign_clears_modulation():
    bank = LFOBank()
    bank.assign("k", 1)
    bank.lfos[1].amplitude = 0.5
    bank.lfos[1]._phase = math.pi / 2
    bank.lfos[1].value = 1.0
    bank.tick(0, 44100)
    assert bank.effective_value("k", 50.0, 0.0, 100.0) != 50.0
    bank.unassign("k")
    bank.tick(0, 44100)
    assert bank.effective_value("k", 50.0, 0.0, 100.0) == 50.0


def test_three_independent_lfos():
    bank = LFOBank()
    assert len(bank.lfos) == 3
    bank.lfos[0].rate_hz = 1.0
    bank.lfos[1].rate_hz = 5.0
    bank.lfos[2].rate_hz = 0.1
    # Advance each by the same num_samples; phases diverge.
    bank.tick(1000, 44100)
    phases = [lfo._phase for lfo in bank.lfos]
    assert phases[0] != phases[1] != phases[2]


def test_assign_invalid_lfo_index_raises():
    bank = LFOBank()
    with pytest.raises(ValueError):
        bank.assign("k", 3)
