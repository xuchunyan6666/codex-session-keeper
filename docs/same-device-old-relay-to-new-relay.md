# 同一台设备：老中转会话迁移到新中转继续使用

适用于：

```text
同一台电脑原来使用老中转。
后来这台电脑切换到了新 API key / 新中转。
现在想打开老中转时期的 Codex 会话，并让后续请求走新中转。
```

## 触发关键词

```text
Codex 老中转会话迁移到新中转
同一台电脑切中转后继续旧会话
旧 relay 会话用新 relay 继续
old relay session to new relay
codex resume old relay session with new relay
切换中转后恢复旧会话
让老中转会话走新中转
```

## 核心原则

```text
会话历史在本地。
老中转/新中转由当前 config.toml 和 auth.json 决定。
切到新中转后，resume 或 fork 旧会话，后续请求就会走当前新中转。
```

## 操作顺序

1. 备份当前 `.codex` 关键文件。
2. 确认当前已经是新中转 + 新 key。
3. 用 `codex resume` 选择老中转时期的旧会话。
4. 如果 `resume` 不能继续，用 `codex fork` 从旧会话开新分支。
5. 如果 `fork` 也不行，提取旧会话关键上下文，新开会话继续。

## Windows

备份：

```powershell
$codex = "$env:USERPROFILE\.codex"
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$backup = "$codex\history_sync_backups\before-old-relay-session-on-new-relay-$stamp"

New-Item -ItemType Directory -Path $backup -Force | Out-Null
Copy-Item "$codex\auth.json" "$backup\auth.json" -Force -ErrorAction SilentlyContinue
Copy-Item "$codex\config.toml" "$backup\config.toml" -Force -ErrorAction SilentlyContinue
Copy-Item "$codex\session_index.jsonl" "$backup\session_index.jsonl" -Force -ErrorAction SilentlyContinue
Copy-Item "$codex\sessions" "$backup\sessions" -Recurse -Force -ErrorAction SilentlyContinue
Write-Host "Backup created: $backup"
```

确认当前中转：

```powershell
codex login status
notepad "$env:USERPROFILE\.codex\config.toml"
```

恢复旧会话：

```powershell
codex resume
```

如果想从旧会话复制上下文开新分支：

```powershell
codex fork
```

## macOS/Linux

备份：

```bash
codex="$HOME/.codex"
stamp="$(date +%Y%m%d-%H%M%S)"
backup="$codex/history_sync_backups/before-old-relay-session-on-new-relay-$stamp"

mkdir -p "$backup"
cp "$codex/auth.json" "$backup/auth.json" 2>/dev/null || true
cp "$codex/config.toml" "$backup/config.toml" 2>/dev/null || true
cp "$codex/session_index.jsonl" "$backup/session_index.jsonl" 2>/dev/null || true
cp -R "$codex/sessions" "$backup/sessions" 2>/dev/null || true
echo "Backup created: $backup"
```

恢复或 fork：

```bash
codex resume
codex fork
```

## 给 AI 的固定指令

```text
我要在同一台设备上，把老中转时期的 Codex 会话迁移到当前新中转继续使用。

请按以下规则操作：
1. 不要删除 ~/.codex/sessions 和 ~/.codex/session_index.jsonl。
2. 先备份 ~/.codex/auth.json、config.toml、session_index.jsonl、sessions/。
3. 确认当前 auth.json 和 config.toml 已经是新 key / 新中转。
4. 用 codex resume 选择老中转时期的会话测试。
5. 如果 resume 继续失败，用 codex fork 从旧会话创建新分支。
6. 如果 fork 也失败，提取旧会话关键上下文，开启新会话继续。
7. 不要打印、记录或提交任何 API key。
```

## 常见问题

`401 / Unauthorized`：当前 key 不属于当前新中转，或 `auth.json` 还是旧 key。

`404`：新中转 `base_url` 或 `wire_api` 不匹配。

`model not found`：旧会话记录的模型名，新中转不支持。改 `config.toml` 的 `model`，或启动时指定 `codex -m YOUR_MODEL`。

`resume` 能打开但不能继续：可能旧会话依赖老中转或老账号上的服务端 response chain。优先尝试 `codex fork`。
