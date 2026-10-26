$ErrorActionPreference = "Stop"

$projectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$runner = Join-Path $projectDir "run_scheduled.ps1"
$taskName = "TCG Tracker - Hourly Update"

if (-not (Test-Path -LiteralPath $runner)) {
    throw "Scheduled runner not found: $runner"
}

$action = New-ScheduledTaskAction `
    -Execute "$env:SystemRoot\System32\conhost.exe" `
    -Argument "--headless powershell.exe -WindowStyle Hidden -NoProfile -NonInteractive -ExecutionPolicy Bypass -File `"$runner`"" `
    -WorkingDirectory $projectDir

$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(2) `
    -RepetitionInterval (New-TimeSpan -Minutes 30) `
    -RepetitionDuration (New-TimeSpan -Days 3650)

$principal = New-ScheduledTaskPrincipal `
    -UserId ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name) `
    -LogonType Interactive `
    -RunLevel Limited

$settings = New-ScheduledTaskSettingsSet `
    -MultipleInstances IgnoreNew `
    -StartWhenAvailable `
    -WakeToRun `
    -ExecutionTimeLimit (New-TimeSpan -Hours 2)

Register-ScheduledTask `
    -TaskName $taskName `
    -Action $action `
    -Trigger $trigger `
    -Principal $principal `
    -Settings $settings `
    -Description "Runs the TCG tracker every 30 minutes and records output under logs." `
    -Force | Out-Null

Write-Host "Created scheduled task '$taskName'. It starts in about two minutes, then repeats every 30 minutes."
Write-Host "Logs: $(Join-Path $projectDir 'logs')"
