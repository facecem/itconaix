@echo off
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel%==0 (py leadfinder.py) else (python leadfinder.py)
pause
