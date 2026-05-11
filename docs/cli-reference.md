# CLI Reference

`codex-session-keeper` provides a small zero-runtime-dependency Python CLI.

Short alias:

```bash
csk
```

Global options must come before the command:

```bash
csk --codex-home /path/to/.codex status
csk --dry-run backup
```

## status

Show Codex state without printing API keys.

```bash
csk status
csk status --check-login
```

Shows:

- Codex home
- whether `auth.json` exists
- provider / model / base URL from `config.toml`
- session count
- latest session file

## backup

Back up current Codex state before switching key or relay.

```bash
csk backup
csk backup --no-sessions
csk backup --include-archived
csk backup --output /path/to/backup
```

By default, this includes:

- `auth.json`
- `config.toml`
- `session_index.jsonl`
- `history.jsonl` if present
- `sessions/`

Warning: backups may contain `auth.json`, so keep them private.

## export-sessions

Export sessions without `auth.json`.

```bash
csk export-sessions
csk export-sessions --output /path/to/codex-old-sessions
csk export-sessions --include-archived
```

Use this when moving old sessions to another device while keeping the new device's current key and relay.

## import-sessions

Import a session export without replacing current `auth.json` or `config.toml`.

```bash
csk import-sessions /path/to/codex-old-sessions
csk import-sessions /path/to/codex-old-sessions --index-mode append
csk import-sessions /path/to/codex-old-sessions --index-mode replace
csk import-sessions /path/to/codex-old-sessions --index-mode skip
```

Default behavior:

- backs up current `auth.json`, `config.toml`, `session_index.jsonl`, and `sessions/`
- merges old `sessions/` into current `sessions/`
- appends old `session_index.jsonl` to current `session_index.jsonl`
- never replaces current auth/config

## doctor

Check for missing Codex state files and print safe next-step suggestions.

```bash
csk doctor
csk doctor --strict
csk doctor --scan
```

`--scan` looks for sensitive-looking patterns outside `auth*` files.
