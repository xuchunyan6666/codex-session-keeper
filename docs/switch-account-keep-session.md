# 切换账号/中转并保留会话

## 关键关系

- `~/.codex/auth.json`：当前 API key。
- `~/.codex/config.toml`：当前 provider、中转 `base_url`、模型、`wire_api`。
- `~/.codex/sessions/`：本地会话正文。
- `~/.codex/session_index.jsonl`：本地会话索引。

会话历史通常不绑定 API key。切换 key 后，本地历史仍在；后续请求使用当前 `auth.json` 和 `config.toml` 中的新 key / 新中转。

## 切换前备份

Windows：

```powershell
$codex = "$env:USERPROFILE\.codex"
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$backup = "$codex\history_sync_backups\pre-key-switch-$stamp"

New-Item -ItemType Directory -Path $backup -Force | Out-Null
Copy-Item "$codex\auth.json" "$backup\auth.json" -Force
Copy-Item "$codex\config.toml" "$backup\config.toml" -Force
Copy-Item "$codex\session_index.jsonl" "$backup\session_index.jsonl" -Force
Copy-Item "$codex\sessions" "$backup\sessions" -Recurse -Force
Write-Host "Backup created: $backup"
```

macOS/Linux：

```bash
codex="$HOME/.codex"
stamp="$(date +%Y%m%d-%H%M%S)"
backup="$codex/history_sync_backups/pre-key-switch-$stamp"

mkdir -p "$backup"
cp "$codex/auth.json" "$backup/auth.json"
cp "$codex/config.toml" "$backup/config.toml"
cp "$codex/session_index.jsonl" "$backup/session_index.jsonl"
cp -R "$codex/sessions" "$backup/sessions"
echo "Backup created: $backup"
```

## 切换中转配置

编辑：

```bash
~/.codex/config.toml
```

模板：

```toml
model = "YOUR_MODEL"
model_provider = "YOUR_PROVIDER_NAME"

[model_providers.YOUR_PROVIDER_NAME]
name = "YOUR_PROVIDER_NAME"
base_url = "https://YOUR-RELAY.example.com/v1"
wire_api = "responses"
requires_openai_auth = true
```

## 安全输入新 API key

Windows：

```powershell
$sec = Read-Host "Paste new API key" -AsSecureString
$ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($sec)
try {
  [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr) | codex login --with-api-key
}
finally {
  [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr)
  Remove-Variable sec,ptr -ErrorAction SilentlyContinue
}
codex login status
```

macOS/Linux：

```bash
read -rsp "Paste new API key: " OPENAI_API_KEY
printf "\n"
printf "%s" "$OPENAI_API_KEY" | codex login --with-api-key
unset OPENAI_API_KEY
codex login status
```

## 继续旧会话

```bash
codex resume
```

或：

```bash
codex resume --last
```

如果直接继续失败：

```bash
codex fork
```
