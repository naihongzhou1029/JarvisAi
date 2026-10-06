"""System tray icon: shown while Jarvis is online.

Backend: a native ``org.kde.StatusNotifierItem`` served over the session
D-Bus with ``jeepney`` (pure Python, no system dependencies). This is the
protocol GNOME's AppIndicator extension (``ubuntu-appindicators``, enabled by
default on Ubuntu) actually hosts — legacy ``GtkStatusIcon``/``zenity``
icons are *not* shown on GNOME Wayland, which is why those approaches fail
silently here.

The icon doubles as a state indicator: blue orb when idle, orange orb plus
"listening…" tooltip while Jarvis accepts a voice prompt.

Icons are rendered at runtime with Pillow into ``~/.cache/ubuntu-siri/`` so
the repo needs no binary assets. Degrades to a log-only no-op when D-Bus is
unreachable (headless/SSH) or ``jeepney`` is missing.
"""
from __future__ import annotations

import os
import threading
from pathlib import Path

_CACHE_DIR = Path.home() / ".cache" / "ubuntu-siri" / "icons"
_IDLE_ICON = _CACHE_DIR / "jarvis-tray-idle.png"
_LISTENING_ICON = _CACHE_DIR / "jarvis-tray-listening.png"

_SNI_IFACE = "org.kde.StatusNotifierItem"
_PROPS_IFACE = "org.freedesktop.DBus.Properties"
_BUS_NAME = f"org.kde.StatusNotifierItem-{os.getpid()}-jarvis"
_OBJECT_PATH = "/StatusNotifierItem"
_WATCHER = ("session", "/StatusNotifierWatcher", "org.kde.StatusNotifierWatcher")

_lock = threading.Lock()
_state: dict = {
    "conn": None,          # jeepney blocking connection
    "thread": None,        # serve-loop thread
    "stop": None,          # threading.Event
    "listening": False,
    "online": False,
    "registered": False,   # tray host (StatusNotifierWatcher) accepted us
    "tooltip": "Jarvis online — say 'Hey Jarvis'",
}

_INTROSPECT_XML = """<node>
 <interface name="org.freedesktop.DBus.Peer">
  <method name="Ping"/>
  <method name="GetMachineId"><arg name="id" type="s" direction="out"/></method>
 </interface>
 <interface name="org.freedesktop.DBus.Introspectable">
  <method name="Introspect"><arg name="xml" type="s" direction="out"/></method>
 </interface>
 <interface name="org.freedesktop.DBus.Properties">
  <method name="Get"><arg name="iface" type="s" direction="in"/><arg name="prop" type="s" direction="in"/><arg name="value" type="v" direction="out"/></method>
  <method name="GetAll"><arg name="iface" type="s" direction="in"/><arg name="props" type="a{sv}" direction="out"/></method>
 </interface>
 <interface name="org.kde.StatusNotifierItem"/>
</node>"""


def _ui_enabled() -> bool:
    """Read the ``ui.tray`` toggle from config (default on)."""
    try:
        import yaml

        cfg_path = Path(__file__).parent.parent / "config.yaml"
        with open(cfg_path) as f:
            cfg = yaml.safe_load(f) or {}
        return bool(cfg.get("ui", {}).get("tray", True))
    except Exception:
        return True


def _generate_icons() -> None:
    """Render idle/listening PNGs with Pillow (64x64, transparent bg)."""
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        return
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    if _IDLE_ICON.exists() and _LISTENING_ICON.exists():
        return

    def _orb(path: Path, core: tuple, glow: tuple) -> None:
        size = 64
        img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        cx = cy = size // 2
        for r, alpha in ((30, 40), (26, 70), (22, 110)):
            d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=glow[:3] + (alpha,))
        d.ellipse([cx - 15, cy - 15, cx + 15, cy + 15], fill=core + (255,))
        d.ellipse([cx - 9, cy - 12, cx + 1, cy - 2], fill=(255, 255, 255, 200))
        img.save(path)

    try:
        _orb(_IDLE_ICON, core=(37, 150, 255), glow=(37, 150, 255))
        _orb(_LISTENING_ICON, core=(255, 110, 80), glow=(190, 90, 255))
    except Exception as e:
        print(f"[Tray] Icon generation failed: {e}")


def _pixmap_bytes(path: Path) -> bytes:
    """PNG → ARGB32 (network byte order, per-pixel [A,R,G,B]) for IconPixmap.

    GNOME's appindicator extension converts with ``argbToRgba`` which reads
    alpha first, so the plain RGBA buffer Pillow produces must be reordered.
    """
    from PIL import Image

    img = Image.open(path).convert("RGBA").resize((64, 64))
    r, g, b, a = img.split()
    return Image.merge("RGBA", (a, r, g, b)).tobytes()


def _current_pixmap() -> tuple[int, int, bytes]:
    path = _LISTENING_ICON if _state["listening"] else _IDLE_ICON
    try:
        return (64, 64, _pixmap_bytes(path))
    except Exception:
        return (0, 0, b"")


def _props() -> dict:
    """Full property set for the ``org.kde.StatusNotifierItem`` interface."""
    w, h, px = _current_pixmap()
    tooltip = (
        "ubuntu-siri", [], "Jarvis",
        "Jarvis is listening…" if _state["listening"] else _state["tooltip"],
    )
    return {
        "Category": ("s", "ApplicationStatus"),
        "Id": ("s", "ubuntu-siri"),
        "Title": ("s", "Jarvis"),
        "Status": ("s", "Active"),
        "WindowId": ("i", 0),
        "IconName": ("s", ""),
        "IconPixmap": ("a(iiay)", [(w, h, px)] if px else []),
        "OverlayIconName": ("s", ""),
        "OverlayIconPixmap": ("a(iiay)", []),
        "AttentionIconName": ("s", ""),
        "AttentionIconPixmap": ("a(iiay)", []),
        "AttentionMovieName": ("s", ""),
        "ToolTip": ("(sa(iiay)ss)", tooltip),
        "ItemIsMenu": ("b", False),
        "Menu": ("o", "/jarvis/noop"),
    }


def _handle_message(conn, msg) -> None:
    """Reply to Properties/Peer/Introspect calls on our object."""
    from jeepney import new_method_return
    from jeepney.low_level import HeaderFields, MessageType

    fields = msg.header.fields
    if msg.header.message_type != MessageType.method_call:
        # Re-register if the watcher restarted (fresh owner appeared).
        if (
            msg.header.message_type == MessageType.signal
            and fields.get(HeaderFields.interface) == "org.freedesktop.DBus"
            and fields.get(HeaderFields.member) == "NameOwnerChanged"
        ):
            body = msg.body
            if (
                len(body) == 3 and body[0] == _WATCHER[2]
                and body[2]  # new owner non-empty
            ):
                _register(conn)
        return
    if fields.get(HeaderFields.path) != _OBJECT_PATH:
        return
    # Any inbound query from the tray host proves registration worked.
    if not _state["registered"]:
        _state["registered"] = True
        print("[Tray] Registered with the tray host.")
    iface = fields.get(HeaderFields.interface)
    member = fields.get(HeaderFields.member)
    try:
        if iface == _PROPS_IFACE and member == "Get":
            _iface_name, prop = msg.body
            value = _props().get(prop, ("s", ""))
            conn.send_message(new_method_return(msg, "v", (value,)))
        elif iface == _PROPS_IFACE and member == "GetAll":
            conn.send_message(new_method_return(msg, "a{sv}", (_props(),)))
        elif iface == "org.freedesktop.DBus.Peer" and member == "Ping":
            conn.send_message(new_method_return(msg))
        elif iface == "org.freedesktop.DBus.Introspectable" and member == "Introspect":
            conn.send_message(new_method_return(msg, "s", (_INTROSPECT_XML,)))
    except Exception:
        pass


def _serve_loop(conn, stop: threading.Event) -> None:
    import time as _time

    retry_at = 0.0
    while not stop.is_set():
        try:
            msg = conn.receive(timeout=0.5)
        except Exception:
            msg = None
        if msg is not None:
            try:
                _handle_message(conn, msg)
            except Exception:
                _time.sleep(0.05)
        # Retry registration until the tray host (GNOME extension) queries us.
        if not _state["registered"] and _time.monotonic() >= retry_at:
            retry_at = _time.monotonic() + 3.0
            _register(conn)


def _register(conn) -> None:
    """Own the bus name and announce the item to the watcher.

    All sends are fire-and-forget: jeepney's ``send_and_get_reply`` DROPS any
    other inbound message seen while waiting, and the GNOME tray host queries
    our properties (GetAll) in the very same millisecond as the registration
    reply arrives — swallowing that GetAll makes the extension's proxy init
    hang forever and the icon never appears. Replies/errors simply go unread
    here; ``registered`` flips when we see any inbound call from the host.
    """
    from jeepney import DBusAddress, new_method_call

    bus = DBusAddress(
        "/org/freedesktop/DBus", "org.freedesktop.DBus", "org.freedesktop.DBus"
    )
    try:
        conn.send_message(
            new_method_call(bus, "RequestName", "su", (_BUS_NAME, 0)))
    except Exception as e:
        print(f"[Tray] RequestName failed to send: {e}")
        return
    # Hear about the watcher (re)appearing so we can re-register.
    rule = ("type='signal',interface='org.freedesktop.DBus',"
            f"member='NameOwnerChanged',arg0='{_WATCHER[2]}'")
    try:
        conn.send_message(new_method_call(bus, "AddMatch", "s", (rule,)))
    except Exception:
        pass
    watcher = DBusAddress(_WATCHER[1], _WATCHER[2], _WATCHER[2])
    try:
        conn.send_message(
            new_method_call(watcher, "RegisterStatusNotifierItem", "s", (_BUS_NAME,)))
    except Exception as e:
        print(f"[Tray] Register send failed: {e}")


def ensure_online() -> bool:
    """Show the tray icon for "Jarvis online". Returns True if shown."""
    if _state["online"]:
        return True
    if not _ui_enabled():
        return False
    try:
        from jeepney.io.blocking import open_dbus_connection
    except ImportError:
        print("[Tray] jeepney not installed — tray icon disabled.")
        return False
    _generate_icons()
    try:
        conn = open_dbus_connection(bus="SESSION")
    except Exception as e:
        print(f"[Tray] Cannot reach session D-Bus ({e}) — tray disabled.")
        return False
    _register(conn)
    stop = threading.Event()
    t = threading.Thread(
        target=_serve_loop, args=(conn, stop), name="jarvis-tray", daemon=True
    )
    with _lock:
        _state["conn"] = conn
        _state["thread"] = t
        _state["stop"] = stop
        _state["online"] = True
        _state["registered"] = False
    t.start()
    print("[Tray] Tray helper started — icon appears once the GNOME "
          "AppIndicator host acknowledges it.")
    return True


def _emit_state_change() -> None:
    """Tell the watcher the icon/tooltip changed."""
    from jeepney import DBusAddress, new_signal

    with _lock:
        conn = _state["conn"]
    if conn is None:
        return
    emitter = DBusAddress(_OBJECT_PATH, _BUS_NAME, _SNI_IFACE)
    changed = {
        "IconPixmap": ("a(iiay)", _props()["IconPixmap"][1]),
        "ToolTip": ("(sa(iiay)ss)", _props()["ToolTip"][1]),
    }
    try:
        with _lock:
            conn.send_message(
                new_signal(emitter, "PropertiesChanged", "sa{sv}as",
                           (_SNI_IFACE, changed, []))
            )
            conn.send_message(new_signal(emitter, "NewIcon"))
            conn.send_message(new_signal(emitter, "NewToolTip"))
    except Exception:
        pass


def set_listening(active: bool) -> None:
    """Swap tray icon/tooltip while Jarvis accepts a voice prompt."""
    if not _state["online"] or active == _state["listening"]:
        return
    _state["listening"] = active
    _emit_state_change()


def shutdown() -> None:
    """Remove the tray icon (called on exit)."""
    import atexit as _atexit

    with _lock:
        conn = _state["conn"]
        stop = _state["stop"]
        _state.update(conn=None, thread=None, stop=None,
                      online=False, listening=False, registered=False)
    if stop is not None:
        stop.set()
    if conn is not None:
        try:
            conn.close()
        except Exception:
            pass
    try:
        _atexit.unregister(shutdown)
    except Exception:
        pass


import atexit as _atexit_module
_atexit_module.register(shutdown)
