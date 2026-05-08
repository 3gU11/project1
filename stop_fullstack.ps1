param(
  [string]$GoPort = '3001',
  [string]$ApiPort = '8000',
  [string]$WebPort = '3000',
  [string]$MobilePort = '5174'
)

function Log([string]$m) { Write-Host $m }
function LogOk([string]$m) { Write-Host $m -ForegroundColor Green }
function LogWarn([string]$m) { Write-Host $m -ForegroundColor Yellow }

Log '========================================'
Log 'V7 Fullstack Shutdown'
Log '========================================'

# --- 1. Stop Go backend by process name ---
$goProcs = Get-Process -Name 'smart-scheduling-server-go' -ErrorAction SilentlyContinue
if ($goProcs) {
  foreach ($p in $goProcs) {
    Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue
    LogOk "Stopped Go backend PID=$($p.Id)"
  }
} else {
  LogWarn 'Go backend not running (by name)'
}

# --- 2. Stop FastAPI / uvicorn ---
$pyProcs = Get-CimInstance Win32_Process -Filter "name='python.exe'" -ErrorAction SilentlyContinue
$stoppedApi = $false
foreach ($p in $pyProcs) {
  $cmd = [string]$p.CommandLine
  if ($cmd -like '*uvicorn*' -and $cmd -like '*api.main:app*') {
    Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
    LogOk "Stopped FastAPI PID=$($p.ProcessId)"
    $stoppedApi = $true
  }
}
if (-not $stoppedApi) { LogWarn 'FastAPI not running (by command line match)' }

# --- 3. Stop frontend / mobile by port ---
function Stop-PortOwner([string]$port, [string]$label) {
  $conns = Get-NetTCPConnection -State Listen -LocalPort ([int]$port) -ErrorAction SilentlyContinue
  if ($conns) {
    $pids = $conns | Select-Object -ExpandProperty OwningProcess -Unique
    foreach ($ownerPid in $pids) {
      if ($ownerPid -and $ownerPid -gt 0) {
        try {
          $proc = Get-Process -Id $ownerPid -ErrorAction SilentlyContinue
          Stop-Process -Id $ownerPid -Force -ErrorAction SilentlyContinue
          LogOk "Stopped $label on port $port  PID=$ownerPid ($($proc.ProcessName))"
        } catch {}
      }
    }
  } else {
    LogWarn "$label not running on port $port"
  }
}

Stop-PortOwner $WebPort    'Frontend'
Stop-PortOwner $MobilePort 'Mobile frontend'

# Also kill by port for Go/API in case the name-based match missed them
Stop-PortOwner $GoPort  'Go backend (port fallback)'
Stop-PortOwner $ApiPort 'FastAPI (port fallback)'

# --- 4. Cleanup any orphan node processes spawned by npm run dev ---
$nodeProcs = Get-CimInstance Win32_Process -Filter "name='node.exe'" -ErrorAction SilentlyContinue
foreach ($p in $nodeProcs) {
  $cmd = [string]$p.CommandLine
  if ($cmd -like '*vite*' -and ($cmd -like "*$WebPort*" -or $cmd -like "*$MobilePort*")) {
    Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
    LogOk "Stopped orphan node/vite PID=$($p.ProcessId)"
  }
}

Log ''
Log '========================================'
LogOk 'All V7 services stopped.'
Log '========================================'
