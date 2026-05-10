"""
Simple clickable piano GUI for the synthesizer with ADSR controls.
"""
import tkinter as tk
from tkinter import Canvas, Scale, filedialog, messagebox
from typing import Callable, Optional, Dict, Tuple
import math
from pathlib import Path
import numpy as np

from .widgets import Knob, HarmonicSlider
from .widgets import theme as th
from . import presets as _presets


class PianoGUI:
    """A simple clickable piano interface with ADSR controls."""
    
    # Piano key properties
    WHITE_KEY_WIDTH = 26
    WHITE_KEY_HEIGHT = 120
    BLACK_KEY_WIDTH = 16
    BLACK_KEY_HEIGHT = 76
    
    # Standard piano layout
    WHITE_KEYS = ['C', 'D', 'E', 'F', 'G', 'A', 'B']
    BLACK_KEYS = {
        'C#': 0, 'D#': 1, 'F#': 3, 'G#': 4, 'A#': 5,
    }
    
    # 88-key range: A0 (MIDI 21) to C8 (MIDI 108)
    # Note: this codebase uses octave*12 for C, so C4=48 (not standard 60).
    # A0 = octave 1 note 9 = 21; C8 = octave 9 note 0 = 108.
    START_OCTAVE = 1
    END_OCTAVE = 8
    FIRST_NOTE = 21   # A0
    LAST_NOTE = 108   # C8
    
    def __init__(self, root: tk.Tk, on_note_on: Callable, on_note_off: Callable,
                 on_adsr_change: Callable = None,
                 on_volume_change: Callable = None,
                 on_lpf_change: Callable = None,
                 on_reverb_change: Callable = None,
                 on_delay_change: Callable = None,
                 on_wavetable_change: Callable = None,
                 on_chorus_change: Callable = None,
                 on_distortion_change: Callable = None,
                 on_bitcrusher_change: Callable = None,
                 on_panic: Callable = None,
                 on_unison_change: Callable = None,
                 lfo_bank=None):
        """
        Initialize the piano GUI.
        
        Args:
            root: Tkinter root window
            on_note_on: Callback for note on (takes note number and velocity)
            on_note_off: Callback for note off (takes note number)
            on_adsr_change: Callback for ADSR changes (takes attack, decay, sustain, release)
        """
        self.root = root
        self.on_note_on = on_note_on
        self.on_note_off = on_note_off
        self.on_adsr_change = on_adsr_change or (lambda a, d, s, r: None)
        self.on_volume_change = on_volume_change or (lambda v: None)
        self.on_lpf_change    = on_lpf_change    or (lambda cutoff, q: None)
        self.on_reverb_change = on_reverb_change or (lambda room, damp, wet: None)
        self.on_delay_change  = on_delay_change  or (lambda ms, fb, wet: None)
        self.on_wavetable_change = on_wavetable_change or (lambda wt: None)
        self.on_chorus_change = on_chorus_change or (lambda rate, depth, wet: None)
        self.on_distortion_change = on_distortion_change or (lambda drive, wet: None)
        self.on_bitcrusher_change = on_bitcrusher_change or (lambda bits, ds, wet: None)
        self.on_panic = on_panic or (lambda: None)
        self.on_unison_change = on_unison_change or (lambda v, d: None)

        # LFO modulation bank (optional; no-op routing if absent).
        from src.lfo import LFOBank  # local import to avoid cycle concerns
        self.lfo_bank = lfo_bank if lfo_bank is not None else LFOBank()
        # Assignable knob registry: knob_id -> (Knob widget, change-handler).
        # Populated by _register_assignable after each assignable knob is created.
        self._assignable: Dict[str, Tuple[object, Callable]] = {}
        # Currently selected LFO index shown in the LFO panel (0..2).
        self._lfo_selected = 0
        # Per-slot rate/amp knob positions (0..100 on both).
        self._lfo_slot_state = [
            {"rate": self._lfo_rate_hz_to_pct(1.0), "amp": 0},
            {"rate": self._lfo_rate_hz_to_pct(1.0), "amp": 0},
            {"rate": self._lfo_rate_hz_to_pct(1.0), "amp": 0},
        ]

        # Wavetable state: two editable slots (A, B) and a 32-step morph knob.
        # self.wavetable is the interpolated array actually sent to the engine.
        self._wt_a = np.zeros(16, dtype=np.float32)
        self._wt_a[0] = 1.0
        self._wt_b = self._make_preset_waveform('saw')
        self._edit_slot = 'A'
        self._morph_pos = 0
        self._suppress_harmonic_callback = False
        self.wavetable = self._wt_a.copy()

        # Active keys (pressed)
        self.active_keys: Dict[int, int] = {}  # note -> key_id
        self.mouse_down_note: Optional[int] = None
        
        # ADSR state
        self.attack = 0.01
        self.decay = 0.1
        self.sustain = 0.7
        self.release = 0.3
        
        # Transpose state (semitones, applied before note callbacks)
        self.transpose = 0

        # Mono mode state
        self._mono_enabled = False

        # Gain meter state (smoothed)
        self.current_level = 0.0
        self.peak_level = 0.0
        self.smoothed_level = 0.0
        self.meter_smooth_alpha = 0.7  # Higher = more responsive; 0.3 hid real peaks
        
        # Setup window
        self.root.title("PythonSynth")
        self.root.geometry("1440x1080")
        self.root.resizable(False, False)
        self.root.configure(bg=th.BG_ROOT)

        # Count white keys in the FIRST_NOTE..LAST_NOTE range (88-key = 52 white keys)
        _white_offsets = [0, 2, 4, 5, 7, 9, 11]
        num_white_keys = sum(
            1 for oct in range(self.START_OCTAVE, self.END_OCTAVE + 2)
            for off in (_white_offsets if oct <= self.END_OCTAVE else [0])
            if self.FIRST_NOTE <= oct * 12 + off <= self.LAST_NOTE
        )

        # Title
        title_frame = tk.Frame(root, bg=th.BG_ROOT)
        title_frame.pack(pady=(12, 6))
        tk.Label(title_frame, text="PythonSynth", font=th.FONT_TITLE,
                fg=th.TEXT_PRIMARY, bg=th.BG_ROOT).pack()
        # Accent underline echoes the piano bezel
        tk.Frame(title_frame, bg=th.ACCENT, height=2, width=160).pack(pady=(2, 0))

        # Row 1: all panels in one centered strip so they share the same height
        row1 = tk.Frame(root, bg=th.BG_ROOT)
        row1.pack(pady=(6, 2), padx=10)

        row1_inner = tk.Frame(row1, bg=th.BG_ROOT)
        row1_inner.pack(anchor='center')
        self._create_adsr_controls(row1_inner)
        self._create_oscillator_controls(row1_inner)
        self._create_lfo_controls(row1_inner)
        self._create_filter_controls(row1_inner)
        self._create_master_section(row1_inner)

        # Row 2: Effects (centered)
        row2 = tk.Frame(root, bg=th.BG_ROOT)
        row2.pack(pady=(2, 4), padx=10)
        self._create_effects_controls(row2)

        # Row 3: Piano + Transpose (centered)
        piano_outer = tk.Frame(root, bg=th.BG_ROOT)
        piano_outer.pack(pady=(6, 6), fill=tk.X)

        piano_center = tk.Frame(piano_outer, bg=th.BG_ROOT)
        piano_center.pack(anchor='center')

        piano_row = tk.Frame(piano_center, bg=th.BG_ROOT)
        piano_row.pack()

        self._create_transpose_slider(piano_row)

        canvas_width = num_white_keys * self.WHITE_KEY_WIDTH + 20
        # Piano bezel: accent ring → dark pinstripe → inset panel → canvas
        bezel_outer = tk.Frame(piano_row, bg=th.ACCENT)
        bezel_outer.pack(side=tk.LEFT, padx=(10, 0), pady=6)
        bezel_mid = tk.Frame(bezel_outer, bg=th.BORDER_SUBTLE)
        bezel_mid.pack(padx=2, pady=2)
        bezel_inner = tk.Frame(bezel_mid, bg=th.BG_INSET)
        bezel_inner.pack(padx=1, pady=1)

        self.canvas = Canvas(bezel_inner, bg=th.BG_INSET, highlightthickness=0,
                           width=canvas_width, height=140)
        self.canvas.pack(padx=8, pady=8)

        self.canvas.bind('<Button-1>', self._on_mouse_down)
        self.canvas.bind('<ButtonRelease-1>', self._on_mouse_up)
        self.canvas.bind('<Motion>', self._on_mouse_motion)

        self._draw_piano()
        self._draw_piano_jewelry(canvas_width, 140)
        self._bind_keyboard()
        self._draw_kb_labels()

        info_frame = tk.Frame(piano_center, bg=th.BG_ROOT)
        info_frame.pack(pady=(8, 4))
        self.info_label = tk.Label(info_frame, text="Active voices: 0",
                                   font=th.FONT_LABEL, fg=th.ACCENT, bg=th.BG_ROOT)
        self.info_label.pack()
    
    # QWERTY key → semitone offset within the mapped octave
    # White keys: A=C, S=D, D=E, F=F, G=G, H=A, J=B, K=C(+1), L=D(+1)
    # Black keys: W=C#, E=D#, T=F#, Y=G#, U=A#, O=C#(+1)
    _KB_WHITE = {'a': 0, 's': 2, 'd': 4, 'f': 5, 'g': 7, 'h': 9, 'j': 11, 'k': 12, 'l': 14}
    _KB_BLACK = {'w': 1, 'e': 3, 't': 6, 'y': 8, 'u': 10, 'o': 13}
    _KB_ALL   = {**_KB_WHITE, **_KB_BLACK}
    # Display labels for each key (uppercase for readability)
    _KB_LABELS = {k: k.upper() for k in {**_KB_WHITE, **_KB_BLACK}}

    def _bind_keyboard(self):
        self.kb_octave = 4  # default: C4, near middle of 88-key range
        self._kb_held: set = set()          # keys currently held down

        self.root.bind('<KeyPress>',   self._on_key_press)
        self.root.bind('<KeyRelease>', self._on_key_release)
        self.root.bind('<space>',      lambda _: self._on_panic())

    def _kb_shift(self, direction: int):
        """Shift kb_octave by direction (±1). If at limit, transpose by ±12 instead."""
        new_oct = self.kb_octave + direction
        if self.START_OCTAVE <= new_oct <= self.END_OCTAVE - 1:
            self.kb_octave = new_oct
            self._draw_kb_labels()
        else:
            # At octave limit — try transposing by one octave
            cur_octs = self.transpose_scale.get()
            new_octs = cur_octs + direction
            if -2 <= new_octs <= 2:
                self.transpose_scale.set(new_octs)
                self.transpose = new_octs * 12
                self.transpose_label.config(text=f"{new_octs:+d} oct")
                self._draw_c_labels()

    def _on_key_press(self, event):
        ch = event.char.lower() if event.char else ''
        if ch == 'z':
            self._kb_shift(-1)
            return
        if ch == 'x':
            self._kb_shift(+1)
            return
        if ch in self._KB_ALL and ch not in self._kb_held:
            self._kb_held.add(ch)
            semitone = self._KB_ALL[ch]
            extra_oct = semitone // 12
            raw_note = (self.kb_octave + extra_oct) * 12 + (semitone % 12)
            note = self._apply_transpose(raw_note)
            self.on_note_on(note, 100)
            if raw_note in self.note_key_map:
                key_id = self.note_key_map[raw_note]
                self.active_keys[raw_note] = key_id
                self._highlight_key(key_id, True)

    def _on_key_release(self, event):
        ch = event.char.lower() if event.char else ''
        if ch in self._KB_ALL and ch in self._kb_held:
            self._kb_held.discard(ch)
            semitone = self._KB_ALL[ch]
            extra_oct = semitone // 12
            raw_note = (self.kb_octave + extra_oct) * 12 + (semitone % 12)
            note = self._apply_transpose(raw_note)
            self.on_note_off(note)
            if raw_note in self.active_keys:
                self._highlight_key(self.active_keys.pop(raw_note), False)

    def _draw_kb_labels(self):
        """Draw (or redraw) QWERTY shortcut labels on the piano canvas keys."""
        self.canvas.delete('kb_label')

        # Build a lookup: midi_note → canvas x-centre, y position
        # Reconstruct key positions the same way _draw_piano does
        white_midi_offsets = [0, 2, 4, 5, 7, 9, 11]
        x_pos = 10

        # Map midi_note -> (cx, cy, is_black)
        note_cx: dict = {}
        for octave in range(self.START_OCTAVE, self.END_OCTAVE + 1):
            for wi in range(len(self.WHITE_KEYS)):
                midi_note = octave * 12 + white_midi_offsets[wi]
                if midi_note < self.FIRST_NOTE or midi_note > self.LAST_NOTE:
                    continue
                cx = x_pos + self.WHITE_KEY_WIDTH // 2
                cy = 10 + self.WHITE_KEY_HEIGHT - 14
                note_cx[midi_note] = (cx, cy, False)

                # Black key to the right of this white key
                black_offsets = {0: 1, 1: 3, 3: 6, 4: 8, 5: 10}
                if wi in black_offsets:
                    bx = x_pos + self.WHITE_KEY_WIDTH - self.BLACK_KEY_WIDTH // 2 + self.BLACK_KEY_WIDTH // 2
                    by = 10 + self.BLACK_KEY_HEIGHT - 10
                    black_note = octave * 12 + black_offsets[wi]
                    if self.FIRST_NOTE <= black_note <= self.LAST_NOTE:
                        note_cx[black_note] = (bx, by, True)

                x_pos += self.WHITE_KEY_WIDTH

        # Trailing C (mirrors _draw_piano)
        trailing_note = (self.END_OCTAVE + 1) * 12
        if trailing_note <= self.LAST_NOTE:
            note_cx[trailing_note] = (x_pos + self.WHITE_KEY_WIDTH // 2, 10 + self.WHITE_KEY_HEIGHT - 14, False)

        for ch, semitone in self._KB_ALL.items():
            extra_oct = semitone // 12
            note = (self.kb_octave + extra_oct) * 12 + (semitone % 12)
            if note not in note_cx:
                continue
            cx, cy, is_black = note_cx[note]
            color = th.ACCENT if not is_black else th.ACCENT_MUTED
            self.canvas.create_text(
                cx, cy,
                text=ch.upper(),
                font=(th.FONT_FAMILY, 7, 'bold'),
                fill=color,
                tags='kb_label',
            )

    def _create_adsr_controls(self, parent):
        """ADSR envelope section: 4 knobs on top, envelope graph below."""
        section = tk.Frame(parent, bg=th.BG_PANEL,
                           highlightbackground=th.BORDER_SUBTLE, highlightthickness=1)
        section.pack(side=tk.LEFT, padx=8, pady=6, fill=tk.BOTH, expand=True)

        tk.Label(section, text="ADSR Envelope", font=th.FONT_SECTION,
                 fg=th.ACCENT, bg=th.BG_PANEL).pack(pady=(8, 4), padx=10, anchor='w')

        knob_row = tk.Frame(section, bg=th.BG_PANEL)
        knob_row.pack(padx=10, pady=(2, 4))

        self.attack_scale = Knob(knob_row, from_=1, to=500, resolution=1,
                                 label="Attack", value_format="{:.0f} ms",
                                 initial=int(self.attack * 1000),
                                 command=self._on_adsr_changed,
                                 logarithmic=True)
        self.attack_scale.set(int(self.attack * 1000))
        self.attack_scale.grid(row=0, column=0, padx=6, pady=4)
        self._register_assignable('attack', self.attack_scale, self._on_adsr_changed)

        self.decay_scale = Knob(knob_row, from_=1, to=500, resolution=1,
                                label="Decay", value_format="{:.0f} ms",
                                initial=int(self.decay * 1000),
                                command=self._on_adsr_changed,
                                logarithmic=True)
        self.decay_scale.set(int(self.decay * 1000))
        self.decay_scale.grid(row=0, column=1, padx=6, pady=4)
        self._register_assignable('decay', self.decay_scale, self._on_adsr_changed)

        self.sustain_scale = Knob(knob_row, from_=0, to=100, resolution=1,
                                  label="Sustain", value_format="{:.0f}%",
                                  initial=int(self.sustain * 100),
                                  command=self._on_adsr_changed)
        self.sustain_scale.set(int(self.sustain * 100))
        self.sustain_scale.grid(row=0, column=2, padx=6, pady=4)
        self._register_assignable('sustain', self.sustain_scale, self._on_adsr_changed)

        self.release_scale = Knob(knob_row, from_=1, to=2000, resolution=1,
                                  label="Release", value_format="{:.0f} ms",
                                  initial=int(self.release * 1000),
                                  command=self._on_adsr_changed,
                                  logarithmic=True)
        self.release_scale.set(int(self.release * 1000))
        self.release_scale.grid(row=0, column=3, padx=6, pady=4)
        self._register_assignable('release', self.release_scale, self._on_adsr_changed)

        self.envelope_canvas = Canvas(section, bg=th.BG_INSET, highlightthickness=1,
                                      highlightbackground=th.BORDER_SUBTLE,
                                      width=320, height=140)
        self.envelope_canvas.pack(padx=10, pady=(2, 10), fill=tk.BOTH, expand=True)

        self.envelope_canvas.bind('<Configure>', lambda _: self._draw_envelope())


    def _apply_transpose(self, raw_note: int) -> int:
        return max(0, min(127, raw_note + self.transpose))

    def _create_transpose_slider(self, parent: tk.Frame):
        frame = tk.Frame(parent, bg=th.BG_PANEL,
                         highlightbackground=th.BORDER_SUBTLE, highlightthickness=1)
        frame.pack(side=tk.LEFT, padx=(0, 6), pady=2, fill=tk.Y)

        tk.Label(frame, text="Transpose", font=th.FONT_SUBGROUP,
                 fg=th.ACCENT_MUTED, bg=th.BG_PANEL).pack(pady=(6, 2))

        # from_=2 at top (higher pitch), to=-2 at bottom; each step = 1 octave
        self.transpose_scale = Scale(
            frame, from_=2, to=-2, orient=tk.VERTICAL,
            bg=th.BG_PANEL, fg=th.TEXT_PRIMARY, length=200,
            troughcolor=th.BG_INSET, activebackground=th.ACCENT_MUTED,
            highlightthickness=0, bd=0,
            tickinterval=1, resolution=1,
            command=self._on_transpose_changed,
        )
        self.transpose_scale.set(0)
        self.transpose_scale.pack(padx=6)

        self.transpose_label = tk.Label(
            frame, text="0 oct", font=th.FONT_VALUE,
            fg=th.TEXT_SECONDARY, bg=th.BG_PANEL,
        )
        self.transpose_label.pack(pady=(0, 6))

    def _on_transpose_changed(self, _):
        octs = self.transpose_scale.get()
        self.transpose = octs * 12
        self.transpose_label.config(text=f"{octs:+d} oct")
        self._draw_c_labels()

    def _on_adsr_changed(self, value):
        """Handle ADSR slider changes."""
        self.attack  = self._eff(self.attack_scale,  'attack')  / 1000.0
        self.decay   = self._eff(self.decay_scale,   'decay')   / 1000.0
        self.sustain = self._eff(self.sustain_scale, 'sustain') / 100.0
        self.release = self._eff(self.release_scale, 'release') / 1000.0

        # Notify synthesizer
        self.on_adsr_change(self.attack, self.decay, self.sustain, self.release)

        # Redraw envelope
        self._draw_envelope()

    def _create_lfo_controls(self, parent):
        """LFO panel: dropdown selecting 1 of 3 LFOs, with rate + amount knobs."""
        section = tk.Frame(parent, bg=th.BG_PANEL,
                           highlightbackground=th.BORDER_SUBTLE, highlightthickness=1)
        section.pack(side=tk.LEFT, padx=8, pady=6, fill=tk.BOTH, expand=True)

        tk.Label(section, text="LFO", font=th.FONT_SECTION,
                 fg=th.ACCENT, bg=th.BG_PANEL).pack(pady=(8, 4), padx=10, anchor='w')

        # Dropdown — OptionMenu (ttk.Combobox would look nicer but needs ttk styling).
        select_row = tk.Frame(section, bg=th.BG_PANEL)
        select_row.pack(padx=10, pady=(0, 13))
        self._lfo_select_var = tk.StringVar(value="LFO 1")
        opts = ["LFO 1", "LFO 2", "LFO 3"]
        om = tk.OptionMenu(select_row, self._lfo_select_var, *opts,
                           command=lambda _: self._on_lfo_select())
        om.config(bg=th.BG_INSET, fg=th.TEXT_PRIMARY,
                  activebackground=th.ACCENT, activeforeground=th.TEXT_PRIMARY,
                  highlightthickness=0, bd=0, font=th.FONT_LABEL_BOLD)
        om["menu"].config(bg=th.BG_PANEL, fg=th.TEXT_PRIMARY,
                          activebackground=th.ACCENT,
                          activeforeground=th.TEXT_PRIMARY)
        om.pack()

        knob_row = tk.Frame(section, bg=th.BG_PANEL)
        knob_row.pack(padx=10, pady=(2, 10))

        def _rate_fmt(v):
            hz = self._lfo_pct_to_hz(v)
            return f"{hz:.2f} Hz" if hz < 10 else f"{hz:.1f} Hz"

        initial = self._lfo_slot_state[0]
        self.lfo_rate_knob = Knob(
            knob_row, from_=0, to=100, resolution=1,
            label="Rate", value_format=_rate_fmt,
            initial=initial["rate"],
            command=self._on_lfo_params_changed,
        )
        self.lfo_rate_knob.set(initial["rate"])
        self.lfo_rate_knob.grid(row=0, column=0, padx=6, pady=4)

        self.lfo_amp_knob = Knob(
            knob_row, from_=0, to=100, resolution=1,
            label="Amount", value_format="{:.0f}%",
            initial=initial["amp"],
            command=self._on_lfo_params_changed,
        )
        self.lfo_amp_knob.set(initial["amp"])
        self.lfo_amp_knob.grid(row=1, column=0, padx=6, pady=4)

        # LFO knobs are NOT right-clickable (intentionally).
        # They are not registered in self._assignable.

        # Push initial values to the bank.
        self._on_lfo_params_changed(None)

    def _on_lfo_select(self):
        """Dropdown changed: save current knob values to the old slot, load new."""
        new_idx = ["LFO 1", "LFO 2", "LFO 3"].index(self._lfo_select_var.get())
        # Save current knob positions to the slot we're leaving.
        self._lfo_slot_state[self._lfo_selected] = {
            "rate": float(self.lfo_rate_knob.get()),
            "amp":  float(self.lfo_amp_knob.get()),
        }
        self._lfo_selected = new_idx
        nxt = self._lfo_slot_state[new_idx]
        # Load new slot into the knobs (fires _on_lfo_params_changed via command).
        self.lfo_rate_knob.set(nxt["rate"])
        self.lfo_amp_knob.set(nxt["amp"])

    def _on_lfo_params_changed(self, _):
        """Rate / Amount knob changed: write to the currently-selected LFO."""
        idx = self._lfo_selected
        rate_hz = self._lfo_pct_to_hz(float(self.lfo_rate_knob.get()))
        amp = float(self.lfo_amp_knob.get()) / 100.0
        self.lfo_bank.lfos[idx].rate_hz = rate_hz
        self.lfo_bank.lfos[idx].amplitude = amp
        self._lfo_slot_state[idx] = {
            "rate": float(self.lfo_rate_knob.get()),
            "amp":  float(self.lfo_amp_knob.get()),
        }

    def _create_filter_controls(self, parent):
        """Low-pass filter section: Cutoff + Q as knobs."""
        section = tk.Frame(parent, bg=th.BG_PANEL,
                           highlightbackground=th.BORDER_SUBTLE, highlightthickness=1)
        section.pack(side=tk.LEFT, padx=8, pady=6, fill=tk.BOTH, expand=True)

        tk.Label(section, text="LPF", font=th.FONT_SECTION,
                 fg=th.ACCENT, bg=th.BG_PANEL).pack(pady=(8, 4), padx=10, anchor='w')

        # Spacer matching Master btn_row height (30px) + pady=(0,6) = 38px gap, same as Master
        tk.Frame(section, bg=th.BG_PANEL, height=30).pack(padx=10, pady=(0, 6))

        knob_row = tk.Frame(section, bg=th.BG_PANEL)
        knob_row.pack(padx=10, pady=(2, 10))

        def _cutoff_fmt(v):
            hz = 20.0 * (1000.0 ** (v / 100.0))
            return f"{hz:.0f} Hz" if hz < 1000 else f"{hz/1000:.2g} kHz"

        self.lpf_cutoff_scale = Knob(knob_row, from_=0, to=100, resolution=1,
                                     label="Cutoff", value_format=_cutoff_fmt,
                                     initial=100,
                                     command=self._on_lpf_changed)
        self.lpf_cutoff_scale.set(100)
        self.lpf_cutoff_scale.grid(row=0, column=0, padx=6, pady=4)
        self._register_assignable('lpf_cutoff', self.lpf_cutoff_scale, self._on_lpf_changed)

        self.lpf_q_scale = Knob(knob_row, from_=0.5, to=12.0, resolution=0.1,
                                label="Reso", value_format="Q {:.1f}",
                                initial=0.7,
                                command=self._on_lpf_changed)
        self.lpf_q_scale.set(0.7)
        self.lpf_q_scale.grid(row=1, column=0, padx=6, pady=4)
        self._register_assignable('lpf_q', self.lpf_q_scale, self._on_lpf_changed)

    def _create_effects_controls(self, parent):
        """Effects section: Reverb, Delay, Chorus, and Bitcrusher sub-groups."""
        section = tk.Frame(parent, bg=th.BG_PANEL,
                           highlightbackground=th.BORDER_SUBTLE, highlightthickness=1)
        section.pack(side=tk.LEFT, padx=8, pady=6, fill=tk.Y)

        tk.Label(section, text="Effects", font=th.FONT_SECTION,
                 fg=th.ACCENT, bg=th.BG_PANEL).pack(pady=(8, 4), padx=10, anchor='w')

        groups_row = tk.Frame(section, bg=th.BG_PANEL)
        groups_row.pack(padx=10, pady=(2, 10))

        def _subgroup(parent_, title: str) -> tk.Frame:
            """Sub-group: 1px accent top border + uppercase caption, no box."""
            wrap = tk.Frame(parent_, bg=th.BG_PANEL)
            wrap.pack(side=tk.LEFT, padx=8, pady=2, anchor='n')
            tk.Frame(wrap, bg=th.ACCENT, height=1).pack(fill=tk.X, padx=2)
            tk.Label(wrap, text=title.upper(), font=th.FONT_SUBGROUP,
                     fg=th.ACCENT_MUTED, bg=th.BG_PANEL).pack(pady=(3, 2))
            body = tk.Frame(wrap, bg=th.BG_PANEL)
            body.pack()
            return body

        # ── Distortion ────────────────────────────────────────────────────
        dist = _subgroup(groups_row, "Distortion")

        self.dist_drive_scale = Knob(dist, from_=1, to=20, resolution=0.1,
                                     label="Drive", value_format="{:.1f}x",
                                     initial=1,
                                     command=self._on_distortion_changed)
        self.dist_drive_scale.set(1)
        self.dist_drive_scale.grid(row=0, column=0, padx=5, pady=4)
        self._register_assignable('dist_drive', self.dist_drive_scale, self._on_distortion_changed)

        self.dist_wet_scale = Knob(dist, from_=0, to=100, resolution=1,
                                   label="Wet", value_format="{:.0f}%",
                                   initial=0,
                                   command=self._on_distortion_changed)
        self.dist_wet_scale.set(0)
        self.dist_wet_scale.grid(row=0, column=1, padx=5, pady=4)
        self._register_assignable('dist_wet', self.dist_wet_scale, self._on_distortion_changed)

        # ── Reverb ────────────────────────────────────────────────────────
        rev = _subgroup(groups_row, "Reverb")
        for col, (lbl, attr, kid, default) in enumerate([
            ("Room", "reverb_room_scale", "reverb_room", 50),
            ("Damp", "reverb_damp_scale", "reverb_damp", 50),
            ("Wet",  "reverb_wet_scale",  "reverb_wet",   0),
        ]):
            k = Knob(rev, from_=0, to=100, resolution=1,
                     label=lbl, value_format="{:.0f}%",
                     initial=default,
                     command=self._on_reverb_changed)
            k.set(default)
            k.grid(row=0, column=col, padx=5, pady=4)
            setattr(self, attr, k)
            self._register_assignable(kid, k, self._on_reverb_changed)

        # ── Delay ─────────────────────────────────────────────────────────
        dly = _subgroup(groups_row, "Delay")

        self.delay_time_scale = Knob(dly, from_=10, to=1000, resolution=10,
                                     label="Time", value_format="{:.0f}ms",
                                     initial=250,
                                     command=self._on_delay_changed)
        self.delay_time_scale.set(250)
        self.delay_time_scale.grid(row=0, column=0, padx=5, pady=4)

        self.delay_fb_scale = Knob(dly, from_=0, to=90, resolution=1,
                                   label="Feedback", value_format="{:.0f}%",
                                   initial=40,
                                   command=self._on_delay_changed)
        self.delay_fb_scale.set(40)
        self.delay_fb_scale.grid(row=0, column=1, padx=5, pady=4)
        self._register_assignable('delay_fb', self.delay_fb_scale, self._on_delay_changed)

        self.delay_wet_scale = Knob(dly, from_=0, to=100, resolution=1,
                                    label="Wet", value_format="{:.0f}%",
                                    initial=0,
                                    command=self._on_delay_changed)
        self.delay_wet_scale.set(0)
        self.delay_wet_scale.grid(row=0, column=2, padx=5, pady=4)
        self._register_assignable('delay_wet', self.delay_wet_scale, self._on_delay_changed)

        # ── Chorus ────────────────────────────────────────────────────────
        cho = _subgroup(groups_row, "Chorus")

        self.chorus_rate_scale = Knob(cho, from_=0, to=100, resolution=1,
                                      label="Rate", value_format="{:.0f}%",
                                      initial=30,
                                      command=self._on_chorus_changed)
        self.chorus_rate_scale.set(30)
        self.chorus_rate_scale.grid(row=0, column=0, padx=5, pady=4)
        self._register_assignable('chorus_rate', self.chorus_rate_scale, self._on_chorus_changed)

        self.chorus_depth_scale = Knob(cho, from_=0, to=100, resolution=1,
                                       label="Depth", value_format="{:.0f}%",
                                       initial=50,
                                       command=self._on_chorus_changed)
        self.chorus_depth_scale.set(50)
        self.chorus_depth_scale.grid(row=0, column=1, padx=5, pady=4)
        self._register_assignable('chorus_depth', self.chorus_depth_scale, self._on_chorus_changed)

        self.chorus_wet_scale = Knob(cho, from_=0, to=100, resolution=1,
                                     label="Wet", value_format="{:.0f}%",
                                     initial=0,
                                     command=self._on_chorus_changed)
        self.chorus_wet_scale.set(0)
        self.chorus_wet_scale.grid(row=0, column=2, padx=5, pady=4)
        self._register_assignable('chorus_wet', self.chorus_wet_scale, self._on_chorus_changed)

        # ── Bitcrusher ────────────────────────────────────────────────────
        bc = _subgroup(groups_row, "Bitcrusher")

        self.bc_bits_scale = Knob(bc, from_=1, to=16, resolution=1,
                                  label="Bits", value_format="{:.0f} bit",
                                  initial=16,
                                  command=self._on_bitcrusher_changed)
        self.bc_bits_scale.set(16)
        self.bc_bits_scale.grid(row=0, column=0, padx=5, pady=4)
        self._register_assignable('bc_bits', self.bc_bits_scale, self._on_bitcrusher_changed)

        self.bc_ds_scale = Knob(bc, from_=1, to=32, resolution=1,
                                label="Downsamp", value_format="÷{:.0f}",
                                initial=1,
                                command=self._on_bitcrusher_changed)
        self.bc_ds_scale.set(1)
        self.bc_ds_scale.grid(row=0, column=1, padx=5, pady=4)
        self._register_assignable('bc_ds', self.bc_ds_scale, self._on_bitcrusher_changed)

        self.bc_wet_scale = Knob(bc, from_=0, to=100, resolution=1,
                                 label="Wet", value_format="{:.0f}%",
                                 initial=0,
                                 command=self._on_bitcrusher_changed)
        self.bc_wet_scale.set(0)
        self.bc_wet_scale.grid(row=0, column=2, padx=5, pady=4)
        self._register_assignable('bc_wet', self.bc_wet_scale, self._on_bitcrusher_changed)

    def _create_master_section(self, parent):
        """Master section: Volume knob + compact vertical level meter."""
        METER_W, METER_H, MARGIN = 28, 120, 3

        section = tk.Frame(parent, bg=th.BG_PANEL,
                           highlightbackground=th.BORDER_SUBTLE, highlightthickness=1)
        section.pack(side=tk.LEFT, padx=8, pady=6, fill=tk.BOTH, expand=True)

        tk.Label(section, text="Master", font=th.FONT_SECTION,
                 fg=th.ACCENT, bg=th.BG_PANEL).pack(pady=(8, 4), padx=10, anchor='w')

        # PANIC + MONO side by side
        btn_row = tk.Frame(section, bg=th.BG_PANEL)
        btn_row.pack(pady=(0, 6), padx=10)

        tk.Button(btn_row, text="PANIC", font=th.FONT_LABEL_BOLD,
                  fg=th.TEXT_PRIMARY, bg=th.DANGER, activebackground=th.DANGER_ACTIVE,
                  relief=tk.FLAT, bd=0, padx=8, pady=3,
                  command=self._on_panic).pack(side=tk.LEFT, padx=(0, 4))

        self._mono_btn = tk.Label(btn_row, text="MONO", font=th.FONT_LABEL_BOLD,
                                  fg=th.TEXT_SECONDARY, bg=th.BG_INSET,
                                  padx=8, pady=3, cursor='hand2',
                                  highlightthickness=1, highlightbackground=th.BORDER_SUBTLE)
        self._mono_btn.pack(side=tk.LEFT)
        self._mono_btn.bind('<Button-1>', lambda _: self._on_mono_toggle())

        # Volume + Legato knobs stacked vertically (mirrors LFO Rate/Amount layout)
        knob_row = tk.Frame(section, bg=th.BG_PANEL)
        knob_row.pack(padx=10, pady=(2, 4))

        self.volume_scale = Knob(knob_row, from_=0, to=100, resolution=1,
                                 label="Volume", value_format="{:.0f}%",
                                 initial=70,
                                 command=self._on_volume_changed)
        self.volume_scale.set(70)
        self.volume_scale.grid(row=0, column=0, padx=6, pady=4)
        self._register_assignable('volume', self.volume_scale, self._on_volume_changed)
        self._on_volume_changed(None)

        # Portamento knob (only meaningful in mono mode)
        self.legato_knob = Knob(knob_row, from_=0, to=100, resolution=1,
                                label="Portamento", value_format="{:.0f}%",
                                initial=0,
                                command=self._on_legato_changed)
        self.legato_knob.set(0)
        self.legato_knob.grid(row=1, column=0, padx=6, pady=4)

        self.gain_canvas = Canvas(section, bg=th.BG_INSET, highlightthickness=1,
                                  highlightbackground=th.BORDER_SUBTLE,
                                  width=METER_W, height=METER_H)
        self.gain_canvas.pack(padx=8, pady=(0, 4))

        self.level_label = tk.Label(section, text="0%",
                                    font=th.FONT_VALUE, fg=th.TEXT_SECONDARY,
                                    bg=th.BG_PANEL, justify=tk.CENTER)
        self.level_label.pack(pady=(0, 8))

        # Pre-create persistent canvas items to avoid flicker from delete/recreate
        mh = METER_H - MARGIN * 2
        clip_y  = MARGIN + mh * (1.0 - 0.9)
        warn_y  = MARGIN + mh * (1.0 - 0.7)
        self._m = MARGIN
        self._mw = METER_W
        self._mh = METER_H

        self._gc_bg    = self.gain_canvas.create_rectangle(MARGIN, MARGIN, METER_W - MARGIN, METER_H - MARGIN,
                                                           fill=th.BG_INSET, outline=th.BORDER_SUBTLE)
        self._gc_warn  = self.gain_canvas.create_rectangle(MARGIN, clip_y, METER_W - MARGIN, warn_y,
                                                           fill=th.METER_WARN_BG, outline='')
        self._gc_clip  = self.gain_canvas.create_rectangle(MARGIN, MARGIN, METER_W - MARGIN, clip_y,
                                                           fill=th.METER_CLIP_BG, outline='')
        self._gc_bar   = self.gain_canvas.create_rectangle(MARGIN, METER_H - MARGIN, METER_W - MARGIN, METER_H - MARGIN,
                                                           fill=th.METER_SAFE, outline='')
        self._gc_l70   = self.gain_canvas.create_line(MARGIN, warn_y, METER_W - MARGIN, warn_y,
                                                      fill=th.METER_GUIDE, width=1)
        self._gc_l95   = self.gain_canvas.create_line(MARGIN, MARGIN + mh * (1.0 - 0.95), METER_W - MARGIN,
                                                      MARGIN + mh * (1.0 - 0.95), fill=th.METER_GUIDE, width=1)

    def midi_note_on(self, note: int, velocity: int):
        self.on_note_on(note, velocity)
        if note in self.note_key_map:
            key_id = self.note_key_map[note]
            self.active_keys[note] = key_id
            self._highlight_key(key_id, True)

    def midi_note_off(self, note: int):
        self.on_note_off(note)
        if note in self.active_keys:
            self._highlight_key(self.active_keys.pop(note), False)

    def _on_panic(self):
        self.on_panic()
        for key_id in list(self.active_keys.values()):
            self._highlight_key(key_id, False)
        self.active_keys.clear()
        self.mouse_down_note = None
        self._kb_held.clear()

    def _on_mono_toggle(self):
        self._mono_enabled = not self._mono_enabled
        if self._mono_enabled:
            self._mono_btn.config(bg=th.ACCENT, fg=th.TEXT_PRIMARY)
        else:
            self._mono_btn.config(bg=th.BG_INSET, fg=th.TEXT_SECONDARY)
        if hasattr(self, '_on_mono_change'):
            self._on_mono_change(self._mono_enabled)

    def _on_legato_changed(self, _=None):
        if hasattr(self, '_on_legato_change'):
            self._on_legato_change(self.legato_knob.get() / 100.0)

    # ── LFO routing helpers ──────────────────────────────────────────────

    # Rate taper: 0..100 on the knob -> 0.05..20 Hz on the LFO.
    _LFO_RATE_MIN_HZ = 0.05
    _LFO_RATE_MAX_HZ = 20.0

    @classmethod
    def _lfo_pct_to_hz(cls, pct: float) -> float:
        t = max(0.0, min(1.0, pct / 100.0))
        ratio = cls._LFO_RATE_MAX_HZ / cls._LFO_RATE_MIN_HZ
        return cls._LFO_RATE_MIN_HZ * (ratio ** t)

    @classmethod
    def _lfo_rate_hz_to_pct(cls, hz: float) -> float:
        import math as _m
        hz = max(cls._LFO_RATE_MIN_HZ, min(cls._LFO_RATE_MAX_HZ, hz))
        ratio = cls._LFO_RATE_MAX_HZ / cls._LFO_RATE_MIN_HZ
        return 100.0 * _m.log(hz / cls._LFO_RATE_MIN_HZ) / _m.log(ratio)

    def _register_assignable(self, knob_id: str, knob, handler: Callable):
        """Register a knob as an LFO-modulation target (right-click menu + visual animation)."""
        self._assignable[knob_id] = (knob, handler)
        knob.on_right_click = lambda event, kid=knob_id: self._show_lfo_menu(kid, event)

    def _eff(self, knob, knob_id: str) -> float:
        """Return knob's raw value with any LFO offset applied and clamped."""
        raw = float(knob.get())
        return self.lfo_bank.effective_value(knob_id, raw, float(knob._from), float(knob._to))

    def _show_lfo_menu(self, knob_id: str, event):
        menu = tk.Menu(self.root, tearoff=0,
                       bg=th.BG_PANEL, fg=th.TEXT_PRIMARY,
                       activebackground=th.ACCENT, activeforeground=th.TEXT_PRIMARY)
        current = self.lfo_bank.route_of(knob_id)
        for i in range(self.lfo_bank.NUM_LFOS):
            label = f"Assign to LFO {i + 1}"
            if current == i:
                label = f"✓ {label}"
            menu.add_command(label=label,
                             command=lambda idx=i: self._assign_lfo(knob_id, idx))
        if current is not None:
            menu.add_separator()
            menu.add_command(label="Remove LFO",
                             command=lambda: self._unassign_lfo(knob_id))
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _assign_lfo(self, knob_id: str, lfo_index: int):
        self.lfo_bank.assign(knob_id, lfo_index)

    def _unassign_lfo(self, knob_id: str):
        self.lfo_bank.unassign(knob_id)
        entry = self._assignable.get(knob_id)
        if entry is None:
            return
        knob, handler = entry
        knob.clear_display_override()
        try:
            handler(None)
        except Exception as e:
            print(f"LFO unassign handler error: {type(e).__name__}: {e}")

    def update_lfo_visuals(self):
        """GUI-poll hook: re-apply modulated params, animate modulated knobs."""
        handlers = set()
        for knob_id in list(self.lfo_bank.routes.keys()):
            entry = self._assignable.get(knob_id)
            if entry is not None:
                handlers.add(entry[1])
        # Runs on the background update_gui thread. Handlers must suppress
        # tk canvas work here — concurrent draws with the main loop crash tk.
        self._lfo_polling = True
        try:
            for h in handlers:
                try:
                    h(None)
                except Exception as e:
                    print(f"LFO handler error: {type(e).__name__}: {e}")
        finally:
            self._lfo_polling = False

        routes = self.lfo_bank.routes
        for knob_id, (knob, _h) in self._assignable.items():
            try:
                if knob_id in routes:
                    eff = self.lfo_bank.effective_value(
                        knob_id, float(knob.get()),
                        float(knob._from), float(knob._to))
                    knob.set_display_override(eff)
                else:
                    knob.clear_display_override()
            except Exception:
                pass

    def _on_volume_changed(self, _):
        self.on_volume_change(self._eff(self.volume_scale, 'volume') / 100.0 * (3.0 / 7.0))

    def _on_lpf_changed(self, _):
        t = self._eff(self.lpf_cutoff_scale, 'lpf_cutoff') / 100.0
        cutoff = 20.0 * (1000.0 ** t)  # log mapping: 20 Hz → 20000 Hz
        q = self._eff(self.lpf_q_scale, 'lpf_q')
        self.on_lpf_change(cutoff, q)

    def _on_distortion_changed(self, _):
        self.on_distortion_change(
            self._eff(self.dist_drive_scale, 'dist_drive'),
            self._eff(self.dist_wet_scale,   'dist_wet') / 100.0,
        )

    def _on_reverb_changed(self, _):
        self.on_reverb_change(
            self._eff(self.reverb_room_scale, 'reverb_room') / 100.0,
            self._eff(self.reverb_damp_scale, 'reverb_damp') / 100.0,
            self._eff(self.reverb_wet_scale,  'reverb_wet')  / 100.0,
        )

    def _on_delay_changed(self, _):
        self.on_delay_change(
            float(self.delay_time_scale.get()),
            self._eff(self.delay_fb_scale,  'delay_fb')  / 100.0,
            self._eff(self.delay_wet_scale, 'delay_wet') / 100.0,
        )

    def _on_chorus_changed(self, _):
        # Rate knob: 0–100% → 0.05–8 Hz (log-ish feel)
        rate_hz = 0.05 * (160.0 ** (self._eff(self.chorus_rate_scale, 'chorus_rate') / 100.0))
        self.on_chorus_change(
            rate_hz,
            self._eff(self.chorus_depth_scale, 'chorus_depth') / 100.0,
            self._eff(self.chorus_wet_scale,   'chorus_wet')   / 100.0,
        )

    def _on_bitcrusher_changed(self, _):
        self.on_bitcrusher_change(
            float(self._eff(self.bc_bits_scale, 'bc_bits')),
            int(self._eff(self.bc_ds_scale,    'bc_ds')),
            self._eff(self.bc_wet_scale, 'bc_wet') / 100.0,
        )

    # Harmonic amplitudes for each preset (16 bins, index 0 = fundamental)
    _WAVEFORM_PRESETS = {
        'sine':     lambda k: 1.0 if k == 0 else 0.0,
        'saw':      lambda k: 1.0 / (k + 1),
        'square':   lambda k: (1.0 / (k + 1)) if (k % 2 == 0) else 0.0,
        'triangle': lambda k: ((-1) ** (k // 2) / (k + 1) ** 2) if (k % 2 == 0) else 0.0,
        'semisine': lambda k: (1.0 / (k + 1)) if (k % 2 == 1) else (1.0 if k == 0 else 0.0),
    }

    def _make_preset_waveform(self, name: str) -> np.ndarray:
        fn = self._WAVEFORM_PRESETS[name]
        wt = np.array([fn(k) for k in range(16)], dtype=np.float32)
        peak = np.max(np.abs(wt))
        if peak > 0:
            wt /= peak
        return wt

    def _draw_preset_button_waveform(self, canvas: tk.Canvas, wt: np.ndarray):
        canvas.delete('all')
        w = canvas.winfo_width() or 54
        h = canvas.winfo_height() or 36
        N = 120
        phases = np.linspace(0, 2 * np.pi, N, endpoint=False)
        wave = np.zeros(N, dtype=np.float64)
        for k in range(16):
            if wt[k] != 0.0:
                wave += wt[k] * np.sin((k + 1) * phases)
        peak = max(float(np.max(np.abs(wave))), 1e-6)
        wave /= peak
        mx, my = 3, 4
        draw_w, draw_h = w - mx * 2, h - my * 2
        mid_y = my + draw_h // 2
        xs = mx + np.arange(N) * draw_w / (N - 1)
        ys = mid_y - wave * (draw_h / 2 - 2)
        coords = []
        for x, y in zip(xs, ys):
            coords.extend([float(x), float(y)])
        if len(coords) >= 4:
            canvas.create_line(coords, fill=th.ACCENT, width=1, smooth=False)

    def _apply_preset(self, name: str):
        wt = self._make_preset_waveform(name)
        if self._edit_slot == 'A':
            self._wt_a = wt.copy()
        else:
            self._wt_b = wt.copy()
        self._refresh_sliders_from_slot()
        self._recompute_current_wt()

    # -- Preset save/load bar ----------------------------------------------

    def _create_preset_bar(self, parent):
        """Dropdown to load a preset + save-as button. Folders render as submenus."""
        bar = tk.Frame(parent, bg=th.BG_PANEL)
        bar.pack(padx=10, pady=(0, 6), fill=tk.X)

        self._current_preset_name = "Standard"
        self._preset_menu_btn = tk.Menubutton(
            bar, text="Standard  ▾", font=th.FONT_LABEL_BOLD,
            bg=th.BG_INSET, fg=th.TEXT_PRIMARY,
            activebackground=th.ACCENT, activeforeground=th.TEXT_PRIMARY,
            relief='flat', bd=0, padx=10, pady=3, cursor='hand2',
            highlightthickness=1, highlightbackground=th.BORDER_SUBTLE,
        )
        self._preset_menu = tk.Menu(
            self._preset_menu_btn, tearoff=0,
            bg=th.BG_PANEL, fg=th.TEXT_PRIMARY,
            activebackground=th.ACCENT, activeforeground=th.TEXT_PRIMARY,
        )
        self._preset_menu_btn.config(menu=self._preset_menu)
        # Rebuild the menu each time it's about to post so new files appear.
        self._preset_menu_btn.bind('<Button-1>', lambda _e: self._rebuild_preset_menu())
        self._preset_menu_btn.pack(side=tk.LEFT)

        save_btn = tk.Label(
            bar, text="Save…", font=th.FONT_LABEL_BOLD,
            bg=th.BG_INSET, fg=th.TEXT_PRIMARY,
            padx=10, pady=3, cursor='hand2',
            highlightthickness=1, highlightbackground=th.BORDER_SUBTLE,
        )
        save_btn.bind('<Button-1>', lambda _e: self._save_preset_dialog())
        save_btn.pack(side=tk.LEFT, padx=(6, 0))

        self._rebuild_preset_menu()

    def _rebuild_preset_menu(self):
        """Repopulate the preset dropdown from disk. Folders → cascading submenus."""
        menu = self._preset_menu
        menu.delete(0, 'end')
        root = _presets.presets_root()
        paths = _presets.scan_presets(root)
        if not paths:
            menu.add_command(label="(no presets yet)", state='disabled')
            return

        # Build a nested dict: folder tree of relative path parts.
        tree: dict = {}
        for p in paths:
            rel = p.relative_to(root)
            parts = rel.parts
            node = tree
            for d in parts[:-1]:
                node = node.setdefault(d, {})
            node.setdefault('__files__', []).append((parts[-1], p))

        self._populate_preset_menu(menu, tree)

    def _populate_preset_menu(self, menu: tk.Menu, node: dict):
        for name in sorted(k for k in node.keys() if k != '__files__'):
            submenu = tk.Menu(
                menu, tearoff=0,
                bg=th.BG_PANEL, fg=th.TEXT_PRIMARY,
                activebackground=th.ACCENT, activeforeground=th.TEXT_PRIMARY,
            )
            self._populate_preset_menu(submenu, node[name])
            menu.add_cascade(label=name, menu=submenu)
        for fname, path in sorted(node.get('__files__', []), key=lambda t: t[0].lower()):
            label = fname[:-5] if fname.lower().endswith('.json') else fname
            menu.add_command(label=label,
                             command=lambda p=path: self._load_preset_from(p))

    def _save_preset_dialog(self):
        root = _presets.presets_root()
        root.mkdir(parents=True, exist_ok=True)
        path = filedialog.asksaveasfilename(
            title="Save preset",
            initialdir=str(root),
            defaultextension=".json",
            filetypes=[("Preset JSON", "*.json")],
        )
        if not path:
            return
        try:
            data = _presets.capture_state(self)
            data["name"] = Path(path).stem
            _presets.save_preset(Path(path), data)
        except Exception as e:
            messagebox.showerror("Save preset failed",
                                 f"{type(e).__name__}: {e}")
            return
        self._set_preset_label(Path(path).stem)
        self._rebuild_preset_menu()

    def _set_preset_label(self, name: str):
        self._current_preset_name = name
        self._preset_menu_btn.config(text=f"{name}  ▾")

    def _load_preset_from(self, path: Path):
        try:
            data = _presets.load_preset(path)
            _presets.apply_state(self, data)
            label = path.stem
            self._set_preset_label(label)
        except Exception as e:
            messagebox.showerror("Load preset failed",
                                 f"{type(e).__name__}: {e}")

    def _refresh_sliders_from_slot(self):
        """Sync slider positions to the currently selected slot's harmonics."""
        wt = self._wt_a if self._edit_slot == 'A' else self._wt_b
        self._suppress_harmonic_callback = True
        try:
            for k, slider in enumerate(self.harmonic_sliders):
                slider.set(float(wt[k]))
        finally:
            self._suppress_harmonic_callback = False

    def _recompute_current_wt(self):
        """Compute the interpolated wavetable from A, B, and morph position; push to engine."""
        t = self._morph_pos / 31.0
        self.wavetable = ((1.0 - t) * self._wt_a + t * self._wt_b).astype(np.float32)
        # From the LFO poller thread, defer the redraw onto the tk main thread
        # — concurrent canvas ops with mainloop crash the app.
        if getattr(self, '_lfo_polling', False):
            try:
                self.waveform_canvas.after(0, self._draw_waveform)
            except Exception:
                pass
        else:
            self._draw_waveform()
        self.on_wavetable_change(self.wavetable.copy())

    def _on_slot_changed(self, name: str):
        if name == self._edit_slot:
            return
        self._edit_slot = name
        self._refresh_sliders_from_slot()
        self._update_slot_button_styles()
        self._draw_waveform()

    def _update_slot_button_styles(self):
        for name, lbl in self._ab_buttons.items():
            if name == self._edit_slot:
                lbl.config(bg=th.ACCENT, fg=th.TEXT_PRIMARY)
            else:
                lbl.config(bg=th.BG_INSET, fg=th.TEXT_SECONDARY)

    def _on_morph_changed(self, value):
        # Use _eff so LFO modulation reaches the morph parameter.
        self._morph_pos = int(round(self._eff(self.morph_knob, 'morph')))
        self._recompute_current_wt()

    def _on_unison_changed(self, _=None):
        v = int(self.unison_voices_knob.get())
        d = float(self.unison_detune_knob.get())
        self.on_unison_change(v, d)

    def _create_oscillator_controls(self, parent):
        """Wavetable oscillator section: waveform preview + 16 harmonic sliders."""
        section = tk.Frame(parent, bg=th.BG_PANEL,
                           highlightbackground=th.BORDER_SUBTLE, highlightthickness=1)
        section.pack(side=tk.LEFT, padx=8, pady=6, fill=tk.BOTH, expand=True)

        tk.Label(section, text="Oscillator", font=th.FONT_SECTION,
                 fg=th.ACCENT, bg=th.BG_PANEL).pack(pady=(8, 4), padx=10, anchor='w')

        self._create_preset_bar(section)

        graph_row = tk.Frame(section, bg=th.BG_PANEL)
        graph_row.pack(padx=10, pady=(4, 6), fill=tk.BOTH, expand=True)

        # Left column: waveform preset buttons (centered) above the canvas
        graph_col = tk.Frame(graph_row, bg=th.BG_PANEL)
        graph_col.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        preset_row = tk.Frame(graph_col, bg=th.BG_PANEL)
        preset_row.pack(pady=(0, 4))  # centered by default (no anchor/fill)

        self._preset_btn_canvases = {}
        for name in ('sine', 'saw', 'square', 'triangle', 'semisine'):
            btn_frame = tk.Frame(preset_row, bg=th.BORDER_SUBTLE, cursor='hand2')
            btn_frame.pack(side=tk.LEFT, padx=3)
            c = tk.Canvas(btn_frame, bg=th.BG_INSET, highlightthickness=0,
                          width=54, height=36)
            c.pack(padx=1, pady=1)
            wt = self._make_preset_waveform(name)
            c.bind('<Configure>', lambda _, cv=c, w=wt:
                   self._draw_preset_button_waveform(cv, w))
            c.bind('<Button-1>', lambda _, n=name: self._apply_preset(n))
            btn_frame.bind('<Button-1>', lambda _, n=name: self._apply_preset(n))
            self._preset_btn_canvases[name] = c

        self.waveform_canvas = tk.Canvas(
            graph_col, bg=th.BG_INSET, highlightthickness=1,
            highlightbackground=th.BORDER_SUBTLE, width=380, height=120,
        )
        self.waveform_canvas.pack(fill=tk.BOTH, expand=True)

        # A/B slot-select buttons placed inside the bottom-left of the canvas.
        self._ab_buttons = {}
        for i, name in enumerate(('A', 'B')):
            lbl = tk.Label(
                self.waveform_canvas,
                text=name, font=th.FONT_LABEL_BOLD,
                fg=th.TEXT_SECONDARY, bg=th.BG_INSET,
                width=2, padx=4, pady=0, cursor='hand2',
                highlightthickness=1, highlightbackground=th.BORDER_SUBTLE,
            )
            lbl.place(in_=self.waveform_canvas, x=6 + i * 32, rely=1.0, y=-6, anchor='sw')
            lbl.bind('<Button-1>', lambda _, n=name: self._on_slot_changed(n))
            self._ab_buttons[name] = lbl
        self._update_slot_button_styles()

        # Morph knob to the right of the graph (discrete 0..31 positions between A and B).
        self.morph_knob = Knob(
            graph_row,
            from_=0, to=31, resolution=1,
            label="Morph",
            value_format="{:.0f}",
            size=56,
            initial=0,
            command=self._on_morph_changed,
            bg=th.BG_PANEL,
        )
        self.morph_knob.pack(side=tk.LEFT, padx=(10, 0))
        self._register_assignable('morph', self.morph_knob, self._on_morph_changed)

        # Unison knobs
        unison_col = tk.Frame(graph_row, bg=th.BG_PANEL)
        unison_col.pack(side=tk.LEFT, padx=(10, 0))
        tk.Frame(unison_col, bg=th.ACCENT, height=1).pack(fill=tk.X, padx=2)
        tk.Label(unison_col, text="UNISON", font=th.FONT_SUBGROUP,
                 fg=th.ACCENT_MUTED, bg=th.BG_PANEL).pack(pady=(3, 2))

        self.unison_voices_knob = Knob(unison_col, from_=1, to=8, resolution=1,
                                       label="Voices", value_format="{:.0f}",
                                       size=56, initial=1,
                                       command=self._on_unison_changed,
                                       bg=th.BG_PANEL)
        self.unison_voices_knob.pack(pady=(0, 4))

        self.unison_detune_knob = Knob(unison_col, from_=0, to=100, resolution=0.5,
                                       label="Detune", value_format="{:.1f} ct",
                                       size=56, initial=0,
                                       command=self._on_unison_changed,
                                       bg=th.BG_PANEL)
        self.unison_detune_knob.pack()

        slider_row = tk.Frame(section, bg=th.BG_PANEL)
        slider_row.pack(padx=10, pady=(0, 10))

        self.harmonic_sliders = []
        for k in range(16):
            label = "F" if k == 0 else str(k + 1)
            initial = float(self._wt_a[k])
            slider = HarmonicSlider(
                slider_row,
                label=label,
                initial=initial,
                command=lambda val, idx=k: self._on_harmonic_changed(idx, val),
                bg=th.BG_PANEL,
            )
            slider.grid(row=0, column=k, padx=1)
            self.harmonic_sliders.append(slider)

        self.waveform_canvas.bind('<Configure>', lambda _: self._draw_waveform())

        # Fire initial callback so the engine receives the computed wavetable (sine at pos 0).
        self._recompute_current_wt()

    def _on_harmonic_changed(self, index: int, value: float):
        if self._suppress_harmonic_callback:
            return
        wt = self._wt_a if self._edit_slot == 'A' else self._wt_b
        wt[index] = float(value)
        self._recompute_current_wt()

    def _harmonics_to_wave(self, wt: np.ndarray, N: int = 200) -> np.ndarray:
        phases = np.linspace(0, 2 * np.pi, N, endpoint=False)
        wave = np.zeros(N, dtype=np.float64)
        for k in range(16):
            if wt[k] != 0.0:
                wave += wt[k] * np.sin((k + 1) * phases)
        return wave

    def _draw_waveform(self):
        """Draw A, B, and the current interpolated waveform overlaid on the preview canvas."""
        c = self.waveform_canvas
        c.delete('all')
        w = c.winfo_width() or 320
        h = c.winfo_height() or 80
        mx, my = 4, 6
        draw_w = w - mx * 2
        draw_h = h - my * 2
        mid_y = my + draw_h // 2

        c.create_line(mx, mid_y, w - mx, mid_y, fill=th.BORDER_SUBTLE, width=1)

        N = 200
        wave_a   = self._harmonics_to_wave(self._wt_a, N)
        wave_b   = self._harmonics_to_wave(self._wt_b, N)
        wave_cur = self._harmonics_to_wave(self.wavetable, N)

        peak = max(
            float(np.max(np.abs(wave_a))),
            float(np.max(np.abs(wave_b))),
            float(np.max(np.abs(wave_cur))),
            1.0,
        )
        wave_a   /= peak
        wave_b   /= peak
        wave_cur /= peak

        xs = mx + np.arange(N) * draw_w / (N - 1)

        def _coords(wave):
            ys = mid_y - wave * (draw_h / 2 - 2)
            out = []
            for x, y in zip(xs, ys):
                out.extend([float(x), float(y)])
            return out

        c.create_line(_coords(wave_a),   fill=th.BORDER_SUBTLE, width=1, smooth=False)
        c.create_line(_coords(wave_b),   fill=th.ACCENT_MUTED,  width=1, smooth=False)
        c.create_line(_coords(wave_cur), fill=th.ACCENT,        width=2, smooth=False)

        # Keep the A/B buttons above the newly drawn lines.
        for lbl in getattr(self, '_ab_buttons', {}).values():
            lbl.lift()

    def _draw_envelope(self):
        """Draw ADSR envelope visualization."""
        self.envelope_canvas.delete('all')
        
        # Canvas size
        w = self.envelope_canvas.winfo_width()
        h = self.envelope_canvas.winfo_height()
        if w <= 1:
            w = 300
        if h <= 1:
            h = 100
        
        # Margins — top headroom so the peak is never clipped; bottom strip for labels
        margin_x = 40
        margin_y = 30        # top margin
        label_strip = 30     # pixels reserved at the bottom for A/D/S/R labels
        baseline_y = h - label_strip  # y-coordinate of the time (zero-amplitude) axis
        graph_w = w - margin_x * 2
        graph_h = baseline_y - margin_y
        
        # Total time (arbitrary for visualization)
        total_time = self.attack + self.decay + 1.0 + self.release  # 1 sec sustain
        
        # Scale factors
        time_scale = graph_w / total_time
        
        # Draw grid
        self.envelope_canvas.create_line(margin_x, baseline_y, w - margin_x, baseline_y,
                                        fill=th.BORDER_SUBTLE, width=1)  # Time axis
        self.envelope_canvas.create_line(margin_x, margin_y, margin_x, baseline_y,
                                        fill=th.BORDER_SUBTLE, width=1)  # Amplitude axis

        # Draw axis labels
        self.envelope_canvas.create_text(margin_x - 15, baseline_y, text='0',
                                        fill=th.TEXT_SECONDARY, font=th.FONT_VALUE)
        self.envelope_canvas.create_text(margin_x - 15, margin_y, text='1',
                                        fill=th.TEXT_SECONDARY, font=th.FONT_VALUE)

        # Build envelope points
        points = []

        # Start
        points.append((margin_x, baseline_y))

        # Attack peak
        points.append((margin_x + self.attack * time_scale, margin_y))

        # Decay to sustain
        sustain_y = baseline_y - self.sustain * graph_h
        points.append((margin_x + (self.attack + self.decay) * time_scale, sustain_y))

        # Sustain (flat)
        points.append((margin_x + (self.attack + self.decay + 1.0) * time_scale, sustain_y))

        # Release to zero
        points.append((margin_x + total_time * time_scale, baseline_y))
        
        # Draw envelope line
        if len(points) > 1:
            for i in range(len(points) - 1):
                x1, y1 = points[i]
                x2, y2 = points[i + 1]
                self.envelope_canvas.create_line(x1, y1, x2, y2,
                                               fill=th.ACCENT, width=2)

            # Draw points
            for x, y in points:
                self.envelope_canvas.create_oval(x - 3, y - 3, x + 3, y + 3,
                                               fill=th.ACCENT, outline=th.ACCENT_MUTED)

        # Draw ADSR labels inside the bottom reserved strip; skip any that
        # would overlap a previously drawn label (min 14 px separation).
        label_y = h - 15
        min_gap = 14
        label_positions = [
            (margin_x + self.attack * time_scale / 2, 'A'),
            (margin_x + self.attack * time_scale + self.decay * time_scale / 2, 'D'),
            (margin_x + (self.attack + self.decay) * time_scale + 0.5 * time_scale, 'S'),
            (margin_x + (self.attack + self.decay + 1.0) * time_scale + self.release * time_scale / 2, 'R'),
        ]
        last_drawn_x = margin_x - min_gap - 1
        for lx, letter in label_positions:
            lx = max(lx, last_drawn_x + min_gap)
            self.envelope_canvas.create_text(lx, label_y, text=letter,
                                            fill=th.TEXT_SECONDARY, font=th.FONT_VALUE)
            last_drawn_x = lx
    
    def update_gain_meter(self, current_level: float, peak_level: float, is_clipping: bool = False):
        self.smoothed_level = (self.meter_smooth_alpha * current_level
                               + (1 - self.meter_smooth_alpha) * self.smoothed_level)
        self.current_level = self.smoothed_level
        self.peak_level = peak_level

        # Convert to dB, floor at -60 dB
        DB_FLOOR = -60.0
        db = 20.0 * np.log10(max(self.current_level, 1e-10))
        db = max(db, DB_FLOOR)
        normalized = (db - DB_FLOOR) / (-DB_FLOOR)  # 0.0 at -60 dB, 1.0 at 0 dB

        m, w, h = self._m, self._mw, self._mh
        mh = h - m * 2
        bar_top = h - m - mh * normalized

        if is_clipping:
            color = th.METER_CLIP
        elif db > -6:
            color = th.METER_HOT
        elif db > -12:
            color = th.METER_WARN
        else:
            color = th.METER_SAFE

        self.gain_canvas.coords(self._gc_bar, m, bar_top, w - m, h - m)
        self.gain_canvas.itemconfig(self._gc_bar, fill=color)

        clip_text = " CLIP" if is_clipping else ""
        db_text = f"{db:.0f}dB" if self.current_level > 1e-10 else "-inf"
        self.level_label.config(
            text=f"{db_text}{clip_text}",
            fg=th.METER_CLIP if is_clipping else th.TEXT_SECONDARY,
        )
    
    def _draw_c_labels(self):
        self.canvas.delete('c_label')
        transpose_octs = self.transpose // 12
        white_midi_offsets = [0, 2, 4, 5, 7, 9, 11]
        x_pos = 10
        # Track x_pos the same way _draw_piano does, skipping notes outside range
        for octave in range(self.START_OCTAVE, self.END_OCTAVE + 2):
            c_note = octave * 12
            # Compute x_pos for this C by counting drawn white keys before it
            # We'll place the label only if the C note is within range
            if self.FIRST_NOTE <= c_note <= self.LAST_NOTE:
                sounding_oct = octave + transpose_octs
                self.canvas.create_text(
                    x_pos + self.WHITE_KEY_WIDTH // 2, 18,
                    text=f"C{sounding_oct}", font=th.FONT_SMALL, fill=th.TEXT_SECONDARY, tags='c_label',
                )
            # Advance x_pos past the 7 white keys in this octave (if within range)
            if octave <= self.END_OCTAVE:
                for wi in range(len(self.WHITE_KEYS)):
                    midi_note = octave * 12 + white_midi_offsets[wi]
                    if self.FIRST_NOTE <= midi_note <= self.LAST_NOTE:
                        x_pos += self.WHITE_KEY_WIDTH

    def _draw_piano_jewelry(self, canvas_w: int, canvas_h: int):
        """Draw decorative accents on the piano canvas itself."""
        # Subtle accent highlight above the keys (1px line across the top)
        top_y = 6
        self.canvas.create_line(
            4, top_y, canvas_w - 4, top_y,
            fill=th.ACCENT_MUTED, width=1, tags='jewelry',
        )
        # L-bracket corner accents
        LEN, W = 10, 2
        corners = [
            (2, 2, 1, 1),                                   # top-left
            (canvas_w - 2, 2, -1, 1),                       # top-right
            (2, canvas_h - 2, 1, -1),                       # bottom-left
            (canvas_w - 2, canvas_h - 2, -1, -1),           # bottom-right
        ]
        for x, y, dx, dy in corners:
            self.canvas.create_line(
                x, y, x + LEN * dx, y, fill=th.ACCENT, width=W, tags='jewelry',
            )
            self.canvas.create_line(
                x, y, x, y + LEN * dy, fill=th.ACCENT, width=W, tags='jewelry',
            )

    def _get_midi_note(self, white_key_index: int, octave: int) -> int:
        """Get MIDI note number from white key index and octave."""
        midi_offsets = [0, 2, 4, 5, 7, 9, 11]
        return octave * 12 + midi_offsets[white_key_index % 7]
    
    def _draw_piano(self):
        """Draw all piano keys on the canvas."""
        self.key_map = {}       # canvas item ID → MIDI note
        self.note_key_map = {}  # MIDI note → canvas item ID (last drawn wins for duplicates)
        
        x_pos = 10
        
        # Draw white keys first
        for octave in range(self.START_OCTAVE, self.END_OCTAVE + 1):
            for white_key_idx in range(len(self.WHITE_KEYS)):
                midi_note = self._get_midi_note(white_key_idx, octave)
                if midi_note < self.FIRST_NOTE or midi_note > self.LAST_NOTE:
                    continue

                key_id = self.canvas.create_rectangle(
                    x_pos, 10,
                    x_pos + self.WHITE_KEY_WIDTH, 10 + self.WHITE_KEY_HEIGHT,
                    fill='#F0F0F2', outline='#0A0A0E', width=1
                )

                self.key_map[key_id] = midi_note
                self.note_key_map[midi_note] = key_id
                x_pos += self.WHITE_KEY_WIDTH

        # Trailing C8 (MIDI 108)
        trailing_note = (self.END_OCTAVE + 1) * 12
        if trailing_note <= self.LAST_NOTE:
            key_id = self.canvas.create_rectangle(
                x_pos, 10,
                x_pos + self.WHITE_KEY_WIDTH, 10 + self.WHITE_KEY_HEIGHT,
                fill='#F0F0F2', outline='#0A0A0E', width=1
            )
            self.key_map[key_id] = trailing_note
            self.note_key_map[trailing_note] = key_id

        self._draw_c_labels()

        # Draw black keys on top
        x_pos = 10

        for octave in range(self.START_OCTAVE, self.END_OCTAVE + 1):
            for white_key_idx in range(len(self.WHITE_KEYS)):
                white_note = self._get_midi_note(white_key_idx, octave)
                # Check if there's a black key after this white key
                black_key_midi_offset = 0
                has_black = False

                if white_key_idx == 0:    # C -> C#
                    has_black = True; black_key_midi_offset = 1
                elif white_key_idx == 1:  # D -> D#
                    has_black = True; black_key_midi_offset = 3
                elif white_key_idx == 3:  # F -> F#
                    has_black = True; black_key_midi_offset = 6
                elif white_key_idx == 4:  # G -> G#
                    has_black = True; black_key_midi_offset = 8
                elif white_key_idx == 5:  # A -> A#
                    has_black = True; black_key_midi_offset = 10

                if white_note >= self.FIRST_NOTE and white_note <= self.LAST_NOTE:
                    if has_black:
                        black_x = x_pos + self.WHITE_KEY_WIDTH - self.BLACK_KEY_WIDTH // 2
                        midi_note = octave * 12 + black_key_midi_offset
                        if self.FIRST_NOTE <= midi_note <= self.LAST_NOTE:
                            key_id = self.canvas.create_rectangle(
                                black_x, 10,
                                black_x + self.BLACK_KEY_WIDTH, 10 + self.BLACK_KEY_HEIGHT,
                                fill='#0A0A0E', outline=th.BORDER_SUBTLE, width=1
                            )
                            self.key_map[key_id] = midi_note
                            self.note_key_map[midi_note] = key_id
                    x_pos += self.WHITE_KEY_WIDTH
    
    def _on_mouse_down(self, event):
        """Handle mouse down event."""
        items = self.canvas.find_overlapping(event.x, event.y, event.x, event.y)
        
        if items:
            key_id = items[-1]
            if key_id in self.key_map:
                note_num = self._apply_transpose(self.key_map[key_id])

                # Only trigger if not already pressed
                if note_num not in self.active_keys:
                    self.on_note_on(note_num, 100)
                    self.active_keys[note_num] = key_id
                    self.mouse_down_note = note_num
                    self._highlight_key(key_id, True)
    
    def _on_mouse_up(self, event):
        """Handle mouse up event."""
        # Release the note that was pressed with this mouse button
        if self.mouse_down_note is not None and self.mouse_down_note in self.active_keys:
            note_num = self.mouse_down_note
            key_id = self.active_keys[note_num]
            self.on_note_off(note_num)
            self._highlight_key(key_id, False)
            del self.active_keys[note_num]
            self.mouse_down_note = None
    
    def _on_mouse_motion(self, event):
        """Handle mouse motion while button is held."""
        if self.mouse_down_note is not None:
            # Get key under current position
            items = self.canvas.find_overlapping(event.x, event.y, event.x, event.y)
            
            if items:
                key_id = items[-1]
                if key_id in self.key_map:
                    note_num = self._apply_transpose(self.key_map[key_id])

                    # If we moved to a different key, trigger the new key
                    if note_num != self.mouse_down_note and note_num not in self.active_keys:
                        # Release old note
                        old_note = self.mouse_down_note
                        old_key_id = self.active_keys[old_note]
                        self.on_note_off(old_note)
                        self._highlight_key(old_key_id, False)
                        del self.active_keys[old_note]

                        # Trigger new note
                        self.on_note_on(note_num, 100)
                        self.active_keys[note_num] = key_id
                        self.mouse_down_note = note_num
                        self._highlight_key(key_id, True)
    
    def _highlight_key(self, key_id: int, highlighted: bool):
        """Highlight or unhighlight a key."""
        note_num = self.key_map[key_id]
        note_in_octave = note_num % 12
        black_key_midi = [1, 3, 6, 8, 10]
        is_black = note_in_octave in black_key_midi

        if highlighted:
            # Accent tint when pressed: lighter for white keys, muted accent for black
            self.canvas.itemconfig(key_id, fill=th.ACCENT_MUTED if is_black else th.ACCENT)
        else:
            self.canvas.itemconfig(key_id, fill='#0A0A0E' if is_black else '#F0F0F2')
    
    def update_voice_count(self, count: int):
        """Update the active voice count display."""
        self.info_label.config(text=f"Active voices: {count} / 16")
