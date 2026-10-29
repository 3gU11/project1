param(
  [int]$DelaySeconds = 60,
  [switch]$NoMobile
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$log = Join-Path $root 'startup-task.log'

function Write-StartupLog([string]$message) {
  $line = "{0} {1}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss zzz'), $message
  Add-Content -LiteralPath $log -Value $line -Encoding UTF8
}

try {
  Set-Location -LiteralPath $root
  Write-StartupLog "Startup task triggered. Waiting $DelaySeconds seconds for Windows services."
  if ($DelaySeconds -gt 0) { Start-Sleep -Seconds $DelaySeconds }

  $launcher = Join-Path $root 'run_fullstack.ps1'
  if (-not (Test-Path -LiteralPath $launcher)) {
    throw "Launcher not found: $launcher"
  }

  $args = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $launcher, '-NoMobile')
  Write-StartupLog "Launching full stack from $root"
  & powershell.exe @args *>> $log
  if ($LASTEXITCODE -ne 0) {
    throw "Full stack launcher exited with code $LASTEXITCODE"
  }
  Write-StartupLog 'Full stack launcher completed.'
} catch {
  Write-StartupLog "ERROR: $($_.Exception.Message)"
  exit 1
}
