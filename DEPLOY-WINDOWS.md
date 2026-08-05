# Deployment auf Windows 10 mit Docker Desktop + Portainer

Ziel: Der Mini-PC am Rednerpult startet nach dem Einschalten selbstständig den
Rednerpult-Server (im Container) und öffnet den Bildschirm im Kiosk-Modus auf
`/display`. Neue Versionen werden per **Watchtower** automatisch aus **GHCR**
gezogen. Bedient wird über `http://<PC>:8080/control`.

```
git push  ->  GitHub Actions baut Image  ->  ghcr.io/xgi4nnix/rednerpult:latest
                                                      |
                                        Watchtower (auf dem Mini-PC) pollt & redeployt
```

## 0. Voraussetzungen prüfen

- **Windows 10 64-bit, Version 2004 (Build 19041) oder neuer.** Prüfen mit `winver`.
- **Virtualisierung im BIOS aktiviert** (VT-x / AMD-V).
- **WSL2** verfügbar (installiert Docker Desktop bei Bedarf mit).

> Läuft der PC nur mit Windows 8 oder einem sehr alten Windows-10-Build, ist
> Docker Desktop nicht möglich – dann Linux auf das Gerät oder den nativen
> Windows-Dienst-Weg (waitress) wählen.

## 1. Docker Desktop installieren

1. Docker Desktop für Windows installieren, beim Setup **WSL2-Backend** wählen.
2. In den Einstellungen aktivieren:
   - **General → Start Docker Desktop when you log in**
   - **General → Use the WSL 2 based engine**

## 2. Portainer bereitstellen

In PowerShell:

```powershell
docker volume create portainer_data
docker run -d -p 9443:9443 --name portainer --restart=always `
  -v /var/run/docker.sock:/var/run/docker.sock `
  -v portainer_data:/data `
  portainer/portainer-ce:latest
```

Portainer öffnen: `https://localhost:9443` → Admin-Konto anlegen → lokale Docker-Umgebung wählen.

## 3. Stack in Portainer anlegen

**Stacks → Add stack → Web editor.** Inhalt von [`docker-compose.yml`](docker-compose.yml)
einfügen. Darunter unter **Environment variables** setzen:

| Variable         | Wert                                   |
|------------------|----------------------------------------|
| `APP_SECRET`     | langer Zufallswert                     |
| `ADMIN_USER`     | z. B. `admin`                          |
| `ADMIN_PASSWORD` | **eigenes, sicheres Passwort**         |
| `MAX_UPLOAD_MB`  | `25` (optional)                        |

Zufallswert für `APP_SECRET` erzeugen:

```powershell
[Convert]::ToBase64String((1..48 | ForEach-Object { Get-Random -Max 256 }))
```

**Deploy the stack** drücken. Danach läuft der Server auf Port **8080**.

> Ist das GHCR-Image **privat**, vorher in Portainer unter *Registries* GHCR mit
> einem GitHub-Token (Scope `read:packages`) hinterlegen. Bei öffentlichem Image
> nicht nötig.

## 4. Funktion testen

- Steuerung: `http://localhost:8080/control` (Login mit den oben gesetzten Daten)
- Display:   `http://localhost:8080/display`
- Im Netzwerk: `http://<IP-DES-PC>:8080/control`

IP anzeigen: `ipconfig`. Firewall-Freigabe für Port 8080 (einmalig, als Admin):

```powershell
New-NetFirewallRule -DisplayName "Rednerpult 8080" -Direction Inbound -Protocol TCP -LocalPort 8080 -Action Allow
```

## 5. Kiosk-Browser automatisch starten

Die Datei [`windows/start-kiosk.bat`](windows/start-kiosk.bat) wartet auf den
Server und öffnet dann Edge im Vollbild-Kiosk auf `/display`.

Autostart per **Task Scheduler**:

1. *Aufgabenplanung* → **Aufgabe erstellen** (nicht „einfache Aufgabe").
2. Reiter *Allgemein*: Name z. B. `Rednerpult Kiosk`, „Nur ausführen, wenn Benutzer angemeldet ist".
3. Reiter *Trigger*: **Bei Anmeldung**.
4. Reiter *Aktionen*: **Programm starten** → Pfad zur `start-kiosk.bat`.
5. Reiter *Bedingungen*: „Nur starten, wenn Wechselstrom" **deaktivieren**.

Kiosk beenden: `Alt` + `F4` bzw. `Strg` + `Alt` + `Entf`.

## 6. Selbststart nach Stromausfall (wichtig für ein Rednerpult)

Docker Desktop startet erst, wenn ein Benutzer angemeldet ist. Damit der PC nach
einem Stromausfall ohne Handgriff hochkommt:

- **Windows-Autologin einrichten** (`netplwiz` → Haken „Benutzer müssen … eingeben"
  entfernen, oder per Registry `DefaultUserName`/`DefaultPassword`/`AutoAdminLogon`).
- **Energie/Ruhezustand aus:** Systemsteuerung → Energieoptionen → Bildschirm/Standby
  auf „Nie". Zusätzlich Bildschirmschoner deaktivieren.
- Optional im BIOS: **„AC Power Recovery / Restore on Power Loss = On"**, damit der
  PC nach Stromrückkehr automatisch anschaltet.

Ablauf nach Stromausfall: PC an → Autologin → Docker Desktop startet →
Container (`restart: unless-stopped`) kommen hoch → Task Scheduler startet den
Kiosk-Browser, der auf `/health` wartet und dann `/display` zeigt.

## Updates

Einfach nach `main` pushen. GitHub Actions baut das neue Image, Watchtower zieht
es innerhalb von ~5 Minuten und startet den Container neu. Sofort testen:
in Portainer den `watchtower`-Container → **Recreate**, oder den Stack neu deployen.

## Datensicherung

Slides, Logos und `state.json` liegen im Named Volume `rednerpult-data`.
Sichern:

```powershell
docker run --rm -v rednerpult-data:/data -v ${PWD}:/backup alpine tar czf /backup/rednerpult-data.tgz -C /data .
```
