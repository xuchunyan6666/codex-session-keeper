$ErrorActionPreference = "Stop"

$codex = Join-Path $env:USERPROFILE ".codex"
if (-not (Test-Path $codex)) {
  throw "Codex directory not found: $codex"
}

$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$export = Join-Path ([Environment]::GetFolderPath("Desktop")) "codex-old-sessions-$stamp"
New-Item -ItemType Directory -Path $export -Force | Out-Null

$sessions = Join-Path $codex "sessions"
if (Test-Path $sessions) {
  Copy-Item -LiteralPath $sessions -Destination (Join-Path $export "sessions") -Recurse -Force
}

$index = Join-Path $codex "session_index.jsonl"
if (Test-Path $index) {
  Copy-Item -LiteralPath $index -Destination (Join-Path $export "session_index.jsonl") -Force
}

$archived = Join-Path $codex "archived_sessions"
if (Test-Path $archived) {
  Copy-Item -LiteralPath $archived -Destination (Join-Path $export "archived_sessions") -Recurse -Force
}

Write-Host "Session export created: $export"
Write-Host "This export intentionally excludes auth.json."
