#!/usr/bin/env bash
set -uo pipefail
PIDFILE="/tmp/jarvis.pid"

stop_pid() {
    local pid="$1"
    kill "$pid" 2>/dev/null || return 1
    # Give it up to 5s to exit gracefully, then force kill.
    for _ in $(seq 1 50); do
        kill -0 "$pid" 2>/dev/null || return 0
        sleep 0.1
    done
    kill -9 "$pid" 2>/dev/null
    echo "[stop] Force killed (pid $pid)."
    return 0
}

if [ -f "$PIDFILE" ]; then
    PID="$(cat "$PIDFILE")"
    if kill -0 "$PID" 2>/dev/null; then
        if stop_pid "$PID"; then
            echo "[stop] Jarvis stopped."
        fi
    else
        echo "[stop] Stale pid file (process $PID not running), cleaning up."
    fi
    rm -f "$PIDFILE"
    # Clean up the tray helper if it outlived the main process.
    pkill -f "zenity --notification" 2>/dev/null || true
    exit 0
fi

# No pid file — fall back to matching the process.
if pgrep -f "jarvis\.main" >/dev/null 2>&1; then
    pkill -f "jarvis\.main"
    pkill -f "zenity --notification" 2>/dev/null || true
    echo "[stop] Jarvis stopped (matched by process name)."
else
    echo "[stop] Jarvis is not running."
fi
