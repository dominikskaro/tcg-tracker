$ErrorActionPreference = "Continue"
$projectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$pythonExe = Join-Path $projectDir ".venv\Scripts\python.exe"
$runScript = Join-Path $projectDir "run.py"
$logsDir = Join-Path $projectDir "logs"

if (-not (Test-Path -LiteralPath $pythonExe)) {
    throw "Python virtual environment not found: $pythonExe"
}
New-Item -ItemType Directory -Path $logsDir -Force | Out-Null
$logPath = Join-Path $logsDir ("run-{0}.log" -f (Get-Date -Format "yyyy-MM-dd"))

"`n===== RUN START $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') =====" |
    Out-File -FilePath $logPath -Append -Encoding utf8
    $env:PYTHONIOENCODING = "utf-8"
& $pythonExe $runScript *>> $logPath
$runExitCode = $LASTEXITCODE
"===== RUN END $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') (exit $runExitCode) =====" |
    Out-File -FilePath $logPath -Append -Encoding utf8
try {
    if ($runExitCode -ne 0) {
        & $pythonExe -c "from telegram_notify import send_status; send_status('TCG Tracker: run je prekinut s greskom prije zavrsnog izvjestaja. Provjeri log.')"

        if ($LASTEXITCODE -ne 0) {
            "GREŠKA: Telegram statusna poruka nije poslana." |
                Out-File -FilePath $logPath -Append -Encoding utf8
        }
    }
} catch {
    "GREŠKA pri slanju Telegram statusa: $_" |
        Out-File -FilePath $logPath -Append -Encoding utf8
}
exit $runExitCode
