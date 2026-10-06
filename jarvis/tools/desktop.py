"""Wayland/GNOME desktop automation backend.

Replaces the original Windows pyautogui + PowerShell OCR implementation with:
- input injection via `ydotool` (uinput, works under Wayland)
- screenshots via `gnome-screenshot` / GNOME Shell D-Bus / XDG portal
- OCR via `tesseract`

Note: window enumeration / focus is not available on GNOME Wayland without a
shell extension, so those tools degrade gracefully.
"""
import shutil
import subprocess
import time
import os
import tempfile


def _run(cmd, timeout=10) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def _ydotool(args: list[str], timeout=10) -> bool:
    try:
        r = _run(["ydotool"] + args, timeout=timeout)
        return r.returncode == 0
    except Exception:
        return False


# ─────────────── Key name → Linux keycode ───────────────
# Full table not needed; common names map to keycodes from input-event-codes.h.
_KEYCODES = {
    "esc": 1, "escape": 1, "enter": 28, "return": 28, "tab": 15,
    "space": 57, "backspace": 14, "delete": 111, "del": 111,
    "up": 103, "down": 108, "left": 105, "right": 106,
    "home": 102, "end": 107, "pageup": 104, "pagedown": 109,
    "page_up": 104, "page_down": 109, "insert": 110, "ins": 110,
    "capslock": 58, "shift": 42, "ctrl": 29, "control": 29, "alt": 56,
    "super": 125, "win": 125, "cmd": 125, "meta": 125,
    "printscreen": 99, "f1": 59, "f2": 60, "f3": 61, "f4": 62, "f5": 63,
    "f6": 64, "f7": 65, "f8": 66, "f9": 67, "f10": 68, "f11": 87, "f12": 88,
    # printable
    "a": 30, "b": 48, "c": 46, "d": 32, "e": 18, "f": 33, "g": 34,
    "h": 35, "i": 23, "j": 36, "k": 37, "l": 38, "m": 50, "n": 49,
    "o": 24, "p": 25, "q": 16, "r": 19, "s": 31, "t": 20, "u": 22,
    "v": 47, "w": 17, "x": 45, "y": 21, "z": 44,
    "0": 11, "1": 2, "2": 3, "3": 4, "4": 5, "5": 6, "6": 7, "7": 8,
    "8": 9, "9": 10,
}

_MODIFIER_KEYS = {"ctrl", "control", "shift", "alt", "super", "win", "cmd", "meta"}


def _keycode(name: str) -> int:
    name = name.strip().lower()
    if name in _KEYCODES:
        return _KEYCODES[name]
    raise ValueError(f"Unknown key name: {name}")


def type_text(text: str) -> str:
    """Type text at the current cursor position."""
    time.sleep(0.15)
    try:
        r = _run(["ydotool", "type", "--key-delay", "20", text], timeout=30)
        if r.returncode != 0:
            return f"Typing failed: {r.stderr.strip()}"
    except Exception as e:
        return f"Typing failed: {e}"
    return f"Typed: {text[:80]}"


def press_key(keys: str) -> str:
    """Press a key or hotkey combo. Example: 'ctrl+shift+esc', 'alt+tab', 'enter'."""
    parts = [k.strip().lower() for k in keys.split("+") if k.strip()]
    try:
        mods = [p for p in parts if p in _MODIFIER_KEYS]
        mains = [p for p in parts if p not in _MODIFIER_KEYS]
        seq = []
        # press modifiers
        for m in mods:
            seq.append(f"{_keycode(m)}:1")
        # press and release main keys
        for k in mains:
            seq.append(f"{_keycode(k)}:1")
        for k in mains:
            seq.append(f"{_keycode(k)}:0")
        # release modifiers
        for m in mods:
            seq.append(f"{_keycode(m)}:0")
        if not seq:
            return f"No keys parsed from: {keys}"
        r = _run(["ydotool", "key"] + seq, timeout=10)
        if r.returncode != 0:
            return f"Key press failed: {r.stderr.strip()}"
    except ValueError as e:
        return str(e)
    return f"Pressed: {keys}"


# ──────────────── Mouse Control ────────────────

def click_at(x: int, y: int, button: str = "left") -> str:
    """Click at screen coordinates (x, y). Button: left, right, double."""
    _ydotool(["mousemove", "--absolute", "-x", str(x), "-y", str(y)])
    time.sleep(0.05)
    if button == "double":
        _ydotool(["click", "0xC0"])
        time.sleep(0.05)
        _ydotool(["click", "0xC0"])
    elif button == "right":
        _ydotool(["click", "0xC1"])
    else:
        _ydotool(["click", "0xC0"])
    return f"Clicked ({button}) at ({x}, {y})."


def scroll_screen(direction: str, amount: int = 3) -> str:
    """Scroll up or down. Amount = number of scroll steps."""
    direction = direction.lower()
    if direction not in ("up", "down"):
        return f"Unknown direction: {direction}. Use up/down."
    # ydotool has no dedicated wheel command; use arrow/page keys which scroll
    # most applications on Wayland.
    if direction == "up":
        seq = "pageup" if amount >= 3 else "up"
        for _ in range(max(1, amount if amount < 3 else 1)):
            press_key(seq)
            time.sleep(0.03)
    else:
        seq = "pagedown" if amount >= 3 else "down"
        for _ in range(max(1, amount if amount < 3 else 1)):
            press_key(seq)
            time.sleep(0.03)
    return f"Scrolled {direction} by {amount}."


def move_mouse(x: int, y: int) -> str:
    """Move mouse cursor to (x, y) without clicking."""
    if _ydotool(["mousemove", "--absolute", "-x", str(x), "-y", str(y)]):
        return f"Moved mouse to ({x}, {y})."
    return "Move mouse failed."


# ──────────────── Screenshot ────────────────

_GI_PY: str | None = None
_SHOT_HELPER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_shot.py")


def _gi_python() -> str | None:
    """Find an interpreter that can import PyGObject (system python3 on Ubuntu)."""
    global _GI_PY
    if _GI_PY is not None:
        return _GI_PY or None
    import sys
    candidates = ["/usr/bin/python3", sys.exec_prefix + "/bin/python3", "python3"]
    for py in candidates:
        if not py or not shutil.which(py) and not os.path.exists(py):
            continue
        try:
            r = _run([py, "-c", "import gi"], timeout=10)
            if r.returncode == 0:
                _GI_PY = py
                return py
        except Exception:
            continue
    _GI_PY = ""
    return None


def _screenshot_to_file(path: str) -> bool:
    """Best-effort screenshot under GNOME Wayland. Returns True on success."""
    py = _gi_python()
    if py:
        try:
            r = _run([py, _SHOT_HELPER, path], timeout=20)
            if r.returncode == 0 and os.path.exists(path):
                return True
        except Exception:
            pass
    # Fallback: gnome-screenshot (if present)
    if shutil.which("gnome-screenshot"):
        try:
            r = _run(["gnome-screenshot", "-f", path], timeout=10)
            if r.returncode == 0 and os.path.exists(path):
                return True
        except Exception:
            pass
    return os.path.exists(path)



# ──────────────── Screen Reading (OCR) ────────────────

def read_screen() -> str:
    """Take a screenshot and OCR it. Returns all visible text with approximate positions.
    Format: each line is 'text | x,y' where x,y is the center of the text bounding box."""
    tmp = os.path.join(tempfile.gettempdir(), "jarvis_screen.png")
    if not _screenshot_to_file(tmp):
        return "Could not take a screenshot."
    return _ocr_image(tmp)


def _ocr_image(image_path: str) -> str:
    """Run tesseract OCR on an image, return text with positions."""
    try:
        r = _run([
            "tesseract", image_path, "stdout", "--psm", "6", "tsv",
        ], timeout=20)
    except Exception as e:
        return f"OCR failed: {e}"
    lines = []
    for raw in r.stdout.splitlines():
        parts = raw.split("\t")
        if len(parts) < 12:
            continue
        try:
            conf = float(parts[10])
            text = parts[11].strip()
        except (ValueError, IndexError):
            continue
        if not text or conf <= 0:
            continue
        try:
            left, top, w, h = int(parts[6]), int(parts[7]), int(parts[8]), int(parts[9])
        except ValueError:
            continue
        cx, cy = left + w // 2, top + h // 2
        lines.append(f"{text} | {cx},{cy}")
    if not lines:
        return "No text found on screen."
    return "\n".join(lines)


def find_on_screen(text: str) -> str:
    """Find text on screen using OCR. Returns coordinates of the match, or 'not found'.
    Use click_at() with the returned coordinates to click on it."""
    screen_text = read_screen()
    if screen_text in ("No text found on screen.", "Could not take a screenshot."):
        return screen_text

    target = text.lower()

    def _scan(screen):
        best_match = None
        best_score = 0
        for line in screen.split("\n"):
            if " | " not in line:
                continue
            content, coords = line.rsplit(" | ", 1)
            content_lower = content.lower()
            if target in content_lower:
                x, y = coords.split(",")
                return f"Found '{text}' at ({x.strip()}, {y.strip()}). Use click_at to click it."
            words_target = set(target.split())
            words_content = set(content_lower.split())
            overlap = len(words_target & words_content)
            if overlap > best_score:
                best_score = overlap
                best_match = (content, coords)
        if best_match and best_score > 0:
            content, coords = best_match
            x, y = coords.split(",")
            return f"Closest match: '{content}' at ({x.strip()}, {y.strip()}). Use click_at to click it."
        return None

    result = _scan(screen_text)
    if result:
        return result

    # Try scrolling down and searching again
    scroll_screen("down", 3)
    time.sleep(0.5)
    screen_text_2 = read_screen()
    result = _scan(screen_text_2)
    if result:
        return result.replace(". Use click_at", " (after scrolling). Use click_at")

    return f"'{text}' not found on screen (tried scrolling)."


# ──────────────── Window Management ────────────────

def get_open_windows() -> str:
    """Return titles of all open windows. Not supported on GNOME Wayland."""
    return "get_open_windows() is not supported on GNOME Wayland (sandboxed). Use web UI window list instead."


def focus_window(title: str) -> str:
    """Bring a window to the foreground by partial title match. Not supported on Wayland."""
    return "focus_window() is not supported on GNOME Wayland (sandboxed)."


# ──────────────── Media Control ────────────────

def media_control(action: str) -> str:
    """Control media playback: play, pause, next, previous, mute."""
    action = action.lower().strip()
    map_ = {
        "play": ["playerctl", "play"],
        "pause": ["playerctl", "pause"],
        "playpause": ["playerctl", "play-pause"],
        "next": ["playerctl", "next"],
        "skip": ["playerctl", "next"],
        "previous": ["playerctl", "previous"],
        "prev": ["playerctl", "previous"],
        # Mute = set MPRIS volume to 0
        "mute": ["playerctl", "volume", "0.0"],
    }
    cmd = map_.get(action)
    if cmd is None:
        return f"Unknown media action: {action}. Use play/pause/next/previous/mute."
    try:
        r = _run(cmd, timeout=5)
        if r.returncode == 0:
            return f"Media: {action}"
        return f"Media action failed: {r.stderr.strip()}"
    except FileNotFoundError:
        return "playerctl not available."


def screenshot(filename: str = "") -> str:
    """Take a screenshot and save to Desktop."""
    desktop = os.path.join(os.path.expanduser("~"), "Desktop")
    if not filename:
        filename = f"screenshot_{int(time.time())}.png"
    if not filename.endswith(".png"):
        filename += ".png"
    path = os.path.join(desktop, filename)
    tmp = path
    if _screenshot_to_file(tmp):
        return f"Screenshot saved: {path}"
    return "Could not take a screenshot."
