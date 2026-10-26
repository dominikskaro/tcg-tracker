$ErrorActionPreference = "Stop"

$secureToken = Read-Host "Paste the bot token from BotFather (input is hidden)" -AsSecureString
$tokenPtr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureToken)
try {
    $token = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($tokenPtr)
}
finally {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($tokenPtr)
}

$response = Invoke-RestMethod `
    -Uri "https://api.telegram.org/bot$token/getUpdates" `
    -Method Get `
    -TimeoutSec 20

$startUpdate = $response.result |
    Where-Object { $_.message.text -match '^/start(?:@\w+)?$' } |
    Select-Object -Last 1

if (-not $startUpdate) {
    throw "Nisam našao /start poruku. Otvori razgovor sa svojim botom, pošalji /start pa pokreni ovu skriptu ponovno."
}

$chatId = [string]$startUpdate.message.chat.id
[Environment]::SetEnvironmentVariable("TCG_TELEGRAM_BOT_TOKEN", $token, "User")
[Environment]::SetEnvironmentVariable("TCG_TELEGRAM_CHAT_ID", $chatId, "User")

Write-Host "Telegram postavke spremljene za ovog Windows korisnika."
Write-Host "Chat ID: $chatId"
Write-Host "Odjavi se i ponovno prijavi u Windows da ih Task Scheduler sigurno preuzme."
