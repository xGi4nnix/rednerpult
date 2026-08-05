#!/usr/bin/env bash
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AUTOSTART_DIR="$HOME/.config/autostart"
DESKTOP_FILE="$AUTOSTART_DIR/pult-display.desktop"

chmod +x "$APP_DIR/start-pult-display-python-linux.sh"
mkdir -p "$AUTOSTART_DIR"

cat > "$DESKTOP_FILE" <<EOF
[Desktop Entry]
Type=Application
Name=Pult Display
Comment=Startet Pult Display lokal mit Python
Exec=$APP_DIR/start-pult-display-python-linux.sh
Terminal=false
X-GNOME-Autostart-enabled=true
EOF

echo "Autostart installiert: $DESKTOP_FILE"
