# ── PowerShell Setup Script ──
Write-Host ""
Write-Host "╔══════════════════════════════════════════════════════════════╗" -ForegroundColor Blue
Write-Host "║   Zava Energy - On-Device AI for Field Operations  SETUP   ║" -ForegroundColor Blue
Write-Host "║   Powered by Microsoft Surface + Foundry Local              ║" -ForegroundColor Blue
Write-Host "╚══════════════════════════════════════════════════════════════╝" -ForegroundColor Blue
Write-Host ""

# Resolve Python command (try python, py -3, python3)
$pythonCmd = $null
foreach ($cmd in @('python', 'py', 'python3')) {
    try {
        $testArgs = if ($cmd -eq 'py') { @('-3', '--version') } else { @('--version') }
        & $cmd @testArgs 2>&1 | Out-Null
        if ($LASTEXITCODE -eq 0 -or $?) {
            $pythonCmd = if ($cmd -eq 'py') { 'py -3' } else { $cmd }
            break
        }
    } catch { }
}
if (-not $pythonCmd) {
    Write-Host "[ERROR] Python not found. Install Python 3.10+ from https://python.org" -ForegroundColor Red
    Write-Host "        Make sure to check 'Add Python to PATH' during install." -ForegroundColor Red
    exit 1
}
Write-Host "[OK] Python found: $pythonCmd" -ForegroundColor Green

# Check Foundry Local
$foundryOk = $false
try { foundry --version 2>&1 | Out-Null; $foundryOk = $true } catch {}
if (-not $foundryOk) {
    Write-Host "[INFO] Installing Foundry Local..." -ForegroundColor Yellow
    winget install Microsoft.FoundryLocal
}

# Create venv
if (-not (Test-Path ".venv\Scripts\Activate.ps1")) {
    Write-Host "[SETUP] Creating virtual environment..." -ForegroundColor Cyan
    Invoke-Expression "$pythonCmd -m venv .venv"
    if (-not (Test-Path ".venv\Scripts\Activate.ps1")) {
        Write-Host "[ERROR] Failed to create virtual environment." -ForegroundColor Red
        Write-Host "        Try manually: $pythonCmd -m venv .venv" -ForegroundColor Red
        exit 1
    }
    Write-Host "[OK] Virtual environment created." -ForegroundColor Green
}

# Install deps
Write-Host "[SETUP] Installing dependencies..." -ForegroundColor Cyan
& .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt --quiet

Write-Host ""
Write-Host "[OK] Setup complete! Run StartApp.bat or: python app.py" -ForegroundColor Green
Write-Host "     Then open http://localhost:5000" -ForegroundColor Green
Write-Host "     NOTE: Foundry Local model loading may take a moment on first run." -ForegroundColor Yellow
Write-Host ""
