@echo off
REM ============================================================
REM  Rednerpult-Kiosk fuer Windows 10
REM  Wartet, bis der Docker-Container antwortet, und oeffnet
REM  dann Microsoft Edge im Vollbild-Kioskmodus auf /display.
REM  Per Task Scheduler beim Anmelden ausfuehren lassen.
REM ============================================================

set URL=http://localhost:8080

echo Warte auf Rednerpult-Server (%URL%/health) ...
:waitloop
powershell -NoProfile -Command "try { if ((Invoke-WebRequest -UseBasicParsing -Uri '%URL%/health' -TimeoutSec 3).StatusCode -eq 200) { exit 0 } else { exit 1 } } catch { exit 1 }"
if errorlevel 1 (
  timeout /t 3 /nobreak >nul
  goto waitloop
)

echo Server bereit. Starte Kiosk-Browser ...
start "" msedge.exe --kiosk "%URL%/display" --edge-kiosk-type=fullscreen --no-first-run --disable-features=Translate --disable-pinch --overscroll-history-navigation=0
