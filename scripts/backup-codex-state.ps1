$ErrorActionPreference = "Stop"

$codex = Join-Path $env:USERPROFILE ".codex"
if (-not (Test-Path $codex)) {
  throw "Codex directory not found: $codex"
}

$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$backup = Join-Path $codex "history_sync_backups\manual-backup-$stamp"
New-Item -ItemType Directory -Path $backup -Force | Out-Null

$items = @(
  "auth.json",
  "config.toml",
  "session_index.jsonl",
  "history.jsonl"
)

foreach ($item in $items) {
  $src = Join-Path $codex $item
  if (Test-Path $src) {
    Copy-Item -LiteralPath $src -Destination (Join-Path $backup $item) -Force
  }
}

$sessions = Join-Path $codex "sessions"
if (Test-Path $sessions) {
  Copy-Item -LiteralPath $sessions -Destination (Join-Path $backup "sessions") -Recurse -Force
}

Write-Host "Backup created: $backup"
Write-Host "Warning: auth.json may contain credentials. Keep this backup private."
