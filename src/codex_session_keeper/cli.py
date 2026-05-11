from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable


SENSITIVE_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9_\-]{12,}"),
    re.compile(r"cr_[A-Za-z0-9_\-]{12,}"),
    re.compile(r"OPENAI_API_KEY\s*[:=]"),
    re.compile(r"Authorization\s*[:=]", re.IGNORECASE),
]


@dataclass(frozen=True)
class CodexPaths:
    home: Path
    auth: Path
    config: Path
    sessions: Path
    session_index: Path
    archived_sessions: Path
    backups: Path


def default_codex_home() -> Path:
    override = os.environ.get("CODEX_HOME")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".codex"


def codex_paths(home: Path | None = None) -> CodexPaths:
    root = (home or default_codex_home()).expanduser().resolve()
    return CodexPaths(
        home=root,
        auth=root / "auth.json",
        config=root / "config.toml",
        sessions=root / "sessions",
        session_index=root / "session_index.jsonl",
        archived_sessions=root / "archived_sessions",
        backups=root / "history_sync_backups",
    )


def stamp() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def copy_file(src: Path, dst: Path, *, dry_run: bool = False) -> bool:
    if not src.exists():
        return False
    if dry_run:
        print(f"would copy file: {src} -> {dst}")
        return True
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    return True


def copy_dir_contents(src: Path, dst: Path, *, dry_run: bool = False) -> bool:
    if not src.exists():
        return False
    if not src.is_dir():
        raise SystemExit(f"Expected directory: {src}")
    if dry_run:
        print(f"would merge directory: {src} -> {dst}")
        return True
    dst.mkdir(parents=True, exist_ok=True)
    for child in src.iterdir():
        target = dst / child.name
        if child.is_dir():
            shutil.copytree(child, target, dirs_exist_ok=True)
        else:
            shutil.copy2(child, target)
    return True


def copy_dir(src: Path, dst: Path, *, dry_run: bool = False) -> bool:
    if not src.exists():
        return False
    if not src.is_dir():
        raise SystemExit(f"Expected directory: {src}")
    if dry_run:
        print(f"would copy directory: {src} -> {dst}")
        return True
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)
    return True


def append_file(src: Path, dst: Path, *, dry_run: bool = False) -> bool:
    if not src.exists():
        return False
    if dry_run:
        print(f"would append file: {src} -> {dst}")
        return True
    dst.parent.mkdir(parents=True, exist_ok=True)
    with src.open("r", encoding="utf-8", errors="replace") as reader:
        with dst.open("a", encoding="utf-8") as writer:
            for line in reader:
                writer.write(line)
                if not line.endswith("\n"):
                    writer.write("\n")
    return True


def parse_simple_toml_values(config: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not config.exists():
        return values
    current_section = ""
    for raw in config.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            current_section = line.strip("[]")
            continue
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        qualified = f"{current_section}.{key}" if current_section else key
        values[qualified] = value
    provider = values.get("model_provider")
    if provider:
        prefix = f"model_providers.{provider}."
        for key, value in list(values.items()):
            if key.startswith(prefix):
                values[key.removeprefix(prefix)] = value
    return values


def count_session_files(root: Path) -> int:
    if not root.exists():
        return 0
    return sum(1 for _ in root.rglob("rollout-*.jsonl"))


def latest_session(root: Path) -> Path | None:
    if not root.exists():
        return None
    files = list(root.rglob("rollout-*.jsonl"))
    if not files:
        return None
    return max(files, key=lambda p: p.stat().st_mtime)


def run_cmd(command: list[str], *, dry_run: bool = False) -> int:
    if dry_run:
        print("would run:", " ".join(command))
        return 0
    return subprocess.call(command)


def command_status(args: argparse.Namespace) -> int:
    paths = codex_paths(args.codex_home)
    config = parse_simple_toml_values(paths.config)

    print(f"Codex home: {paths.home}")
    print(f"auth.json: {'present' if paths.auth.exists() else 'missing'}")
    print(f"config.toml: {'present' if paths.config.exists() else 'missing'}")
    print(f"sessions: {count_session_files(paths.sessions)} rollout files")
    print(f"session_index.jsonl: {'present' if paths.session_index.exists() else 'missing'}")

    model = config.get("model", "unknown")
    provider = config.get("model_provider", "unknown")
    base_url = config.get("base_url", "unknown")
    wire_api = config.get("wire_api", "unknown")
    print(f"model: {model}")
    print(f"provider: {provider}")
    print(f"base_url: {base_url}")
    print(f"wire_api: {wire_api}")

    latest = latest_session(paths.sessions)
    if latest:
        print(f"latest session: {latest}")

    if args.check_login:
        print()
        print("codex login status:")
        return run_cmd(["codex", "login", "status"], dry_run=args.dry_run)
    return 0


def command_backup(args: argparse.Namespace) -> int:
    paths = codex_paths(args.codex_home)
    backup_dir = Path(args.output).expanduser().resolve() if args.output else paths.backups / f"manual-backup-{stamp()}"

    if not paths.home.exists():
        raise SystemExit(f"Codex home not found: {paths.home}")

    print(f"Creating backup: {backup_dir}")
    if not args.dry_run:
        backup_dir.mkdir(parents=True, exist_ok=True)

    copied: list[str] = []
    for src in [paths.auth, paths.config, paths.session_index, paths.home / "history.jsonl"]:
        if copy_file(src, backup_dir / src.name, dry_run=args.dry_run):
            copied.append(src.name)

    if args.include_sessions:
        if copy_dir(paths.sessions, backup_dir / "sessions", dry_run=args.dry_run):
            copied.append("sessions/")

    if args.include_archived:
        if copy_dir(paths.archived_sessions, backup_dir / "archived_sessions", dry_run=args.dry_run):
            copied.append("archived_sessions/")

    manifest = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "codex_home": str(paths.home),
        "contains_auth_json": paths.auth.exists(),
        "copied": copied,
        "warning": "auth.json may contain credentials. Keep this backup private.",
    }
    if not args.dry_run:
        (backup_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    print("Copied:", ", ".join(copied) if copied else "nothing")
    print("Warning: auth.json may contain credentials. Keep this backup private.")
    return 0


def command_export_sessions(args: argparse.Namespace) -> int:
    paths = codex_paths(args.codex_home)
    output = Path(args.output).expanduser().resolve() if args.output else Path.home() / "Desktop" / f"codex-old-sessions-{stamp()}"

    if not paths.sessions.exists():
        raise SystemExit(f"No sessions directory found: {paths.sessions}")

    print(f"Exporting sessions: {output}")
    if not args.dry_run:
        output.mkdir(parents=True, exist_ok=True)

    copied: list[str] = []
    if copy_dir(paths.sessions, output / "sessions", dry_run=args.dry_run):
        copied.append("sessions/")
    if copy_file(paths.session_index, output / "session_index.jsonl", dry_run=args.dry_run):
        copied.append("session_index.jsonl")
    if args.include_archived and copy_dir(paths.archived_sessions, output / "archived_sessions", dry_run=args.dry_run):
        copied.append("archived_sessions/")

    if not args.dry_run:
        manifest = {
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "source_codex_home": str(paths.home),
            "contains_auth_json": False,
            "session_count": count_session_files(paths.sessions),
        }
        (output / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    print("Copied:", ", ".join(copied))
    print("This export intentionally excludes auth.json.")
    return 0


def command_import_sessions(args: argparse.Namespace) -> int:
    paths = codex_paths(args.codex_home)
    old = Path(args.old_sessions_path).expanduser().resolve()
    old_sessions = old / "sessions"
    old_index = old / "session_index.jsonl"

    if not old.exists():
        raise SystemExit(f"Old sessions package not found: {old}")
    if not old_sessions.exists():
        raise SystemExit(f"Missing sessions directory in package: {old_sessions}")

    backup_dir = paths.backups / f"before-import-old-sessions-{stamp()}"
    print(f"Backing up current local state: {backup_dir}")
    if not args.dry_run:
        backup_dir.mkdir(parents=True, exist_ok=True)

    for src in [paths.auth, paths.config, paths.session_index]:
        copy_file(src, backup_dir / src.name, dry_run=args.dry_run)
    copy_dir(paths.sessions, backup_dir / "sessions", dry_run=args.dry_run)

    print(f"Importing sessions from: {old}")
    copy_dir_contents(old_sessions, paths.sessions, dry_run=args.dry_run)

    if args.index_mode == "append":
        append_file(old_index, paths.session_index, dry_run=args.dry_run)
    elif args.index_mode == "replace":
        copy_file(old_index, paths.session_index, dry_run=args.dry_run)
    elif args.index_mode == "skip":
        print("Skipping session_index.jsonl import")
    else:
        raise SystemExit(f"Unknown index mode: {args.index_mode}")

    if args.include_archived:
        copy_dir_contents(old / "archived_sessions", paths.archived_sessions, dry_run=args.dry_run)

    print("Done. Next: run `codex resume`.")
    return 0


def scan_file(path: Path) -> list[str]:
    hits: list[str] = []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return hits
    for pattern in SENSITIVE_PATTERNS:
        if pattern.search(text):
            hits.append(pattern.pattern)
    return hits


def command_doctor(args: argparse.Namespace) -> int:
    paths = codex_paths(args.codex_home)
    issues: list[str] = []

    if not paths.home.exists():
        issues.append(f"Codex home missing: {paths.home}")
    if not paths.config.exists():
        issues.append("config.toml missing")
    if not paths.auth.exists():
        issues.append("auth.json missing")
    if not paths.sessions.exists():
        issues.append("sessions/ missing")
    if not paths.session_index.exists():
        issues.append("session_index.jsonl missing")

    config = parse_simple_toml_values(paths.config)
    if paths.config.exists():
        if not config.get("model_provider"):
            issues.append("config.toml has no model_provider")
        if not config.get("base_url"):
            issues.append("current provider has no visible base_url")

    print("Codex Session Keeper doctor")
    print(f"Codex home: {paths.home}")
    print(f"Session count: {count_session_files(paths.sessions)}")
    print()

    if issues:
        print("Issues:")
        for issue in issues:
            print(f"- {issue}")
    else:
        print("No obvious structural issues found.")

    print()
    print("Suggested next steps:")
    print("- Before switching key/relay: csk backup --include-sessions")
    print("- To continue old relay sessions on new relay: codex resume, then codex fork if needed")
    print("- To export sessions only: csk export-sessions")
    print("- To import sessions without replacing auth/config: csk import-sessions PATH")

    if args.scan:
        print()
        print("Sensitive pattern scan:")
        files = list(iter_files(paths.home, max_files=args.max_scan_files))
        found = False
        for file in files:
            if file.name.lower().startswith("auth"):
                continue
            hits = scan_file(file)
            if hits:
                found = True
                print(f"- {file}: {', '.join(hits)}")
        if not found:
            print("No sensitive patterns found outside auth* files in scanned files.")

    return 1 if issues and args.strict else 0


def iter_files(root: Path, *, max_files: int) -> Iterable[Path]:
    count = 0
    if not root.exists():
        return
    for path in root.rglob("*"):
        if count >= max_files:
            break
        if path.is_file():
            count += 1
            yield path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="codex-session-keeper",
        description="Keep and resume Codex sessions across API key, relay, and device switches.",
    )
    parser.add_argument("--codex-home", type=Path, help="Codex home directory, defaults to CODEX_HOME or ~/.codex")
    parser.add_argument("--dry-run", action="store_true", help="Print planned actions without writing files")

    sub = parser.add_subparsers(dest="command", required=True)

    status = sub.add_parser("status", help="Show Codex auth/config/session summary without printing secrets")
    status.add_argument("--check-login", action="store_true", help="Also run `codex login status`")
    status.set_defaults(func=command_status)

    backup = sub.add_parser("backup", help="Back up Codex auth/config/session index and optionally sessions")
    backup.add_argument("-o", "--output", help="Backup output directory")
    backup.add_argument("--include-sessions", action="store_true", default=True, help="Include sessions/ backup")
    backup.add_argument("--no-sessions", action="store_false", dest="include_sessions", help="Do not back up sessions/")
    backup.add_argument("--include-archived", action="store_true", help="Include archived_sessions/")
    backup.set_defaults(func=command_backup)

    export = sub.add_parser("export-sessions", help="Export sessions without auth.json")
    export.add_argument("-o", "--output", help="Export output directory")
    export.add_argument("--include-archived", action="store_true", help="Include archived_sessions/")
    export.set_defaults(func=command_export_sessions)

    import_cmd = sub.add_parser("import-sessions", help="Import a sessions export without replacing auth/config")
    import_cmd.add_argument("old_sessions_path", help="Path produced by export-sessions")
    import_cmd.add_argument(
        "--index-mode",
        choices=["append", "replace", "skip"],
        default="append",
        help="How to handle session_index.jsonl",
    )
    import_cmd.add_argument("--include-archived", action="store_true", help="Also import archived_sessions/")
    import_cmd.set_defaults(func=command_import_sessions)

    doctor = sub.add_parser("doctor", help="Check structure and print safe next-step suggestions")
    doctor.add_argument("--strict", action="store_true", help="Exit non-zero if issues are found")
    doctor.add_argument("--scan", action="store_true", help="Scan for sensitive-looking patterns outside auth* files")
    doctor.add_argument("--max-scan-files", type=int, default=5000, help="Maximum files to scan")
    doctor.set_defaults(func=command_doctor)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)
