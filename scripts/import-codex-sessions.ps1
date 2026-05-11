param(
  [Parameter(Mandatory = $true)]
  [string]$OldSessionsPath
)

$ErrorActionPreference = "Stop"

$codex = Join-Path $env:USERPROFILE ".codex"
New-Item -ItemType Directory -Path $codex -Force | Out-Null

if (-not (Test-Path $OldSessionsPath)) {
  throw "Old sessions path not found: $OldSessionsPath"
}

$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$backup = Join-Path $codex "history_sync_backups\before-import-old-sessions-$stamp"
New-Item -ItemType Directory -Path $backup -Force | Out-Null

$items = @("auth.json", "config.toml", "session_index.jsonl")
foreach ($item in $items) {
  $src = Join-Path $codex $item
  if (Test-Path $src) {
    Copy-Item -LiteralPath $src -Destination (Join-Path $backup $item) -Force
  }
}

$currentSessions = Join-Path $codex "sessions"
if (Test-Path $currentSessions) {
  Copy-Item -LiteralPath $currentSessions -Destination (Join-Path $backup "sessions") -Recurse -Force
}

$oldSessions = Join-Path $OldSessionsPath "sessions"
if (-not (Test-Path $oldSessions)) {
  throw "Missing sessions directory in old sessions package: $oldSessions"
}

New-Item -ItemType Directory -Path $currentSessions -Force | Out-Null
Copy-Item -Path (Join-Path $oldSessions "*") -Destination $currentSessions -Recurse -Force

$oldIndex = Join-Path $OldSessionsPath "session_index.jsonl"
$currentIndex = Join-Path $codex "session_index.jsonl"
if (Test-Path $oldIndex) {
  if (Test-Path $currentIndex) {
    Get-Content -LiteralPath $oldIndex | Add-Content -LiteralPath $currentIndex
  } else {
    Copy-Item -LiteralPath $oldIndex -Destination $currentIndex -Force
  }
}

Write-Host "Imported old sessions from: $OldSessionsPath"
Write-Host "Backup of previous local state: $backup"
Write-Host "Run: codex resume"
