#!/usr/bin/env bash
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LAUNCHER_FILE="$APP_DIR/pult-autostart-launcher.sh"
XSESSION_FILE="$HOME/.xsessionrc"
OLD_DESKTOP_FILE="$HOME/.config/autostart/pult-display.desktop"

chmod +x "$APP_DIR/start-pult-display-python-linux.sh"

cat > "$LAUNCHER_FILE" <<EOF
#!/usr/bin/env bash
set -u

cd "$APP_DIR" || exit 1

{
  echo
  echo "===== Autostart \$(date '+%Y-%m-%d %H:%M:%S') ====="
  echo "USER=\${USER:-}"
  echo "HOME=\${HOME:-}"
  echo "DISPLAY=\${DISPLAY:-}"
  echo "XDG_CURRENT_DESKTOP=\${XDG_CURRENT_DESKTOP:-}"
  echo "DESKTOP_SESSION=\${DESKTOP_SESSION:-}"
  echo "Starte Rednerpult..."
} >> "$APP_DIR/pult-autostart.log" 2>&1

sleep 5
exec bash "$APP_DIR/start-pult-display-python-linux.sh" >> "$APP_DIR/pult-autostart.log" 2>&1
EOF

chmod +x "$LAUNCHER_FILE"
rm -f "$OLD_DESKTOP_FILE"

touch "$XSESSION_FILE"
START_MARKER="# BEGIN REDNERPULT AUTOSTART"
END_MARKER="# END REDNERPULT AUTOSTART"
sed -i.bak "/$START_MARKER/,/$END_MARKER/d" "$XSESSION_FILE"

cat >> "$XSESSION_FILE" <<EOF
$START_MARKER
if [ -z "\${REDNERPULT_AUTOSTART_STARTED:-}" ]; then
  export REDNERPULT_AUTOSTART_STARTED=1
  (sleep 8; bash "$LAUNCHER_FILE") &
fi
$END_MARKER
EOF

echo "Autostart installiert in: $XSESSION_FILE"
echo "Alte Desktop-Autostart-Datei entfernt: $OLD_DESKTOP_FILE"
echo "Autostart-Logdatei: $APP_DIR/pult-autostart.log"
