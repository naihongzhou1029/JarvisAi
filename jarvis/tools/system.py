"""System control tools — Ubuntu/Linux port (wpctl, brightnessctl, etc.)."""
import shutil
import subprocess
import threading
import time

import psutil


def _run(cmd, timeout=10) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def _wpctl(*args, timeout=10) -> subprocess.CompletedProcess:
    return _run(["wpctl"] + list(args), timeout=timeout)


def set_volume(level: int) -> str:
    """Set system volume (0-100) via wpctl."""
    level = max(0, min(100, level))
    scalar = level / 100.0
    r = _wpctl("set-volume", "@DEFAULT_AUDIO_SINK@", f"{scalar:.2f}")
    if r.returncode == 0:
        return f"Volume set to {level}%."
    return f"Could not set volume: {r.stderr.strip()}"


def get_volume() -> str:
    """Get current system volume (0-100)."""
    r = _wpctl("get-volume", "@DEFAULT_AUDIO_SINK@")
    try:
        # output like: "Volume: 0.50" or "Volume: 0.50 [MUTED]"
        val = r.stdout.split(":", 1)[1].strip().split()[0]
        vol = round(float(val) * 100)
        return f"Volume is at {vol}%."
    except Exception:
        return "Could not read volume."


def get_clipboard() -> str:
    """Return current clipboard text."""
    if shutil.which("wl-paste"):
        r = _run(["wl-paste"], timeout=5)
        return r.stdout
    if shutil.which("xclip"):
        r = _run(["xclip", "-selection", "clipboard", "-o"], timeout=5)
        return r.stdout
    return "Clipboard tool not available."


def set_clipboard(text: str) -> str:
    """Set clipboard content."""
    if shutil.which("wl-copy"):
        subprocess.run(["wl-copy"], input=text, text=True, timeout=5)
        return "Clipboard updated."
    if shutil.which("xclip"):
        subprocess.run(["xclip", "-selection", "clipboard"], input=text, text=True, timeout=5)
        return "Clipboard updated."
    return "Clipboard tool not available."


def get_system_info() -> str:
    """Get CPU, RAM, and disk usage."""
    try:
        cpu = psutil.cpu_percent(interval=0.5)
        vm = psutil.virtual_memory()
        disk = psutil.disk_usage("/")
        ram_used = round(vm.used / (1024 ** 3), 1)
        ram_total = round(vm.total / (1024 ** 3), 1)
        disk_free = round(disk.free / (1024 ** 3), 1)
        disk_total = round(disk.total / (1024 ** 3), 1)
        return f"CPU: {cpu}% | RAM: {ram_used}/{ram_total} GB | Disk /: {disk_free}/{disk_total} GB free"
    except Exception as e:
        return f"Could not read system info: {e}"


def set_brightness(level: int) -> str:
    """Set screen brightness (0-100). Only works on laptops."""
    level = max(0, min(100, level))
    if shutil.which("brightnessctl"):
        r = _run(["brightnessctl", "set", f"{level}%"], timeout=5)
        if r.returncode == 0:
            return f"Brightness set to {level}%."
        return f"Could not set brightness: {r.stderr.strip()}"
    return "Brightness control not available."


def lock_screen() -> str:
    """Lock the workstation."""
    try:
        r = _run(["loginctl", "lock-session"], timeout=5)
        if r.returncode == 0:
            return "Screen locked."
        # fallback: GNOME dbus lock
        r2 = _run(["gdbus", "call", "--session", "--dest", "org.gnome.ScreenSaver",
                   "--object-path", "/org/gnome/ScreenSaver", "--method", "org.gnome.ScreenSaver.Lock"], timeout=5)
        return "Screen locked."
    except Exception as e:
        return f"Could not lock: {e}"


def power_command(action: str) -> str:
    """Shutdown, restart, or sleep the PC."""
    action = action.lower().strip()
    try:
        if action == "shutdown":
            subprocess.Popen(["systemctl", "poweroff"])
            return "Shutting down."
        elif action == "restart":
            subprocess.Popen(["systemctl", "reboot"])
            return "Restarting."
        elif action == "sleep":
            subprocess.Popen(["systemctl", "suspend"])
            return "Going to sleep."
    except Exception as e:
        return f"Power command failed: {e}"
    return f"Unknown power action: {action}. Use shutdown/restart/sleep."


def show_notification(title: str, message: str) -> str:
    """Show a desktop notification."""
    if shutil.which("notify-send"):
        r = _run(["notify-send", title, message], timeout=5)
        if r.returncode == 0:
            return f"Notification shown: {title}"
        return f"Notification failed: {r.stderr.strip()}"
    return "notify-send not available."


# --- Timer / Reminder ---
_timers: list = []


def set_timer(seconds: int, message: str = "Timer done!") -> str:
    """Set a timer that shows a notification after N seconds."""
    def _timer_cb():
        show_notification("Jarvis Timer", message)

    t = threading.Timer(seconds, _timer_cb)
    t.daemon = True
    t.start()
    _timers.append(t)

    if seconds >= 3600:
        time_str = f"{seconds // 3600}h {(seconds % 3600) // 60}m"
    elif seconds >= 60:
        time_str = f"{seconds // 60}m {seconds % 60}s"
    else:
        time_str = f"{seconds}s"
    return f"Timer set for {time_str}: {message}"
