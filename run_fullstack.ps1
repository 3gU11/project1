param(
  [switch]$DryRun,
  [switch]$NoMobile,
  [string]$GoPort = '3001',
  [string]$ApiPort = '8000',
  [string]$WebPort = '8888',
  [string]$MobilePort = '5174',
  [string]$PythonExe = ''
)

$ErrorActionPreference = 'Stop'

function Log([string]$message) { Write-Output $message }
function Fail([string]$message, [int]$code = 1) {
  Write-Error $message
  exit $code
}
function Test-PortValue([string]$port, [string]$label) {
  $value = 0
  if (-not [int]::TryParse($port, [ref]$value) -or $value -lt 1 -or $value -gt 65535) {
    Fail "Invalid $label port: $port" 1
  }
}
function Resolve-CommandSource([string]$name) {
  $cmd = Get-Command $name -ErrorAction SilentlyContinue
  if ($cmd -and $cmd.Source) { return $cmd.Source }
  return $null
}
function Resolve-PythonExe([string]$requested, [string]$repoRoot) {
  if (-not [string]::IsNullOrWhiteSpace($requested)) {
    if (Test-Path -LiteralPath $requested) { return (Resolve-Path -LiteralPath $requested).Path }
    Fail "Python not found: $requested" 1
  }

  foreach ($candidate in @(
    (Join-Path $repoRoot '.venv\Scripts\python.exe'),
    (Join-Path $repoRoot 'venv\Scripts\python.exe')
  )) {
    if (Test-Path -LiteralPath $candidate) { return (Resolve-Path -LiteralPath $candidate).Path }
  }

  $python = Resolve-CommandSource 'python.exe'
  if (-not $python) { $python = Resolve-CommandSource 'python' }
  if ($python) { return $python }

  Fail 'Python not found. Install Python, create .venv, or pass -PythonExe <path>.' 1
}
function Get-ProcessInfo([int]$processId) {
  return Get-CimInstance Win32_Process -Filter "ProcessId=$processId" -ErrorAction SilentlyContinue
}
function Save-PidFile() {
  if ($DryRun) { return }

  $state = [ordered]@{
    root = $root
    startedAt = $script:startedAt
    ports = [ordered]@{
      go = $GoPort
      api = $ApiPort
      web = $WebPort
      mobile = if ($NoMobile) { $null } else { $MobilePort }
    }
    processes = $script:startedProcesses
  }
  $state | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $pidFile -Encoding UTF8
}
function Add-StartedProcess([string]$name, [int]$processId) {
  $info = Get-ProcessInfo -processId $processId
  $script:startedProcesses += [ordered]@{
    name = $name
    pid = $processId
    createdAt = if ($info -and $info.CreationDate) { ([datetime]$info.CreationDate).ToString('o') } else { $null }
  }
  Save-PidFile
}
function Stop-ProcessTree([int]$processId, [string]$label) {
  if ($processId -le 0 -or $processId -eq $PID) { return }

  $children = Get-CimInstance Win32_Process -Filter "ParentProcessId=$processId" -ErrorAction SilentlyContinue
  foreach ($child in @($children)) {
    Stop-ProcessTree -processId ([int]$child.ProcessId) -label "$label child"
  }

  $proc = Get-Process -Id $processId -ErrorAction SilentlyContinue
  if ($proc) {
    Stop-Process -Id $processId -Force -ErrorAction SilentlyContinue
    Log "Stopped $label PID=$processId ($($proc.ProcessName))"
  }
}
function Stop-LaunchedProcesses() {
  foreach ($record in @($script:startedProcesses)) {
    if ($record.pid) {
      Stop-ProcessTree -processId ([int]$record.pid) -label ([string]$record.name)
    }
  }
}
function Fail-Launch([string]$message, [int]$code) {
  Stop-LaunchedProcesses
  Remove-Item -LiteralPath $pidFile -Force -ErrorAction SilentlyContinue
  Fail $message $code
}
function Show-LogTail([string]$path, [int]$lines = 80) {
  if (Test-Path -LiteralPath $path) {
    Log "---- $path ----"
    Get-Content -LiteralPath $path -Tail $lines | ForEach-Object { Log $_ }
  }
}
function Wait-Port([string]$hostName, [string]$port, [int]$timeoutSeconds, [string]$label) {
  $deadline = (Get-Date).AddSeconds($timeoutSeconds)
  while ((Get-Date) -lt $deadline) {
    $client = $null
    try {
      $client = [System.Net.Sockets.TcpClient]::new()
      $async = $client.BeginConnect($hostName, [int]$port, $null, $null)
      if ($async.AsyncWaitHandle.WaitOne(1000, $false)) {
        $client.EndConnect($async)
        if ($client.Connected) {
          Log "$label is listening on $hostName`:$port"
          return $true
        }
      }
    } catch {
    } finally {
      if ($client) { $client.Close() }
    }
    Start-Sleep -Seconds 1
  }
  return $false
}
function Wait-Http([string]$url, [int]$timeoutSeconds, [string]$label) {
  $deadline = (Get-Date).AddSeconds($timeoutSeconds)
  while ((Get-Date) -lt $deadline) {
    try {
      $response = Invoke-WebRequest -UseBasicParsing -Uri $url -TimeoutSec 5
      if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 500) {
        Log "$label responded with HTTP $($response.StatusCode)"
        return $true
      }
    } catch {
    }
    Start-Sleep -Seconds 1
  }
  return $false
}
function Start-LoggedProcess(
  [string]$name,
  [string]$filePath,
  [string[]]$argumentList,
  [string]$workingDirectory,
  [string]$stdoutPath,
  [string]$stderrPath
) {
  if ($DryRun) {
    Log "[DRY-RUN] ${name}: $filePath $($argumentList -join ' ')"
    return $null
  }

  $startArgs = @{
    FilePath = $filePath
    WorkingDirectory = $workingDirectory
    RedirectStandardOutput = $stdoutPath
    RedirectStandardError = $stderrPath
    PassThru = $true
    WindowStyle = 'Hidden'
  }
  if ($argumentList -and $argumentList.Count -gt 0) {
    $startArgs.ArgumentList = $argumentList
  }

  $proc = Start-Process @startArgs
  Log "$name PID=$($proc.Id)"
  Add-StartedProcess -name $name -processId $proc.Id
  return $proc
}

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

$serverDir = Join-Path $root 'server'
$frontendDir = Join-Path $root 'frontend'
$mobileDir = Join-Path $root 'frontend-mobile'
$goExe = Join-Path $serverDir 'smart-scheduling-server-go.exe'
$stopScript = Join-Path $root 'stop_fullstack.ps1'
$pidFile = Join-Path $root '.fullstack.pids.json'
$script:startedAt = (Get-Date).ToString('o')
$script:startedProcesses = @()

$goOut = Join-Path $serverDir 'go-launcher.out.log'
$goErr = Join-Path $serverDir 'go-launcher.err.log'
$apiOut = Join-Path $root 'api-launcher.out.log'
$apiErr = Join-Path $root 'api-launcher.err.log'
$webOut = Join-Path $frontendDir 'web-launcher.out.log'
$webErr = Join-Path $frontendDir 'web-launcher.err.log'
$mobileOut = Join-Path $mobileDir 'mobile-launcher.out.log'
$mobileErr = Join-Path $mobileDir 'mobile-launcher.err.log'

Log '========================================'
Log 'V8 Fullstack Launcher'
Log "ROOT: $root"
Log '========================================'

Test-PortValue -port $GoPort -label 'Go'
Test-PortValue -port $ApiPort -label 'API'
Test-PortValue -port $WebPort -label 'frontend'
Test-PortValue -port $MobilePort -label 'mobile frontend'

if (-not (Test-Path -LiteralPath (Join-Path $serverDir 'cmd\main.go'))) { Fail 'Missing server\cmd\main.go' 1 }
if (-not (Test-Path -LiteralPath (Join-Path $frontendDir 'package.json'))) { Fail 'Missing frontend\package.json' 1 }

$PythonExe = Resolve-PythonExe -requested $PythonExe -repoRoot $root
Log "Python: $PythonExe"

$goCmd = Resolve-CommandSource 'go.exe'
if (-not $goCmd) { $goCmd = Resolve-CommandSource 'go' }
if (-not $goCmd -and (Test-Path -LiteralPath 'C:\Program Files\Go\bin\go.exe')) {
  $goCmd = 'C:\Program Files\Go\bin\go.exe'
}
if (-not $goCmd -and (Test-Path -LiteralPath 'C:\Program Files (x86)\Go\bin\go.exe')) {
  $goCmd = 'C:\Program Files (x86)\Go\bin\go.exe'
}
if (-not $goCmd) { Fail 'go not found in PATH or fallback paths.' 1 }
Log "Go: $goCmd"

$npmCmd = Resolve-CommandSource 'npm.cmd'
if (-not $npmCmd) { $npmCmd = Resolve-CommandSource 'npm' }
if (-not $npmCmd) { Fail 'npm not found in PATH.' 1 }
Log "npm: $npmCmd"

$goCache = Join-Path $serverDir '.gocache-build'
$goModCache = Join-Path $serverDir '.gomodcache-build'
if (-not $DryRun) {
  New-Item -ItemType Directory -Force -Path $goCache | Out-Null
  New-Item -ItemType Directory -Force -Path $goModCache | Out-Null
}

Log '[1/5] Cleaning old V8 processes...'
if ($DryRun) {
  Log "[DRY-RUN] powershell -File '$stopScript'"
} elseif (Test-Path -LiteralPath $stopScript) {
  & powershell -NoProfile -ExecutionPolicy Bypass -File $stopScript -GoPort $GoPort -ApiPort $ApiPort -WebPort $WebPort -MobilePort $MobilePort | ForEach-Object { Log $_ }
  if ($LASTEXITCODE -ne 0) { Fail "Stop script failed with exit code $LASTEXITCODE" 2 }
} else {
  Remove-Item -LiteralPath $pidFile -Force -ErrorAction SilentlyContinue
}

if (-not $DryRun) {
  Remove-Item -LiteralPath $goOut,$goErr,$apiOut,$apiErr,$webOut,$webErr -ErrorAction SilentlyContinue
  if (Test-Path -LiteralPath $mobileDir) {
    Remove-Item -LiteralPath $mobileOut,$mobileErr -ErrorAction SilentlyContinue
  }
}

Log '[2/5] Building Go sandbox binary...'
if ($DryRun) {
  Log "[DRY-RUN] $goCmd build -o '$goExe' .\cmd\main.go"
} else {
  Push-Location $serverDir
  try {
    $env:GOCACHE = $goCache
    $env:GOMODCACHE = $goModCache
    & $goCmd build -o $goExe .\cmd\main.go
    if ($LASTEXITCODE -ne 0) { Fail 'Go build failed.' 3 }
  } finally {
    Pop-Location
  }
}

Log "[3/5] Starting Go sandbox on $GoPort..."
if (-not $DryRun) { $env:HTTP_ADDR = ":$GoPort" }
$null = Start-LoggedProcess `
  -name 'Go backend' `
  -filePath $goExe `
  -argumentList @() `
  -workingDirectory $serverDir `
  -stdoutPath $goOut `
  -stderrPath $goErr
if (-not $DryRun -and -not (Wait-Http -url "http://127.0.0.1:$GoPort/api/health" -timeoutSeconds 45 -label 'Go health')) {
  Fail-Launch "Go health check failed. See logs: $goOut / $goErr" 4
}

Log "[4/5] Starting FastAPI on $ApiPort..."
if (-not $DryRun) { $env:GO_SANDBOX_URL = "http://127.0.0.1:$GoPort" }
$null = Start-LoggedProcess `
  -name 'FastAPI' `
  -filePath $PythonExe `
  -argumentList @('-m','uvicorn','api.main:app','--host','0.0.0.0','--port',$ApiPort) `
  -workingDirectory $root `
  -stdoutPath $apiOut `
  -stderrPath $apiErr
if (-not $DryRun -and -not (Wait-Http -url "http://127.0.0.1:$ApiPort/health" -timeoutSeconds 90 -label 'FastAPI health')) {
  Fail-Launch "FastAPI health check failed. See logs: $apiOut / $apiErr" 5
}

Log "[5/5] Starting frontends..."
if (-not $DryRun) {
  $env:VITE_API_BASE_URL = '/api/v1'
  $env:VITE_PROXY_TARGET = "http://127.0.0.1:$ApiPort"
}
$null = Start-LoggedProcess `
  -name 'frontend' `
  -filePath $npmCmd `
  -argumentList @('run','dev','--','--host','0.0.0.0','--port',$WebPort,'--strictPort') `
  -workingDirectory $frontendDir `
  -stdoutPath $webOut `
  -stderrPath $webErr
if (-not $DryRun -and -not (Wait-Port -hostName '127.0.0.1' -port $WebPort -timeoutSeconds 300 -label 'Frontend')) {
  Show-LogTail $webOut
  Show-LogTail $webErr
  Fail-Launch "Frontend did not listen on port $WebPort. See logs: $webOut / $webErr" 6
}

if ($NoMobile) {
  Log 'Skipping mobile frontend: -NoMobile'
} elseif (Test-Path -LiteralPath (Join-Path $mobileDir 'package.json')) {
  $null = Start-LoggedProcess `
    -name 'mobile frontend' `
    -filePath $npmCmd `
    -argumentList @('run','dev','--','--host','0.0.0.0','--port',$MobilePort,'--strictPort') `
    -workingDirectory $mobileDir `
    -stdoutPath $mobileOut `
    -stderrPath $mobileErr
  if (-not $DryRun -and -not (Wait-Port -hostName '127.0.0.1' -port $MobilePort -timeoutSeconds 300 -label 'Mobile frontend')) {
    Show-LogTail $mobileOut
    Show-LogTail $mobileErr
    Fail-Launch "Mobile frontend did not listen on port $MobilePort. See logs: $mobileOut / $mobileErr" 7
  }
} else {
  Log 'Skipping mobile frontend: frontend-mobile\package.json not found'
}

Log ''
Log 'Started.'
Log "Go health : http://127.0.0.1:$GoPort/api/health"
Log "API docs  : http://127.0.0.1:$ApiPort/docs"
Log "Frontend  : http://127.0.0.1:$WebPort"
if (-not $NoMobile) { Log "Mobile    : http://127.0.0.1:$MobilePort" }
Log "PID file  : $pidFile"
Log 'Logs:'
Log "- $goOut"
Log "- $goErr"
Log "- $apiOut"
Log "- $apiErr"
Log "- $webOut"
Log "- $webErr"
if (-not $NoMobile -and (Test-Path -LiteralPath $mobileDir)) {
  Log "- $mobileOut"
  Log "- $mobileErr"
}
