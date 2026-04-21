"""LFO module: sine LFOs + routing registry for knob modulation.

Mirrors the phase-tracking pattern used by Chorus in effects.py. Each LFO
advances its phase once per audio block. A routing table maps assignable
knob IDs to an LFO index; ``effective_value`` applies the current bipolar
offset, clamped to the knob's range.
"""
import math
from typing import Dict, Optional


class LFO:
    """Fixed-sine LFO with persistent phase."""

    def __init__(self, rate_hz: float = 1.0, amplitude: float = 0.0):
        self.rate_hz = float(rate_hz)
        self.amplitude = float(amplitude)
        self._phase = 0.0
        self.value = 0.0  # last emitted sin(phase)

    def advance(self, num_samples: int, sample_rate: int) -> float:
        phase_inc = 2.0 * math.pi * self.rate_hz / float(sample_rate)
        self._phase += phase_inc * num_samples
        if self._phase > 2.0 * math.pi:
            self._phase = math.fmod(self._phase, 2.0 * math.pi)
        self.value = math.sin(self._phase)
        return self.value


class LFOBank:
    """Bank of LFOs with knob routing.

    Routes are ``knob_id -> lfo_index``. At most one LFO per knob.
    ``tick`` advances all LFOs once per block; ``effective_value`` is then
    called by GUI change-handlers to apply the bipolar offset.
    """

    NUM_LFOS = 3

    def __init__(self):
        self.lfos = [LFO() for _ in range(self.NUM_LFOS)]
        self.routes: Dict[str, int] = {}
        self.offsets: Dict[str, float] = {}  # knob_id -> bipolar fractional offset (-amp..amp)

    def tick(self, num_samples: int, sample_rate: int) -> None:
        for lfo in self.lfos:
            lfo.advance(num_samples, sample_rate)
        self.offsets = {
            kid: self.lfos[idx].amplitude * self.lfos[idx].value
            for kid, idx in self.routes.items()
        }

    def effective_value(self, knob_id: str, raw: float, from_: float, to_: float) -> float:
        offset = self.offsets.get(knob_id)
        if offset is None:
            return raw
        span = to_ - from_
        if span == 0:
            return raw
        lo, hi = (from_, to_) if from_ <= to_ else (to_, from_)
        v = raw + offset * span
        return max(lo, min(hi, v))

    def assign(self, knob_id: str, lfo_index: int) -> None:
        if not 0 <= lfo_index < self.NUM_LFOS:
            raise ValueError(f"lfo_index {lfo_index} out of range")
        self.routes[knob_id] = lfo_index

    def unassign(self, knob_id: str) -> None:
        self.routes.pop(knob_id, None)
        self.offsets.pop(knob_id, None)

    def route_of(self, knob_id: str) -> Optional[int]:
        return self.routes.get(knob_id)
