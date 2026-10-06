#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

# Load cloud provider credentials
if [ -f "$HOME/.config/ubuntu-siri/env" ]; then
    set -a
    # shellcheck disable=SC1091
    source "$HOME/.config/ubuntu-siri/env"
    set +a
fi

if [ -z "${OPENROUTER_API_KEY:-}" ]; then
    echo "WARNING: OPENROUTER_API_KEY is not set. Add it to ~/.config/ubuntu-siri/env" >&2
fi

if [ ! -x .venv/bin/python ]; then
    echo "Virtual environment not found. Run ./install.sh first." >&2
    exit 1
fi

# Make sure the ydotool daemon is running (needed for keyboard/mouse input).
if command -v ydotoold >/dev/null 2>&1; then
    if ! pgrep -x ydotoold >/dev/null 2>&1; then
        if groups | grep -qw uinput || groups | grep -qw input; then
            nohup ydotoold >/tmp/ydotoold.log 2>&1 &
            sleep 0.5
            echo "[start] ydotoold launched."
        else
            echo "WARNING: you are not in the 'uinput'/'input' group yet. Log out and back in, then run sudo bash setup_system.sh." >&2
        fi
    fi
fi

# CUDA libraries shipped inside the venv (ctranslate2 dlopens libcudnn/libcublas
# by soname, so they must be on the loader path).
export LD_LIBRARY_PATH="$PWD/.venv/lib/python3.11/site-packages/nvidia/cudnn/lib:$PWD/.venv/lib/python3.11/site-packages/nvidia/cublas/lib:$PWD/.venv/lib/python3.11/site-packages/nvidia/cuda_runtime/lib:$PWD/.venv/lib/python3.11/site-packages/nvidia/cufft/lib:$PWD/.venv/lib/python3.11/site-packages/nvidia/curand/lib:$PWD/.venv/lib/python3.11/site-packages/nvidia/cusolver/lib:$PWD/.venv/lib/python3.11/site-packages/nvidia/cusparse/lib:${LD_LIBRARY_PATH:-}"

PIDFILE="/tmp/jarvis.pid"
LOGFILE="/tmp/jarvis.log"

# Already running? Don't start a second copy.
if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
    echo "Jarvis is already running (pid $(cat "$PIDFILE")). Use ./stop.sh first." >&2
    exit 1
fi
rm -f "$PIDFILE"

nohup .venv/bin/python -u -m jarvis.main >>"$LOGFILE" 2>&1 &
echo $! > "$PIDFILE"
echo "[start] Jarvis running in background (pid $!, log $LOGFILE)."
echo "[start] Say 'Hey Jarvis', or stop it with ./stop.sh"
