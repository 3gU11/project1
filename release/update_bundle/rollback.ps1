param(
  [string]$InstallDir = "D:\antigraveity_pj\V7ex",
  [string]$BackupDir = "",
  [string]$ServiceName = "",
  [int]$ApiPort = 8000,
  [string]$HealthUrl = "http://127.0.0.1:8000/health",
  [switch]$SkipDbRestore
)

$ErrorActionPreference = "Stop"

function Read-DotEnv([string]$Path) {
  $map = @{}
  if (!(Test-Path -LiteralPath $Path)) { return $map }
  $lines = Get-Content -LiteralPath $Path -Encoding UTF8
  foreach ($line in $lines) {
    $raw = ""
    if ($null -ne $line) { $raw = [string]$line }
    $t = $raw.Trim()
    if ($t.Length -eq 0) { continue }
    if ($t.StartsWith("#")) { continue }
    $idx = $t.IndexOf("=")
    if ($idx -le 0) { continue }
    $k = $t.Substring(0, $idx).Trim()
    $v = $t.Substring($idx + 1).Trim()
    if (($v.StartsWith('"') -and $v.EndsWith('"')) -or ($v.StartsWith("'") -and $v.EndsWith("'"))) {
      $v = $v.Substring(1, $v.Length - 2)
    }
    if ($k) { $map[$k] = $v }
  }
  return $map
}

function Set-EnvFromMap($map) {
  foreach ($k in $map.Keys) {
    $v = [string]$map[$k]
    if ($null -ne $v) { Set-Item -Path ("Env:" + $k) -Value $v }
  }
}

function Assert-Path([string]$Path, [string]$Message) {
  if (!(Test-Path -LiteralPath $Path)) { throw $Message }
}

function Invoke-RoboCopy([string]$Source, [string]$Dest, [string[]]$Args) {
  New-Item -ItemType Directory -Force -Path $Dest | Out-Null
  $cmdArgs = @($Source, $Dest) + $Args
  & robocopy @cmdArgs | Out-Null
  $code = $LASTEXITCODE
  if ($code -ge 8) { throw "robocopy failed ($code): $Source -> $Dest" }
}

function Get-CommandPath([string]$Name) {
  try { return (Get-Command $Name -ErrorAction Stop).Source } catch { return $null }
}

function Get-PythonPath {
  $p = Get-CommandPath "python"
  if ($p) { return $p }
  return (Get-CommandPath "py")
}

function Stop-Api([int]$Port, [string]$SvcName) {
  if ($SvcName.Trim()) {
    $svc = Get-Service -Name $SvcName -ErrorAction SilentlyContinue
    if ($svc -and $svc.Status -ne "Stopped") {
      Stop-Service -Name $SvcName -Force
      $svc.WaitForStatus("Stopped", (New-TimeSpan -Seconds 30))
    }
    return
  }

  $conns = @()
  try { $conns = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction Stop } catch { $conns = @() }
  foreach ($c in $conns) {
    $pid = [int]$c.OwningProcess
    if ($pid -le 0) { continue }
    $p = Get-Process -Id $pid -ErrorAction SilentlyContinue
    if (!$p) { continue }
    Stop-Process -Id $pid -Force
  }
}

function Start-Api([string]$Dir, [string]$SvcName) {
  if ($SvcName.Trim()) {
    Start-Service -Name $SvcName
    return
  }
  $python = Get-PythonPath
  if (!$python) { throw "python not found in PATH" }
  $proc = Start-Process -FilePath $python -ArgumentList @("run_api.py") -WorkingDirectory $Dir -PassThru -WindowStyle Hidden
  Set-Content -LiteralPath (Join-Path $Dir "run_api.pid") -Value ([string]$proc.Id) -Encoding ASCII
}

function Test-Health([string]$Url) {
  $ok = $false
  $last = $null
  for ($i = 0; $i -lt 20; $i++) {
    try {
      $r = Invoke-RestMethod -Uri $Url -Method GET -TimeoutSec 2
      if ($null -ne $r) { $ok = $true; break }
    } catch { $last = $_ }
    Start-Sleep -Seconds 1
  }
  if (!$ok) { throw ("health check failed: " + $Url + " " + ($last | Out-String)) }
}

Assert-Path $InstallDir "InstallDir not found: $InstallDir"
if (!$BackupDir.Trim()) { throw "BackupDir is required" }
Assert-Path $BackupDir "BackupDir not found: $BackupDir"

$backupAppDir = Join-Path $BackupDir "app"
Assert-Path $backupAppDir "backup app dir not found: $backupAppDir"

Stop-Api -Port $ApiPort -SvcName $ServiceName

Invoke-RoboCopy $backupAppDir $InstallDir @("/E")

$envBackup = Join-Path $BackupDir ".env"
$envPath = Join-Path $InstallDir ".env"
if (Test-Path -LiteralPath $envBackup) {
  Copy-Item -LiteralPath $envBackup -Destination $envPath -Force
}

$envMap = Read-DotEnv $envPath
Set-EnvFromMap $envMap

if (!$SkipDbRestore) {
  $mysql = Get-CommandPath "mysql"
  if (!$mysql) { throw "mysql not found in PATH (use -SkipDbRestore to bypass)" }

  $dbDir = Join-Path $BackupDir "db"
  Assert-Path $dbDir "backup db dir not found: $dbDir"
  $sqlFile = Get-ChildItem -LiteralPath $dbDir -Filter "*.sql" -File | Sort-Object LastWriteTime -Descending | Select-Object -First 1
  if (!$sqlFile) { throw "no .sql found in backup db dir: $dbDir" }

  $host = $envMap["MYSQL_HOST"]; if (!$host) { $host = "localhost" }
  $port = $envMap["MYSQL_PORT"]; if (!$port) { $port = "3306" }
  $user = $envMap["MYSQL_USER"]; if (!$user) { $user = "root" }
  $pass = $envMap["MYSQL_PASSWORD"]
  $db = $envMap["MYSQL_DB"]; if (!$db) { $db = "rjfinshed" }

  $passArg = ""
  if ($pass) { $passArg = "--password=" + $pass }
  $cmd = '"' + $mysql + '" --host=' + $host + ' --port=' + $port + ' --user=' + $user + ' ' + $passArg + ' ' + $db + ' < "' + $sqlFile.FullName + '"'
  cmd /c $cmd | Out-Null
  if ($LASTEXITCODE -ne 0) { throw "mysql restore failed: $($sqlFile.FullName)" }
}

Start-Api -Dir $InstallDir -SvcName $ServiceName
Test-Health -Url $HealthUrl

Write-Host "[rollback] SUCCESS"
