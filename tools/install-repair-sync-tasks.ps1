[CmdletBinding()]
param(
    [string]$TaskPrefix = 'V8-RepairSync',
    [string]$DailyTime = '02:30'
)

$project = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$dailyBat = Join-Path $project 'tools\repair_sync_daily.bat'
$pendingBat = Join-Path $project 'tools\repair_sync_send_pending.bat'

$dailyAction = New-ScheduledTaskAction -Execute $dailyBat -WorkingDirectory $project
$pendingAction = New-ScheduledTaskAction -Execute $pendingBat -WorkingDirectory $project
$dailyTrigger = New-ScheduledTaskTrigger -Daily -At ([datetime]::ParseExact($DailyTime, 'HH:mm', $null))
$pendingTrigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) `
    -RepetitionInterval (New-TimeSpan -Minutes 5) -RepetitionDuration (New-TimeSpan -Days 3650)

Register-ScheduledTask -TaskName "$TaskPrefix-Daily" -Action $dailyAction -Trigger $dailyTrigger `
    -Description 'V8 repair snapshot generation and upload outbox enqueue' -Force | Out-Null
Register-ScheduledTask -TaskName "$TaskPrefix-SendPending" -Action $pendingAction -Trigger $pendingTrigger `
    -Description 'V8 repair snapshot upload retry worker' -Force | Out-Null

Write-Host "Installed $TaskPrefix-Daily and $TaskPrefix-SendPending for $project"
