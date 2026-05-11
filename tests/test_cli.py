from __future__ import annotations

import json
from pathlib import Path

from codex_session_keeper.cli import main


def make_codex_home(root: Path) -> Path:
    codex = root / ".codex"
    session_dir = codex / "sessions" / "2026" / "05" / "11"
    session_dir.mkdir(parents=True)
    (codex / "auth.json").write_text('{"OPENAI_API_KEY":"test-secret"}', encoding="utf-8")
    (codex / "config.toml").write_text(
        '\n'.join(
            [
                'model = "gpt-test"',
                'model_provider = "relay"',
                "",
                "[model_providers.relay]",
                'base_url = "https://relay.example.com/v1"',
                'wire_api = "responses"',
            ]
        ),
        encoding="utf-8",
    )
    (codex / "session_index.jsonl").write_text('{"id":"current"}\n', encoding="utf-8")
    (session_dir / "rollout-2026-05-11T00-00-00-current.jsonl").write_text("current\n", encoding="utf-8")
    return codex


def test_backup_creates_manifest(tmp_path: Path) -> None:
    codex = make_codex_home(tmp_path)
    output = tmp_path / "backup"

    assert main(["--codex-home", str(codex), "backup", "--output", str(output)]) == 0

    assert (output / "auth.json").exists()
    assert (output / "config.toml").exists()
    assert (output / "session_index.jsonl").exists()
    assert (output / "sessions").exists()
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["contains_auth_json"] is True


def test_export_sessions_excludes_auth(tmp_path: Path) -> None:
    codex = make_codex_home(tmp_path)
    output = tmp_path / "export"

    assert main(["--codex-home", str(codex), "export-sessions", "--output", str(output)]) == 0

    assert (output / "sessions").exists()
    assert (output / "session_index.jsonl").exists()
    assert not (output / "auth.json").exists()


def test_import_sessions_keeps_auth_and_config(tmp_path: Path) -> None:
    codex = make_codex_home(tmp_path / "new")
    old = tmp_path / "old-export"
    old_session_dir = old / "sessions" / "2026" / "05" / "10"
    old_session_dir.mkdir(parents=True)
    (old_session_dir / "rollout-2026-05-10T00-00-00-old.jsonl").write_text("old\n", encoding="utf-8")
    (old / "session_index.jsonl").write_text('{"id":"old"}\n', encoding="utf-8")

    before_auth = (codex / "auth.json").read_text(encoding="utf-8")
    before_config = (codex / "config.toml").read_text(encoding="utf-8")

    assert main(["--codex-home", str(codex), "import-sessions", str(old)]) == 0

    assert (codex / "auth.json").read_text(encoding="utf-8") == before_auth
    assert (codex / "config.toml").read_text(encoding="utf-8") == before_config
    assert (codex / "sessions" / "2026" / "05" / "10" / "rollout-2026-05-10T00-00-00-old.jsonl").exists()
    index = (codex / "session_index.jsonl").read_text(encoding="utf-8")
    assert '{"id":"current"}' in index
    assert '{"id":"old"}' in index


def test_status_does_not_print_auth_secret(tmp_path: Path, capsys) -> None:
    codex = make_codex_home(tmp_path)

    assert main(["--codex-home", str(codex), "status"]) == 0
    output = capsys.readouterr().out

    assert "test-secret" not in output
    assert "https://relay.example.com/v1" in output
