$ErrorActionPreference = "Stop"

$taskName = "V8-Mobile-5174-Watchdog"
$scriptPath = Join-Path $PSScriptRoot "start-mobile-watchdog.ps1"

if (-not (Test-Path $scriptPath)) {
  throw "Missing watchdog script: $scriptPath"
}

try {
  $existing = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
  if ($existing) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
  }

  $action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$scriptPath`""

  $trigger = New-ScheduledTaskTrigger -AtLogOn
  $settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Seconds 0)

  Register-ScheduledTask `
    -TaskName $taskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Description "Keeps V8 frontend-mobile Vite dev server running on port 5174." `
    -Force | Out-Null

  Start-ScheduledTask -TaskName $taskName
  Write-Host "Installed and started scheduled task: $taskName"
} catch {
  $startupDir = [Environment]::GetFolderPath("Startup")
  $shortcutPath = Join-Path $startupDir "$taskName.lnk"
  $shell = New-Object -ComObject WScript.Shell
  $shortcut = $shell.CreateShortcut($shortcutPath)
  $shortcut.TargetPath = "powershell.exe"
  $shortcut.Arguments = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$scriptPath`""
  $shortcut.WorkingDirectory = Split-Path -Parent $scriptPath
  $shortcut.Description = "Keeps V8 frontend-mobile Vite dev server running on port 5174."
  $shortcut.Save()

  Start-Process `
    -FilePath "powershell.exe" `
    -ArgumentList @("-NoProfile", "-ExecutionPolicy", "Bypass", "-WindowStyle", "Hidden", "-File", $scriptPath) `
    -WindowStyle Hidden

  Write-Host "Scheduled task was not allowed, installed Startup shortcut instead: $shortcutPath"
}

Write-Host "Mobile URL: http://localhost:5174/ or http://<this-computer-ip>:5174/"
