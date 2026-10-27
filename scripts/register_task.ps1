# Register a Windows scheduled task that runs run_today.bat every day.
#   - Runs only while the user is logged on (it shows a confirm dialog and a browser)
#   - If the scheduled time was missed (PC off), it runs as soon as possible afterwards
# Usage (normal PowerShell, no admin needed):
#   powershell -ExecutionPolicy Bypass -File scripts\register_task.ps1
#   powershell -ExecutionPolicy Bypass -File scripts\register_task.ps1 -Time 21:00 -ExtraArgs "--auto"
#   powershell -ExecutionPolicy Bypass -File scripts\register_task.ps1 -Unregister
param(
    [string]$TaskName = "CRM Weekly Plan Run",
    [string]$Time = "20:30",
    [string]$ExtraArgs = "",
    [switch]$Unregister
)

$ErrorActionPreference = "Stop"

if ($Unregister) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    Write-Host "Removed scheduled task: $TaskName"
    exit 0
}

$projectRoot = Split-Path -Parent $PSScriptRoot
$batPath = Join-Path $projectRoot "run_today.bat"
if (-not (Test-Path $batPath)) {
    throw "run_today.bat not found: $batPath"
}

$action = New-ScheduledTaskAction -Execute "cmd.exe" `
    -Argument "/c `"`"$batPath`" $ExtraArgs`"" `
    -WorkingDirectory $projectRoot
$trigger = New-ScheduledTaskTrigger -Daily -At $Time
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive
$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Hours 3) `
    -MultipleInstances IgnoreNew

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
    -Principal $principal -Settings $settings -Force | Out-Null

Write-Host "Registered scheduled task: $TaskName (daily at $Time, $batPath $ExtraArgs)"
