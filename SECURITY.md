# Security Policy

This repository documents local Codex state management. It should never contain real credentials.

## Sensitive Files

Do not publish:

- `~/.codex/auth.json`
- API keys
- bearer tokens
- private relay URLs
- full local Codex backups
- logs containing request headers

## Before Publishing

Run a local scan:

```bash
grep -RInE "sk-|cr_|OPENAI_API_KEY|api[_-]?key|token|secret|Authorization" .
```

On Windows PowerShell:

```powershell
Get-ChildItem -Recurse -File |
  Select-String -Pattern 'sk-','cr_','OPENAI_API_KEY','api_key','token','secret','Authorization'
```

## Reporting

If you find a credential accidentally committed, revoke it immediately before opening a public issue.
