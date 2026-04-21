"""Central palette and font constants for the PythonSynth GUI.

Single source of truth imported by piano_gui and the custom widgets so that
every accent element shares one color.
"""

# ── Palette ───────────────────────────────────────────────────────────────
BG_ROOT        = "#1E1E24"
BG_PANEL       = "#2A2A33"
BG_INSET       = "#14141A"
BORDER_SUBTLE  = "#3A3A45"

ACCENT         = "#6B5BE8"
ACCENT_MUTED   = "#8A7FE0"

TEXT_PRIMARY   = "#DADAE0"
TEXT_SECONDARY = "#8A8A95"

DANGER         = "#CC3333"
DANGER_ACTIVE  = "#FF4444"

# Gain-meter zones kept as industry-standard audio convention.
METER_SAFE     = "#00FF00"
METER_WARN     = "#FFFF00"
METER_HOT      = "#FFAA00"
METER_CLIP     = "#FF3333"
METER_GUIDE    = "#3A3A45"
METER_WARN_BG  = "#2A2A00"
METER_CLIP_BG  = "#2A0000"

# ── Fonts ─────────────────────────────────────────────────────────────────
FONT_FAMILY     = "Segoe UI"
FONT_TITLE      = (FONT_FAMILY, 20, "bold")
FONT_SECTION    = (FONT_FAMILY, 12, "bold")
FONT_SUBGROUP   = (FONT_FAMILY, 8, "bold")
FONT_LABEL      = (FONT_FAMILY, 9)
FONT_LABEL_BOLD = (FONT_FAMILY, 9, "bold")
FONT_VALUE      = (FONT_FAMILY, 8)
FONT_SMALL      = (FONT_FAMILY, 7)
