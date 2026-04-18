param(
  [string]$InstallDir = "D:\antigraveity_pj\V7ex",
  [string]$BackupRoot = "D:\backup\V7ex_updates",
  [ValidateSet("inplace", "newdb")][string]$DbMode = "inplace",
  [string]$PackageDir = "",
  [string]$ServiceName = "",
  [int]$ApiPort = 8000,
  [string]$HealthUrl = "http://127.0.0.1:8000/health",
  [switch]$NoBackend,
  [switch]$NoFrontend,
  [switch]$NoDb,
  [switch]$SkipDbBackup
)

$ErrorActionPreference = "Stop"

function New-Timestamp {
  return (Get-Date).ToString("yyyy-MM-dd_HHmmss")
}

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

if (!$PackageDir.Trim()) { $PackageDir = Join-Path $PSScriptRoot "package" }

$envPath = Join-Path $InstallDir ".env"
Assert-Path $InstallDir "InstallDir not found: $InstallDir"
Assert-Path $envPath ".env not found: $envPath"
Assert-Path $PackageDir "PackageDir not found: $PackageDir"

$envMap = Read-DotEnv $envPath
Set-EnvFromMap $envMap

$stamp = New-Timestamp
$backupDir = Join-Path $BackupRoot $stamp
$backupAppDir = Join-Path $backupDir "app"
$backupDbDir = Join-Path $backupDir "db"
New-Item -ItemType Directory -Force -Path $backupAppDir | Out-Null
New-Item -ItemType Directory -Force -Path $backupDbDir | Out-Null

Write-Host ("[update] InstallDir: " + $InstallDir)
Write-Host ("[update] PackageDir: " + $PackageDir)
Write-Host ("[update] BackupDir:  " + $backupDir)
Write-Host ("[update] DbMode:     " + $DbMode)

Copy-Item -LiteralPath $envPath -Destination (Join-Path $backupDir ".env") -Force

$excludeDirs = @("venv", "__pycache__", ".git", "node_modules")
$backupArgs = @("/E", "/XD") + $excludeDirs
Invoke-RoboCopy $InstallDir $backupAppDir $backupArgs

if (!$SkipDbBackup -and !$NoDb) {
  $mysqldump = Get-CommandPath "mysqldump"
  if (!$mysqldump) { throw "mysqldump not found in PATH (use -SkipDbBackup to bypass)" }

  $host = $envMap["MYSQL_HOST"]; if (!$host) { $host = "localhost" }
  $port = $envMap["MYSQL_PORT"]; if (!$port) { $port = "3306" }
  $user = $envMap["MYSQL_USER"]; if (!$user) { $user = "root" }
  $pass = $envMap["MYSQL_PASSWORD"]
  $db = $envMap["MYSQL_DB"]; if (!$db) { $db = "rjfinshed" }

  $outSql = Join-Path $backupDbDir ("mysql_" + $db + "_" + $stamp + ".sql")
  $args = @("--host=$host", "--port=$port", "--user=$user", "--single-transaction", "--routines", "--triggers", "--databases", $db)
  if ($pass) { $args = @("--password=$pass") + $args }

  $tmpOut = Join-Path $backupDbDir ("dump_" + $db + "_" + $stamp + ".tmp.sql")
  $tmpErr = Join-Path $backupDbDir ("dump_" + $db + "_" + $stamp + ".tmp.err")
  $p = Start-Process -FilePath $mysqldump -ArgumentList $args -NoNewWindow -Wait -PassThru -RedirectStandardOutput $tmpOut -RedirectStandardError $tmpErr
  if ($p.ExitCode -ne 0) {
    $stderr = ""
    if (Test-Path -LiteralPath $tmpErr) { $stderr = (Get-Content -LiteralPath $tmpErr -Raw -ErrorAction SilentlyContinue) }
    throw ("mysqldump failed: " + $stderr)
  }
  Move-Item -LiteralPath $tmpOut -Destination $outSql -Force
  Write-Host ("[update] DB backup: " + $outSql)
}

Stop-Api -Port $ApiPort -SvcName $ServiceName

if (!$NoBackend) {
  $backendSrc = Join-Path $PackageDir "backend"
  Assert-Path $backendSrc "backend package not found: $backendSrc"
  Invoke-RoboCopy $backendSrc $InstallDir @("/E", "/XF", ".env")
}

if (!$NoFrontend) {
  $frontendSrc = Join-Path $PackageDir "frontend-dist"
  Assert-Path $frontendSrc "frontend-dist package not found: $frontendSrc"
  $frontendRoot = $envMap["FRONTEND_WEB_ROOT"]
  if ($frontendRoot -and (Test-Path -LiteralPath $frontendRoot)) {
    Invoke-RoboCopy $frontendSrc $frontendRoot @("/E")
    Write-Host ("[update] Frontend deployed to FRONTEND_WEB_ROOT: " + $frontendRoot)
  } else {
    $fallback = Join-Path $InstallDir "frontend\dist"
    Invoke-RoboCopy $frontendSrc $fallback @("/E")
    Write-Host ("[update] Frontend deployed to: " + $fallback)
  }
}

if (!$NoDb) {
  $python = Get-PythonPath
  if (!$python) { throw "python not found in PATH" }
  $scriptDir = Join-Path $PSScriptRoot "scripts"
  if ($DbMode -eq "inplace") {
    & $python (Join-Path $scriptDir "db_migrate_inplace.py") --env $envPath --workdir $InstallDir
    if ($LASTEXITCODE -ne 0) { throw "db migrate inplace failed" }
  } else {
    $out = & $python (Join-Path $scriptDir "db_migrate_newdb.py") --env $envPath --workdir $InstallDir
    if ($LASTEXITCODE -ne 0) { throw "db migrate newdb failed" }
    $newDb = ([string]$out | Select-Object -Last 1).Trim()
    if (!$newDb) { throw "db migrate newdb: missing new db name output" }
    $envText = Get-Content -LiteralPath $envPath -Encoding UTF8
    $next = @()
    $replaced = $false
    foreach ($line in $envText) {
      if ($line -match '^\s*MYSQL_DB=') { $next += ("MYSQL_DB=" + $newDb); $replaced = $true }
      else { $next += $line }
    }
    if (!$replaced) { $next += ("MYSQL_DB=" + $newDb) }
    Set-Content -LiteralPath $envPath -Value $next -Encoding UTF8
    $envMap = Read-DotEnv $envPath
    Set-EnvFromMap $envMap
    Write-Host ("[update] .env MYSQL_DB updated to: " + $newDb)
  }
}

Start-Api -Dir $InstallDir -SvcName $ServiceName
Test-Health -Url $HealthUrl

Write-Host "[update] SUCCESS"
Write-Host ("[update] BackupDir: " + $backupDir)
