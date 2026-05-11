from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from .cli import codex_paths, stamp


@dataclass(frozen=True)
class SessionRecord:
    id: str
    path: Path
    provider: str
    cwd: str
    timestamp: str
    updated_at: str
    thread_name: str


def read_jsonl_first(path: Path) -> dict[str, Any] | None:
    try:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            first = handle.readline()
    except OSError:
        return None
    first = first.lstrip("\ufeff")
    if not first.strip():
        return None
    try:
        return json.loads(first)
    except json.JSONDecodeError:
        return None


def write_jsonl_first(path: Path, first_obj: dict[str, Any]) -> None:
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)
    except OSError as exc:
        raise ValueError(f"Could not read session file: {path}") from exc
    if not lines:
        raise ValueError(f"Empty session file: {path}")
    lines[0] = json.dumps(first_obj, ensure_ascii=False, separators=(",", ":")) + "\n"
    path.write_text("".join(lines), encoding="utf-8")


def load_session_index(codex_home: Path) -> dict[str, dict[str, Any]]:
    index_path = codex_home / "session_index.jsonl"
    result: dict[str, dict[str, Any]] = {}
    if not index_path.exists():
        return result
    with index_path.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            session_id = str(row.get("id") or "")
            if session_id:
                result[session_id] = row
    return result


def scan_sessions(codex_home: Path | None = None) -> list[SessionRecord]:
    paths = codex_paths(codex_home)
    index = load_session_index(paths.home)
    records: list[SessionRecord] = []
    if not paths.sessions.exists():
        return records
    for file in paths.sessions.rglob("rollout-*.jsonl"):
        first = read_jsonl_first(file)
        if not first:
            continue
        payload = first.get("payload") if isinstance(first.get("payload"), dict) else {}
        if first.get("type") != "session_meta" or not isinstance(payload, dict):
            continue
        session_id = str(payload.get("id") or file.stem.replace("rollout-", ""))
        index_row = index.get(session_id, {})
        records.append(
            SessionRecord(
                id=session_id,
                path=file,
                provider=str(payload.get("model_provider") or "unknown"),
                cwd=str(payload.get("cwd") or ""),
                timestamp=str(payload.get("timestamp") or first.get("timestamp") or ""),
                updated_at=str(index_row.get("updated_at") or ""),
                thread_name=str(index_row.get("thread_name") or ""),
            )
        )
    return sorted(records, key=lambda r: r.updated_at or r.timestamp or str(r.path), reverse=True)


def provider_counts(records: list[SessionRecord]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for record in records:
        counts[record.provider] = counts.get(record.provider, 0) + 1
    return dict(sorted(counts.items(), key=lambda item: (-item[1], item[0])))


def backup_session_files(codex_home: Path | None, files: list[Path], reason: str) -> Path:
    paths = codex_paths(codex_home)
    backup = paths.backups / f"{reason}-{stamp()}"
    backup.mkdir(parents=True, exist_ok=True)
    for file in files:
        try:
            relative = file.resolve().relative_to(paths.home)
        except ValueError:
            relative = Path(file.name)
        target = backup / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(file, target)
    manifest = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "reason": reason,
        "file_count": len(files),
        "contains_auth_json": False,
    }
    (backup / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return backup


def migrate_provider(codex_home: Path | None, source_provider: str, target_provider: str, *, dry_run: bool = False) -> dict[str, Any]:
    records = [r for r in scan_sessions(codex_home) if r.provider == source_provider]
    files = [r.path for r in records]
    backup = None if dry_run or not files else backup_session_files(codex_home, files, f"before-provider-migrate-{source_provider}-to-{target_provider}")
    changed = 0
    for record in records:
        first = read_jsonl_first(record.path)
        if not first:
            continue
        payload = first.get("payload")
        if not isinstance(payload, dict):
            continue
        payload["model_provider"] = target_provider
        if not dry_run:
            write_jsonl_first(record.path, first)
        changed += 1
    return {
        "source_provider": source_provider,
        "target_provider": target_provider,
        "matched": len(records),
        "changed": changed,
        "backup": str(backup) if backup else None,
        "dry_run": dry_run,
    }


def export_provider_sessions(codex_home: Path | None, provider: str, output: Path, *, rewrite_provider: str | None = None) -> dict[str, Any]:
    paths = codex_paths(codex_home)
    records = [r for r in scan_sessions(codex_home) if provider == "*" or r.provider == provider]
    output.mkdir(parents=True, exist_ok=True)
    sessions_out = output / "sessions"
    sessions_out.mkdir(parents=True, exist_ok=True)
    for record in records:
        relative = record.path.resolve().relative_to(paths.sessions.resolve())
        target = sessions_out / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(record.path, target)
        if rewrite_provider:
            first = read_jsonl_first(target)
            if first and isinstance(first.get("payload"), dict):
                first["payload"]["model_provider"] = rewrite_provider
                write_jsonl_first(target, first)
    if paths.session_index.exists():
        shutil.copy2(paths.session_index, output / "session_index.jsonl")
    manifest = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "source_provider": provider,
        "target_provider": rewrite_provider or provider,
        "session_count": len(records),
        "contains_auth_json": False,
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def import_session_package(codex_home: Path | None, package: Path, *, target_provider: str | None = None, index_mode: str = "append") -> dict[str, Any]:
    paths = codex_paths(codex_home)
    sessions_in = package / "sessions"
    if not sessions_in.exists():
        raise ValueError(f"Missing sessions directory: {sessions_in}")
    incoming = list(sessions_in.rglob("rollout-*.jsonl"))
    backup = backup_session_files(codex_home, list(paths.sessions.rglob("rollout-*.jsonl")) if paths.sessions.exists() else [], "before-provider-import")
    for file in incoming:
        relative = file.resolve().relative_to(sessions_in.resolve())
        target = paths.sessions / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(file, target)
        if target_provider:
            first = read_jsonl_first(target)
            if first and isinstance(first.get("payload"), dict):
                first["payload"]["model_provider"] = target_provider
                write_jsonl_first(target, first)
    old_index = package / "session_index.jsonl"
    if old_index.exists() and index_mode != "skip":
        if index_mode == "replace" or not paths.session_index.exists():
            shutil.copy2(old_index, paths.session_index)
        else:
            with old_index.open("r", encoding="utf-8", errors="replace") as reader:
                with paths.session_index.open("a", encoding="utf-8") as writer:
                    for line in reader:
                        writer.write(line)
                        if not line.endswith("\n"):
                            writer.write("\n")
    return {
        "imported": len(incoming),
        "target_provider": target_provider,
        "backup": str(backup),
        "index_mode": index_mode,
    }
