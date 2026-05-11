# 新设备导入旧会话，但继续使用新账号/新中转

适用于：

```text
新设备已经使用新 API key / 新中转。
你想导入旧设备或旧账号留下的 Codex 本地会话历史。
```

## 核心原则

- 不要覆盖新设备的 `auth.json`，除非明确要切回旧 key。
- 不要覆盖新设备的 `config.toml`，除非明确要切回旧中转。
- 旧会话主要迁移 `sessions/` 和 `session_index.jsonl`。
- 新设备已有会话时，先备份，再合并。

## 旧设备导出

Windows：

```powershell
$codex = "$env:USERPROFILE\.codex"
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$export = "$env:USERPROFILE\Desktop\codex-old-sessions-$stamp"

New-Item -ItemType Directory -Path $export -Force | Out-Null
Copy-Item "$codex\sessions" "$export\sessions" -Recurse -Force
Copy-Item "$codex\session_index.jsonl" "$export\session_index.jsonl" -Force
Copy-Item "$codex\archived_sessions" "$export\archived_sessions" -Recurse -Force -ErrorAction SilentlyContinue
Write-Host "Export created: $export"
```

macOS/Linux：

```bash
codex="$HOME/.codex"
stamp="$(date +%Y%m%d-%H%M%S)"
export="$HOME/Desktop/codex-old-sessions-$stamp"

mkdir -p "$export"
cp -R "$codex/sessions" "$export/sessions"
cp "$codex/session_index.jsonl" "$export/session_index.jsonl"
cp -R "$codex/archived_sessions" "$export/archived_sessions" 2>/dev/null || true
echo "Export created: $export"
```

## 新设备导入

Windows：

```powershell
$codex = "$env:USERPROFILE\.codex"
$old = "$env:USERPROFILE\Desktop\codex-old-sessions-YYYYMMDD-HHMMSS"
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$backup = "$codex\history_sync_backups\before-import-old-sessions-$stamp"

New-Item -ItemType Directory -Path $backup -Force | Out-Null
Copy-Item "$codex\auth.json" "$backup\auth.json" -Force -ErrorAction SilentlyContinue
Copy-Item "$codex\config.toml" "$backup\config.toml" -Force -ErrorAction SilentlyContinue
Copy-Item "$codex\session_index.jsonl" "$backup\session_index.jsonl" -Force -ErrorAction SilentlyContinue
Copy-Item "$codex\sessions" "$backup\sessions" -Recurse -Force -ErrorAction SilentlyContinue

New-Item -ItemType Directory -Path "$codex\sessions" -Force | Out-Null
Copy-Item "$old\sessions\*" "$codex\sessions" -Recurse -Force

if (Test-Path "$old\session_index.jsonl") {
  if (Test-Path "$codex\session_index.jsonl") {
    Get-Content "$old\session_index.jsonl" | Add-Content "$codex\session_index.jsonl"
  } else {
    Copy-Item "$old\session_index.jsonl" "$codex\session_index.jsonl" -Force
  }
}

codex resume
```

macOS/Linux：

```bash
codex="$HOME/.codex"
old="$HOME/Desktop/codex-old-sessions-YYYYMMDD-HHMMSS"
stamp="$(date +%Y%m%d-%H%M%S)"
backup="$codex/history_sync_backups/before-import-old-sessions-$stamp"

mkdir -p "$backup"
cp "$codex/auth.json" "$backup/auth.json" 2>/dev/null || true
cp "$codex/config.toml" "$backup/config.toml" 2>/dev/null || true
cp "$codex/session_index.jsonl" "$backup/session_index.jsonl" 2>/dev/null || true
cp -R "$codex/sessions" "$backup/sessions" 2>/dev/null || true

mkdir -p "$codex/sessions"
cp -R "$old/sessions/." "$codex/sessions/"

if [ -f "$old/session_index.jsonl" ]; then
  if [ -f "$codex/session_index.jsonl" ]; then
    cat "$old/session_index.jsonl" >> "$codex/session_index.jsonl"
  else
    cp "$old/session_index.jsonl" "$codex/session_index.jsonl"
  fi
fi

codex resume
```

## 给 AI 的提示词

```text
请帮我在新设备上导入旧 Codex 会话，但继续使用当前新账号/新中转。
不要覆盖 auth.json 和 config.toml。
先备份新设备 ~/.codex，再导入旧备份里的 sessions/ 和 session_index.jsonl。
最后运行 codex resume 验证。
不要打印任何 API key。
```
