"""
Simple clickable piano GUI for the synthesizer with ADSR controls.
"""
import tkinter as tk
from tkinter import Canvas, Scale, HORIZONTAL
from typing import Callable, Optional, Dict, Tuple
import math
import numpy as np

from .widgets import Knob, HarmonicSlider
from .widgets import theme as th


class PianoGUI:
    """A simple clickable piano interface with ADSR controls."""
    
    # Piano key properties
    WHITE_KEY_WIDTH = 50
    WHITE_KEY_HEIGHT = 200
    BLACK_KEY_WIDTH = 32
    BLACK_KEY_HEIGHT = 130
    
    # Standard piano layout
    WHITE_KEYS = ['C', 'D', 'E', 'F', 'G', 'A', 'B']
    BLACK_KEYS = {
        'C#': 0, 'D#': 1, 'F#': 3, 'G#': 4, 'A#': 5,
    }
    
    # Piano range: 2 octaves (C4 to C6)
    START_OCTAVE = 4
    END_OCTAVE = 6
    
    def __init__(self, root: tk.Tk, on_note_on: Callable, on_note_off: Callable,
                 on_adsr_change: Callable = None,
                 on_volume_change: Callable = None,
                 on_lpf_change: Callable = None,
                 on_reverb_change: Callable = None,
                 on_delay_change: Callable = None,
                 on_wavetable_change: Callable = None,
                 on_chorus_change: Callable = None,
                 on_bitcrusher_change: Callable = None,
                 on_panic: Callable = None):
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
        self.on_bitcrusher_change = on_bitcrusher_change or (lambda bits, ds, wet: None)
        self.on_panic = on_panic or (lambda: None)

        # Wavetable state (16 harmonic amplitudes)
        self.wavetable = np.zeros(16, dtype=np.float32)
        self.wavetable[0] = 1.0

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

        # Gain meter state (smoothed)
        self.current_level = 0.0
        self.peak_level = 0.0
        self.smoothed_level = 0.0
        self.meter_smooth_alpha = 0.7  # Higher = more responsive; 0.3 hid real peaks
        
        # Setup window
        self.root.title("PythonSynth")
        self.root.geometry("1260x940")
        self.root.resizable(False, False)
        self.root.configure(bg=th.BG_ROOT)

        num_white_keys = (self.END_OCTAVE - self.START_OCTAVE + 1) * 7 + 1

        # Title
        title_frame = tk.Frame(root, bg=th.BG_ROOT)
        title_frame.pack(pady=(14, 8))
        tk.Label(title_frame, text="PythonSynth", font=th.FONT_TITLE,
                fg=th.TEXT_PRIMARY, bg=th.BG_ROOT).pack()
        # Accent underline echoes the piano bezel
        tk.Frame(title_frame, bg=th.ACCENT, height=2, width=160).pack(pady=(2, 0))

        # Row 1: [ADSR + Osc centered] [LPF + Master right-aligned]
        row1 = tk.Frame(root, bg=th.BG_ROOT)
        row1.pack(pady=(6, 2), padx=10, fill=tk.X)

        row1_right = tk.Frame(row1, bg=th.BG_ROOT)
        row1_right.pack(side=tk.RIGHT, padx=4, fill=tk.Y)
        row1_right_inner = tk.Frame(row1_right, bg=th.BG_ROOT)
        row1_right_inner.pack(anchor='e', fill=tk.Y, expand=True)
        self._create_filter_controls(row1_right_inner)
        self._create_master_section(row1_right_inner)

        row1_center = tk.Frame(row1, bg=th.BG_ROOT)
        row1_center.pack(side=tk.LEFT, expand=True)
        row1_inner = tk.Frame(row1_center, bg=th.BG_ROOT)
        row1_inner.pack(anchor='center')
        self._create_adsr_controls(row1_inner)
        self._create_oscillator_controls(row1_inner)

        # Row 2: Effects (centered)
        row2 = tk.Frame(root, bg=th.BG_ROOT)
        row2.pack(pady=(2, 6), padx=10)
        self._create_effects_controls(row2)

        # Row 3: Piano + Transpose (centered)
        piano_outer = tk.Frame(root, bg=th.BG_ROOT)
        piano_outer.pack(pady=(6, 4), fill=tk.X)

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
                           width=canvas_width, height=220)
        self.canvas.pack(padx=10, pady=10)

        self.canvas.bind('<Button-1>', self._on_mouse_down)
        self.canvas.bind('<ButtonRelease-1>', self._on_mouse_up)
        self.canvas.bind('<Motion>', self._on_mouse_motion)

        self._draw_piano()
        self._draw_piano_jewelry(canvas_width, 220)
        self._bind_keyboard()
        self._draw_kb_labels()

        info_frame = tk.Frame(piano_center, bg=th.BG_ROOT)
        info_frame.pack(pady=(8, 2))
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
        self.kb_octave = self.START_OCTAVE + 1  # default: C5, centered on 3-octave layout
        self._kb_held: set = set()          # keys currently held down

        self.root.bind('<KeyPress>',   self._on_key_press)
        self.root.bind('<KeyRelease>', self._on_key_release)
        self.root.bind('<space>',      lambda _: self._on_panic())

    def _kb_shift(self, direction: int):
        """Shift kb_octave by direction (±1). If at limit, transpose by ±12 instead."""
        new_oct = self.kb_octave + direction
        if self.START_OCTAVE <= new_oct <= self.END_OCTAVE:
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
                cx = x_pos + self.WHITE_KEY_WIDTH // 2
                cy = 10 + self.WHITE_KEY_HEIGHT - 18
                note_cx[midi_note] = (cx, cy, False)

                # Black key to the right of this white key
                black_offsets = {0: 1, 1: 3, 3: 6, 4: 8, 5: 10}
                if wi in black_offsets:
                    bx = x_pos + self.WHITE_KEY_WIDTH - self.BLACK_KEY_WIDTH // 2 + self.BLACK_KEY_WIDTH // 2
                    by = 10 + self.BLACK_KEY_HEIGHT - 14
                    note_cx[octave * 12 + black_offsets[wi]] = (bx, by, True)

                x_pos += self.WHITE_KEY_WIDTH

        # Trailing C (mirrors _draw_piano)
        trailing_note = (self.END_OCTAVE + 1) * 12
        note_cx[trailing_note] = (x_pos + self.WHITE_KEY_WIDTH // 2, 10 + self.WHITE_KEY_HEIGHT - 18, False)

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
        section.pack(side=tk.LEFT, padx=8, pady=6, fill=tk.Y)

        tk.Label(section, text="ADSR Envelope", font=th.FONT_SECTION,
                 fg=th.ACCENT, bg=th.BG_PANEL).pack(pady=(8, 4), padx=10, anchor='w')

        knob_row = tk.Frame(section, bg=th.BG_PANEL)
        knob_row.pack(padx=10, pady=(2, 4))

        self.attack_scale = Knob(knob_row, from_=1, to=500, resolution=1,
                                 label="Attack", value_format="{:.0f} ms",
                                 initial=int(self.attack * 1000),
                                 command=self._on_adsr_changed)
        self.attack_scale.set(int(self.attack * 1000))
        self.attack_scale.grid(row=0, column=0, padx=6, pady=4)

        self.decay_scale = Knob(knob_row, from_=1, to=500, resolution=1,
                                label="Decay", value_format="{:.0f} ms",
                                initial=int(self.decay * 1000),
                                command=self._on_adsr_changed)
        self.decay_scale.set(int(self.decay * 1000))
        self.decay_scale.grid(row=0, column=1, padx=6, pady=4)

        self.sustain_scale = Knob(knob_row, from_=0, to=100, resolution=1,
                                  label="Sustain", value_format="{:.0f}%",
                                  initial=int(self.sustain * 100),
                                  command=self._on_adsr_changed)
        self.sustain_scale.set(int(self.sustain * 100))
        self.sustain_scale.grid(row=0, column=2, padx=6, pady=4)

        self.release_scale = Knob(knob_row, from_=1, to=2000, resolution=1,
                                  label="Release", value_format="{:.0f} ms",
                                  initial=int(self.release * 1000),
                                  command=self._on_adsr_changed)
        self.release_scale.set(int(self.release * 1000))
        self.release_scale.grid(row=0, column=3, padx=6, pady=4)

        self.envelope_canvas = Canvas(section, bg=th.BG_INSET, highlightthickness=1,
                                      highlightbackground=th.BORDER_SUBTLE,
                                      width=300, height=100)
        self.envelope_canvas.pack(padx=10, pady=(2, 10))

        self.envelope_canvas.bind('<Configure>', lambda _: self._draw_envelope())


    def _apply_transpose(self, raw_note: int) -> int:
        return max(0, min(127, raw_note + self.transpose))

    def _create_transpose_slider(self, parent: tk.Frame):
        # Accent left-edge echoes the piano bezel
        wrapper = tk.Frame(parent, bg=th.ACCENT)
        wrapper.pack(side=tk.LEFT, padx=(0, 6), pady=10, fill=tk.Y)
        frame = tk.Frame(wrapper, bg=th.BG_PANEL,
                         highlightbackground=th.BORDER_SUBTLE, highlightthickness=1)
        frame.pack(side=tk.LEFT, padx=(2, 0), pady=0, fill=tk.Y)

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
        self.attack = self.attack_scale.get() / 1000.0
        self.decay = self.decay_scale.get() / 1000.0
        self.sustain = self.sustain_scale.get() / 100.0
        self.release = self.release_scale.get() / 1000.0

        # Notify synthesizer
        self.on_adsr_change(self.attack, self.decay, self.sustain, self.release)

        # Redraw envelope
        self._draw_envelope()

    def _create_filter_controls(self, parent):
        """Low-pass filter section: Cutoff + Q as knobs."""
        section = tk.Frame(parent, bg=th.BG_PANEL,
                           highlightbackground=th.BORDER_SUBTLE, highlightthickness=1)
        section.pack(side=tk.LEFT, padx=8, pady=6, fill=tk.Y)

        tk.Label(section, text="LPF", font=th.FONT_SECTION,
                 fg=th.ACCENT, bg=th.BG_PANEL).pack(pady=(8, 4), padx=10, anchor='w')

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

        self.lpf_q_scale = Knob(knob_row, from_=0.5, to=12.0, resolution=0.1,
                                label="Reso", value_format="Q {:.1f}",
                                initial=0.7,
                                command=self._on_lpf_changed)
        self.lpf_q_scale.set(0.7)
        self.lpf_q_scale.grid(row=1, column=0, padx=6, pady=4)

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

        # ── Reverb ────────────────────────────────────────────────────────
        rev = _subgroup(groups_row, "Reverb")
        for col, (lbl, attr, default) in enumerate([
            ("Room", "reverb_room_scale", 50),
            ("Damp", "reverb_damp_scale", 50),
            ("Wet",  "reverb_wet_scale",   0),
        ]):
            k = Knob(rev, from_=0, to=100, resolution=1,
                     label=lbl, value_format="{:.0f}%",
                     initial=default,
                     command=self._on_reverb_changed)
            k.set(default)
            k.grid(row=0, column=col, padx=5, pady=4)
            setattr(self, attr, k)

        # ── Delay ─────────────────────────────────────────────────────────
        dly = _subgroup(groups_row, "Delay")

        time_col = tk.Frame(dly, bg=th.BG_PANEL)
        time_col.grid(row=0, column=0, padx=5, pady=4, sticky='n')
        tk.Label(time_col, text="Time", font=th.FONT_LABEL_BOLD,
                 fg=th.ACCENT_MUTED, bg=th.BG_PANEL).pack()
        self.delay_time_scale = Scale(time_col, from_=10, to=1000,
                                      orient=HORIZONTAL,
                                      bg=th.BG_PANEL, fg=th.TEXT_PRIMARY, length=120,
                                      troughcolor=th.BG_INSET,
                                      activebackground=th.ACCENT_MUTED,
                                      highlightthickness=0, bd=0,
                                      label="", showvalue=True,
                                      command=self._on_delay_changed)
        self.delay_time_scale.set(250)
        self.delay_time_scale.pack()
        tk.Label(time_col, text="ms", font=th.FONT_VALUE,
                 fg=th.TEXT_SECONDARY, bg=th.BG_PANEL).pack()

        self.delay_fb_scale = Knob(dly, from_=0, to=90, resolution=1,
                                   label="Feedback", value_format="{:.0f}%",
                                   initial=40,
                                   command=self._on_delay_changed)
        self.delay_fb_scale.set(40)
        self.delay_fb_scale.grid(row=0, column=1, padx=5, pady=4)

        self.delay_wet_scale = Knob(dly, from_=0, to=100, resolution=1,
                                    label="Wet", value_format="{:.0f}%",
                                    initial=0,
                                    command=self._on_delay_changed)
        self.delay_wet_scale.set(0)
        self.delay_wet_scale.grid(row=0, column=2, padx=5, pady=4)

        # ── Chorus ────────────────────────────────────────────────────────
        cho = _subgroup(groups_row, "Chorus")

        self.chorus_rate_scale = Knob(cho, from_=0, to=100, resolution=1,
                                      label="Rate", value_format="{:.0f}%",
                                      initial=30,
                                      command=self._on_chorus_changed)
        self.chorus_rate_scale.set(30)
        self.chorus_rate_scale.grid(row=0, column=0, padx=5, pady=4)

        self.chorus_depth_scale = Knob(cho, from_=0, to=100, resolution=1,
                                       label="Depth", value_format="{:.0f}%",
                                       initial=50,
                                       command=self._on_chorus_changed)
        self.chorus_depth_scale.set(50)
        self.chorus_depth_scale.grid(row=0, column=1, padx=5, pady=4)

        self.chorus_wet_scale = Knob(cho, from_=0, to=100, resolution=1,
                                     label="Wet", value_format="{:.0f}%",
                                     initial=0,
                                     command=self._on_chorus_changed)
        self.chorus_wet_scale.set(0)
        self.chorus_wet_scale.grid(row=0, column=2, padx=5, pady=4)

        # ── Bitcrusher ────────────────────────────────────────────────────
        bc = _subgroup(groups_row, "Bitcrusher")

        self.bc_bits_scale = Knob(bc, from_=1, to=16, resolution=1,
                                  label="Bits", value_format="{:.0f} bit",
                                  initial=16,
                                  command=self._on_bitcrusher_changed)
        self.bc_bits_scale.set(16)
        self.bc_bits_scale.grid(row=0, column=0, padx=5, pady=4)

        self.bc_ds_scale = Knob(bc, from_=1, to=32, resolution=1,
                                label="Downsamp", value_format="÷{:.0f}",
                                initial=1,
                                command=self._on_bitcrusher_changed)
        self.bc_ds_scale.set(1)
        self.bc_ds_scale.grid(row=0, column=1, padx=5, pady=4)

        self.bc_wet_scale = Knob(bc, from_=0, to=100, resolution=1,
                                 label="Wet", value_format="{:.0f}%",
                                 initial=0,
                                 command=self._on_bitcrusher_changed)
        self.bc_wet_scale.set(0)
        self.bc_wet_scale.grid(row=0, column=2, padx=5, pady=4)

    def _create_master_section(self, parent):
        """Master section: Volume knob + compact vertical level meter."""
        METER_W, METER_H, MARGIN = 28, 120, 3

        section = tk.Frame(parent, bg=th.BG_PANEL,
                           highlightbackground=th.BORDER_SUBTLE, highlightthickness=1)
        section.pack(side=tk.LEFT, padx=8, pady=6, fill=tk.Y)

        tk.Label(section, text="Master", font=th.FONT_SECTION,
                 fg=th.ACCENT, bg=th.BG_PANEL).pack(pady=(8, 4), padx=10, anchor='w')

        tk.Button(section, text="PANIC", font=th.FONT_LABEL_BOLD,
                  fg=th.TEXT_PRIMARY, bg=th.DANGER, activebackground=th.DANGER_ACTIVE,
                  relief=tk.FLAT, bd=0, padx=10, pady=3,
                  command=self._on_panic).pack(pady=(0, 6))

        self.volume_scale = Knob(section, from_=0, to=100, resolution=1,
                                 label="Volume", value_format="{:.0f}%",
                                 size=56, initial=70,
                                 command=self._on_volume_changed)
        self.volume_scale.set(70)
        self.volume_scale.pack(pady=(0, 4))
        self._on_volume_changed(None)

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

    def _on_volume_changed(self, _):
        self.on_volume_change(self.volume_scale.get() / 100.0 * (3.0 / 7.0))

    def _on_lpf_changed(self, _):
        t = self.lpf_cutoff_scale.get() / 100.0
        cutoff = 20.0 * (1000.0 ** t)  # log mapping: 20 Hz → 20000 Hz
        q = self.lpf_q_scale.get()
        self.on_lpf_change(cutoff, q)

    def _on_reverb_changed(self, _):
        self.on_reverb_change(
            self.reverb_room_scale.get() / 100.0,
            self.reverb_damp_scale.get() / 100.0,
            self.reverb_wet_scale.get()  / 100.0,
        )

    def _on_delay_changed(self, _):
        self.on_delay_change(
            float(self.delay_time_scale.get()),
            self.delay_fb_scale.get()  / 100.0,
            self.delay_wet_scale.get() / 100.0,
        )

    def _on_chorus_changed(self, _):
        # Rate knob: 0–100% → 0.05–8 Hz (log-ish feel)
        rate_hz = 0.05 * (160.0 ** (self.chorus_rate_scale.get() / 100.0))
        self.on_chorus_change(
            rate_hz,
            self.chorus_depth_scale.get() / 100.0,
            self.chorus_wet_scale.get()   / 100.0,
        )

    def _on_bitcrusher_changed(self, _):
        self.on_bitcrusher_change(
            float(self.bc_bits_scale.get()),
            int(self.bc_ds_scale.get()),
            self.bc_wet_scale.get() / 100.0,
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
        self.wavetable = wt.copy()
        for k, slider in enumerate(self.harmonic_sliders):
            slider.set(float(wt[k]))
        self._draw_waveform()
        self.on_wavetable_change(self.wavetable.copy())

    def _create_oscillator_controls(self, parent):
        """Wavetable oscillator section: waveform preview + 16 harmonic sliders."""
        section = tk.Frame(parent, bg=th.BG_PANEL,
                           highlightbackground=th.BORDER_SUBTLE, highlightthickness=1)
        section.pack(side=tk.LEFT, padx=8, pady=6, fill=tk.Y)

        tk.Label(section, text="Oscillator", font=th.FONT_SECTION,
                 fg=th.ACCENT, bg=th.BG_PANEL).pack(pady=(8, 4), padx=10, anchor='w')

        # Preset buttons row
        preset_row = tk.Frame(section, bg=th.BG_PANEL)
        preset_row.pack(padx=10, pady=(0, 4))

        self._preset_btn_canvases = {}
        for name in ('sine', 'saw', 'square', 'triangle', 'semisine'):
            btn_frame = tk.Frame(preset_row, bg=th.BORDER_SUBTLE,
                                 cursor='hand2')
            btn_frame.pack(side=tk.LEFT, padx=3)
            c = tk.Canvas(btn_frame, bg=th.BG_INSET, highlightthickness=0,
                          width=54, height=36)
            c.pack(padx=1, pady=1)
            wt = self._make_preset_waveform(name)
            # Draw after packing so winfo_width is correct on next update
            c.bind('<Configure>', lambda _, cv=c, w=wt:
                   self._draw_preset_button_waveform(cv, w))
            c.bind('<Button-1>', lambda _, n=name: self._apply_preset(n))
            btn_frame.bind('<Button-1>', lambda _, n=name: self._apply_preset(n))
            self._preset_btn_canvases[name] = c

        self.waveform_canvas = tk.Canvas(
            section, bg=th.BG_INSET, highlightthickness=1,
            highlightbackground=th.BORDER_SUBTLE, width=320, height=80,
        )
        self.waveform_canvas.pack(padx=10, pady=(4, 6))

        slider_row = tk.Frame(section, bg=th.BG_PANEL)
        slider_row.pack(padx=10, pady=(0, 10))

        self.harmonic_sliders = []
        for k in range(16):
            label = "F" if k == 0 else str(k + 1)
            initial = 1.0 if k == 0 else 0.0
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

    def _on_harmonic_changed(self, index: int, value: float):
        self.wavetable[index] = float(value)
        self._draw_waveform()
        self.on_wavetable_change(self.wavetable.copy())

    def _draw_waveform(self):
        """Draw one cycle of the current wavetable waveform on the preview canvas."""
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
        phases = np.linspace(0, 2 * np.pi, N, endpoint=False)
        wt = self.wavetable
        wave = np.zeros(N, dtype=np.float64)
        for k in range(16):
            if wt[k] != 0.0:
                wave += wt[k] * np.sin((k + 1) * phases)

        peak = max(float(np.max(np.abs(wave))), 1.0)
        wave /= peak

        xs = mx + np.arange(N) * draw_w / (N - 1)
        ys = mid_y - wave * (draw_h / 2 - 2)
        coords = []
        for x, y in zip(xs, ys):
            coords.extend([float(x), float(y)])
        if len(coords) >= 4:
            c.create_line(coords, fill=th.ACCENT, width=2, smooth=False)

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
        
        # Margins
        margin_x = 40
        margin_y = 20
        graph_w = w - margin_x * 2
        graph_h = h - margin_y * 2
        
        # Total time (arbitrary for visualization)
        total_time = self.attack + self.decay + 1.0 + self.release  # 1 sec sustain
        
        # Scale factors
        time_scale = graph_w / total_time
        
        # Draw grid
        self.envelope_canvas.create_line(margin_x, h - margin_y, w - margin_x, h - margin_y,
                                        fill=th.BORDER_SUBTLE, width=1)  # Time axis
        self.envelope_canvas.create_line(margin_x, margin_y, margin_x, h - margin_y,
                                        fill=th.BORDER_SUBTLE, width=1)  # Amplitude axis

        # Draw labels
        self.envelope_canvas.create_text(margin_x - 15, h - margin_y, text='0',
                                        fill=th.TEXT_SECONDARY, font=th.FONT_VALUE)
        self.envelope_canvas.create_text(margin_x - 15, margin_y + graph_h, text='1',
                                        fill=th.TEXT_SECONDARY, font=th.FONT_VALUE)
        
        # Build envelope points
        points = []
        
        # Start
        x = margin_x
        y = h - margin_y
        points.append((x, y))
        
        # Attack
        x = margin_x + self.attack * time_scale
        y = margin_y
        points.append((x, y))
        
        # Decay
        sustain_y = h - margin_y - self.sustain * graph_h
        x = margin_x + (self.attack + self.decay) * time_scale
        y = sustain_y
        points.append((x, y))
        
        # Sustain (flat)
        x = margin_x + (self.attack + self.decay + 1.0) * time_scale
        y = sustain_y
        points.append((x, y))
        
        # Release
        x = margin_x + total_time * time_scale
        y = h - margin_y
        points.append((x, y))
        
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

        # Draw attack label
        attack_x = margin_x + self.attack * time_scale / 2
        self.envelope_canvas.create_text(attack_x, h - margin_y + 15, text='A',
                                        fill=th.TEXT_SECONDARY, font=th.FONT_VALUE)

        # Draw decay label
        decay_x = margin_x + self.attack * time_scale + self.decay * time_scale / 2
        self.envelope_canvas.create_text(decay_x, h - margin_y + 15, text='D',
                                        fill=th.TEXT_SECONDARY, font=th.FONT_VALUE)

        # Draw sustain label
        sustain_x = margin_x + (self.attack + self.decay) * time_scale + 0.5 * time_scale
        self.envelope_canvas.create_text(sustain_x, h - margin_y + 15, text='S',
                                        fill=th.TEXT_SECONDARY, font=th.FONT_VALUE)

        # Draw release label
        release_x = margin_x + (self.attack + self.decay + 1.0) * time_scale + self.release * time_scale / 2
        self.envelope_canvas.create_text(release_x, h - margin_y + 15, text='R',
                                        fill=th.TEXT_SECONDARY, font=th.FONT_VALUE)
    
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
        x_pos = 10
        for octave in range(self.START_OCTAVE, self.END_OCTAVE + 1):
            sounding_oct = (octave - 1) + transpose_octs
            self.canvas.create_text(
                x_pos + self.WHITE_KEY_WIDTH // 2, 22,
                text=f"C{sounding_oct}", font=th.FONT_SMALL, fill=th.TEXT_SECONDARY, tags='c_label',
            )
            x_pos += len(self.WHITE_KEYS) * self.WHITE_KEY_WIDTH
        # Trailing C
        sounding_oct = self.END_OCTAVE + transpose_octs
        self.canvas.create_text(
            x_pos + self.WHITE_KEY_WIDTH // 2, 22,
            text=f"C{sounding_oct}", font=th.FONT_SMALL, fill=th.TEXT_SECONDARY, tags='c_label',
        )

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
                
                key_id = self.canvas.create_rectangle(
                    x_pos, 10,
                    x_pos + self.WHITE_KEY_WIDTH, 10 + self.WHITE_KEY_HEIGHT,
                    fill='#F0F0F2', outline='#0A0A0E', width=1
                )

                self.key_map[key_id] = midi_note
                self.note_key_map[midi_note] = key_id
                x_pos += self.WHITE_KEY_WIDTH

        # Trailing C one octave above END_OCTAVE
        trailing_note = (self.END_OCTAVE + 1) * 12
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
                # Check if there's a black key after this white key
                black_key_name = None
                black_key_midi_offset = 0
                
                if white_key_idx == 0:  # C -> C#
                    black_key_name = 'C#'
                    black_key_midi_offset = 1
                elif white_key_idx == 1:  # D -> D#
                    black_key_name = 'D#'
                    black_key_midi_offset = 3
                elif white_key_idx == 3:  # F -> F#
                    black_key_name = 'F#'
                    black_key_midi_offset = 6
                elif white_key_idx == 4:  # G -> G#
                    black_key_name = 'G#'
                    black_key_midi_offset = 8
                elif white_key_idx == 5:  # A -> A#
                    black_key_name = 'A#'
                    black_key_midi_offset = 10
                
                # Draw black key if it exists
                if black_key_name:
                    black_x = x_pos + self.WHITE_KEY_WIDTH - self.BLACK_KEY_WIDTH // 2
                    midi_note = octave * 12 + black_key_midi_offset
                    
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
