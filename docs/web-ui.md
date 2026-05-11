# Web UI

`csk-web` starts a local tool page for managing provider snapshots and session packages.

```bash
csk-web
```

Default URL:

```text
http://127.0.0.1:8765
```

## Workflow

1. Open the page and check the current Codex provider.
2. Save the current provider snapshot, for example `old-relay`.
3. Export the current sessions with a source label.
4. Activate a target provider snapshot, for example `new-relay`.
5. Import the session package into the current or selected target provider.
6. Run `codex resume` or `codex fork`.

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
- Session files are not transformed; they are copied into the current Codex home.
