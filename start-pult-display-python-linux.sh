#!/usr/bin/env bash
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$APP_DIR"

URL="http://localhost:5000/display"
HEALTH_URL="http://localhost:5000/health"
LOG_FILE="$APP_DIR/pult-display.log"
BROWSER_PROFILE_DIR="$APP_DIR/browser-profile"

export APP_SECRET="${APP_SECRET:-pult-display-local-secret}"
export ADMIN_USER="${ADMIN_USER:-admin}"
export ADMIN_PASSWORD="${ADMIN_PASSWORD:-admin}"

if ! python3 -c "import flask, PIL" >/dev/null 2>&1; then
  echo "Fehler: Flask oder Pillow ist nicht installiert."
  echo "Installiere es mit:"
  echo "  sudo apt update"
  echo "  sudo apt install -y python3-flask python3-pil"
  exit 1
fi

if ! pgrep -f "$APP_DIR/app.py" >/dev/null 2>&1; then
  echo "Starte Pult Display Webapp..."
  nohup python3 "$APP_DIR/app.py" > "$LOG_FILE" 2>&1 &
else
  echo "Pult Display Webapp laeuft bereits."
fi

echo "Warte auf Webapp..."
for _ in $(seq 1 60); do
  if curl -fsS "$HEALTH_URL" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

if ! curl -fsS "$HEALTH_URL" >/dev/null 2>&1; then
  echo "Fehler: Webapp ist nicht erreichbar: $HEALTH_URL"
  echo "Logdatei:"
  echo "$LOG_FILE"
  exit 1
fi

if command -v chromium >/dev/null 2>&1; then
  BROWSER="chromium"
elif command -v chromium-browser >/dev/null 2>&1; then
  BROWSER="chromium-browser"
elif command -v google-chrome >/dev/null 2>&1; then
  BROWSER="google-chrome"
elif command -v firefox >/dev/null 2>&1; then
  BROWSER="firefox"
else
  echo "Fehler: Kein Chromium, Chrome oder Firefox gefunden."
  echo "Installiere zum Beispiel:"
  echo "  sudo apt install -y chromium"
  exit 1
fi

echo "Oeffne Display im Kiosk-Modus mit $BROWSER..."
if [[ "$BROWSER" == "firefox" ]]; then
  exec "$BROWSER" --kiosk "$URL"
else
  mkdir -p "$BROWSER_PROFILE_DIR"
  exec "$BROWSER" \
    --kiosk "$URL" \
    --user-data-dir="$BROWSER_PROFILE_DIR" \
    --password-store=basic \
    --no-first-run \
    --no-default-browser-check \
    --disable-infobars \
    --disable-session-crashed-bubble \
    --disable-features=Translate,AutofillServerCommunication
fi
