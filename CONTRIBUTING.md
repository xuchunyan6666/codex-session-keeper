# Contributing

欢迎提交更多 Codex 会话迁移、账号切换、中转兼容相关经验。

## 请不要提交敏感信息

提交前请检查：

```bash
grep -RInE "sk-|cr_|OPENAI_API_KEY|api[_-]?key|token|secret" .
```

不要提交：

- 真实 `auth.json`
- 真实 API key
- 私有中转地址
- 带个人用户名的本机绝对路径
- 完整 `~/.codex` 目录

## 推荐贡献内容

- 不同系统上的迁移命令
- 常见错误和修复方式
- 不同中转 provider 的通用配置注意点
- 更安全的备份/恢复脚本
- CLI 命令、测试和打包改进
- 英文版或其他语言翻译

## 本地测试

```bash
python -m pytest
python -m codex_session_keeper status --codex-home /path/to/test/.codex
```

## 写作风格

- 用占位符，例如 `YOUR_PROVIDER_NAME`、`https://YOUR-RELAY.example.com/v1`。
- 先解释风险，再给命令。
- 命令默认先备份，再修改。
- 不假设用户一定使用某个特定 relay。
