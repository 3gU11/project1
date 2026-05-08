param(
  [switch]$DryRun,
  [switch]$NoMobile,
  [string]$GoPort = '3001',
  [string]$ApiPort = '8000',
  [string]$WebPort = '3000',
  [string]$MobilePort = '5174',
  [string]$PythonExe = 'C:\Users\zc123\python-sdk\python3.13.2\python.exe'
)

$ErrorActionPreference = 'Stop'

function Log([string]$m) { Write-Host $m }
function Fail([string]$m, [int]$code = 1) { Write-Host "[ERROR] $m" -ForegroundColor Red; exit $code }
function Stop-PortOwner([string]$port) {
  $conns = Get-NetTCPConnection -State Listen -LocalPort ([int]$port) -ErrorAction SilentlyContinue
  if ($conns) {
    $pids = $conns | Select-Object -ExpandProperty OwningProcess -Unique
    foreach ($pid in $pids) {
      try {
        if ($pid -and $pid -gt 0) {
          Stop-Process -Id $pid -Force -ErrorAction SilentlyContinue
          Log "Freed port $port by stopping PID=$pid"
        }
      } catch {}
    }
    Start-Sleep -Milliseconds 500
  }
}

function Stop-StaleProcesses() {
  Stop-Process -Name smart-scheduling-server-go -Force -ErrorAction SilentlyContinue
  Stop-Process -Name go -Force -ErrorAction SilentlyContinue
  # Only stop python processes that are likely uvicorn from this repo.
  $py = Get-CimInstance Win32_Process -Filter "name='python.exe'" -ErrorAction SilentlyContinue
  foreach ($p in $py) {
    $cmd = [string]$p.CommandLine
    if ($cmd -like "*uvicorn*" -and $cmd -like "*api.main:app*") {
      Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
      Log "Stopped stale FastAPI PID=$($p.ProcessId)"
    }
  }
}

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root
$serverDir = Join-Path $root 'server'
$frontendDir = Join-Path $root 'frontend'
$mobileDir = Join-Path $root 'frontend-mobile'
$goExe = Join-Path $serverDir 'smart-scheduling-server-go.exe'

Log '========================================'
Log 'V7 Fullstack Launcher (PowerShell)'
Log "ROOT: $root"
Log '========================================'

if (!(Test-Path (Join-Path $serverDir 'cmd\main.go'))) { Fail 'Missing server\cmd\main.go' 1 }
if (!(Test-Path (Join-Path $frontendDir 'package.json'))) { Fail 'Missing frontend\package.json' 1 }
if (!(Test-Path $PythonExe)) {
  $venvPy = Join-Path $root '.venv\Scripts\python.exe'
  if (Test-Path $venvPy) {
    $PythonExe = $venvPy
  } else {
    Fail "Python not found: $PythonExe" 1
  }
}

# Prefer project venv python when available.
$venvPreferred = Join-Path $root '.venv\Scripts\python.exe'
if (Test-Path $venvPreferred) {
  $PythonExe = $venvPreferred
}

$goCmd = Get-Command go -ErrorAction SilentlyContinue
if (-not $goCmd) {
  $fallbackGo = 'C:\Program Files\Go\bin\go.exe'
  if (Test-Path $fallbackGo) { $goCmd = @{ Source = $fallbackGo } } else { Fail 'go not found in PATH or fallback path' 1 }
}

$goCache = Join-Path $serverDir '.gocache-build'
$goModCache = Join-Path $serverDir '.gomodcache-build'
if (!(Test-Path $goCache)) { New-Item -ItemType Directory -Force -Path $goCache | Out-Null }
if (!(Test-Path $goModCache)) { New-Item -ItemType Directory -Force -Path $goModCache | Out-Null }

Log '[1/4] Building Go sandbox binary...'
if ($DryRun) {
  Log "[DRY-RUN] & '$($goCmd.Source)' build -o '$goExe' .\cmd\main.go"
} else {
  Push-Location $serverDir
  $env:GOCACHE = $goCache
  $env:GOMODCACHE = $goModCache
  & $goCmd.Source build -o $goExe .\cmd\main.go
  if ($LASTEXITCODE -ne 0) { Pop-Location; Fail 'Go build failed' 2 }
  Pop-Location
}

$goOut = Join-Path $serverDir 'go-launcher.out.log'
$goErr = Join-Path $serverDir 'go-launcher.err.log'
$apiOut = Join-Path $root 'api-launcher.out.log'
$apiErr = Join-Path $root 'api-launcher.err.log'
$webOut = Join-Path $frontendDir 'web-launcher.out.log'
$webErr = Join-Path $frontendDir 'web-launcher.err.log'
$mobileOut = Join-Path $mobileDir 'mobile-launcher.out.log'
$mobileErr = Join-Path $mobileDir 'mobile-launcher.err.log'

if (-not $DryRun) {
  Stop-StaleProcesses
  Stop-PortOwner $GoPort
  Stop-PortOwner $ApiPort
  Stop-PortOwner $WebPort
  if (-not $NoMobile) { Stop-PortOwner $MobilePort }

  Remove-Item -LiteralPath $goOut,$goErr,$apiOut,$apiErr,$webOut,$webErr -ErrorAction SilentlyContinue
  if (Test-Path $mobileDir) { Remove-Item -LiteralPath $mobileOut,$mobileErr -ErrorAction SilentlyContinue }
}

Log "[2/4] Starting Go sandbox on $GoPort..."
if ($DryRun) {
  Log '[DRY-RUN] start Go process'
} else {
  $env:HTTP_ADDR = ":$GoPort"
  $goProc = Start-Process -FilePath $goExe -WorkingDirectory $serverDir -RedirectStandardOutput $goOut -RedirectStandardError $goErr -PassThru -WindowStyle Hidden
  Log "Go PID=$($goProc.Id)"
}

Log 'Waiting for Go health...'
if ($DryRun) {
  Log '[DRY-RUN] skip health check'
} else {
  $ok = $false
  for ($i=0; $i -lt 30; $i++) {
    try {
      $resp = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:$GoPort/api/health" -TimeoutSec 2
      if ($resp.StatusCode -eq 200) { $ok = $true; break }
    } catch {}
    Start-Sleep -Seconds 1
  }
  if (-not $ok) { Fail "Go health check failed. See logs: $goOut / $goErr" 3 }
}

Log "[3/4] Starting FastAPI on $ApiPort..."
if ($DryRun) {
  Log '[DRY-RUN] start FastAPI process'
} else {
  $env:GO_SANDBOX_URL = "http://127.0.0.1:$GoPort"
  $apiProc = Start-Process -FilePath $PythonExe -ArgumentList @('-m','uvicorn','api.main:app','--host','0.0.0.0','--port',$ApiPort) -WorkingDirectory $root -RedirectStandardOutput $apiOut -RedirectStandardError $apiErr -PassThru -WindowStyle Hidden
  Log "FastAPI PID=$($apiProc.Id)"

  $apiOk = $false
  for ($i=0; $i -lt 60; $i++) {
    try {
      $resp = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:$ApiPort/health" -TimeoutSec 2
      if ($resp.StatusCode -eq 200) { $apiOk = $true; break }
    } catch {}
    Start-Sleep -Seconds 1
  }
  if (-not $apiOk) { Fail "FastAPI health check failed. See logs: $apiOut / $apiErr" 4 }
}

Log "[4/4] Starting V7 frontend on $WebPort..."
if ($DryRun) {
  Log '[DRY-RUN] start frontend process'
} else {
  $npmCmd = Get-Command npm.cmd -ErrorAction SilentlyContinue
  if (-not $npmCmd) { $npmCmd = Get-Command npm -ErrorAction SilentlyContinue }
  if (-not $npmCmd) { Fail 'npm not found in PATH' 1 }
  $env:VITE_API_BASE_URL = '/api/v1'
  $env:VITE_PROXY_TARGET = "http://127.0.0.1:$ApiPort"
  $webProc = Start-Process -FilePath $npmCmd.Source -ArgumentList @('run','dev','--','--host','0.0.0.0','--port',$WebPort,'--strictPort') -WorkingDirectory $frontendDir -RedirectStandardOutput $webOut -RedirectStandardError $webErr -PassThru -WindowStyle Hidden
  Log "Frontend PID=$($webProc.Id)"
}

if ($NoMobile) {
  Log '[Optional] Skip mobile frontend: --NoMobile'
} elseif (Test-Path (Join-Path $mobileDir 'package.json')) {
  Log "[Optional] Starting mobile frontend on $MobilePort..."
  if ($DryRun) {
    Log '[DRY-RUN] start mobile frontend process'
  } else {
    $npmCmd = Get-Command npm.cmd -ErrorAction SilentlyContinue
    if (-not $npmCmd) { $npmCmd = Get-Command npm -ErrorAction SilentlyContinue }
    if (-not $npmCmd) { Fail 'npm not found in PATH' 1 }
    $mobileProc = Start-Process -FilePath $npmCmd.Source -ArgumentList @('run','dev','--','--host','0.0.0.0','--port',$MobilePort,'--strictPort') -WorkingDirectory $mobileDir -RedirectStandardOutput $mobileOut -RedirectStandardError $mobileErr -PassThru -WindowStyle Hidden
    Log "Mobile PID=$($mobileProc.Id)"
  }
} else {
  Log '[Optional] Skip mobile frontend: package.json not found'
}

Log '.'
Log 'Started.'
Log "Go health: http://127.0.0.1:$GoPort/api/health"
Log "API docs : http://127.0.0.1:$ApiPort/docs"
Log "Frontend : http://127.0.0.1:$WebPort"
Log 'Logs:'
Log "- $goOut"
Log "- $goErr"
Log "- $apiOut"
Log "- $apiErr"
Log "- $webOut"
Log "- $webErr"
if (-not $NoMobile) {
  Log "- $mobileOut"
  Log "- $mobileErr"
}
