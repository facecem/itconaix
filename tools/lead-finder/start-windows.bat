@echo off
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel%==0 (
  py leadfinder.py
) else (
  where python >nul 2>nul
  if errorlevel 1 (
    echo Python ist nicht installiert. Bitte von https://www.python.org/downloads/ installieren
    echo und dabei "Add python.exe to PATH" anhaken. Danach diese Datei erneut starten.
  ) else (
    python leadfinder.py
  )
)
pause
