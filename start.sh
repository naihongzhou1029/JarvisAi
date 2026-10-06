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

exec .venv/bin/python -m jarvis.main
