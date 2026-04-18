"""Rotary knob widget for tkinter. Drop-in replacement for tk.Scale."""

import math
import tkinter as tk


_START_ANGLE_DEG = 225.0
_SWEEP_DEG = 270.0
_DRAG_PIXELS_FULL_RANGE = 150.0


class Knob(tk.Frame):
    """Canvas-based rotary knob.

    API mirrors tk.Scale: .get(), .set(value), config(command=...).
    The command callback receives the new value as a string, matching Scale.

    Parameters
    ----------
    parent : tk widget
    from_, to : float
        Value range. May be inverted (from_ > to).
    resolution : float
        Step for wheel scroll and rounding. >=1 -> int values.
    label : str
        Parameter name shown above the knob.
    value_format : str
        Format string for the value label (e.g. "{:.0f}", "{:.2f}").
    size : int
        Diameter of the knob canvas in pixels.
    command : callable or None
        Called with the new value (as str) whenever it changes.
    initial : float or None
        Value used by double-click reset. Defaults to from_.
    bg : str
        Frame background.
    """

    def __init__(
        self,
        parent,
        *,
        from_,
        to,
        resolution=1,
        label="",
        value_format="{:.0f}",
        size=56,
        command=None,
        initial=None,
        bg="#444444",
    ):
        super().__init__(parent, bg=bg)

        self._from = float(from_)
        self._to = float(to)
        self._resolution = float(resolution)
        self._format = value_format
        self._command = command
        self._size = int(size)
        self._initial = float(initial) if initial is not None else self._from
        self._value = self._initial

        self._drag_y0 = None
        self._drag_v0 = None
        self._drag_delta_px = 0

        self._name_label = tk.Label(
            self,
            text=label,
            font=("Arial", 9, "bold"),
            fg="#AAAAFF",
            bg=bg,
        )
        self._name_label.pack()

        self._canvas = tk.Canvas(
            self,
            width=self._size,
            height=self._size,
            bg=bg,
            highlightthickness=0,
        )
        self._canvas.pack()

        self._value_label = tk.Label(
            self,
            text="",
            font=("Arial", 8),
            fg="#888888",
            bg=bg,
            width=8,
        )
        self._value_label.pack()

        self._canvas.bind("<ButtonPress-1>", self._on_press)
        self._canvas.bind("<B1-Motion>", self._on_drag)
        self._canvas.bind("<ButtonRelease-1>", self._on_release)
        self._canvas.bind("<Double-Button-1>", self._on_double_click)
        self._canvas.bind("<MouseWheel>", self._on_wheel)
        self._canvas.bind("<Shift-MouseWheel>", self._on_wheel)
        self._canvas.bind("<Button-4>", self._on_wheel_x11_up)
        self._canvas.bind("<Button-5>", self._on_wheel_x11_down)

        self._redraw()

    # -- Public API --------------------------------------------------------

    def get(self):
        """Return the current value. int if resolution>=1, else float."""
        if self._resolution >= 1:
            return int(round(self._value))
        return self._value

    def set(self, value):
        """Set value, clamp, redraw, fire command."""
        v = self._clamp(float(value))
        v = self._quantize(v)
        if v == self._value:
            self._redraw()
            return
        self._value = v
        self._redraw()
        if self._command is not None:
            self._command(str(self.get()))

    def config(self, **kwargs):
        if "command" in kwargs:
            self._command = kwargs.pop("command")
        if "from_" in kwargs:
            self._from = float(kwargs.pop("from_"))
        if "to" in kwargs:
            self._to = float(kwargs.pop("to"))
        if kwargs:
            super().config(**kwargs)

    configure = config

    # -- Internals ---------------------------------------------------------

    def _clamp(self, v):
        lo, hi = (self._from, self._to) if self._from <= self._to else (self._to, self._from)
        return max(lo, min(hi, v))

    def _quantize(self, v):
        if self._resolution <= 0:
            return v
        steps = round((v - self._from) / self._resolution)
        q = self._from + steps * self._resolution
        return self._clamp(q)

    def _fraction(self):
        """Return current value as 0..1 along the from_->to span."""
        span = self._to - self._from
        if span == 0:
            return 0.0
        f = (self._value - self._from) / span
        return max(0.0, min(1.0, f))

    def _redraw(self):
        c = self._canvas
        c.delete("all")
        s = self._size
        pad = 4
        x0, y0 = pad, pad
        x1, y1 = s - pad, s - pad
        cx, cy = s / 2.0, s / 2.0
        radius = (s - 2 * pad) / 2.0

        # Track arc (background).
        c.create_arc(
            x0, y0, x1, y1,
            start=_START_ANGLE_DEG + 360.0,
            extent=-_SWEEP_DEG,
            style=tk.ARC,
            outline="#2a2a2a",
            width=4,
        )

        # Value arc.
        frac = self._fraction()
        if frac > 0.0:
            c.create_arc(
                x0, y0, x1, y1,
                start=-_START_ANGLE_DEG + 360.0 - _SWEEP_DEG,
                extent=_SWEEP_DEG * -frac,
                style=tk.ARC,
                outline="#00AA00",
                width=4,
            )

        # Face circle.
        face_pad = pad + 6
        c.create_oval(
            face_pad, face_pad, s - face_pad, s - face_pad,
            fill="#444444",
            outline="#888888",
            width=1,
        )

        # Pointer line.
        angle_deg = _START_ANGLE_DEG - _SWEEP_DEG * frac
        angle_rad = math.radians(angle_deg)
        inner_r = radius - 10
        outer_r = radius - 3
        x_in = cx + inner_r * math.cos(angle_rad)
        y_in = cy - inner_r * math.sin(angle_rad)
        x_out = cx + outer_r * math.cos(angle_rad)
        y_out = cy - outer_r * math.sin(angle_rad)
        c.create_line(x_in, y_in, x_out, y_out, fill="#FFFFFF", width=2)

        # Value label.
        self._value_label.config(text=self._format.format(self._value))

    def _on_press(self, event):
        self._drag_y0 = event.y
        self._drag_v0 = self._value
        self._drag_delta_px = 0
        self._canvas.focus_set()

    def _on_drag(self, event):
        if self._drag_y0 is None:
            return
        dy = self._drag_y0 - event.y
        self._drag_delta_px = dy
        span = self._to - self._from
        delta = dy * span / _DRAG_PIXELS_FULL_RANGE
        if event.state & 0x0001:  # Shift
            delta *= 0.1
        self.set(self._drag_v0 + delta)

    def _on_release(self, _event):
        self._drag_y0 = None
        self._drag_v0 = None
        # keep _drag_delta_px for double-click guard

    def _on_double_click(self, _event):
        if abs(self._drag_delta_px) > 2:
            return
        self.set(self._initial)

    def _on_wheel(self, event):
        steps = event.delta / 120.0
        step = self._resolution if self._resolution > 0 else (self._to - self._from) / 100.0
        if event.state & 0x0001:  # Shift = fine
            step *= 0.1
        self.set(self._value + steps * step)

    def _on_wheel_x11_up(self, event):
        event.delta = 120
        self._on_wheel(event)

    def _on_wheel_x11_down(self, event):
        event.delta = -120
        self._on_wheel(event)
