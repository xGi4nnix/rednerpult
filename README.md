# Pult Display Webapp

Lokale Python-Webapp für ein vertikales Rednerpult-Display. `/display` zeigt die aktuell ausgewählte Grafik fullscreen, `/control` ist die geschützte Bedienoberfläche zum Hochladen, Umschalten, Drehen und Einstellen des Übergangs.

## Deployment-Wege

- **Docker + Portainer + Watchtower auf Windows 10** (empfohlen für den Mini-PC am Pult): siehe [DEPLOY-WINDOWS.md](DEPLOY-WINDOWS.md). Server läuft im Container, Auto-Update aus GHCR; der Kiosk-Browser läuft auf dem Windows-Host.
- **Bare-Metal auf MX/Linux** (klassischer Weg): siehe unten.

## Schnellstart auf MX Linux

Einmalig installieren:

```bash
sudo apt update
sudo apt install -y python3-flask python3-pil curl chromium
```

Projekt starten:

```bash
cd /home/mms/rednerpult
chmod +x start-pult-display-python-linux.sh
./start-pult-display-python-linux.sh
```

Login:

```text
admin / admin
```

Display lokal:

```text
http://localhost:5000/display
```

Steuerung im Netzwerk:

```text
http://IP-DES-MX-RECHNERS:5000/control
```

## Autostart

Wenn der MX-Rechner automatisch in den Desktop startet:

```bash
cd /home/mms/rednerpult
sudo apt install -y python3-flask python3-pil curl chromium
chmod +x install-python-autostart-linux.sh
./install-python-autostart-linux.sh
```

Das legt diese Datei an:

```text
/home/mms/.config/autostart/pult-display.desktop
```

Beim nächsten Desktop-Login startet die App und öffnet Chromium im Kiosk-Modus auf `/display`.

Kompletter Copy-Paste-Block fuer die Ersteinrichtung:

```bash
cd /home/mms/rednerpult
sudo apt update
sudo apt install -y python3-flask python3-pil curl chromium
chmod +x start-pult-display-python-linux.sh install-python-autostart-linux.sh
./install-python-autostart-linux.sh
pkill -f /home/mms/rednerpult/app.py || true
./start-pult-display-python-linux.sh
```

Wenn der Test funktioniert, neu starten:

```bash
sudo reboot
```

Nach dem Neustart sollte MX automatisch in den Desktop gehen, die App starten und Chromium im Kiosk-Modus öffnen.

### Schlüsselbund-Fenster bei Chromium

Falls beim Start ein Fenster `Schlüsselbund entsperren` oder `Default Keyring` erscheint: Das Startskript startet Chromium absichtlich mit:

```bash
--password-store=basic
--user-data-dir=/home/mms/rednerpult/browser-profile
```

Dadurch soll Chromium keinen Linux-Schlüsselbund mehr anfragen. Nach einem Update des Skripts auf dem MX-Rechner einmal laufende Chromium-Fenster schließen und neu starten:

```bash
pkill chromium || true
pkill chromium-browser || true
pkill -f /home/mms/rednerpult/app.py || true
cd /home/mms/rednerpult
./start-pult-display-python-linux.sh
```

## Funktionen

- Login für `/control`, `/upload` und Schreib-APIs
- Öffentliches `/display` ohne Login
- Upload von `.png`, `.jpg`, `.jpeg`, `.webp` und `.gif`
- Große Touch-Kacheln für alle Grafiken
- Notfallbuttons für `logo.png` und `blank.png`
- Aktive Grafik klar markiert
- Übergang wahlweise `Cut` oder `Fade`
- Einstellbare Fade-Zeit von 0 bis 5000 ms
- Grafik per Control-Interface dauerhaft um 90 Grad drehen
- 9:16-Ausschnitt bearbeiten, besonders für hochgeladene 16:9-Bilder
- Grafik mit Haken plus Bestätigung löschen
- Reihenfolge per Drag-and-drop sortieren
- Präsentationssteuerung mit `Zurück` und `Weiter`
- Kompakte Control-Oberfläche für 16:9-Bedienbildschirme
- Polling auf `/display` alle 400 ms
- Cache-Busting beim Bildwechsel
- Persistenter Zustand in `data/state.json`
- Healthcheck unter `/health`

## Stromausfall

Der Zustand liegt in:

```text
data/state.json
```

Beispiel:

```json
{
  "current": "logo.png",
  "version": 1,
  "transition": "cut",
  "duration": 500,
  "order": [
    "blank.png",
    "logo.png"
  ]
}
```

Nach einem Neustart lädt `/display` wieder die zuletzt aktive Grafik, solange die Datei noch in `data/slides/` liegt und der Autostart eingerichtet ist.

## Datenstruktur

```text
data/
  slides/
    logo.png
    blank.png
  state.json
```

Uploads landen dauerhaft in `data/slides/`. Gedrehte Bilder werden direkt überschrieben, damit sie auch nach einem Neustart gedreht bleiben.

Die manuelle Sortierung der Kacheln wird in `data/state.json` unter `order` gespeichert. Gelöschte Bilder werden aus `data/slides/` entfernt.

## Manuell starten

Ohne Kiosk:

```bash
cd /home/mms/rednerpult
python3 app.py
```

Dann öffnen:

```text
http://localhost:5000/control
```

## Netzwerk

IP anzeigen:

```bash
ip -br addr
```

Vom Bediengerät dann:

```text
http://DIE-IP:5000/control
```

Wenn die Seite lokal geht, aber im Netzwerk nicht erreichbar ist, Firewall prüfen:

```bash
sudo ufw status
sudo ufw allow 5000/tcp
```
