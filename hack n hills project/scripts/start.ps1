param([switch]$NoBrowser)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
$pythonPath = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) { throw 'Create .venv and install the project first. See README.md.' }
$logDir = Join-Path $projectRoot 'logs'
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$api = Start-Process -FilePath $pythonPath -ArgumentList '-m','uvicorn','backend.main:app','--host','127.0.0.1','--port','8000' -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $logDir 'api.log') -RedirectStandardError (Join-Path $logDir 'api.err.log')
try {
    $ready = $false
    for ($attempt=0; $attempt -lt 30; $attempt++) {
        try { $health = Invoke-RestMethod -Uri 'http://127.0.0.1:8000/health' -TimeoutSec 2; $ready = $health.status -eq 'ok' } catch { Start-Sleep -Milliseconds 500 }
        if ($ready) { break }
        if ($api.HasExited) { throw 'API exited. Check logs/api.err.log.' }
    }
    if (-not $ready) { throw 'API did not become ready. Check logs/api.err.log.' }
    Write-Host 'AURUM X: http://127.0.0.1:8501. Press Ctrl+C to stop both services.'
    & $pythonPath -m streamlit run frontend/app.py --server.address 127.0.0.1 --server.port 8501 --server.headless true
} finally {
    if (-not $api.HasExited) { Stop-Process -Id $api.Id }
}
