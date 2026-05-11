# Web UI

`csk-web` starts a local tool page for managing Codex session provider bindings and portable session packages.

```bash
csk-web
```

Default URL:

```text
http://127.0.0.1:8765
```

## Workflow

1. Open the page and scan local sessions grouped by `model_provider`.
2. Save current provider config/auth snapshots if you want one-click switching later.
3. Rebind all sessions from one provider to another, with a preview first.
4. Export sessions for one provider or all providers.
5. Optionally rewrite the provider while exporting, so the package is ready for another device.
6. Import a package on another device and bind imported sessions to the current provider.
7. Run `codex resume` or `codex fork`.

## What Provider Snapshots Contain

Provider snapshots are stored under:

```text
~/.codex/session_keeper_profiles
```

They contain copies of:

```text
config.toml
auth.json
```

Because `auth.json` may contain credentials, keep this directory private.

## Provider Binding

The UI reads each session file's first `session_meta` JSON line and uses:

```text
payload.model_provider
```

When you rebind sessions, only that provider field is changed. Matching session files are backed up first under:

```text
~/.codex/history_sync_backups
```

## What Session Packages Contain

Session exports are stored under:

```text
~/.codex/session_keeper_exports
```

They contain:

```text
sessions/
session_index.jsonl
manifest.json
```

They intentionally do not contain `auth.json`.

## Safety Model

- The server binds to `127.0.0.1` by default.
- The UI does not display API keys.
- Activating a provider snapshot backs up current auth/config/session state first.
- Importing sessions backs up current state first.
- Rebinding sessions backs up matching session files first.
- Export/import can rewrite `payload.model_provider` when requested.
