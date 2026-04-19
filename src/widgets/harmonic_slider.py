"""Custom vertical slider widget for harmonic amplitude control."""
import tkinter as tk


class HarmonicSlider(tk.Frame):
    """Vertical slider for a single harmonic bin (0.0–1.0).

    Clicking anywhere on the track jumps to that value immediately.
    """

    TRACK_WIDTH  = 18
    TRACK_HEIGHT = 110
    FILL_COLOR   = "#00AA00"
    TRACK_COLOR  = "#2a2a2a"
    THUMB_COLOR  = "#00DD00"

    def __init__(self, parent, *, label="", initial=0.0, command=None, bg="#444444"):
        super().__init__(parent, bg=bg)
        self._value   = max(0.0, min(1.0, float(initial)))
        self._command = command
        self._bg      = bg

        # Index label above
        if label:
            tk.Label(self, text=label, font=("Arial", 7),
                     fg="#aaaaaa", bg=bg, width=3).pack()

        # Track canvas
        self._canvas = tk.Canvas(
            self,
            width=self.TRACK_WIDTH,
            height=self.TRACK_HEIGHT,
            bg=bg,
            highlightthickness=1,
            highlightbackground="#555555",
            cursor="sb_v_double_arrow",
        )
        self._canvas.pack()

        # Percentage label below
        self._pct_label = tk.Label(
            self, text=self._pct_text(), font=("Arial", 7),
            fg="#cccccc", bg=bg, width=4,
        )
        self._pct_label.pack()

        self._canvas.bind("<Button-1>",  self._on_click)
        self._canvas.bind("<B1-Motion>", self._on_drag)

        self._redraw()

    # ── Public API ────────────────────────────────────────────────────────────

    def get(self) -> float:
        return self._value

    def set(self, value: float) -> None:
        new = max(0.0, min(1.0, float(value)))
        if new == self._value:
            return
        self._value = new
        self._redraw()
        self._pct_label.config(text=self._pct_text())
        if self._command:
            self._command(self._value)

    # ── Internal ──────────────────────────────────────────────────────────────

    def _pct_text(self) -> str:
        return f"{round(self._value * 100)}%"

    def _y_to_value(self, y: int) -> float:
        return max(0.0, min(1.0, 1.0 - y / self.TRACK_HEIGHT))

    def _on_click(self, event):
        self.set(self._y_to_value(event.y))

    def _on_drag(self, event):
        self.set(self._y_to_value(event.y))

    def _redraw(self):
        c = self._canvas
        w = self.TRACK_WIDTH
        h = self.TRACK_HEIGHT
        fill_y = h * (1.0 - self._value)

        c.delete("all")
        # Empty part
        c.create_rectangle(0, 0, w, fill_y, fill=self.TRACK_COLOR, outline="")
        # Filled part
        c.create_rectangle(0, fill_y, w, h, fill=self.FILL_COLOR, outline="")
        # Thumb line
        c.create_line(0, fill_y, w, fill_y, fill=self.THUMB_COLOR, width=2)
