"""Standalone portal-screenshot helper.

Run by any Python that can import PyGObject (`gi`) — on Ubuntu that is the
system interpreter (`/usr/bin/python3`). Uses the XDG Desktop Portal
Screenshot API (interactive=false) so it captures silently under GNOME Wayland,
without the per-call permission dialog.

Usage: python3 _shot.py <output.png>
Exit code 0 on success.
"""
import os
import sys


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: _shot.py <out.png>", file=sys.stderr)
        return 2
    out = os.path.abspath(sys.argv[1])
    try:
        import gi
        gi.require_version("Gio", "2.0")
        gi.require_version("GLib", "2.0")
        from gi.repository import Gio, GLib
    except Exception as e:
        print(f"gi unavailable: {e}", file=sys.stderr)
        return 3

    bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
    state = {}
    loop = GLib.MainLoop()

    def on_response(_conn, _sender, _path, _iface, _member, params):
        try:
            arr = params.unpack()          # (u code, a{sv} opts)
            state["code"] = arr[0]
            state["opts"] = arr[1]
        except Exception as e:
            state["err"] = repr(e)
        loop.quit()

    sub = bus.signal_subscribe(
        None, "org.freedesktop.portal.Request", None, None, None,
        Gio.DBusSignalFlags.NONE, on_response,
    )
    try:
        resp = bus.call_sync(
            "org.freedesktop.portal.Desktop",
            "/org/freedesktop/portal/desktop",
            "org.freedesktop.portal.Screenshot",
            "Screenshot",
            GLib.Variant("(sa{sv})", ("", {"interactive": GLib.Variant("b", False)})),
            None, Gio.DBusCallFlags.NONE, 6000, None,
        )
        GLib.timeout_add_seconds(12, lambda: (loop.quit(), False)[1])
        loop.run()
    finally:
        bus.signal_unsubscribe(sub)

    uri = str(state.get("opts", {}).get("uri", ""))
    if uri.startswith("file://"):
        src = uri[len("file://"):]
        try:
            with open(src, "rb") as f:
                data = f.read()
            with open(out, "wb") as f:
                f.write(data)
            return 0 if os.path.exists(out) else 1
        except Exception as e:
            print(f"copy failed: {e}", file=sys.stderr)
            return 1
    print("portal returned no file", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
