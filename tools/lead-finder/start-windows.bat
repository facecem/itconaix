@echo off
cd /d "%~dp0"
set PY=
where py >nul 2>nul
if %errorlevel%==0 (set PY=py) else (
  where python >nul 2>nul
  if not errorlevel 1 set PY=python
)
if "%PY%"=="" (
  echo Python ist nicht installiert. Bitte von https://www.python.org/downloads/ installieren
  echo und dabei "Add python.exe to PATH" anhaken. Danach diese Datei erneut starten.
  pause
  exit /b
)
rem Claude-Paket fuer die KI-Bewertung (optional, Tool laeuft auch ohne)
%PY% -c "import anthropic" >nul 2>nul || %PY% -m pip install --quiet --disable-pip-version-check anthropic
%PY% leadfinder.py
pause
