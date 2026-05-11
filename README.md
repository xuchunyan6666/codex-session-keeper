# Codex Session Keeper

一份关于 **Codex CLI / Codex Desktop 切换 API key、中转 provider，并继续使用本地历史会话** 的实战指南和小工具。

The guide explains how to switch API keys or relay providers in Codex while preserving local session history.

## 适用场景

- 你从老中转切到新中转，但想继续打开老中转时期的会话。
- 你换了 API key，但希望 `codex resume` 仍能看到历史会话。
- 你在新设备上迁移旧设备的 Codex 会话历史。
- 你想把账号凭据和会话历史分开备份，避免误删。

## 一句话原则

```text
key 看 auth，路由看 config，历史看 sessions。
先备份，再换配；再登录，再 resume。
```

Codex 的本地状态通常分成几类：

| 文件/目录 | 用途 |
| --- | --- |
| `~/.codex/auth.json` | 当前 API key 登录凭据 |
| `~/.codex/config.toml` | 当前模型、provider、中转 `base_url`、`wire_api` 等配置 |
| `~/.codex/sessions/` | 本地会话正文，通常是 `rollout-*.jsonl` |
| `~/.codex/session_index.jsonl` | 本地会话索引，影响 `codex resume` 列表 |

切换 key 或中转后，本地会话文件通常仍然可用。后续请求走哪个 key / relay，取决于当前的 `auth.json` 和 `config.toml`。

## CLI 工具

安装本地开发版：

```bash
pip install -e .
```

查看当前 Codex 状态，不打印密钥：

```bash
csk status
```

切换 key / 中转前备份：

```bash
csk backup
```

只导出会话，不带 `auth.json`：

```bash
csk export-sessions
```

在新设备导入旧会话，保留当前新设备的 `auth.json` 和 `config.toml`：

```bash
csk import-sessions /path/to/codex-old-sessions-YYYYMMDD-HHMMSS
```

检查结构并给出下一步建议：

```bash
csk doctor
```

也可以不安装，直接运行：

```bash
python -m codex_session_keeper status
```

## 文档入口

- [同一台设备：老中转会话迁移到新中转继续使用](docs/same-device-old-relay-to-new-relay.md)
- [切换账号/中转并保留会话](docs/switch-account-keep-session.md)
- [跨设备速记版](docs/portable-cheatsheet.md)
- [新设备导入旧会话，但继续使用新账号/新中转](docs/new-device-use-old-sessions.md)
- [CLI Reference](docs/cli-reference.md)

## 可直接使用的触发词

把下面这段发给 AI 助手即可：

```text
请帮我在同一台设备上，让老中转时期的 Codex 会话用当前新中转继续运行。
先备份 ~/.codex 的 auth.json、config.toml、session_index.jsonl、sessions/；
不要删除会话历史；
确认当前 config/auth 是新中转；
优先用 codex resume 选择旧会话，失败则用 codex fork 创建新分支；
不要打印任何 API key。
```

## Shell 脚本

Windows PowerShell：

```powershell
.\scripts\backup-codex-state.ps1
.\scripts\export-codex-sessions.ps1
.\scripts\import-codex-sessions.ps1 -OldSessionsPath "C:\path\to\codex-old-sessions-YYYYMMDD-HHMMSS"
```

macOS/Linux：

```bash
bash scripts/backup-codex-state.sh
bash scripts/export-codex-sessions.sh
bash scripts/import-codex-sessions.sh "$HOME/Desktop/codex-old-sessions-YYYYMMDD-HHMMSS"
```

## 安全提醒

- `auth.json` 可能包含真实 API key，不要公开上传。
- 发布 issue、日志、截图前，先搜索并清理 `sk-`、`cr_`、`OPENAI_API_KEY` 等敏感片段。
- 不建议把个人 `~/.codex` 目录整体打包发给别人。

## 失败时先看

| 现象 | 常见原因 |
| --- | --- |
| `401 / Unauthorized` | key 不对，或 key 不属于当前中转 |
| `404` | `base_url` 路径或 `wire_api` 不匹配 |
| `model not found` | 新中转不支持旧会话里的模型名 |
| `resume` 找不到旧会话 | `sessions/` 或 `session_index.jsonl` 未迁移 |
| 旧会话能打开但不能继续 | 可能依赖旧服务端 response chain，尝试 `codex fork` |

## License

MIT
