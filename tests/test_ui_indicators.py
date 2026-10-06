# tests/test_ui_indicators.py
"""Tests for the tray icon and listening overlay (both degrade gracefully)."""
import sys
import time
import types
from unittest.mock import patch


# ─── tray (StatusNotifierItem backend) ───

def _fresh_tray():
    import importlib
    import jarvis.tray as tray
    return importlib.reload(tray)


class _FakeConn:
    """Stand-in for jeepney's blocking connection (no real D-Bus)."""

    def __init__(self):
        self.calls = []    # via send_and_get_reply
        self.signals = []  # via send_message
        self.closed = False

    def send_and_get_reply(self, msg, timeout=None):
        self.calls.append(msg)
        return object()

    def send_message(self, msg):
        self.signals.append(msg)

    def receive(self, timeout=None):
        raise TimeoutError("no message")

    def close(self):
        self.closed = True


def _patch_conn(monkeypatch, tray, conn):
    import jeepney.io.blocking as _blocking
    monkeypatch.setattr(_blocking, "open_dbus_connection",
                        lambda bus="SESSION": conn)
    monkeypatch.setattr(_blocking, "unwrap_msg", lambda msg: ())
    monkeypatch.setattr(tray, "_ui_enabled", lambda: True)
    monkeypatch.setattr(tray, "_generate_icons", lambda: None)


def _inbound_getall_msg(tray):
    """Synthetic Properties.GetAll method_call from the tray host."""
    from types import SimpleNamespace
    from jeepney.low_level import HeaderFields, MessageType
    header = SimpleNamespace(
        serial=1,
        message_type=MessageType.method_call,
        fields={
            HeaderFields.path: tray._OBJECT_PATH,
            HeaderFields.interface: "org.freedesktop.DBus.Properties",
            HeaderFields.member: "GetAll",
        },
    )
    return SimpleNamespace(header=header,
                           body=("org.kde.StatusNotifierItem",))


def test_tray_retries_registration_until_host_queries(monkeypatch):
    """While unregistered, the serve loop keeps re-announcing the item."""
    from jeepney.low_level import HeaderFields
    tray = _fresh_tray()
    conn = _FakeConn()
    _patch_conn(monkeypatch, tray, conn)

    assert tray.ensure_online() is True
    assert tray._state["registered"] is False  # nothing inbound yet

    def _reg_count():
        return len([m for m in conn.signals
                    if m.header.fields.get(HeaderFields.member)
                    == "RegisterStatusNotifierItem"])

    n1 = _reg_count()
    assert n1 >= 1
    # The serve loop retries registration every ~3 s while unconfirmed…
    time.sleep(3.8)
    n2 = _reg_count()
    assert n2 >= n1 + 1
    # …then the host queries us → registered flips and retries stop.
    time.sleep(0.8)  # let any in-flight retry round land first
    n_pre = _reg_count()
    tray._handle_message(conn, _inbound_getall_msg(tray))
    assert tray._state["registered"] is True
    time.sleep(3.8)
    assert _reg_count() == n_pre  # no further registrations
    tray.shutdown()


def test_tray_respects_config_toggle(monkeypatch):
    tray = _fresh_tray()
    monkeypatch.setattr(tray, "_ui_enabled", lambda: False)
    assert tray.ensure_online() is False


def test_tray_noop_without_dbus(monkeypatch):
    import jeepney.io.blocking as _blocking
    tray = _fresh_tray()
    monkeypatch.setattr(tray, "_ui_enabled", lambda: True)

    def _boom(bus="SESSION"):
        raise ConnectionError("no bus")

    monkeypatch.setattr(_blocking, "open_dbus_connection", _boom)
    assert tray.ensure_online() is False
    tray.set_listening(True)  # must not raise
    tray.shutdown()


def test_tray_registers_and_updates_icon(monkeypatch):
    from jeepney.low_level import HeaderFields
    tray = _fresh_tray()
    conn = _FakeConn()
    _patch_conn(monkeypatch, tray, conn)

    assert tray.ensure_online() is True
    assert tray.ensure_online() is True  # idempotent

    members = [m.header.fields.get(HeaderFields.member, "reply")
               for m in conn.signals[:3]]
    assert members == ["RequestName", "AddMatch", "RegisterStatusNotifierItem"]
    reg = conn.signals[2]
    assert reg.header.fields[HeaderFields.destination] == \
        "org.kde.StatusNotifierWatcher"
    assert reg.body == (tray._BUS_NAME,)
    assert tray._state["registered"] is False
    # Host queries us → registration confirmed.
    tray._handle_message(conn, _inbound_getall_msg(tray))
    assert tray._state["registered"] is True

    tray.set_listening(True)
    tray.set_listening(True)  # idempotent — no duplicate signals
    tray.set_listening(False)
    assert tray._state["listening"] is False
    # Last six sent messages are the two icon-state updates (skip anything else).
    sig_members = [m.header.fields.get(HeaderFields.member, "reply")
                   for m in conn.signals[-6:]]
    assert sig_members == ["PropertiesChanged", "NewIcon", "NewToolTip"] * 2

    tray.shutdown()
    assert conn.closed is True
    assert tray._state["online"] is False


def test_tray_handle_message_answers_getall():
    from types import SimpleNamespace
    from jeepney.low_level import HeaderFields, MessageType
    tray = _fresh_tray()

    header = SimpleNamespace(
        serial=42,
        message_type=MessageType.method_call,
        fields={
            HeaderFields.path: "/StatusNotifierItem",
            HeaderFields.interface: "org.freedesktop.DBus.Properties",
            HeaderFields.member: "GetAll",
        },
    )
    msg = SimpleNamespace(header=header,
                          body=("org.kde.StatusNotifierItem",))
    sent = []

    class _Conn:
        def send_message(self, m):
            sent.append(m)

    tray._handle_message(_Conn(), msg)
    assert len(sent) == 1
    props = sent[0].body[0]
    assert props["Title"] == ("s", "Jarvis")
    assert props["ItemIsMenu"] == ("b", False)
    sig, pixmaps = props["IconPixmap"]
    assert sig == "a(iiay)"


def test_tray_props_pixmap_shape():
    tray = _fresh_tray()
    tray._generate_icons()  # real render into ~/.cache (harmless)
    props = tray._props()
    sig, pixmaps = props["IconPixmap"]
    assert sig == "a(iiay)"
    if pixmaps:  # Pillow present → 64x64 ARGB32
        w, h, raw = pixmaps[0]
        assert (w, h) == (64, 64)
        assert len(raw) == 64 * 64 * 4


# ─── listening overlay ───

def _fresh_overlay():
    import importlib
    import jarvis.listening_overlay as ov
    return importlib.reload(ov)


def test_overlay_noop_headless(monkeypatch):
    ov = _fresh_overlay()
    monkeypatch.delenv("DISPLAY", raising=False)
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    assert ov.show() is False
    ov.hide()  # must not raise
    assert ov.is_visible() is False


def test_overlay_respects_config_toggle(monkeypatch):
    ov = _fresh_overlay()
    monkeypatch.setenv("DISPLAY", ":0")
    monkeypatch.setattr(ov, "_ui_enabled", lambda: False)
    assert ov.show() is False


def test_overlay_show_hide_with_fake_tk(monkeypatch):
    """Drive the overlay thread with a stub tkinter (no real display)."""
    ov = _fresh_overlay()
    monkeypatch.setenv("DISPLAY", ":0")
    monkeypatch.setattr(ov, "_ui_enabled", lambda: True)

    scheduled = []

    class FakeCanvas:
        def __init__(self, *a, **k):
            self._next_id = 0
        def pack(self, *a, **k):
            pass
        def create_text(self, *a, **k):
            self._next_id += 1
            return self._next_id
        def create_rectangle(self, *a, **k):
            self._next_id += 1
            return self._next_id
        def coords(self, *a):
            pass
        def itemconfig(self, *a, **k):
            pass

    class FakeRoot:
        def __init__(self):
            self.destroyed = False
            self.after_calls = 0
        def title(self, *a):
            pass
        def overrideredirect(self, *a):
            pass
        def attributes(self, *a):
            pass
        def winfo_screenwidth(self):
            return 1920
        def geometry(self, *a):
            pass
        def configure(self, *a, **k):
            pass
        def after(self, ms, fn):
            self.after_calls += 1
            # Run one animation frame synchronously, then stop scheduling
            # so mainloop() returns promptly.
            if self.after_calls == 1:
                fn()
            return 1
        def mainloop(self):
            pass
        def destroy(self):
            self.destroyed = True

    fake_tk = types.ModuleType("tkinter")
    fake_tk.Tk = FakeRoot
    fake_tk.Canvas = FakeCanvas
    monkeypatch.setitem(sys.modules, "tkinter", fake_tk)

    assert ov.show() is True
    # Let the background thread run its (stubbed) Tk loop.
    ov._thread.join(timeout=5)
    assert not ov._thread.is_alive()
    assert ov.is_visible() is False  # hide-event? no — show path ends cleanly

    ov.hide()


def test_main_wake_hides_overlay_after_recording():
    """_handle_wake_inner must close the overlay even when STT raises."""
    import jarvis.main as main

    calls = []

    with patch.object(main, "_broadcast", lambda *a, **k: None), \
         patch.object(main, "_speak_if_unmuted", lambda *a, **k: None), \
         patch("jarvis.listening_overlay.show", lambda: calls.append("show") or True), \
         patch("jarvis.listening_overlay.hide", lambda: calls.append("hide")), \
         patch("jarvis.tray.set_listening", lambda b: calls.append(f"tray={b}")), \
         patch("jarvis.wake.pause_wake_mic", lambda: None), \
         patch("jarvis.wake.resume_wake_mic", lambda: calls.append("resume")), \
         patch.object(main, "is_speaking", return_value=False), \
         patch.object(main, "record_until_silence", side_effect=RuntimeError("mic boom")), \
         patch.object(main.time, "sleep", lambda *a: None):
        try:
            main._handle_wake_inner()
        except RuntimeError:
            pass
    assert "show" in calls
    assert "hide" in calls
    assert calls.index("show") < calls.index("hide")
    assert "resume" in calls
