param(
  [string]$GoPort = '3001',
  [string]$ApiPort = '8000',
  [string]$WebPort = '8888',
  [string]$MobilePort = '5174'
)

$ErrorActionPreference = 'Stop'

function Log([string]$m) { Write-Host $m }
function LogOk([string]$m) { Write-Host $m -ForegroundColor Green }
function LogWarn([string]$m) { Write-Host $m -ForegroundColor Yellow }
function Test-PortValue([string]$port, [string]$name) {
  $parsed = 0
  if (-not [int]::TryParse($port, [ref]$parsed) -or $parsed -lt 1 -or $parsed -gt 65535) {
    throw "Invalid $name port: $port"
  }
  return $parsed
}
function Stop-ProcessTree([int]$processId, [string]$label) {
  if ($processId -le 0 -or $processId -eq $PID) { return $false }

  $stopped = $false
  $children = Get-CimInstance Win32_Process -Filter "ParentProcessId=$processId" -ErrorAction SilentlyContinue
  foreach ($child in @($children)) {
    if (Stop-ProcessTree -processId ([int]$child.ProcessId) -label "$label child") {
      $stopped = $true
    }
  }

  $proc = Get-Process -Id $processId -ErrorAction SilentlyContinue
  if ($proc) {
    Stop-Process -Id $processId -Force -ErrorAction SilentlyContinue
    LogOk "Stopped $label PID=$processId ($($proc.ProcessName))"
    $stopped = $true
  }
  return $stopped
}
function Stop-RecordedProcesses([string]$pidFilePath) {
  if (-not (Test-Path $pidFilePath)) {
    LogWarn 'PID file not found; using project/port cleanup.'
    return
  }

  try {
    $state = Get-Content -LiteralPath $pidFilePath -Raw | ConvertFrom-Json
    foreach ($record in @($state.processes)) {
      if ($record.pid) {
        [void](Stop-ProcessTree -processId ([int]$record.pid) -label ([string]$record.name))
      }
    }
    Remove-Item -LiteralPath $pidFilePath -Force -ErrorAction SilentlyContinue
    LogOk "Removed PID file: $pidFilePath"
  } catch {
    LogWarn "Could not read PID file ${pidFilePath}: $($_.Exception.Message)"
  }
}
function Test-OwnsPort([int]$processId, [string]$port) {
  $conns = Get-NetTCPConnection -State Listen -LocalPort ([int]$port) -ErrorAction SilentlyContinue
  return [bool]($conns | Where-Object { $_.OwningProcess -eq $processId } | Select-Object -First 1)
}
function Stop-PortOwner([string]$port, [string]$label) {
  $conns = Get-NetTCPConnection -State Listen -LocalPort ([int]$port) -ErrorAction SilentlyContinue
  if (-not $conns) {
    LogWarn "$label not running on port $port"
    return
  }

  $pids = $conns | Select-Object -ExpandProperty OwningProcess -Unique
  foreach ($ownerPid in $pids) {
    if ($ownerPid -and $ownerPid -gt 0) {
      [void](Stop-ProcessTree -processId ([int]$ownerPid) -label "$label on port $port")
    }
  }
}
function Stop-ProjectGoProcesses([string]$goExePath) {
  $stopped = $false
  $goProcs = Get-CimInstance Win32_Process -Filter "name='smart-scheduling-server-go.exe'" -ErrorAction SilentlyContinue
  foreach ($p in @($goProcs)) {
    $exe = [string]$p.ExecutablePath
    $cmd = [string]$p.CommandLine
    if ($exe -eq $goExePath -or $cmd -like "*$goExePath*") {
      if (Stop-ProcessTree -processId ([int]$p.ProcessId) -label 'Go backend') {
        $stopped = $true
      }
    }
  }
  if (-not $stopped) { LogWarn 'Go backend not running (by project executable)' }
}
function Stop-ProjectApiProcesses([string]$repoRoot, [string]$port) {
  $stopped = $false
  $pyProcs = Get-CimInstance Win32_Process -Filter "name='python.exe'" -ErrorAction SilentlyContinue
  foreach ($p in @($pyProcs)) {
    $cmd = [string]$p.CommandLine
    $cwdMatch = $cmd -like "*$repoRoot*"
    $uvicornMatch = $cmd -like '*uvicorn*' -and $cmd -like '*api.main:app*'
    if ($uvicornMatch -and ($cwdMatch -or (Test-OwnsPort -processId ([int]$p.ProcessId) -port $port))) {
      if (Stop-ProcessTree -processId ([int]$p.ProcessId) -label 'FastAPI') {
        $stopped = $true
      }
    }
  }
  if (-not $stopped) { LogWarn 'FastAPI not running (by project command line)' }
}
function Stop-ProjectViteProcesses([string]$projectDir, [string]$port, [string]$label) {
  $stopped = $false
  $projectNodeModules = Join-Path $projectDir 'node_modules'
  $nodeProcs = Get-CimInstance Win32_Process -Filter "name='node.exe'" -ErrorAction SilentlyContinue
  foreach ($p in @($nodeProcs)) {
    $cmd = [string]$p.CommandLine
    if ($cmd -like '*vite*' -and ($cmd -like "*$projectNodeModules*" -or $cmd -like "*--port $port*" -or $cmd -like "*--port=$port*")) {
      if (Stop-ProcessTree -processId ([int]$p.ProcessId) -label $label) {
        $stopped = $true
      }
    }
  }
  if (-not $stopped) { LogWarn "$label not running (by project command line)" }
}

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$serverDir = Join-Path $root 'server'
$frontendDir = Join-Path $root 'frontend'
$mobileDir = Join-Path $root 'frontend-mobile'
$goExe = Join-Path $serverDir 'smart-scheduling-server-go.exe'
$pidFile = Join-Path $root '.fullstack.pids.json'

Log '========================================'
Log 'V8betaVer1.0 Fullstack Shutdown'
Log "ROOT: $root"
Log '========================================'

$null = Test-PortValue -port $GoPort -name 'Go'
$null = Test-PortValue -port $ApiPort -name 'API'
$null = Test-PortValue -port $WebPort -name 'frontend'
$null = Test-PortValue -port $MobilePort -name 'mobile frontend'

Stop-RecordedProcesses $pidFile

Stop-ProjectGoProcesses $goExe
Stop-ProjectApiProcesses -repoRoot $root -port $ApiPort
Stop-ProjectViteProcesses -projectDir $frontendDir -port $WebPort -label 'frontend'
if (Test-Path $mobileDir) {
  Stop-ProjectViteProcesses -projectDir $mobileDir -port $MobilePort -label 'mobile frontend'
}

Stop-PortOwner $GoPort 'Go backend'
Stop-PortOwner $ApiPort 'FastAPI'
Stop-PortOwner $WebPort 'frontend'
Stop-PortOwner $MobilePort 'mobile frontend'

Log ''
Log '========================================'
LogOk 'V8betaVer1.0 service shutdown complete.'
Log '========================================'
