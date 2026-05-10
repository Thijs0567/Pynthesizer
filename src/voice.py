"""Voice/Oscillator — one polyphonic note."""
import numpy as np

_DEFAULT_WAVETABLE = np.zeros(16, dtype=np.float32)
_DEFAULT_WAVETABLE[0] = 1.0
_DEFAULT_WAVETABLE.flags.writeable = False


class Voice:
    """Single oscillator voice: sine wave + ADSR envelope."""

    def __init__(self, sample_rate: int, frequency: float, velocity: int = 127,
                 attack: float = 0.01, decay: float = 0.1, sustain: float = 0.7,
                 release: float = 0.3, creation_time: float = 0.0,
                 wavetable=None):
        self.sample_rate = sample_rate
        self.frequency = frequency
        self.velocity = velocity
        self.phase = 0.0
        self.is_active = True
        self.time = 0.0
        self.creation_time = creation_time

        self.attack_time = attack
        self.decay_time = decay
        self.sustain_level = sustain
        self.release_time = release

        self.is_releasing = False
        self.key_off_time = 0.0
        self._retrigger_level = 0.0
        self._release_start_level = 0.0

        self.wavetable = wavetable if wavetable is not None else _DEFAULT_WAVETABLE.copy()
        self._osc_buf = np.zeros(4096, dtype=np.float64)

        # Portamento glide state
        self._glide_target = frequency   # Hz
        self._glide_rate = 0.0           # semitones per sample (0 = instant)

    def set_frequency(self, frequency: float):
        self.frequency = max(20.0, min(20000.0, frequency))
        self._glide_target = self.frequency
        self._glide_rate = 0.0

    def start_glide(self, target_freq: float, glide_time: float):
        """Glide to target_freq over glide_time seconds (0 = instant)."""
        target_freq = max(20.0, min(20000.0, target_freq))
        if glide_time <= 0.0 or self.frequency <= 0.0:
            self.frequency = target_freq
            self._glide_target = target_freq
            self._glide_rate = 0.0
            return
        semitones = 12.0 * np.log2(target_freq / self.frequency)
        self._glide_target = target_freq
        # rate in semitones/sample — sign carries direction
        self._glide_rate = semitones / (glide_time * self.sample_rate)

    def note_off(self):
        self._release_start_level = self._get_envelope_value()
        self.is_releasing = True
        self.key_off_time = self.time

    def retrigger(self, velocity: int):
        """Restart the envelope from its current level so there is no amplitude jump."""
        self._retrigger_level = self._get_envelope_value()
        self.is_releasing = False
        self.time = 0.0
        self.velocity = velocity

    def _get_envelope_value(self) -> float:
        """Current envelope amplitude (single sample, used for retrigger capture)."""
        if self.is_releasing:
            t = self.time - self.key_off_time
            if t >= self.release_time:
                return 0.0
            return self._release_start_level * (1.0 - t / self.release_time)
        if self.time < self.attack_time:
            return self.time / self.attack_time
        if self.time < self.attack_time + self.decay_time:
            return 1.0 - (1.0 - self.sustain_level) * (self.time - self.attack_time) / self.decay_time
        return self.sustain_level

    def generate_samples(self, num_samples: int) -> np.ndarray:
        """Generate one block of audio samples."""
        if not self.is_active:
            return np.zeros(num_samples, dtype=np.float32)
        if num_samples <= 0 or self.sample_rate <= 0:
            return np.zeros(max(1, num_samples), dtype=np.float32)
        if not np.isfinite(self.frequency) or self.frequency <= 0:
            self.is_active = False
            return np.zeros(num_samples, dtype=np.float32)

        dt = 1.0 / self.sample_rate
        # Single index array reused for both phase and envelope time.
        indices = np.arange(num_samples, dtype=np.float64)

        # ── Oscillator ────────────────────────────────────────────────────────
        if self._glide_rate != 0.0:
            # Accumulate phase with per-sample gliding frequency
            log_start = np.log2(self.frequency)
            log_target = np.log2(self._glide_target)
            log_steps = log_start + self._glide_rate / np.log2(np.e) * np.arange(num_samples)
            # clamp to target so we don't overshoot
            if self._glide_rate > 0:
                log_steps = np.minimum(log_steps, log_target)
            else:
                log_steps = np.maximum(log_steps, log_target)
            freqs = 2.0 ** log_steps
            phase_incs = 2.0 * np.pi * freqs / self.sample_rate
            phases = self.phase + np.cumsum(phase_incs) - phase_incs[0]
            self.phase = (phases[-1] + phase_incs[-1]) % (2.0 * np.pi)
            self.frequency = float(freqs[-1])
            if (self._glide_rate > 0 and self.frequency >= self._glide_target) or \
               (self._glide_rate < 0 and self.frequency <= self._glide_target):
                self.frequency = self._glide_target
                self._glide_rate = 0.0
        else:
            phase_inc = 2.0 * np.pi * self.frequency / self.sample_rate
            phases = self.phase + indices * phase_inc
            self.phase = (phases[-1] + phase_inc) % (2.0 * np.pi)
        amplitude = max(0.0, min(1.0, self.velocity / 127.0))

        wt = self.wavetable
        if num_samples > len(self._osc_buf):
            self._osc_buf = np.zeros(num_samples, dtype=np.float64)
        osc = self._osc_buf
        osc[:num_samples] = 0.0
        for k in range(16):
            if wt[k] != 0.0:
                osc[:num_samples] += wt[k] * np.sin((k + 1) * phases)
        samples = (osc[:num_samples] * amplitude).astype(np.float32)

        # ── ADSR envelope (vectorised) ────────────────────────────────────────
        # Use float32 for envelope time — float32 precision is sufficient for
        # ADSR timing and avoids a dtype conversion on every block.
        t = np.float32(self.time) + indices.astype(np.float32) * np.float32(dt)

        if self.is_releasing:
            rel_t = t - np.float32(self.key_off_time)
            env = np.where(
                rel_t < self.release_time,
                np.float32(self._release_start_level) * (1.0 - rel_t / np.float32(self.release_time)),
                np.float32(0.0),
            )
            end_idx = int(np.searchsorted(rel_t, self.release_time))
            if end_idx < num_samples:
                env[end_idx:] = 0.0
                self.is_active = False
        else:
            atk_end = np.float32(self.attack_time)
            dec_end = atk_end + np.float32(self.decay_time)
            rl = np.float32(self._retrigger_level)
            env = np.where(
                t < atk_end,
                rl + (np.float32(1.0) - rl) * t / atk_end,
                np.where(
                    t < dec_end,
                    np.float32(1.0) - (np.float32(1.0) - np.float32(self.sustain_level)) * (t - atk_end) / np.float32(self.decay_time),
                    np.float32(self.sustain_level),
                ),
            )

        self.time = float(t[-1]) + dt
        samples *= env
        return np.nan_to_num(samples, nan=0.0, posinf=0.95, neginf=-0.95)
