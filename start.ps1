# CampusQA Launcher
# Backend: http://localhost:8002  Frontend: http://localhost:5173

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$backend = Join-Path $root "backend"
$frontend = Join-Path $root "frontend"

Write-Host "============================================" -ForegroundColor Cyan
Write-Host "   CampusQA - HHU Campus Q&A Assistant" -ForegroundColor Cyan
Write-Host "   Backend:  http://localhost:8002" -ForegroundColor Gray
Write-Host "   Frontend: http://localhost:5173" -ForegroundColor Gray
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

Write-Host "[1/3] Starting backend..." -ForegroundColor Yellow
Start-Process -FilePath "python3.11" -ArgumentList "-m uvicorn app.main:app --host 0.0.0.0 --port 8002" -WorkingDirectory $backend

Write-Host "[2/3] Starting frontend..." -ForegroundColor Yellow
Start-Process -FilePath "cmd" -ArgumentList "/c npm run dev" -WorkingDirectory $frontend

Write-Host "[3/3] Waiting for services..." -ForegroundColor Yellow
Start-Sleep -Seconds 8

Write-Host "Opening browser..." -ForegroundColor Green
Start-Process "http://localhost:5173"

Write-Host ""
Write-Host "============================================" -ForegroundColor Green
Write-Host "  Done! Browser should be open." -ForegroundColor Green
Write-Host "  Close the backend/frontend windows to stop." -ForegroundColor Gray
Write-Host "============================================" -ForegroundColor Green
Write-Host ""
Write-Host "Press any key to exit this launcher..."
[Console]::ReadKey($true) | Out-Null