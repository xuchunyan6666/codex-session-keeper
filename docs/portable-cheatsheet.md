# 跨设备速记版

## 关键词

```text
auth.json              当前 API key
config.toml            当前 provider / relay / model 配置
sessions/              本地会话正文
session_index.jsonl    本地会话索引
codex login --with-api-key
codex resume
codex fork
```

## 口诀

```text
先备份，再换配；再登录，再 resume。
key 看 auth，路由看 config，历史看 sessions。
```

## 最小备份清单

```text
auth.json
config.toml
session_index.jsonl
sessions/
```

## 新设备迁移旧会话

从旧设备带走：

```text
sessions/
session_index.jsonl
```

一般不要带走：

```text
auth.json
```

除非你明确要在新设备上使用旧 key。

## 给 AI 的提示词

```text
我想在 Codex 中切换 API key 和中转，但保留本地会话历史。
请先备份 ~/.codex/auth.json、config.toml、session_index.jsonl、sessions/。
API key 在 ~/.codex/auth.json，中转/provider 在 ~/.codex/config.toml。
会话历史在 ~/.codex/sessions 和 ~/.codex/session_index.jsonl，不要删除。
修改 config.toml 的 model_provider 和 model_providers.<name>.base_url。
用 codex login --with-api-key 安全输入新 key。
用 codex resume 或 codex fork 继续旧会话。
不要打印任何 API key。
```
