param(
  [switch]$UnregisterTask
)

$ErrorActionPreference = "SilentlyContinue"

$taskName = "V8-Mobile-5174-Watchdog"
$scriptPath = Join-Path $PSScriptRoot "start-mobile-watchdog.ps1"
$projectRoot = Split-Path -Parent $PSScriptRoot
$mobileDir = Join-Path $projectRoot "frontend-mobile"
$startupShortcut = Join-Path ([Environment]::GetFolderPath("Startup")) "$taskName.lnk"

Get-CimInstance Win32_Process |
  Where-Object {
    $_.ProcessId -ne $PID -and
    $_.CommandLine -and
    (
      $_.CommandLine -like "*$scriptPath*" -or
      ($_.CommandLine -like "*frontend-mobile*" -and $_.CommandLine -match "vite|npm|node|cmd")
    )
  } |
  ForEach-Object {
    Stop-Process -Id $_.ProcessId -Force
  }

if ($UnregisterTask) {
  Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
  Remove-Item -LiteralPath $startupShortcut -Force
}

Write-Host "Mobile watchdog and frontend-mobile dev processes stopped."
