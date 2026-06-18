[CmdletBinding()]
param(
  [string]$DatabaseName = "rjfinshed",
  [string]$MysqlRootPassword = "030705",
  [string]$MySqlHost = "127.0.0.1",
  [int]$MySqlPort = 3306,
  [string]$MySqlUser = "root",
  [string]$PythonExe = "",
  [string]$BatchCode = "",
  [string]$LineId = "",
  [string]$Actor = "manual_batch_line_tool",
  [int]$ListLimit = 60,
  [switch]$DryRun,
  [switch]$Force,
  [switch]$ReassignExisting,
  [switch]$ReopenCompleted,
  [switch]$ReplaceLine,
  [switch]$AllStatuses,
  [switch]$IncludeShipped,
  [switch]$AllowEmptyBatch,
  [switch]$EnsureDefaultLines,
  [switch]$ListOnly,
  [switch]$Yes
)

$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$PythonScript = Join-Path $PSScriptRoot "assign_fg_batch_to_kanban_line.py"

if (-not (Test-Path -LiteralPath $PythonScript)) {
  throw "Python helper not found: $PythonScript"
}

if ([string]::IsNullOrWhiteSpace($PythonExe)) {
  $VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
  if (Test-Path -LiteralPath $VenvPython) {
    $PythonExe = $VenvPython
  } else {
    $PythonCmd = Get-Command python -ErrorAction SilentlyContinue
    if ($PythonCmd -and $PythonCmd.Source) {
      $PythonExe = $PythonCmd.Source
    } else {
      $PyLauncher = Get-Command py.exe -ErrorAction SilentlyContinue
      if ($PyLauncher -and $PyLauncher.Source) {
        $PythonExe = $PyLauncher.Source
      } else {
        throw "Python not found. Create .venv, install Python in PATH, or pass -PythonExe <path>."
      }
    }
  }
}

$ArgsList = @(
  $PythonScript,
  "--database", $DatabaseName,
  "--host", $MySqlHost,
  "--port", [string]$MySqlPort,
  "--user", $MySqlUser,
  "--password", $MysqlRootPassword,
  "--actor", $Actor,
  "--list-limit", [string]$ListLimit
)

if (-not [string]::IsNullOrWhiteSpace($BatchCode)) {
  $ArgsList += @("--batch-code", $BatchCode)
}
if (-not [string]::IsNullOrWhiteSpace($LineId)) {
  $ArgsList += @("--line-id", $LineId)
}
if ($DryRun) {
  $ArgsList += "--dry-run"
}
if ($Force) {
  $ArgsList += "--force"
}
if ($ReassignExisting) {
  $ArgsList += "--reassign-existing"
}
if ($ReopenCompleted) {
  $ArgsList += "--reopen-completed"
}
if ($ReplaceLine) {
  $ArgsList += "--replace-line"
}
if ($AllStatuses) {
  $ArgsList += "--all-statuses"
}
if ($IncludeShipped) {
  $ArgsList += "--include-shipped"
}
if ($AllowEmptyBatch) {
  $ArgsList += "--allow-empty-batch"
}
if ($EnsureDefaultLines) {
  $ArgsList += "--ensure-default-lines"
}
if ($ListOnly) {
  $ArgsList += "--list-only"
}
if ($Yes) {
  $ArgsList += "--yes"
}

& $PythonExe @ArgsList
if ($LASTEXITCODE -ne 0) {
  exit $LASTEXITCODE
}
