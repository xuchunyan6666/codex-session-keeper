#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -ne 1 ]; then
  echo "Usage: $0 /path/to/codex-old-sessions-YYYYMMDD-HHMMSS" >&2
  exit 1
fi

old="$1"
codex="${HOME}/.codex"
mkdir -p "$codex"

if [ ! -d "$old" ]; then
  echo "Old sessions path not found: $old" >&2
  exit 1
fi

stamp="$(date +%Y%m%d-%H%M%S)"
backup="$codex/history_sync_backups/before-import-old-sessions-$stamp"
mkdir -p "$backup"

for item in auth.json config.toml session_index.jsonl; do
  if [ -e "$codex/$item" ]; then
    cp "$codex/$item" "$backup/$item"
  fi
done

if [ -d "$codex/sessions" ]; then
  cp -R "$codex/sessions" "$backup/sessions"
fi

if [ ! -d "$old/sessions" ]; then
  echo "Missing sessions directory in old sessions package: $old/sessions" >&2
  exit 1
fi

mkdir -p "$codex/sessions"
cp -R "$old/sessions/." "$codex/sessions/"

if [ -f "$old/session_index.jsonl" ]; then
  if [ -f "$codex/session_index.jsonl" ]; then
    cat "$old/session_index.jsonl" >> "$codex/session_index.jsonl"
  else
    cp "$old/session_index.jsonl" "$codex/session_index.jsonl"
  fi
fi

echo "Imported old sessions from: $old"
echo "Backup of previous local state: $backup"
echo "Run: codex resume"
