param(
  [int]$Port = 5174,
  [int]$IntervalSeconds = 10
)

$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$mobileDir = Join-Path $projectRoot "frontend-mobile"
$logDir = Join-Path $mobileDir "logs"
$watchdogLog = Join-Path $logDir "mobile-watchdog.log"
$viteOutLog = Join-Path $logDir "mobile-vite-5174.out.log"
$viteErrLog = Join-Path $logDir "mobile-vite-5174.err.log"

if (-not (Test-Path $logDir)) {
  New-Item -ItemType Directory -Path $logDir -Force | Out-Null
}

$mutexName = "Global\V8Mobile5174Watchdog"
$mutex = New-Object System.Threading.Mutex($false, $mutexName)
if (-not $mutex.WaitOne(0, $false)) {
  Add-Content -Path $watchdogLog -Value "$(Get-Date -Format s) another watchdog is already running"
  exit 0
}

function Write-WatchdogLog {
  param([string]$Message)
  Add-Content -Path $watchdogLog -Value "$(Get-Date -Format s) $Message"
}

function Test-MobileHttp {
  try {
    $response = Invoke-WebRequest -Uri "http://127.0.0.1:$Port/" -UseBasicParsing -TimeoutSec 4
    return [int]$response.StatusCode -ge 200 -and [int]$response.StatusCode -lt 500
  } catch {
    return $false
  }
}

function Get-MobileDevProcesses {
  Get-CimInstance Win32_Process |
    Where-Object {
      $_.ProcessId -ne $PID -and
      $_.CommandLine -and
      $_.CommandLine -like "*frontend-mobile*" -and
      ($_.CommandLine -match "vite|npm|node") -and
      ($_.CommandLine -match "5174|frontend-mobile")
    }
}

function Start-MobileDevServer {
  Write-WatchdogLog "starting frontend-mobile dev server on 0.0.0.0:$Port"
  Start-Process `
    -FilePath "cmd.exe" `
    -ArgumentList @("/c", "npm run dev -- --host 0.0.0.0 --port $Port --strictPort") `
    -WorkingDirectory $mobileDir `
    -WindowStyle Hidden `
    -RedirectStandardOutput $viteOutLog `
    -RedirectStandardError $viteErrLog | Out-Null
}

function Restart-MobileDevServer {
  $existing = @(Get-MobileDevProcesses)
  foreach ($process in $existing) {
    try {
      Write-WatchdogLog "stopping stale process pid=$($process.ProcessId)"
      Stop-Process -Id $process.ProcessId -Force -ErrorAction SilentlyContinue
    } catch {
      Write-WatchdogLog "failed stopping pid=$($process.ProcessId): $($_.Exception.Message)"
    }
  }
  Start-Sleep -Seconds 2
  Start-MobileDevServer
}

try {
  Write-WatchdogLog "watchdog started pid=$PID port=$Port mobileDir=$mobileDir"
  while ($true) {
    if (-not (Test-MobileHttp)) {
      Write-WatchdogLog "health check failed"
      Restart-MobileDevServer
      Start-Sleep -Seconds 5
      if (Test-MobileHttp) {
        Write-WatchdogLog "frontend-mobile is healthy after restart"
      } else {
        Write-WatchdogLog "frontend-mobile still unhealthy after restart"
      }
    }
    Start-Sleep -Seconds $IntervalSeconds
  }
} finally {
  try {
    $mutex.ReleaseMutex() | Out-Null
    $mutex.Dispose()
  } catch {
  }
}
