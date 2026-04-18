"""
Simple clickable piano GUI for the synthesizer with ADSR controls.
"""
import tkinter as tk
from tkinter import Canvas, Scale, HORIZONTAL
from typing import Callable, Optional, Dict, Tuple
import math

from .widgets import Knob


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
                 on_delay_change: Callable = None):
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
        self.root.title("PythonSynth Piano with ADSR")
        num_white_keys = (self.END_OCTAVE - self.START_OCTAVE + 1) * 7
        window_width = max(1200, num_white_keys * self.WHITE_KEY_WIDTH + 200)
        self.root.geometry(f"{window_width}x720")
        self.root.configure(bg='#333333')

        # Title
        title_frame = tk.Frame(root, bg='#333333')
        title_frame.pack(pady=(8, 4))
        tk.Label(title_frame, text="PythonSynth", font=("Arial", 16, "bold"),
                fg='white', bg='#333333').pack()

        # Top section row: Envelope | Filter | Effects
        top_row = tk.Frame(root, bg='#333333')
        top_row.pack(pady=6, padx=10, fill=tk.X)

        self._create_adsr_controls(top_row)
        self._create_filter_controls(top_row)
        self._create_effects_controls(top_row)

        # Bottom row: piano on left, master section on right
        content_frame = tk.Frame(root, bg='#333333')
        content_frame.pack(pady=8, padx=10, fill=tk.BOTH, expand=True)

        left_frame = tk.Frame(content_frame, bg='#333333')
        left_frame.pack(side=tk.LEFT, padx=5)

        piano_row = tk.Frame(left_frame, bg='#333333')
        piano_row.pack()

        self._create_transpose_slider(piano_row)

        canvas_width = max(800, num_white_keys * self.WHITE_KEY_WIDTH + 20)
        self.canvas = Canvas(piano_row, bg='#333333', highlightthickness=0,
                           width=canvas_width, height=220)
        self.canvas.pack(side=tk.LEFT, pady=10)

        self.canvas.bind('<Button-1>', self._on_mouse_down)
        self.canvas.bind('<ButtonRelease-1>', self._on_mouse_up)
        self.canvas.bind('<Motion>', self._on_mouse_motion)

        self._draw_piano()

        info_frame = tk.Frame(left_frame, bg='#333333')
        info_frame.pack(pady=5)
        self.info_label = tk.Label(info_frame, text="Active voices: 0",
                                   font=("Arial", 10), fg='#00AA00', bg='#333333')
        self.info_label.pack()

        # Master section (Volume + Level meter) on the right
        self._create_master_section(content_frame)
    
    def _create_adsr_controls(self, parent):
        """ADSR envelope section: 4 knobs on top, envelope graph below."""
        section = tk.Frame(parent, bg='#444444', relief=tk.RIDGE, bd=1)
        section.pack(side=tk.LEFT, padx=6, pady=4, fill=tk.Y)

        tk.Label(section, text="ADSR Envelope", font=("Arial", 11, "bold"),
                 fg='white', bg='#444444').pack(pady=(6, 2))

        knob_row = tk.Frame(section, bg='#444444')
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

        self.envelope_canvas = Canvas(section, bg='#1a1a1a', highlightthickness=1,
                                      highlightbackground='#555555',
                                      width=360, height=120)
        self.envelope_canvas.pack(padx=10, pady=(2, 8))

        self._draw_envelope()


    def _apply_transpose(self, raw_note: int) -> int:
        return max(0, min(127, raw_note + self.transpose))

    def _create_transpose_slider(self, parent: tk.Frame):
        frame = tk.Frame(parent, bg='#444444', relief=tk.RIDGE, bd=1)
        frame.pack(side=tk.LEFT, padx=5, pady=10, fill=tk.Y)

        tk.Label(frame, text="Transpose", font=("Arial", 8, "bold"),
                 fg='#AAAAFF', bg='#444444').pack(pady=(3, 0))

        # from_=24 at top (higher pitch), to=-24 at bottom
        self.transpose_scale = Scale(
            frame, from_=24, to=-24, orient=tk.VERTICAL,
            bg='#555555', fg='white', length=200,
            tickinterval=12, resolution=1,
            command=self._on_transpose_changed,
        )
        self.transpose_scale.set(0)
        self.transpose_scale.pack(padx=5)

        self.transpose_label = tk.Label(
            frame, text="0 st", font=("Arial", 8),
            fg='#AAAAFF', bg='#444444',
        )
        self.transpose_label.pack(pady=(0, 3))

    def _on_transpose_changed(self, _):
        self.transpose = self.transpose_scale.get()
        self.transpose_label.config(text=f"{self.transpose:+d} st")

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
        section = tk.Frame(parent, bg='#444444', relief=tk.RIDGE, bd=1)
        section.pack(side=tk.LEFT, padx=6, pady=4, fill=tk.Y)

        tk.Label(section, text="Low-Pass Filter", font=("Arial", 11, "bold"),
                 fg='white', bg='#444444').pack(pady=(6, 2))

        knob_row = tk.Frame(section, bg='#444444')
        knob_row.pack(padx=10, pady=(2, 8))

        self.lpf_cutoff_scale = Knob(knob_row, from_=0, to=100, resolution=1,
                                     label="Cutoff", value_format="{:.0f}",
                                     initial=100,
                                     command=self._on_lpf_changed)
        self.lpf_cutoff_scale.set(100)
        self.lpf_cutoff_scale.grid(row=0, column=0, padx=6, pady=4)

        self.lpf_q_scale = Knob(knob_row, from_=5, to=40, resolution=1,
                                label="Reso", value_format="Q {:.1f}",
                                initial=7,
                                command=self._on_lpf_changed)
        self.lpf_q_scale.set(7)
        self.lpf_q_scale.grid(row=0, column=1, padx=6, pady=4)

    def _create_effects_controls(self, parent):
        """Effects section: Reverb + Delay as two sub-groups."""
        section = tk.Frame(parent, bg='#444444', relief=tk.RIDGE, bd=1)
        section.pack(side=tk.LEFT, padx=6, pady=4, fill=tk.Y)

        tk.Label(section, text="Effects", font=("Arial", 11, "bold"),
                 fg='white', bg='#444444').pack(pady=(6, 2))

        groups_row = tk.Frame(section, bg='#444444')
        groups_row.pack(padx=8, pady=(2, 8))

        # ── Reverb ────────────────────────────────────────────────────────
        rev = tk.LabelFrame(groups_row, text="Reverb", bg='#444444',
                            fg='#AAAAFF', font=("Arial", 9, "bold"),
                            bd=1, relief=tk.GROOVE)
        rev.pack(side=tk.LEFT, padx=4, pady=2)

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
            k.grid(row=0, column=col, padx=5, pady=6)
            setattr(self, attr, k)

        # ── Delay ─────────────────────────────────────────────────────────
        dly = tk.LabelFrame(groups_row, text="Delay", bg='#444444',
                            fg='#AAAAFF', font=("Arial", 9, "bold"),
                            bd=1, relief=tk.GROOVE)
        dly.pack(side=tk.LEFT, padx=4, pady=2)

        time_col = tk.Frame(dly, bg='#444444')
        time_col.grid(row=0, column=0, padx=5, pady=6, sticky='n')
        tk.Label(time_col, text="Time", font=("Arial", 9, "bold"),
                 fg='#AAAAFF', bg='#444444').pack()
        self.delay_time_scale = Scale(time_col, from_=10, to=1000,
                                      orient=HORIZONTAL,
                                      bg='#555555', fg='white', length=120,
                                      label="", showvalue=True,
                                      command=self._on_delay_changed)
        self.delay_time_scale.set(250)
        self.delay_time_scale.pack()
        tk.Label(time_col, text="ms", font=("Arial", 8),
                 fg='#888888', bg='#444444').pack()

        self.delay_fb_scale = Knob(dly, from_=0, to=90, resolution=1,
                                   label="Feedback", value_format="{:.0f}%",
                                   initial=40,
                                   command=self._on_delay_changed)
        self.delay_fb_scale.set(40)
        self.delay_fb_scale.grid(row=0, column=1, padx=5, pady=6)

        self.delay_wet_scale = Knob(dly, from_=0, to=100, resolution=1,
                                    label="Wet", value_format="{:.0f}%",
                                    initial=0,
                                    command=self._on_delay_changed)
        self.delay_wet_scale.set(0)
        self.delay_wet_scale.grid(row=0, column=2, padx=5, pady=6)

    def _create_master_section(self, parent):
        """Master section: Volume knob above vertical level meter."""
        section = tk.Frame(parent, bg='#444444', relief=tk.RIDGE, bd=1)
        section.pack(side=tk.RIGHT, padx=6, pady=4, fill=tk.Y)

        tk.Label(section, text="Master", font=("Arial", 11, "bold"),
                 fg='white', bg='#444444').pack(pady=(6, 4))

        self.volume_scale = Knob(section, from_=0, to=100, resolution=1,
                                 label="Volume", value_format="{:.0f}%",
                                 size=64, initial=80,
                                 command=self._on_volume_changed)
        self.volume_scale.set(80)
        self.volume_scale.pack(pady=(0, 6))

        meter_row = tk.Frame(section, bg='#444444')
        meter_row.pack(padx=8, pady=(0, 8))

        self.gain_canvas = Canvas(meter_row, bg='#1a1a1a', highlightthickness=1,
                                  highlightbackground='#555555',
                                  width=50, height=220)
        self.gain_canvas.pack(side=tk.LEFT, padx=(0, 6))

        self.level_label = tk.Label(meter_row, text="0%\n(0.00)",
                                    font=("Arial", 9), fg='#00AA00', bg='#444444',
                                    justify=tk.CENTER)
        self.level_label.pack(side=tk.LEFT)

    def _on_volume_changed(self, _):
        self.on_volume_change(self.volume_scale.get() / 100.0)

    def _on_lpf_changed(self, _):
        t = self.lpf_cutoff_scale.get() / 100.0
        cutoff = 20.0 * (1000.0 ** t)  # log mapping: 20 Hz → 20000 Hz
        q = self.lpf_q_scale.get() / 10.0
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
    
    def _draw_envelope(self):
        """Draw ADSR envelope visualization."""
        self.envelope_canvas.delete('all')
        
        # Canvas size
        w = self.envelope_canvas.winfo_width()
        h = self.envelope_canvas.winfo_height()
        if w <= 1:
            w = 360
        if h <= 1:
            h = 120
        
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
                                        fill='#555555', width=1)  # Time axis
        self.envelope_canvas.create_line(margin_x, margin_y, margin_x, h - margin_y,
                                        fill='#555555', width=1)  # Amplitude axis
        
        # Draw labels
        self.envelope_canvas.create_text(margin_x - 15, h - margin_y, text='0',
                                        fill='#888888', font=('Arial', 8))
        self.envelope_canvas.create_text(margin_x - 15, margin_y + graph_h, text='1',
                                        fill='#888888', font=('Arial', 8))
        
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
                                               fill='#00FF00', width=2)
            
            # Draw points
            for x, y in points:
                self.envelope_canvas.create_oval(x - 3, y - 3, x + 3, y + 3,
                                               fill='#00FF00', outline='#00AA00')
        
        # Draw attack label
        attack_x = margin_x + self.attack * time_scale / 2
        self.envelope_canvas.create_text(attack_x, h - margin_y + 15, text='A',
                                        fill='#888888', font=('Arial', 8))
        
        # Draw decay label
        decay_x = margin_x + self.attack * time_scale + self.decay * time_scale / 2
        self.envelope_canvas.create_text(decay_x, h - margin_y + 15, text='D',
                                        fill='#888888', font=('Arial', 8))
        
        # Draw sustain label
        sustain_x = margin_x + (self.attack + self.decay) * time_scale + 0.5 * time_scale
        self.envelope_canvas.create_text(sustain_x, h - margin_y + 15, text='S',
                                        fill='#888888', font=('Arial', 8))
        
        # Draw release label
        release_x = margin_x + (self.attack + self.decay + 1.0) * time_scale + self.release * time_scale / 2
        self.envelope_canvas.create_text(release_x, h - margin_y + 15, text='R',
                                        fill='#888888', font=('Arial', 8))
    
    def update_gain_meter(self, current_level: float, peak_level: float, is_clipping: bool = False):
        """Update the vertical gain meter display.
        
        Args:
            current_level: Current output level (0-1)
            peak_level: Peak level since last reset (0-1)
            is_clipping: Whether currently clipping
        """
        # Smooth the level updates to prevent flashing
        self.smoothed_level = self.meter_smooth_alpha * current_level + (1 - self.meter_smooth_alpha) * self.smoothed_level
        
        self.current_level = self.smoothed_level
        self.peak_level = peak_level
        
        # Update canvas
        self.gain_canvas.delete('all')
        
        w = self.gain_canvas.winfo_width()
        h = self.gain_canvas.winfo_height()
        if w <= 1:
            w = 50
        if h <= 1:
            h = 220
        
        margin = 5
        meter_h = h - margin * 2
        
        # Background
        self.gain_canvas.create_rectangle(margin, margin, w - margin, h - margin,
                                         fill='#0a0a0a', outline='#555555')
        
        # Clipping zones (from bottom to top)
        clip_threshold = 0.9
        clip_y = margin + meter_h * (1.0 - clip_threshold)
        
        # Warn zone (0.7-0.9)
        warn_y = margin + meter_h * (1.0 - 0.7)
        self.gain_canvas.create_rectangle(margin, clip_y, w - margin, warn_y,
                                         fill='#3a3a00', outline='')
        
        # Clip zone (0.9+)
        self.gain_canvas.create_rectangle(margin, margin, w - margin, clip_y,
                                         fill='#3a0000', outline='')
        
        # Current level bar (grows upward from bottom)
        current_height = meter_h * min(self.current_level, 1.0)
        current_y = h - margin - current_height
        
        if is_clipping:
            bar_color = '#FF3333'
        elif self.current_level > 0.9:
            bar_color = '#FFAA00'
        elif self.current_level > 0.7:
            bar_color = '#FFFF00'
        else:
            bar_color = '#00FF00'
        
        self.gain_canvas.create_rectangle(margin, current_y, w - margin, h - margin,
                                         fill=bar_color, outline='')
        
        # Target level markers
        self.gain_canvas.create_line(margin, margin + meter_h * (1.0 - 0.7), w - margin, margin + meter_h * (1.0 - 0.7),
                                    fill='#555555', width=1)  # 70% line
        self.gain_canvas.create_line(margin, margin + meter_h * (1.0 - 0.95), w - margin, margin + meter_h * (1.0 - 0.95),
                                    fill='#555555', width=1)  # 95% line
        
        # Update text label
        percent = self.current_level * 100
        clip_text = "\n(CLIP!)" if is_clipping else ""
        self.level_label.config(text=f"{percent:.0f}%\n({self.current_level:.2f}){clip_text}",
                               fg='#FF3333' if is_clipping else '#00AA00')
    
    def _get_midi_note(self, white_key_index: int, octave: int) -> int:
        """Get MIDI note number from white key index and octave."""
        midi_offsets = [0, 2, 4, 5, 7, 9, 11]
        return octave * 12 + midi_offsets[white_key_index % 7]
    
    def _draw_piano(self):
        """Draw all piano keys on the canvas."""
        self.key_map = {}  # Maps canvas item ID to MIDI note
        
        x_pos = 10
        
        # Draw white keys first
        for octave in range(self.START_OCTAVE, self.END_OCTAVE + 1):
            for white_key_idx, white_key_name in enumerate(self.WHITE_KEYS):
                midi_note = self._get_midi_note(white_key_idx, octave)
                
                key_id = self.canvas.create_rectangle(
                    x_pos, 10,
                    x_pos + self.WHITE_KEY_WIDTH, 10 + self.WHITE_KEY_HEIGHT,
                    fill='white', outline='black', width=2
                )
                
                self.key_map[key_id] = midi_note
                x_pos += self.WHITE_KEY_WIDTH
        
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
                        fill='black', outline='#333333', width=1
                    )
                    
                    self.key_map[key_id] = midi_note
                
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
        if highlighted:
            current_fill = self.canvas.itemcget(key_id, 'fill')
            if current_fill == 'white':
                self.canvas.itemconfig(key_id, fill='#CCCCCC')
            else:
                self.canvas.itemconfig(key_id, fill='#444444')
        else:
            note_num = self.key_map[key_id]
            note_in_octave = note_num % 12
            black_key_midi = [1, 3, 6, 8, 10]
            
            if note_in_octave in black_key_midi:
                self.canvas.itemconfig(key_id, fill='black')
            else:
                self.canvas.itemconfig(key_id, fill='white')
    
    def update_voice_count(self, count: int):
        """Update the active voice count display."""
        self.info_label.config(text=f"Active voices: {count}/16")
