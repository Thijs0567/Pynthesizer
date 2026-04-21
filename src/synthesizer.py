"""
Main synthesizer engine.
Manages polyphonic voices and audio generation.
"""
import numpy as np
from typing import Dict, Optional
from src.voice import Voice
from src.midi_handler import MIDIHandler
from src.effects import MasterVolume, LowPassFilter, Reverb, Delay, Chorus, Bitcrusher
from src.lfo import LFOBank


class Synthesizer:
    """Main polyphonic synthesizer engine."""
    
    # MIDI note to frequency lookup
    A4_FREQUENCY = 440.0
    
    def __init__(self, sample_rate: int = 44100, max_voices: int = 16):
        """
        Initialize the synthesizer.
        
        Args:
            sample_rate: Sample rate in Hz (default 44100)
            max_voices: Maximum number of simultaneous voices
        """
        self.sample_rate = sample_rate
        self.max_voices = max_voices
        
        # Voice management
        self.active_voices: Dict[int, Voice] = {}  # note -> Voice
        self.free_voices = []
        self.voice_creation_counter = 0  # Counter for tracking voice age
        
        # ADSR parameters
        self.attack = 0.01
        self.decay = 0.1
        self.sustain = 0.7
        self.release = 0.3

        # Wavetable (16 harmonic amplitudes; bin 0 = fundamental)
        _wt = np.zeros(16, dtype=np.float32)
        _wt[0] = 1.0
        self._wavetable = _wt
        
        # MIDI handler
        self.midi_handler = MIDIHandler()
        self.midi_handler.on_note_on = self._on_note_on
        self.midi_handler.on_note_off = self._on_note_off
        self.midi_handler.on_pitch_bend = self._on_pitch_bend
        
        # Pitch bend
        self.pitch_bend_amount = 0  # -8192 to 8191
        self.pitch_bend_range = 2  # semitones

        # Smoothed envelope-weight sum for √N polyphony scaling
        self._mix_scale = 1.0

        # Compressor state — persists between audio blocks
        self._comp_envelope = 1e-10  # RMS envelope follower
        self._comp_gain = 1.0        # Smoothed gain multiplier

        # Compressor curve (e-piano / optical character)
        # Threshold at -3 dBFS means compression kicks in around 2 voices
        self._comp_threshold_db = -3.0
        self._comp_ratio = 4.0       # 4:1: musical, not aggressive
        self._comp_knee_db = 6.0     # Wide knee for smooth onset

        # Time constants (per sample, raised to block size each call)
        self._attack_coef = np.exp(-1.0 / (0.030 * sample_rate))   # 30ms
        self._release_coef = np.exp(-1.0 / (0.200 * sample_rate))  # 200ms

        # Peak limiter — second stage, catches what the RMS compressor misses.
        # Sine waves have a 3 dB crest factor so the compressor alone cannot
        # prevent peaks from exceeding the threshold between blocks.
        self._lim_gain = 1.0
        self._lim_threshold = 0.90                                         # hard ceiling shown as red on meter
        self._lim_release_coef = np.exp(-1.0 / (0.050 * sample_rate))     # 50ms release

        # Effects chain
        self._volume = MasterVolume(initial_volume=0.3)  # = 70% knob × (3/7)
        self._lpf    = LowPassFilter(sample_rate)
        self._reverb = Reverb(sample_rate, wet=0.0)
        self._delay  = Delay(sample_rate, wet=0.0)
        self._chorus = Chorus(sample_rate, wet=0.0)
        self._bitcrusher = Bitcrusher(bits=16.0, downsample=1, wet=0.0)

        # LFO modulation bank — phase advanced once per audio block.
        # GUI polls ``lfo_bank.offsets`` on its own thread to re-apply
        # modulated parameter values (tkinter is not audio-thread safe).
        self.lfo_bank = LFOBank()

    @staticmethod
    def note_to_frequency(note: int) -> float:
        """
        Convert MIDI note number to frequency in Hz.
        
        Args:
            note: MIDI note number (0-127)
            
        Returns:
            Frequency in Hz
        """
        return Synthesizer.A4_FREQUENCY * (2 ** ((note - 69) / 12.0))
    
    def set_adsr(self, attack: float, decay: float, sustain: float, release: float):
        """Set ADSR parameters for new voices."""
        self.attack = max(0.001, attack)
        self.decay = max(0.001, decay)
        self.sustain = max(0, min(1, sustain))
        self.release = max(0.001, release)

    def set_volume(self, volume: float) -> None:
        self._volume.set_volume(volume)

    def set_lpf(self, cutoff_hz: float, q: float) -> None:
        self._lpf.set_cutoff(cutoff_hz)
        self._lpf.set_q(q)

    def set_reverb(self, room_size: float, damping: float, wet: float) -> None:
        self._reverb.set_room_size(room_size)
        self._reverb.set_damping(damping)
        self._reverb.set_wet(wet)

    def set_delay(self, delay_ms: float, feedback: float, wet: float) -> None:
        self._delay.set_delay_ms(delay_ms)
        self._delay.set_feedback(feedback)
        self._delay.set_wet(wet)

    def set_chorus(self, rate_hz: float, depth: float, wet: float) -> None:
        self._chorus.set_rate(rate_hz)
        self._chorus.set_depth(depth)
        self._chorus.set_wet(wet)

    def set_bitcrusher(self, bits: float, downsample: int, wet: float) -> None:
        self._bitcrusher.set_bits(bits)
        self._bitcrusher.set_downsample(downsample)
        self._bitcrusher.set_wet(wet)

    def set_wavetable(self, amplitudes) -> None:
        """Update harmonic amplitudes for all active and future voices."""
        wt = np.clip(np.array(amplitudes, dtype=np.float32)[:16], 0.0, 1.0)
        self._wavetable = wt
        for voice in list(self.active_voices.values()):
            voice.wavetable = wt

    def _on_note_on(self, note: int, velocity: int):
        """Handle MIDI note on event."""
        if note in self.active_voices:
            voice = self.active_voices[note]
            # Save envelope level so the attack restarts from here, not from 0.
            # Resetting time to 0 without this causes an instant amplitude drop
            # (sustain_level → 0) that sounds like a click or phase jump.
            voice._retrigger_level = voice._get_envelope_value()
            voice.is_releasing = False
            voice.time = 0.0
            voice.velocity = velocity
        else:
            # Check if we need to steal a voice
            if len(self.active_voices) >= self.max_voices:
                # Find the oldest voice and remove it
                oldest_note = min(self.active_voices.keys(),
                                key=lambda n: self.active_voices[n].creation_time)
                del self.active_voices[oldest_note]
            
            # Create new voice
            frequency = self.note_to_frequency(note)
            voice = Voice(self.sample_rate, frequency, velocity,
                        self.attack, self.decay, self.sustain, self.release,
                        creation_time=self.voice_creation_counter,
                        wavetable=self._wavetable)
            self.voice_creation_counter += 1
            self.active_voices[note] = voice
    
    def _on_note_off(self, note: int):
        """Handle MIDI note off event."""
        if note in self.active_voices:
            self.active_voices[note].note_off()

    def panic(self):
        """Immediately silence all voices without blocking future note input."""
        self.active_voices.clear()
    
    def _apply_compression(self, signal: np.ndarray) -> np.ndarray:
        """
        Two-stage dynamics processor:
          Stage 1 — RMS compressor: smooth long-term level riding (e-piano character)
          Stage 2 — Peak limiter:   feedforward brickwall, catches crest-factor peaks
                                    that the RMS stage misses between blocks

        Gain is constant within each block — no per-sample distortion.
        """
        N = len(signal)

        # ── Stage 1: RMS compressor ────────────────────────────────────────────
        rms = float(np.sqrt(np.mean(signal.astype(np.float64) ** 2) + 1e-20))

        if rms > self._comp_envelope:
            a = self._attack_coef ** N
        else:
            a = self._release_coef ** N
        self._comp_envelope = a * self._comp_envelope + (1.0 - a) * rms

        L_db = 20.0 * np.log10(max(self._comp_envelope, 1e-10))
        T = self._comp_threshold_db
        R = self._comp_ratio
        W = self._comp_knee_db

        if L_db < T - W / 2.0:
            gain_db = 0.0
        elif L_db > T + W / 2.0:
            gain_db = (1.0 / R - 1.0) * (L_db - T)
        else:
            gain_db = (1.0 / R - 1.0) * (L_db - T + W / 2.0) ** 2 / (2.0 * W)

        target_gain = 10.0 ** (gain_db / 20.0)

        old_comp_gain = self._comp_gain
        if target_gain < self._comp_gain:
            g = self._attack_coef ** N
        else:
            g = self._release_coef ** N
        self._comp_gain = g * self._comp_gain + (1.0 - g) * target_gain

        # Ramp gain across the block instead of applying a scalar step.
        # A scalar would create a discontinuity at every block boundary.
        compressed = signal * np.linspace(old_comp_gain, self._comp_gain, N)

        # ── Stage 2: Per-sample peak limiter ──────────────────────────────────
        # True per-sample processing: instant attack (gain set exactly so
        # |out[i]| ≤ threshold) and exponential release toward 1.0.
        # A sub-block (64-sample) constant-gain approach created a staircase at
        # ~690 Hz when multi-voice interference caused the peak to vary rapidly
        # between chunks, producing audible amplitude-modulation buzz at note onset.
        out = np.empty(N, dtype=np.float64)
        lim_gain = self._lim_gain
        lim_rel  = self._lim_release_coef   # per-sample release coefficient
        thresh   = self._lim_threshold
        for i in range(N):
            x = float(compressed[i])
            if abs(x) * lim_gain > thresh:
                lim_gain = thresh / (abs(x) + 1e-30)
            else:
                lim_gain = lim_rel * lim_gain + (1.0 - lim_rel)
                if lim_gain > 1.0:
                    lim_gain = 1.0
            out[i] = x * lim_gain
        self._lim_gain = lim_gain

        return out.astype(np.float32)
    
    def _on_pitch_bend(self, value: int):
        """Handle MIDI pitch bend event."""
        self.pitch_bend_amount = value
        
        # Apply pitch bend to all active voices
        pitch_bend_semitones = (value / 8192.0) * self.pitch_bend_range
        pitch_bend_factor = 2 ** (pitch_bend_semitones / 12.0)
        
        for note, voice in list(self.active_voices.items()):
            base_frequency = self.note_to_frequency(note)
            voice.set_frequency(base_frequency * pitch_bend_factor)
    
    def generate_audio(self, num_samples: int) -> np.ndarray:
        """
        Generate audio samples from all active voices.
        
        Args:
            num_samples: Number of samples to generate
            
        Returns:
            Mixed audio samples (mono)
        """
        # Advance LFO phases once per block. GUI thread polls the resulting
        # offsets at ~20 Hz to re-apply modulated parameters via the normal
        # setter callbacks (tkinter is not audio-thread safe).
        self.lfo_bank.tick(num_samples, self.sample_rate)

        output = np.zeros(num_samples, dtype=np.float32)

        # Generate and mix samples from all active voices
        notes_to_remove = []
        
        # Electric piano gain staging:
        # - Add voices directly (they sum naturally)
        # - Soft limiting prevents clipping while maintaining dynamics
        # - No per-voice scaling - let the limiter do the work
        # Result: More voices = gradually louder, but natural compression
        # like a real electric piano that never clips
        
        env_sum = 0.0
        for note, voice in list(self.active_voices.items()):
            try:
                if voice.is_active:
                    samples = voice.generate_samples(num_samples)
                    if samples is not None and len(samples) == num_samples:
                        output += samples
                    env_sum += voice._get_envelope_value()
                else:
                    notes_to_remove.append(note)
            except Exception as e:
                print(f"Error generating voice samples for note {note}: {type(e).__name__}: {e}")
                notes_to_remove.append(note)

        # Remove inactive voices
        for note in notes_to_remove:
            if note in self.active_voices:
                del self.active_voices[note]

        # Envelope-weighted √-scaling: normalise by √(sum of envelope amplitudes)
        # so the gain tracks actual loudness rather than raw voice count.
        # Smoothed with a 50 ms time constant to avoid pumping artifacts.
        target_scale = 1.0 / np.sqrt(max(env_sum, 1.0))
        smooth = np.exp(-1.0 / (0.050 * self.sample_rate / max(num_samples, 1)))
        self._mix_scale = smooth * self._mix_scale + (1.0 - smooth) * target_scale
        output *= self._mix_scale

        # Ensure output is valid
        output = np.nan_to_num(output, nan=0.0, posinf=1.0, neginf=-1.0)
        
        output = self._volume.process(output)
        output = self._lpf.process(output)
        output = self._reverb.process(output)
        output = self._delay.process(output)
        output = self._apply_compression(output)
        output = self._bitcrusher.process(output)

        # Chorus is last — returns (N, 2) stereo
        stereo = self._chorus.process(output)
        return stereo.astype(np.float32)
    
    def open_midi_port(self, port_index: int = 0) -> bool:
        """Open a MIDI input port."""
        return self.midi_handler.open_port(port_index)
    
    def start_midi(self) -> bool:
        """Start listening for MIDI input."""
        return self.midi_handler.start()
    
    def list_midi_ports(self):
        """List available MIDI input ports."""
        return self.midi_handler.list_input_ports()
    
    def stop(self):
        """Stop the synthesizer and close MIDI."""
        self.midi_handler.close()
