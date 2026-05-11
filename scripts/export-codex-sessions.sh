#!/usr/bin/env bash
set -euo pipefail

codex="${HOME}/.codex"
if [ ! -d "$codex" ]; then
  echo "Codex directory not found: $codex" >&2
  exit 1
fi

stamp="$(date +%Y%m%d-%H%M%S)"
desktop="${HOME}/Desktop"
export_dir="$desktop/codex-old-sessions-$stamp"
mkdir -p "$export_dir"

if [ -d "$codex/sessions" ]; then
  cp -R "$codex/sessions" "$export_dir/sessions"
fi

if [ -f "$codex/session_index.jsonl" ]; then
  cp "$codex/session_index.jsonl" "$export_dir/session_index.jsonl"
fi

if [ -d "$codex/archived_sessions" ]; then
  cp -R "$codex/archived_sessions" "$export_dir/archived_sessions"
fi

echo "Session export created: $export_dir"
echo "This export intentionally excludes auth.json."
