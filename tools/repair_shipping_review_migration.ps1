param(
  [string]$SourceDatabase,
  [string]$TargetDatabase = "rjfinshed",
  [string]$MysqlRootPassword = "030705",
  [string]$MysqlBase = "C:\Program Files\MySQL\MySQL Server 8.0",
  [string]$PythonExe = "python",
  [switch]$SkipBackup
)

$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($SourceDatabase)) {
  throw "SourceDatabase is required, for example: -SourceDatabase rjfinshed_source_recover_20260616_140831"
}

$scriptPath = Join-Path $PSScriptRoot "repair_shipping_review_migration.py"
if (-not (Test-Path $scriptPath)) {
  throw "Python repair script not found: $scriptPath"
}

$argsList = @(
  $scriptPath,
  "--source-database", $SourceDatabase,
  "--target-database", $TargetDatabase,
  "--mysql-root-password", $MysqlRootPassword,
  "--mysql-base", $MysqlBase
)

if ($SkipBackup) {
  $argsList += "--skip-backup"
}

& $PythonExe @argsList
if ($LASTEXITCODE -ne 0) {
  throw "shipping review repair failed"
}
