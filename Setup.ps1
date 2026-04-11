# ── PowerShell Setup Script ──
Write-Host ""
Write-Host "╔══════════════════════════════════════════════════════════════╗" -ForegroundColor Blue
Write-Host "║   Zava Energy - On-Device AI for Field Operations  SETUP   ║" -ForegroundColor Blue
Write-Host "║   Powered by Microsoft Surface + Foundry Local              ║" -ForegroundColor Blue
Write-Host "╚══════════════════════════════════════════════════════════════╝" -ForegroundColor Blue
Write-Host ""

# Check Python
try { python --version | Out-Null } catch {
    Write-Host "[ERROR] Python not found. Install Python 3.10+ from https://python.org" -ForegroundColor Red
    exit 1
}

# Check Foundry Local
$foundryOk = $false
try { foundry --version | Out-Null; $foundryOk = $true } catch {}
if (-not $foundryOk) {
    Write-Host "[INFO] Installing Foundry Local..." -ForegroundColor Yellow
    winget install Microsoft.FoundryLocal
}

# Create venv
if (-not (Test-Path ".venv")) {
    Write-Host "[SETUP] Creating virtual environment..." -ForegroundColor Cyan
    python -m venv .venv
}

# Install deps
Write-Host "[SETUP] Installing dependencies..." -ForegroundColor Cyan
& .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt --quiet

Write-Host ""
Write-Host "[OK] Setup complete! Run: python app.py" -ForegroundColor Green
Write-Host "     Then open http://localhost:5000" -ForegroundColor Green
Write-Host ""
