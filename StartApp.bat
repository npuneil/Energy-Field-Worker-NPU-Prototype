@echo off
echo ╔══════════════════════════════════════════════════════════════╗
echo ║   Zava Energy - On-Device AI for Field Operations           ║
echo ║   Starting...                                               ║
echo ╚══════════════════════════════════════════════════════════════╝
echo.

REM ── Activate venv ──
if exist ".venv\Scripts\activate.bat" (
    call .venv\Scripts\activate.bat
) else (
    echo [ERROR] Virtual environment not found. Run Setup.bat first.
    pause
    exit /b 1
)

REM ── Launch browser after short delay ──
start "" "http://localhost:5000"

REM ── Start Flask app ──
echo [Starting] Flask app on http://localhost:5000
echo [INFO] Close this window to stop the app.
echo.
python app.py
