# CampusQA Launcher - Dual services
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$backend = Join-Path $root "backend"
$frontend = Join-Path $root "frontend"
$ai = Join-Path $root "ai_service"
$dist = Join-Path $frontend "dist"

Write-Host "============================================" -ForegroundColor Cyan
Write-Host "   CampusQA - HHU Campus Q&A Assistant" -ForegroundColor Cyan
Write-Host "   AI Service:  http://localhost:8003" -ForegroundColor Gray
Write-Host "   Backend:     http://localhost:8002" -ForegroundColor Gray
Write-Host "   Swagger:     http://localhost:8002/docs" -ForegroundColor Gray
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

# Build frontend if not exists
if (-not (Test-Path (Join-Path $dist "index.html"))) {
    Write-Host "[Build] Building frontend..." -ForegroundColor Yellow
    Push-Location $frontend
    cmd /c "npm run build 2>&1" | Out-Null
    Pop-Location
}

$aiLog = "$env:TEMP\ai_service.log"
$aiErr = "$env:TEMP\ai_service_err.log"
$beLog = "$env:TEMP\backend.log"
$beErr = "$env:TEMP\backend_err.log"

# Clear ALL_PROXY — SOCKS5 breaks OpenAI httpx client
$env:ALL_PROXY = ''
# Skip HuggingFace network checks — model already cached locally
$env:HF_HUB_OFFLINE = '1'

Write-Host "[1/3] Starting AI Service (port 8003)..." -ForegroundColor Yellow
Start-Process -FilePath "python3.11" -ArgumentList "-m uvicorn main:app --host 0.0.0.0 --port 8003 --log-level warning" -WorkingDirectory $ai -WindowStyle Hidden -RedirectStandardOutput $aiLog -RedirectStandardError $aiErr

Start-Sleep 6

Write-Host "[2/3] Starting Backend (port 8002)..." -ForegroundColor Yellow
Start-Process -FilePath "python3.11" -ArgumentList "-m uvicorn app.main:app --host 0.0.0.0 --port 8002 --log-level warning" -WorkingDirectory $backend -WindowStyle Hidden -RedirectStandardOutput $beLog -RedirectStandardError $beErr

Start-Sleep 4

Write-Host "[3/3] Opening browser..." -ForegroundColor Yellow
Start-Process "http://localhost:8002"

Write-Host ""
Write-Host "============================================" -ForegroundColor Green
Write-Host "  CampusQA is running!" -ForegroundColor Green
Write-Host "  Close the two server windows to stop." -ForegroundColor Gray
Write-Host "============================================" -ForegroundColor Green