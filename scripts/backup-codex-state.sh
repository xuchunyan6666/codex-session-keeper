#!/usr/bin/env bash
set -euo pipefail

codex="${HOME}/.codex"
if [ ! -d "$codex" ]; then
  echo "Codex directory not found: $codex" >&2
  exit 1
fi

stamp="$(date +%Y%m%d-%H%M%S)"
backup="$codex/history_sync_backups/manual-backup-$stamp"
mkdir -p "$backup"

for item in auth.json config.toml session_index.jsonl history.jsonl; do
  if [ -e "$codex/$item" ]; then
    cp "$codex/$item" "$backup/$item"
  fi
done

if [ -d "$codex/sessions" ]; then
  cp -R "$codex/sessions" "$backup/sessions"
fi

echo "Backup created: $backup"
echo "Warning: auth.json may contain credentials. Keep this backup private."
