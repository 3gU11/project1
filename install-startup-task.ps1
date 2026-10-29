param(
  [string]$TaskName = 'V8 Fullstack - Start at system boot',
  [int]$DelaySeconds = 60
)

$ErrorActionPreference = 'Stop'

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principalCheck = [Security.Principal.WindowsPrincipal]::new($identity)
if (-not $principalCheck.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
  $self = $MyInvocation.MyCommand.Path
  $arguments = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', "`"$self`"")
  foreach ($bound in $MyInvocation.BoundParameters.GetEnumerator()) {
    $arguments += "-$($bound.Key)"
    $arguments += [string]$bound.Value
  }
  Start-Process -FilePath 'powershell.exe' -Verb RunAs -Wait -ArgumentList $arguments
  exit $LASTEXITCODE
}

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$startupScript = Join-Path $root 'start-on-boot.ps1'
if (-not (Test-Path -LiteralPath $startupScript)) { throw "Missing startup script: $startupScript" }

$principal = New-ScheduledTaskPrincipal -UserId 'SYSTEM' -LogonType ServiceAccount -RunLevel Highest
$action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$startupScript`" -DelaySeconds $DelaySeconds"
$trigger = New-ScheduledTaskTrigger -AtStartup
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Hours 2)

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Description 'Start the V8 Go, OCR, FastAPI and frontend services after Windows boots.' -Force | Out-Null
Write-Output "Registered scheduled task: $TaskName"
Write-Output "Script: $startupScript"
