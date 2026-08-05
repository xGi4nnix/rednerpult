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

try_update_from_github() {
  if [[ "${AUTO_UPDATE:-1}" != "1" ]]; then
    echo "Auto-Update ist deaktiviert."
    return
  fi

  if ! command -v git >/dev/null 2>&1; then
    echo "Auto-Update uebersprungen: git ist nicht installiert."
    return
  fi

  if [[ ! -d "$APP_DIR/.git" ]]; then
    echo "Auto-Update uebersprungen: kein Git-Checkout."
    return
  fi

  local branch
  branch="$(git -C "$APP_DIR" rev-parse --abbrev-ref HEAD 2>/dev/null || true)"
  if [[ -z "$branch" || "$branch" == "HEAD" ]]; then
    echo "Auto-Update uebersprungen: kein Branch ausgecheckt."
    return
  fi

  local timeout_cmd=()
  if command -v timeout >/dev/null 2>&1; then
    timeout_cmd=(timeout 25)
  fi

  echo "Pruefe GitHub auf Updates fuer Branch $branch..."
  if GIT_TERMINAL_PROMPT=0 "${timeout_cmd[@]}" git -C "$APP_DIR" fetch --quiet origin "$branch"; then
    local local_head
    local remote_head
    local_head="$(git -C "$APP_DIR" rev-parse HEAD 2>/dev/null || true)"
    remote_head="$(git -C "$APP_DIR" rev-parse "origin/$branch" 2>/dev/null || true)"

    if [[ -n "$local_head" && "$local_head" == "$remote_head" ]]; then
      echo "Auto-Update abgeschlossen oder bereits aktuell."
      return
    fi

    local stashed_changes=0
    if ! git -C "$APP_DIR" diff --quiet || ! git -C "$APP_DIR" diff --cached --quiet; then
      echo "Lokale Aenderungen gefunden. Sichere sie vor dem Update in einem Git-Stash..."
      if GIT_AUTHOR_NAME="Rednerpult Auto-Update" \
        GIT_AUTHOR_EMAIL="rednerpult@local" \
        GIT_COMMITTER_NAME="Rednerpult Auto-Update" \
        GIT_COMMITTER_EMAIL="rednerpult@local" \
        GIT_TERMINAL_PROMPT=0 \
        "${timeout_cmd[@]}" git -C "$APP_DIR" stash push --quiet --message "rednerpult-auto-update $(date +%Y-%m-%d_%H-%M-%S)"; then
        stashed_changes=1
        echo "Lokale Aenderungen gesichert. Update laeuft weiter."
      else
        echo "Auto-Update uebersprungen: lokale Aenderungen konnten nicht gesichert werden. Starte lokalen Stand."
        return
      fi
    fi

    if GIT_TERMINAL_PROMPT=0 "${timeout_cmd[@]}" git -C "$APP_DIR" merge --ff-only --quiet "origin/$branch"; then
      echo "Auto-Update abgeschlossen oder bereits aktuell."
      if [[ "$stashed_changes" == "1" ]]; then
        echo "Hinweis: Lokale Aenderungen wurden als Git-Stash behalten und nicht wieder eingespielt."
        echo "Bei Bedarf anzeigen mit: git stash list"
      fi
    else
      echo "Auto-Update uebersprungen: Fast-Forward nicht moeglich. Starte lokalen Stand."
      if [[ "$stashed_changes" == "1" ]]; then
        echo "Stelle lokale Aenderungen wieder her..."
        if ! git -C "$APP_DIR" stash pop --quiet >/dev/null 2>&1; then
          echo "Lokale Aenderungen konnten nicht automatisch wiederhergestellt werden."
          echo "Bei Bedarf manuell pruefen mit: git stash list"
        fi
      fi
    fi
  else
    echo "Auto-Update fehlgeschlagen oder offline. Starte lokalen Stand."
  fi
}

try_update_from_github

hide_mouse_cursor() {
  if [[ "${HIDE_MOUSE:-1}" != "1" ]]; then
    echo "Mauszeiger ausblenden ist deaktiviert."
    return
  fi

  if command -v unclutter >/dev/null 2>&1; then
    if ! pgrep -x unclutter >/dev/null 2>&1; then
      echo "Blende Mauszeiger mit unclutter aus..."
      nohup unclutter -idle 0.2 -root >/dev/null 2>&1 &
    fi
  elif command -v unclutter-xfixes >/dev/null 2>&1; then
    if ! pgrep -x unclutter-xfixes >/dev/null 2>&1; then
      echo "Blende Mauszeiger mit unclutter-xfixes aus..."
      nohup unclutter-xfixes --timeout 0.2 --hide-on-touch >/dev/null 2>&1 &
    fi
  else
    echo "Mauszeiger-Ausblendung uebersprungen: unclutter ist nicht installiert."
    echo "Optional installieren mit:"
    echo "  sudo apt install -y unclutter"
  fi
}

hide_mouse_cursor

if ! python3 -c "import flask, PIL" >/dev/null 2>&1; then
  echo "Fehler: Flask oder Pillow ist nicht installiert."
  echo "Installiere es mit:"
  echo "  sudo apt update"
  echo "  sudo apt install -y python3-flask python3-pil git unclutter"
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
