"""App control — Linux/Ubuntu port."""
import os
import shutil
import subprocess
import webbrowser

# Map friendly names to Linux executables/commands.
APP_MAP = {
    # Browsers
    "chrome": "google-chrome",
    "google chrome": "google-chrome",
    "chromium": "chromium",
    "chromium-browser": "chromium-browser",
    "firefox": "firefox",
    "edge": "microsoft-edge",
    "brave": "brave-browser",
    # Communication
    "discord": "discord",
    "telegram": "telegram-desktop",
    "slack": "slack",
    "teams": "teams",
    "zoom": "zoom",
    # Dev tools
    "vscode": "code",
    "vs code": "code",
    "code": "code",
    "terminal": "gnome-terminal",
    "gnome terminal": "gnome-terminal",
    "konsole": "konsole",
    "alacritty": "alacritty",
    "kitty": "kitty",
    # Media
    "spotify": "spotify",
    "vlc": "vlc",
    "mpv": "mpv",
    # Gaming
    "steam": "steam",
    # Productivity
    "notepad": "gedit",
    "gedit": "gedit",
    "text editor": "gedit",
    "calculator": "gnome-calculator",
    "gnome-calculator": "gnome-calculator",
    "files": "nautilus",
    "file manager": "nautilus",
    "nautilus": "nautilus",
    # System
    "settings": "gnome-control-center",
    "control center": "gnome-control-center",
}

# If a friendly name maps to a missing binary but the user typed a literal
# command, try it directly.

_ARGS = {
    "discord": [],
}


def open_app(name: str) -> str:
    """Open an application by friendly name or binary name."""
    key = name.lower().strip()
    exe = APP_MAP.get(key, key)
    # Try the mapped/typed binary if on PATH
    if shutil.which(exe):
        try:
            subprocess.Popen([exe], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return f"Opening {name}."
        except Exception as e:
            return f"Could not open {name}: {e}"
    # Fallback: use gio/gtk-launch via .desktop name
    desktop = key.replace(" ", "-")
    try:
        r = subprocess.run(["gtk-launch", desktop], capture_output=True, timeout=5)
        if r.returncode == 0:
            return f"Opening {name}."
    except Exception:
        pass
    try:
        subprocess.Popen(["xdg-open", key], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return f"Opening {name}."
    except Exception as e:
        return f"Could not open {name}: {e}"


def open_url(url: str) -> str:
    """Open a URL in the default browser."""
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    webbrowser.open(url)
    return f"Opened {url}."


def kill_process(name: str) -> str:
    """Kill a process by name (e.g. 'spotify', 'chrome')."""
    safe = "".join(c for c in name if c.isalnum() or c in ".-_ ")
    result = subprocess.run(
        ["pkill", "-f", safe],
        capture_output=True, text=True,
    )
    if result.returncode == 0:
        return f"Killed {name}."
    return f"Could not kill {name} (not running or no permission)."
