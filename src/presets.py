"""Preset persistence: capture/apply full synth state, JSON save/load, folder scan.

Kept separate from GUI/DSP per CLAUDE.md (presets are a distinct concern).
No tkinter imports here — module is pure Python / numpy.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import List

import numpy as np

SCHEMA_VERSION = 1
APP_NAME = "PythonSynth"


def presets_root() -> Path:
    """Absolute path to the `presets/` directory at the project root."""
    return Path(__file__).resolve().parent.parent / "presets"


# ---------------------------------------------------------------------------
# Capture / apply
# ---------------------------------------------------------------------------

def capture_state(gui) -> dict:
    """Read the full user-visible state from the PianoGUI into a JSON-safe dict."""
    knobs = {kid: _widget_value(widget)
             for kid, (widget, _handler) in gui._assignable.items()}

    scales = {
        "delay_time": int(gui.delay_time_scale.get()),
        "transpose": int(gui.transpose_scale.get()),
    }

    wavetable = {
        "a": [float(x) for x in gui._wt_a],
        "b": [float(x) for x in gui._wt_b],
        "edit_slot": gui._edit_slot,
        "morph": int(gui._morph_pos),
    }

    lfo = {
        "selected": int(gui._lfo_selected),
        "slots": [
            {"rate": float(s["rate"]), "amp": float(s["amp"])}
            for s in gui._lfo_slot_state
        ],
        "routes": {kid: int(idx) for kid, idx in gui.lfo_bank.routes.items()},
    }

    mono = {
        "enabled": bool(gui._mono_enabled),
        "legato": int(gui.legato_knob.get()),
    }

    return {
        "schema_version": SCHEMA_VERSION,
        "app": APP_NAME,
        "knobs": knobs,
        "scales": scales,
        "wavetable": wavetable,
        "lfo": lfo,
        "mono": mono,
    }


def apply_state(gui, data: dict) -> None:
    """Write state from a preset dict back onto the GUI.

    Missing keys are tolerated — current values are kept for any unspecified
    section. Widget .set() calls fire the existing command handlers, which
    push parameters to the audio engine.
    """
    # 1) Wavetable arrays first, copied in-place so any held references stay valid.
    wt = data.get("wavetable")
    if wt is not None:
        a = wt.get("a")
        b = wt.get("b")
        if a is not None and len(a) == 16:
            gui._wt_a[:] = np.asarray(a, dtype=np.float32)
        if b is not None and len(b) == 16:
            gui._wt_b[:] = np.asarray(b, dtype=np.float32)

        edit_slot = wt.get("edit_slot")
        if edit_slot in ("A", "B"):
            gui._edit_slot = edit_slot
            gui._update_slot_button_styles()

        # Sync harmonic sliders to the (now-updated) edit slot without firing
        # per-slider writeback (which would clobber our arrays).
        gui._refresh_sliders_from_slot()

    # 2) Assignable knobs — .set() fires the command handler which pushes to engine.
    for kid, val in data.get("knobs", {}).items():
        entry = gui._assignable.get(kid)
        if entry is None:
            continue  # unknown knob id (older/newer preset); ignore
        widget, _ = entry
        try:
            widget.set(val)
        except Exception as e:
            print(f"preset: failed to set knob {kid}={val!r}: {type(e).__name__}: {e}")

    # 3) Morph position — apply after wavetable arrays so interpolation is fresh.
    if wt is not None and "morph" in wt:
        try:
            gui.morph_knob.set(int(wt["morph"]))
        except Exception as e:
            print(f"preset: failed to set morph: {type(e).__name__}: {e}")

    # 4) Non-assignable scales.
    scales = data.get("scales", {})
    if "delay_time" in scales:
        gui.delay_time_scale.set(int(scales["delay_time"]))
    if "transpose" in scales:
        gui.transpose_scale.set(int(scales["transpose"]))
        gui._on_transpose_changed(None)

    # 5) LFO: per-slot rate/amp, selection, routes.
    lfo = data.get("lfo")
    if lfo is not None:
        slots = lfo.get("slots")
        if isinstance(slots, list):
            for i, slot in enumerate(slots[:len(gui._lfo_slot_state)]):
                rate_pct = float(slot.get("rate", gui._lfo_slot_state[i]["rate"]))
                amp_pct = float(slot.get("amp", gui._lfo_slot_state[i]["amp"]))
                gui._lfo_slot_state[i] = {"rate": rate_pct, "amp": amp_pct}
                # Push directly into the LFO bank so non-visible slots also update.
                gui.lfo_bank.lfos[i].rate_hz = gui._lfo_pct_to_hz(rate_pct)
                gui.lfo_bank.lfos[i].amplitude = amp_pct / 100.0

        sel = lfo.get("selected")
        if isinstance(sel, int) and 0 <= sel < len(gui._lfo_slot_state):
            gui._lfo_selected = sel
            try:
                gui._lfo_select_var.set(f"LFO {sel + 1}")
            except Exception:
                pass
            cur = gui._lfo_slot_state[sel]
            gui.lfo_rate_knob.set(cur["rate"])
            gui.lfo_amp_knob.set(cur["amp"])

        routes = lfo.get("routes")
        if isinstance(routes, dict):
            for kid in list(gui.lfo_bank.routes.keys()):
                gui._unassign_lfo(kid)
            for kid, idx in routes.items():
                if kid in gui._assignable and isinstance(idx, int):
                    gui.lfo_bank.assign(kid, idx)

    # 6) Mono mode / legato.
    mono = data.get("mono")
    if mono is not None:
        legato_val = mono.get("legato", 0)
        try:
            gui.legato_knob.set(int(legato_val))
        except Exception:
            pass
        enabled = bool(mono.get("enabled", False))
        if enabled != gui._mono_enabled:
            gui._on_mono_toggle()


def _widget_value(widget):
    v = widget.get()
    if isinstance(v, (int, float)):
        return v
    try:
        return float(v)
    except (TypeError, ValueError):
        return v


# ---------------------------------------------------------------------------
# Filesystem
# ---------------------------------------------------------------------------

def save_preset(path: Path, data: dict) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def load_preset(path: Path) -> dict:
    with Path(path).open("r", encoding="utf-8") as f:
        data = json.load(f)
    ver = data.get("schema_version")
    if ver != SCHEMA_VERSION:
        print(f"preset: schema_version {ver!r} != {SCHEMA_VERSION}; "
              f"attempting load anyway ({path.name})")
    return data


def scan_presets(root: Path) -> List[Path]:
    """Return every *.json preset under `root`, sorted by relative path."""
    root = Path(root)
    if not root.exists():
        return []
    return sorted(root.rglob("*.json"), key=lambda p: p.relative_to(root).as_posix().lower())
