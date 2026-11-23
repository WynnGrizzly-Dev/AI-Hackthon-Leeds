# Sets up (first run only) and starts RetinaTransform. Needs Node 22.13+ and uv.
# -Seconds N stops everything after N seconds instead of waiting for Enter.
param([int]$Seconds = 0)
$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$back = Join-Path $root 'central-system\backend'
$front = Join-Path $root 'central-system\frontend'
$scan = Join-Path $root 'retina-screening-main'
$py = Join-Path $env:LOCALAPPDATA 'RetinaTransform\venv'
$pyExe = Join-Path $py 'Scripts\python.exe'
$procs = @()

function Test-Step([string]$name) { if ($LASTEXITCODE -ne 0) { throw "$name failed." } }

try {
    foreach ($tool in 'node', 'npm.cmd', 'uv') {
        if (-not (Get-Command $tool -ErrorAction SilentlyContinue)) { throw "$tool is not installed." }
    }
    foreach ($port in 5000, 5174, 8501) {
        if (Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue) {
            throw "Port $port is already in use. Is RetinaTransform already running?"
        }
    }
    if (-not (Test-Path "$back\.env")) {
        $bytes = New-Object byte[] 32
        [Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
        $secret = -join ($bytes | ForEach-Object { $_.ToString('x2') })
        Set-Content "$back\.env" -Encoding ascii -Value "PORT=5000", "SQLITE_PATH=./data/retinatransform.sqlite", "JWT_SECRET=$secret", "APP_ORIGIN=http://localhost:5174", "NODE_ENV=development"
    }
    if (-not (Test-Path "$front\.env")) {
        Set-Content "$front\.env" -Encoding ascii -Value "CENTRAL_API_PROXY_TARGET=http://127.0.0.1:5000", "VITE_CENTRAL_API_BASE=", "VITE_DATA_MODE=live", "VITE_SCANNER_URL=http://localhost:8501", "CENTRAL_WEB_PORT=5174"
    }
    foreach ($dir in $back, $front) {
        if (-not (Test-Path "$dir\node_modules")) {
            Write-Host "Installing packages in $dir ..."
            & npm.cmd --prefix $dir ci; Test-Step 'npm install'
        }
    }
    if (-not (Test-Path "$py\ready.txt")) {
        Write-Host 'Installing Python packages (first run only) ...'
        & uv venv --clear --python 3.12 $py; Test-Step 'Python setup'
        & uv pip install --python $pyExe -r "$scan\retina_app\requirements.txt"; Test-Step 'Python packages'
        Set-Content "$py\ready.txt" 'ok'
    }

    Write-Host 'Starting ...'
    $procs += Start-Process node -ArgumentList 'server.js' -WorkingDirectory $back -WindowStyle Hidden -PassThru
    $procs += Start-Process npm.cmd -ArgumentList 'run', 'dev' -WorkingDirectory $front -WindowStyle Hidden -PassThru
    $procs += Start-Process $pyExe -ArgumentList '-m streamlit run retina_app/retina_app.py --server.port 8501 --server.address localhost --server.headless true --browser.gatherUsageStats false' -WorkingDirectory $scan -WindowStyle Hidden -PassThru

    foreach ($url in 'http://127.0.0.1:5000/health', 'http://localhost:5174', 'http://localhost:8501') {
        $up = $false
        for ($i = 0; $i -lt 60 -and -not $up; $i++) {
            try { Invoke-WebRequest $url -UseBasicParsing -TimeoutSec 3 | Out-Null; $up = $true } catch { Start-Sleep -Seconds 1 }
        }
        if (-not $up) { throw "$url did not start." }
        Write-Host "Ready: $url"
    }
    if (-not (Test-Path "$scan\models\branchA_v1.onnx")) {
        Write-Host 'Note: retina-screening-main\models\branchA_v1.onnx is missing, so images cannot be graded.' -ForegroundColor Yellow
    }
    if ($Seconds -gt 0) { Start-Sleep -Seconds $Seconds }
    else {
        Start-Process 'http://localhost:5174'
        Read-Host 'RetinaTransform is running. Press Enter to stop it' | Out-Null
    }
}
catch {
    Write-Host "Error: $($_.Exception.Message)" -ForegroundColor Red
    if ($Seconds -eq 0) { Read-Host 'Press Enter to close' | Out-Null }
}
finally {
    $ErrorActionPreference = 'SilentlyContinue'
    foreach ($p in $procs) { & taskkill.exe /PID $p.Id /T /F | Out-Null }
}
