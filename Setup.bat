@echo off
echo ╔══════════════════════════════════════════════════════════════╗
echo ║   Zava Energy - On-Device AI for Field Operations  SETUP    ║
echo ║   Powered by Microsoft Surface + Foundry Local              ║
echo ╚══════════════════════════════════════════════════════════════╝
echo.

REM ── Check for Python ──
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python is not installed or not in PATH.
    echo         Install Python 3.10+ from https://python.org
    pause
    exit /b 1
)

REM ── Check for Foundry Local ──
foundry --version >nul 2>&1
if errorlevel 1 (
    echo [INFO] Foundry Local CLI not found. Installing...
    winget install Microsoft.FoundryLocal
    echo [INFO] Please restart this script after Foundry Local installs.
    pause
    exit /b 0
) else (
    echo [OK] Foundry Local detected.
)

REM ── Create virtual environment ──
if not exist ".venv" (
    echo [SETUP] Creating Python virtual environment...
    python -m venv .venv
)

REM ── Activate and install dependencies ──
echo [SETUP] Installing Python dependencies...
call .venv\Scripts\activate.bat
pip install -r requirements.txt --quiet

echo.
echo ╔══════════════════════════════════════════════════════════════╗
echo ║   Setup complete!                                           ║
echo ║   Run StartApp.bat to launch the demo.                     ║
echo ╚══════════════════════════════════════════════════════════════╝
echo.
pause
