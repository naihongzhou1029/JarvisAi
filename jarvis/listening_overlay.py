"""Siri-style listening overlay at the top-right of the screen.

A small borderless pill window with an animated multicolour waveform and a
"Listening…" label. Shown while Jarvis accepts a voice prompt, hidden as soon
as recording stops (timeout, silence, or abort).

Runs Tkinter in its own daemon thread. Cross-thread control is done purely
with :class:`threading.Event` flags — Tk objects are only ever touched from
the Tk thread — so ``show()`` / ``hide()`` are safe to call from the voice
pipeline. Degrades to a no-op when Tkinter or a display is unavailable.
"""
from __future__ import annotations

import math
import os
import threading
import time

_show_event = threading.Event()
_hide_event = threading.Event()
_thread: threading.Thread | None = None
_thread_lock = threading.Lock()
_visible = threading.Event()  # True while the window is on screen.


def _ui_enabled() -> bool:
    try:
        import yaml
        from pathlib import Path

        cfg_path = Path(__file__).parent.parent / "config.yaml"
        with open(cfg_path) as f:
            cfg = yaml.safe_load(f) or {}
        return bool(cfg.get("ui", {}).get("listening_overlay", True))
    except Exception:
        return True


def _can_show() -> bool:
    if not _ui_enabled():
        return False
    if not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
        return False
    try:
        import tkinter  # noqa: F401
    except Exception:
        return False
    return True


def is_visible() -> bool:
    """True while the overlay window is currently on screen."""
    return _visible.is_set()


def show() -> bool:
    """Show the listening animation (idempotent). Returns True if showing."""
    global _thread
    if not _can_show():
        return False
    _hide_event.clear()
    _show_event.set()
    with _thread_lock:
        if _thread is None or not _thread.is_alive():
            _thread = threading.Thread(
                target=_overlay_thread_main, name="jarvis-overlay", daemon=True
            )
            _thread.start()
    return True


def hide() -> None:
    """Hide the listening animation (idempotent)."""
    _show_event.clear()
    _hide_event.set()


# ─── Tk thread internals (never touched from other threads) ───

_BAR_COUNT = 28
_BAR_COLORS = [
    "#22d3ee", "#38bdf8", "#60a5fa", "#818cf8",
    "#a78bfa", "#c084fc", "#e879f9", "#f472b6",
]

_WIDTH, _HEIGHT = 300, 116


def _overlay_thread_main() -> None:
    import tkinter as tk

    try:
        root = tk.Tk()
    except Exception as e:
        print(f"[Overlay] Cannot open window: {e}")
        return
    root.title("Jarvis listening")
    try:
        root.overrideredirect(True)
    except Exception:
        pass
    try:
        root.attributes("-topmost", True)
    except Exception:
        pass
    try:
        root.attributes("-alpha", 0.93)
    except Exception:
        pass

    # Top-right with a small margin (below the GNOME top bar).
    try:
        sw = root.winfo_screenwidth()
    except Exception:
        sw = 1920
    x = max(0, sw - _WIDTH - 24)
    root.geometry(f"{_WIDTH}x{_HEIGHT}+{x}+48")
    try:
        root.configure(bg="#0b0f1a")
    except Exception:
        pass

    canvas = tk.Canvas(
        root,
        width=_WIDTH,
        height=_HEIGHT,
        bg="#0b0f1a",
        highlightthickness=0,
        bd=0,
    )
    canvas.pack(fill="both", expand=True)

    label_id = canvas.create_text(
        _WIDTH // 2, 22,
        text="Listening…",
        fill="#e2e8f0",
        font=("Sans", 12, "bold"),
    )
    bars: list[int] = []
    for i in range(_BAR_COUNT):
        color = _BAR_COLORS[i % len(_BAR_COLORS)]
        bar = canvas.create_rectangle(0, 0, 0, 0, fill=color, outline="")
        bars.append(bar)

    t0 = time.monotonic()
    closed = False

    def _tick() -> None:
        nonlocal closed
        if closed:
            return
        # External hide request, or a show() from an older cycle → close.
        if _hide_event.is_set() or not _show_event.is_set():
            closed = True
            try:
                root.destroy()
            except Exception:
                pass
            _visible.clear()
            return
        t = time.monotonic() - t0
        mid_y = 72
        slot = (_WIDTH - 32) / _BAR_COUNT
        for i, bar in enumerate(bars):
            # Travelling sine gives the flowing Siri-wave feel.
            phase = t * 4.0 - i * 0.55
            amp = 8 + 22 * (0.5 + 0.5 * math.sin(phase))
            amp *= 0.75 + 0.25 * math.sin(t * 1.7 + i * 0.2)
            x0 = 16 + i * slot + 1.5
            x1 = 16 + (i + 1) * slot - 1.5
            canvas.coords(bar, x0, mid_y - amp / 2, x1, mid_y + amp / 2)
        # Gentle label pulse.
        try:
            dots = "." * (1 + int(t * 2) % 3)
            canvas.itemconfig(label_id, text=f"Listening{dots}")
        except Exception:
            pass
        try:
            root.after(33, _tick)
        except Exception:
            pass

    _visible.set()
    try:
        root.after(33, _tick)
        root.mainloop()
    except Exception:
        pass
    finally:
        _visible.clear()
