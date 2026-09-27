@echo off
REM Start ShortsRadar (Windows). Opens the dashboard in your browser.
cd /d "%~dp0"
where py >nul 2>nul && (py -3 run.py %*) || (python run.py %*)
if errorlevel 1 pause
