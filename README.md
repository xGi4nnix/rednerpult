# Rednerpult Display

Eine kleine lokale Webapp für ein vertikales Rednerpult-Display. Die App läuft
auf einem Rechner am Pult, zeigt auf `/display` die aktuelle Grafik im
Vollbild und bietet auf `/control` eine Bedienoberfläche für Uploads,
Vorschau, Umschalten und Übergänge.

Die App ist für den Live-Betrieb gedacht: Eine Person kann am Handy, Tablet
oder Laptop eine Grafik auswählen, sie zuerst in der Preview prüfen und sie
dann mit `Cut` oder `Fade` auf das Program-Display schicken.

## Was die App tut

- `/display` zeigt die aktuell aktive Grafik fullscreen auf dem Pult-Display.
- `/control` ist die geschützte Steueroberfläche für Bediengeräte im Netzwerk.
- Hochgeladene Grafiken werden dauerhaft lokal gespeichert.
- Links werden alle Grafiken als sortierbare Liste angezeigt.
- Rechts gibt es zwei Fenster:
  - `Preview`: die ausgewählte Grafik, noch nicht live.
  - `Program`: das aktuell live angezeigte Bild.
- `Umschalten` schickt die Preview mit dem gewählten Übergang auf Program.
- `Schwarz` blendet mit dem gewählten Übergang auf eine schwarze Szene.
- `Cut` und `Fade` werden automatisch gespeichert; die Fade-Zeit ebenfalls.
- Die Steueroberfläche zeigt oben `Verbindung Okay` oder bei Problemen einen
  roten Verbindungsstatus.
- Die Bedienoberfläche funktioniert auf Desktop, Tablet und Smartphone.
- Der Zustand bleibt über Neustarts erhalten.

## Bedienung

1. `/control` öffnen und einloggen.
2. Links über `Dateien auswählen` eine oder mehrere Grafiken auswählen.
3. Erst danach erscheint der `Upload`-Button.
4. Eine Grafik in der linken Liste anklicken. Sie erscheint in `Preview`.
5. Übergang wählen:
   - `Cut`: sofortiger Wechsel.
   - `Fade`: weicher Übergang mit der eingestellten Zeit in Millisekunden.
6. `Umschalten` drücken, um die Preview live auf `Program` und `/display` zu
   schicken.
7. `Schwarz` drücken, um mit dem eingestellten Übergang auf schwarz zu blenden.

Zusätzliche Werkzeuge:

- Drehen: Eine Grafik dauerhaft um 90 Grad drehen.
- Löschen: Grafik aus der lokalen Sammlung entfernen.
- Ausschnitt bearbeiten: Eine Grafik dauerhaft auf 9:16 zuschneiden.
- Sortieren: Grafiken per Drag-and-drop in der Liste umordnen.

## URLs

Lokal auf dem Pult-Rechner:

```text
http://localhost:5000/display
http://localhost:5000/control
```

Im Netzwerk:

```text
http://IP-DES-PULT-RECHNERS:5000/control
```

Der Display-Endpunkt ist absichtlich ohne Login erreichbar, damit der
Kiosk-Browser direkt starten kann. Schreibende Aktionen und `/control` sind
login-geschützt.

## Login

Standard für lokale Entwicklung:

```text
admin / admin
```

Für den Betrieb sollten diese Umgebungsvariablen gesetzt werden:

```bash
export ADMIN_USER="admin"
export ADMIN_PASSWORD="eigenes-passwort"
export APP_SECRET="langer-zufallswert"
```

## Schnellstart auf MX/Linux

Einmalig installieren:

```bash
sudo apt update
sudo apt install -y python3-flask python3-pil curl chromium git
```

Projekt starten:

```bash
cd /home/mms/rednerpult
chmod +x start-pult-display-python-linux.sh
./start-pult-display-python-linux.sh
```

Das Startskript startet die Webapp und öffnet Chromium im Kiosk-Modus auf
`/display`.

## Autostart auf Linux

Wenn der Rechner automatisch in den Desktop startet:

```bash
cd /home/mms/rednerpult
sudo apt install -y python3-flask python3-pil curl chromium git
chmod +x install-python-autostart-linux.sh
./install-python-autostart-linux.sh
```

Das legt diese Datei an:

```text
/home/mms/.config/autostart/pult-display.desktop
```

Beim nächsten Desktop-Login startet die App automatisch und öffnet das Display
im Kiosk-Modus.

Kompletter Copy-Paste-Block für die Ersteinrichtung:

```bash
cd /home/mms/rednerpult
sudo apt update
sudo apt install -y python3-flask python3-pil curl chromium git
chmod +x start-pult-display-python-linux.sh install-python-autostart-linux.sh
./install-python-autostart-linux.sh
pkill -f /home/mms/rednerpult/app.py || true
./start-pult-display-python-linux.sh
```

Wenn der Test funktioniert:

```bash
sudo reboot
```

## Automatische Updates auf Linux

Beim Start versucht `start-pult-display-python-linux.sh`, den aktuellen Branch
von GitHub zu aktualisieren:

```text
git fetch origin <branch>
git merge --ff-only origin/<branch>
```

Wenn das klappt, startet direkt der neue Stand. Wenn kein Internet vorhanden
ist, GitHub nicht erreichbar ist, `git` fehlt oder kein Fast-Forward möglich
ist, startet die App einfach mit dem lokalen Stand weiter.

Das ist absichtlich defensiv: Ein fehlgeschlagenes Update darf den Pultbetrieb
nicht verhindern.

Auto-Update deaktivieren:

```bash
AUTO_UPDATE=0 ./start-pult-display-python-linux.sh
```

Für Updates ohne Login sollte das Repository öffentlich sein oder der Rechner
einen passenden GitHub-Zugang haben.

## Docker/Windows

Für Windows 10 mit Docker Desktop, Portainer und Watchtower gibt es eine eigene
Anleitung:

```text
DEPLOY-WINDOWS.md
```

Kurzfassung: Der Server läuft im Container, Watchtower zieht neue Images
automatisch, und `windows/start-kiosk.bat` öffnet Edge im Kiosk-Modus auf
`/display`.

## Manuell starten

Ohne Kiosk-Browser:

```bash
cd /home/mms/rednerpult
python3 app.py
```

Dann öffnen:

```text
http://localhost:5000/control
```

## Datenablage

Die App speichert ihre Daten standardmäßig im Ordner `data/`:

```text
data/
  slides/
    hochgeladene-grafiken.png
  logos/
    hochgeladene-logos.png
  state.json
```

Uploads landen in `data/slides/`. Gedrehte oder zugeschnittene Bilder werden
direkt überschrieben. Die Sortierung, der aktuelle Program-Zustand, der
Übergang und die Fade-Zeit stehen in `data/state.json`.

Der Datenordner kann über `DATA_DIR` geändert werden:

```bash
DATA_DIR=/pfad/zum/datenspeicher python3 app.py
```

## Stromausfall

Der aktuelle Zustand wird in `data/state.json` gespeichert. Nach einem Neustart
lädt `/display` wieder den zuletzt aktiven Zustand, sofern die referenzierte
Datei noch existiert. Der eingebaute Schwarz-Zustand funktioniert ohne Datei.

## Netzwerk und Firewall

IP-Adresse anzeigen:

```bash
ip -br addr
```

Wenn die Seite lokal geht, aber im Netzwerk nicht erreichbar ist:

```bash
sudo ufw status
sudo ufw allow 5000/tcp
```

## Chromium-Schlüsselbund

Falls beim Start ein Fenster `Schlüsselbund entsperren` oder `Default Keyring`
erscheint: Das Startskript startet Chromium mit:

```bash
--password-store=basic
--user-data-dir=/home/mms/rednerpult/browser-profile
```

Nach Änderungen am Startskript einmal laufende Browser und App beenden und neu
starten:

```bash
pkill chromium || true
pkill chromium-browser || true
pkill -f /home/mms/rednerpult/app.py || true
cd /home/mms/rednerpult
./start-pult-display-python-linux.sh
```

## Healthcheck

Für Autostart, Kiosk-Wartezeiten und die Verbindungsanzeige gibt es:

```text
http://localhost:5000/health
```

Antwort:

```json
{"ok": true}
```
