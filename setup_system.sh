#!/usr/bin/env bash
# System setup for JarvisAi on Ubuntu (GNOME Wayland). Run with sudo:
#   sudo bash setup_system.sh
set -euo pipefail

USER_NAME="${SUDO_USER:-$USER}"

echo "==> Installing system packages..."
apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y \
    tesseract-ocr tesseract-ocr-eng tesseract-ocr-chi-tra \
    espeak-ng ydotool brightnessctl playerctl libportaudio2 ca-certificates

# Optional fallback screenshot tool (may not exist on newer GNOME); ignore failure.
apt-get install -y gnome-screenshot || echo "(gnome-screenshot unavailable — using portal capture)"

echo "==> Configuring /dev/uinput access for ydotool..."
modprobe uinput || true
echo "uinput" > /etc/modules-load.d/uinput.conf
groupadd -f uinput
usermod -aG uinput,input "$USER_NAME"
cat > /etc/udev/rules.d/80-ydotool.rules <<'EOF'
KERNEL=="uinput", GROUP="uinput", MODE="0660"
EOF
udevadm control --reload-rules
udevadm trigger

echo "==> Preparing Tesseract language data (already installed)."

echo
echo "=================================================================="
echo " DONE. IMPORTANT: log out and log back in so that the 'uinput' and"
echo " 'input' group memberships take effect (needed for ydotool)."
echo " Then run:  ./install.sh   (first time only)   and   ./start.sh"
echo " Set your key in:  ~/.config/ubuntu-siri/env  (OPENROUTER_API_KEY=...)"
echo "=================================================================="
