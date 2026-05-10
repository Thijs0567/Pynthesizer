"""
DSP effects chain: MasterVolume, LowPassFilter, Reverb, Delay, Chorus.
All classes pre-allocate buffers in __init__; no per-block allocation.
"""
import math
import numpy as np


class TubeDistortion:
    """Soft-clip tube saturation using tanh waveshaping. Drive boosts gain into the clipper."""

    def __init__(self, drive: float = 1.0, wet: float = 0.0,
                 max_block_size: int = 4096):
        self._drive = max(1.0, float(drive))
        self._wet   = max(0.0, min(1.0, float(wet)))
        self._buf   = np.zeros(max_block_size, dtype=np.float64)

    def set_drive(self, drive: float) -> None:
        # 1.0 = unity (no saturation), up to ~20.0 = heavy clipping
        self._drive = max(1.0, min(20.0, float(drive)))

    def set_wet(self, wet: float) -> None:
        self._wet = max(0.0, min(1.0, float(wet)))

    def process(self, signal: np.ndarray) -> np.ndarray:
        n = len(signal)
        if n > len(self._buf):
            self._buf = np.zeros(n, dtype=np.float64)
        wet = self._wet
        dry = 1.0 - wet
        drive = self._drive
        out = self._buf
        for i in range(n):
            x = float(signal[i])
            # tanh soft-clip; compensate output level by dividing by tanh(drive)
            clipped = math.tanh(x * drive) / math.tanh(drive)
            out[i] = dry * x + wet * clipped
        return out[:n]

    def reset_state(self) -> None:
        pass  # stateless waveshaper


class MasterVolume:
    def __init__(self, initial_volume: float = 0.8):
        self.volume = max(0.0, min(1.0, initial_volume))

    def set_volume(self, volume: float) -> None:
        self.volume = max(0.0, min(1.0, float(volume)))

    def process(self, signal: np.ndarray) -> np.ndarray:
        signal *= self.volume
        return signal


class LowPassFilter:
    def __init__(self, sample_rate: int, cutoff_hz: float = 20000.0,
                 q: float = 0.707, max_block_size: int = 4096):
        self._sr = sample_rate
        self._cutoff = float(cutoff_hz)
        self._q = float(q)
        self._z1 = 0.0
        self._z2 = 0.0
        self._buf = np.zeros(max_block_size, dtype=np.float64)
        # Coefficients (normalised)
        self._b0 = self._b1 = self._b2 = 0.0
        self._a1 = self._a2 = 0.0
        self._compute_coefficients()

    def set_cutoff(self, cutoff_hz: float) -> None:
        self._cutoff = float(cutoff_hz)
        self._compute_coefficients()

    def set_q(self, q: float) -> None:
        self._q = float(q)
        self._compute_coefficients()

    def _compute_coefficients(self) -> None:
        cutoff = max(20.0, min(self._cutoff, self._sr * 0.4999))
        q = max(0.5, self._q)
        w0 = 2.0 * math.pi * cutoff / self._sr
        alpha = math.sin(w0) / (2.0 * q)
        cos_w0 = math.cos(w0)
        b0 = (1.0 - cos_w0) / 2.0
        b1 = 1.0 - cos_w0
        b2 = b0
        a0 = 1.0 + alpha
        a1 = -2.0 * cos_w0
        a2 = 1.0 - alpha
        self._b0 = b0 / a0
        self._b1 = b1 / a0
        self._b2 = b2 / a0
        self._a1 = a1 / a0
        self._a2 = a2 / a0

    def process(self, signal: np.ndarray) -> np.ndarray:
        n = len(signal)
        if n > len(self._buf):
            self._buf = np.zeros(n, dtype=np.float64)
        b0, b1, b2 = self._b0, self._b1, self._b2
        a1, a2 = self._a1, self._a2
        z1, z2 = self._z1, self._z2
        out = self._buf
        for i in range(n):
            x = float(signal[i])
            y = b0 * x + z1
            z1 = b1 * x - a1 * y + z2
            z2 = b2 * x - a2 * y
            out[i] = y
        self._z1 = z1
        self._z2 = z2
        return out[:n]

    def reset_state(self) -> None:
        self._z1 = 0.0
        self._z2 = 0.0


class Reverb:
    _COMB_LENGTHS_44100    = [1116, 1188, 1277, 1356]
    _ALLPASS_LENGTHS_44100 = [556, 441]

    def __init__(self, sample_rate: int, room_size: float = 0.5,
                 damping: float = 0.5, wet: float = 0.0,
                 max_block_size: int = 4096):
        self._sr = sample_rate
        self._wet = max(0.0, min(1.0, float(wet)))
        self._feedback = 0.0
        self._damp1 = 0.0
        self._damp2 = 1.0

        # Allocate comb filter buffers
        self._comb_bufs = [
            np.zeros(self._scale(L), dtype=np.float64)
            for L in self._COMB_LENGTHS_44100
        ]
        self._comb_ptrs = [0] * len(self._COMB_LENGTHS_44100)
        self._comb_states = [0.0] * len(self._COMB_LENGTHS_44100)

        # Allocate allpass buffers
        self._ap_bufs = [
            np.zeros(self._scale(L), dtype=np.float64)
            for L in self._ALLPASS_LENGTHS_44100
        ]
        self._ap_ptrs = [0] * len(self._ALLPASS_LENGTHS_44100)

        self._buf = np.zeros(max_block_size, dtype=np.float64)
        self._max_block_size = max_block_size

        self.set_room_size(room_size)
        self.set_damping(damping)

    def _scale(self, base_length: int) -> int:
        return max(1, int(base_length * self._sr / 44100))

    def set_room_size(self, room_size: float) -> None:
        # Maps [0,1] → feedback [0.70, 0.98]
        self._feedback = 0.28 * max(0.0, min(1.0, float(room_size))) + 0.70

    def set_damping(self, damping: float) -> None:
        self._damp1 = max(0.0, min(1.0, float(damping))) * 0.4
        self._damp2 = 1.0 - self._damp1

    def set_wet(self, wet: float) -> None:
        self._wet = max(0.0, min(1.0, float(wet)))

    def process(self, signal: np.ndarray) -> np.ndarray:
        n = len(signal)
        if n > len(self._buf):
            self._buf = np.zeros(n, dtype=np.float64)
        wet = self._wet
        dry = 1.0 - wet
        feedback = self._feedback
        damp1 = self._damp1
        damp2 = self._damp2
        comb_bufs = self._comb_bufs
        comb_ptrs = self._comb_ptrs
        comb_states = self._comb_states
        ap_bufs = self._ap_bufs
        ap_ptrs = self._ap_ptrs
        out = self._buf

        for i in range(n):
            x = float(signal[i])
            comb_sum = 0.0
            for c in range(4):
                buf = comb_bufs[c]
                ptr = comb_ptrs[c]
                buf_out = buf[ptr]
                filt = buf_out * damp2 + comb_states[c] * damp1
                comb_states[c] = filt
                buf[ptr] = x + filt * feedback
                comb_ptrs[c] = (ptr + 1) % len(buf)
                comb_sum += buf_out
            comb_sum *= 0.25  # normalise 4 combs

            for a in range(2):
                buf = ap_bufs[a]
                ptr = ap_ptrs[a]
                buf_out = buf[ptr]
                buf[ptr] = comb_sum + buf_out * 0.5
                ap_ptrs[a] = (ptr + 1) % len(buf)
                comb_sum = buf_out - comb_sum

            out[i] = x * dry + comb_sum * wet

        return out[:n]

    def reset_state(self) -> None:
        for buf in self._comb_bufs:
            buf[:] = 0.0
        for buf in self._ap_bufs:
            buf[:] = 0.0
        self._comb_ptrs = [0] * len(self._comb_ptrs)
        self._ap_ptrs = [0] * len(self._ap_ptrs)
        self._comb_states = [0.0] * len(self._comb_states)


class Delay:
    def __init__(self, sample_rate: int, delay_ms: float = 250.0,
                 feedback: float = 0.4, wet: float = 0.0,
                 max_block_size: int = 4096):
        self._sr = sample_rate
        self._max_samples = int(sample_rate)  # 1 second max
        self._buf = np.zeros(self._max_samples, dtype=np.float64)
        self._write_ptr = 0
        self._delay_samples = 0
        self._feedback = 0.0
        self._wet = 0.0
        self._out_buf = np.zeros(max_block_size, dtype=np.float64)

        self.set_delay_ms(delay_ms)
        self.set_feedback(feedback)
        self.set_wet(wet)

    def set_delay_ms(self, delay_ms: float) -> None:
        ms = max(10.0, min(1000.0, float(delay_ms)))
        self._delay_samples = int(ms * self._sr / 1000)

    def set_feedback(self, feedback: float) -> None:
        self._feedback = max(0.0, min(0.9, float(feedback)))

    def set_wet(self, wet: float) -> None:
        self._wet = max(0.0, min(1.0, float(wet)))

    def process(self, signal: np.ndarray) -> np.ndarray:
        n = len(signal)
        if n > len(self._out_buf):
            self._out_buf = np.zeros(n, dtype=np.float64)
        buf = self._buf
        max_s = self._max_samples
        delay_s = self._delay_samples
        feedback = self._feedback
        wet = self._wet
        dry = 1.0 - wet
        ptr = self._write_ptr
        out = self._out_buf

        for i in range(n):
            read_ptr = (ptr - delay_s) % max_s
            d = buf[read_ptr]
            buf[ptr] = float(signal[i]) + d * feedback
            out[i] = float(signal[i]) * dry + d * wet
            ptr = (ptr + 1) % max_s

        self._write_ptr = ptr
        return out[:n]

    def reset_state(self) -> None:
        self._buf[:] = 0.0
        self._write_ptr = 0


class Bitcrusher:
    """Bit-depth reduction + sample-rate reduction (downsampling hold)."""

    def __init__(self, bits: float = 16.0, downsample: int = 1,
                 wet: float = 0.0, max_block_size: int = 4096):
        self._bits = float(bits)
        self._downsample = max(1, int(downsample))
        self._wet = max(0.0, min(1.0, float(wet)))
        self._held = 0.0
        self._hold_count = 0
        self._buf = np.zeros(max_block_size, dtype=np.float64)

    def set_bits(self, bits: float) -> None:
        self._bits = max(1.0, min(24.0, float(bits)))

    def set_downsample(self, factor: int) -> None:
        self._downsample = max(1, int(factor))

    def set_wet(self, wet: float) -> None:
        self._wet = max(0.0, min(1.0, float(wet)))

    def process(self, signal: np.ndarray) -> np.ndarray:
        n = len(signal)
        if n > len(self._buf):
            self._buf = np.zeros(n, dtype=np.float64)
        levels = 2.0 ** (self._bits - 1)
        step = 1.0 / levels
        wet = self._wet
        dry = 1.0 - wet
        ds = self._downsample
        held = self._held
        count = self._hold_count
        out = self._buf

        for i in range(n):
            x = float(signal[i])
            if count == 0:
                # quantise
                held = math.floor(x / step + 0.5) * step
            count = (count + 1) % ds
            out[i] = dry * x + wet * held

        self._held = held
        self._hold_count = count
        return out[:n]

    def reset_state(self) -> None:
        self._held = 0.0
        self._hold_count = 0


class Chorus:
    """
    Stereo chorus: two LFO-modulated delay lines (L/R) with opposite LFO phase.
    Input: mono (N,) array. Output: stereo (N, 2) array.
    """
    # Delay range: centre ± depth in samples
    _DELAY_CENTER_MS = 20.0
    _MAX_DELAY_MS    = 40.0

    def __init__(self, sample_rate: int, rate_hz: float = 0.5,
                 depth: float = 0.5, wet: float = 0.0,
                 max_block_size: int = 4096):
        self._sr    = sample_rate
        self._wet   = max(0.0, min(1.0, float(wet)))
        self._rate  = float(rate_hz)
        self._depth = max(0.0, min(1.0, float(depth)))

        max_delay = int(self._MAX_DELAY_MS * sample_rate / 1000) + 4
        self._buf_l = np.zeros(max_delay, dtype=np.float64)
        self._buf_r = np.zeros(max_delay, dtype=np.float64)
        self._buf_size = max_delay
        self._write = 0

        self._lfo_phase = 0.0  # radians, L uses phase, R uses phase + π

        self._out = np.zeros((max_block_size, 2), dtype=np.float32)

    def set_rate(self, rate_hz: float) -> None:
        self._rate = max(0.01, min(10.0, float(rate_hz)))

    def set_depth(self, depth: float) -> None:
        self._depth = max(0.0, min(1.0, float(depth)))

    def set_wet(self, wet: float) -> None:
        self._wet = max(0.0, min(1.0, float(wet)))

    def process(self, signal: np.ndarray) -> np.ndarray:
        n = len(signal)
        if n > len(self._out):
            self._out = np.zeros((n, 2), dtype=np.float32)

        wet   = self._wet
        dry   = 1.0 - wet
        center = self._DELAY_CENTER_MS * self._sr / 1000.0
        # depth scales the LFO swing: 0 → no modulation, 1 → ±center ms
        swing  = center * self._depth
        phase_inc = 2.0 * math.pi * self._rate / self._sr

        buf_l    = self._buf_l
        buf_r    = self._buf_r
        buf_size = self._buf_size
        write    = self._write
        phase    = self._lfo_phase
        out      = self._out

        for i in range(n):
            x = float(signal[i])

            # Write dry sample into both delay lines
            buf_l[write] = x
            buf_r[write] = x

            # LFO: L and R are π apart for stereo width
            lfo_l = math.sin(phase)
            lfo_r = math.sin(phase + math.pi)

            delay_l = center + swing * lfo_l
            delay_r = center + swing * lfo_r

            # Linear interpolation for fractional delay
            dl_i = int(delay_l)
            dl_f = delay_l - dl_i
            rl0 = (write - dl_i) % buf_size
            rl1 = (write - dl_i - 1) % buf_size
            wet_l = buf_l[rl0] * (1.0 - dl_f) + buf_l[rl1] * dl_f

            dr_i = int(delay_r)
            dr_f = delay_r - dr_i
            rr0 = (write - dr_i) % buf_size
            rr1 = (write - dr_i - 1) % buf_size
            wet_r = buf_r[rr0] * (1.0 - dr_f) + buf_r[rr1] * dr_f

            out[i, 0] = x * dry + wet_l * wet
            out[i, 1] = x * dry + wet_r * wet

            write = (write + 1) % buf_size
            phase += phase_inc

        self._write = write
        self._lfo_phase = phase % (2.0 * math.pi)
        return out[:n]

    def reset_state(self) -> None:
        self._buf_l[:] = 0.0
        self._buf_r[:] = 0.0
        self._write = 0
        self._lfo_phase = 0.0
