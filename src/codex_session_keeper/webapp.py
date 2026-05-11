from __future__ import annotations

import argparse
import json
import os
import shutil
import threading
import webbrowser
from dataclasses import asdict, dataclass
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from .cli import codex_paths, count_session_files, latest_session, parse_simple_toml_values, stamp


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


@dataclass(frozen=True)
class ProviderProfile:
    name: str
    model: str
    base_url: str
    wire_api: str
    config_path: str
    auth_path: str
    current: bool
    session_count: int
    latest_session: str | None


class KeeperState:
    def __init__(self, codex_home: Path | None = None) -> None:
        self.paths = codex_paths(codex_home)
        self.profile_dir = self.paths.home / "session_keeper_profiles"
        self.export_dir = self.paths.home / "session_keeper_exports"
        self.lock = threading.Lock()

    def current_profile(self) -> ProviderProfile:
        config = parse_simple_toml_values(self.paths.config)
        return ProviderProfile(
            name=config.get("model_provider", "current"),
            model=config.get("model", "unknown"),
            base_url=config.get("base_url", "unknown"),
            wire_api=config.get("wire_api", "unknown"),
            config_path=str(self.paths.config),
            auth_path=str(self.paths.auth),
            current=True,
            session_count=count_session_files(self.paths.sessions),
            latest_session=str(latest_session(self.paths.sessions)) if latest_session(self.paths.sessions) else None,
        )

    def profiles(self) -> list[ProviderProfile]:
        current = self.current_profile()
        result = [current]
        if not self.profile_dir.exists():
            return result
        for path in sorted(self.profile_dir.glob("*.json")):
            try:
                data = json.loads(read_text(path))
            except json.JSONDecodeError:
                continue
            result.append(
                ProviderProfile(
                    name=str(data.get("name") or path.stem),
                    model=str(data.get("model") or "unknown"),
                    base_url=str(data.get("base_url") or "unknown"),
                    wire_api=str(data.get("wire_api") or "unknown"),
                    config_path=str(data.get("config_path") or ""),
                    auth_path=str(data.get("auth_path") or ""),
                    current=False,
                    session_count=count_session_files(self.paths.sessions),
                    latest_session=str(latest_session(self.paths.sessions)) if latest_session(self.paths.sessions) else None,
                )
            )
        return result

    def save_current_profile(self, name: str) -> Path:
        safe = safe_name(name)
        profile_path = self.profile_dir / f"{safe}.json"
        snapshot_dir = self.profile_dir / safe
        snapshot_dir.mkdir(parents=True, exist_ok=True)
        config_copy = snapshot_dir / "config.toml"
        auth_copy = snapshot_dir / "auth.json"
        if self.paths.config.exists():
            shutil.copy2(self.paths.config, config_copy)
        if self.paths.auth.exists():
            shutil.copy2(self.paths.auth, auth_copy)
        config = parse_simple_toml_values(config_copy)
        data = {
            "name": name,
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "model": config.get("model", "unknown"),
            "base_url": config.get("base_url", "unknown"),
            "wire_api": config.get("wire_api", "unknown"),
            "config_path": str(config_copy),
            "auth_path": str(auth_copy),
            "warning": "auth_path may contain credentials. Keep this profile private.",
        }
        write_text(profile_path, json.dumps(data, indent=2, ensure_ascii=False))
        return profile_path

    def activate_profile(self, name: str) -> Path:
        profile_path = self.profile_dir / f"{safe_name(name)}.json"
        if not profile_path.exists():
            raise ValueError(f"Profile not found: {name}")
        data = json.loads(read_text(profile_path))
        config_path = Path(data["config_path"])
        auth_path = Path(data["auth_path"])
        backup = self.backup_current(f"before-activate-{safe_name(name)}")
        if config_path.exists():
            shutil.copy2(config_path, self.paths.config)
        if auth_path.exists():
            shutil.copy2(auth_path, self.paths.auth)
        return backup

    def backup_current(self, prefix: str = "web-backup") -> Path:
        backup = self.paths.backups / f"{prefix}-{stamp()}"
        backup.mkdir(parents=True, exist_ok=True)
        for path in [self.paths.auth, self.paths.config, self.paths.session_index, self.paths.home / "history.jsonl"]:
            if path.exists():
                shutil.copy2(path, backup / path.name)
        if self.paths.sessions.exists():
            shutil.copytree(self.paths.sessions, backup / "sessions", dirs_exist_ok=True)
        write_text(
            backup / "manifest.json",
            json.dumps(
                {
                    "created_at": datetime.now().isoformat(timespec="seconds"),
                    "codex_home": str(self.paths.home),
                    "contains_auth_json": self.paths.auth.exists(),
                },
                indent=2,
            ),
        )
        return backup

    def export_sessions(self, source_label: str, note: str = "") -> Path:
        safe = safe_name(source_label or self.current_profile().name)
        out = self.export_dir / f"{safe}-sessions-{stamp()}"
        out.mkdir(parents=True, exist_ok=True)
        if self.paths.sessions.exists():
            shutil.copytree(self.paths.sessions, out / "sessions", dirs_exist_ok=True)
        if self.paths.session_index.exists():
            shutil.copy2(self.paths.session_index, out / "session_index.jsonl")
        manifest = {
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "source_label": source_label,
            "note": note,
            "contains_auth_json": False,
            "session_count": count_session_files(self.paths.sessions),
        }
        write_text(out / "manifest.json", json.dumps(manifest, indent=2, ensure_ascii=False))
        return out

    def import_sessions(self, package_path: Path, target_profile: str = "", index_mode: str = "append") -> Path:
        package = package_path.expanduser().resolve()
        if not package.exists():
            raise ValueError(f"Session package not found: {package}")
        old_sessions = package / "sessions"
        if not old_sessions.exists():
            raise ValueError(f"Missing sessions directory: {old_sessions}")
        backup = self.backup_current("before-web-import")
        if target_profile:
            self.activate_profile(target_profile)
        self.paths.sessions.mkdir(parents=True, exist_ok=True)
        for child in old_sessions.iterdir():
            target = self.paths.sessions / child.name
            if child.is_dir():
                shutil.copytree(child, target, dirs_exist_ok=True)
            else:
                shutil.copy2(child, target)
        old_index = package / "session_index.jsonl"
        if old_index.exists() and index_mode != "skip":
            if index_mode == "replace" or not self.paths.session_index.exists():
                shutil.copy2(old_index, self.paths.session_index)
            else:
                with old_index.open("r", encoding="utf-8", errors="replace") as reader:
                    with self.paths.session_index.open("a", encoding="utf-8") as writer:
                        for line in reader:
                            writer.write(line)
                            if not line.endswith("\n"):
                                writer.write("\n")
        return backup

    def exports(self) -> list[dict[str, Any]]:
        if not self.export_dir.exists():
            return []
        result = []
        for path in sorted(self.export_dir.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
            if not path.is_dir():
                continue
            manifest_path = path / "manifest.json"
            manifest: dict[str, Any] = {}
            if manifest_path.exists():
                try:
                    manifest = json.loads(read_text(manifest_path))
                except json.JSONDecodeError:
                    manifest = {}
            result.append(
                {
                    "path": str(path),
                    "name": path.name,
                    "source_label": manifest.get("source_label", ""),
                    "session_count": manifest.get("session_count", count_session_files(path / "sessions")),
                    "created_at": manifest.get("created_at", ""),
                }
            )
        return result


def safe_name(value: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in "-_." else "-" for ch in value.strip())
    return cleaned.strip("-") or "profile"


class KeeperHandler(BaseHTTPRequestHandler):
    state: KeeperState

    def log_message(self, format: str, *args: Any) -> None:
        return

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/":
            self.send_html(INDEX_HTML)
        elif parsed.path == "/api/state":
            self.send_json(
                {
                    "codex_home": str(self.state.paths.home),
                    "current": asdict(self.state.current_profile()),
                    "profiles": [asdict(p) for p in self.state.profiles()],
                    "exports": self.state.exports(),
                }
            )
        else:
            self.send_error(HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        try:
            body = self.read_json()
            with self.state.lock:
                if parsed.path == "/api/profile/save-current":
                    path = self.state.save_current_profile(str(body.get("name") or "current"))
                    self.send_json({"ok": True, "path": str(path)})
                elif parsed.path == "/api/profile/activate":
                    backup = self.state.activate_profile(str(body.get("name") or ""))
                    self.send_json({"ok": True, "backup": str(backup)})
                elif parsed.path == "/api/backup":
                    backup = self.state.backup_current("web-backup")
                    self.send_json({"ok": True, "backup": str(backup)})
                elif parsed.path == "/api/export":
                    out = self.state.export_sessions(str(body.get("source_label") or ""), str(body.get("note") or ""))
                    self.send_json({"ok": True, "path": str(out)})
                elif parsed.path == "/api/import":
                    backup = self.state.import_sessions(
                        Path(str(body.get("package_path") or "")),
                        str(body.get("target_profile") or ""),
                        str(body.get("index_mode") or "append"),
                    )
                    self.send_json({"ok": True, "backup": str(backup)})
                else:
                    self.send_error(HTTPStatus.NOT_FOUND)
        except Exception as exc:
            self.send_json({"ok": False, "error": str(exc)}, status=400)

    def read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("content-length") or "0")
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        return json.loads(raw.decode("utf-8"))

    def send_json(self, payload: dict[str, Any], status: int = 200) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("content-type", "application/json; charset=utf-8")
        self.send_header("content-length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def send_html(self, html: str) -> None:
        data = html.encode("utf-8")
        self.send_response(200)
        self.send_header("content-type", "text/html; charset=utf-8")
        self.send_header("content-length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


INDEX_HTML = r"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Codex Session Keeper</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #f6f7f9;
      --panel: #ffffff;
      --text: #1f2933;
      --muted: #617083;
      --border: #d8dee7;
      --accent: #0f766e;
      --accent-strong: #115e59;
      --warn: #9f580a;
      --danger: #b42318;
      --code: #eef2f6;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: "Segoe UI", system-ui, -apple-system, sans-serif;
      background: var(--bg);
      color: var(--text);
    }
    header {
      padding: 20px 28px 12px;
      border-bottom: 1px solid var(--border);
      background: var(--panel);
    }
    h1 { margin: 0 0 6px; font-size: 24px; letter-spacing: 0; }
    h2 { margin: 0 0 12px; font-size: 16px; letter-spacing: 0; }
    p { color: var(--muted); line-height: 1.5; margin: 0; }
    main {
      display: grid;
      grid-template-columns: minmax(280px, 360px) minmax(420px, 1fr);
      gap: 18px;
      padding: 18px;
    }
    section {
      background: var(--panel);
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 16px;
    }
    .stack { display: grid; gap: 14px; }
    .grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px; }
    label { display: grid; gap: 6px; color: var(--muted); font-size: 13px; }
    input, select, textarea {
      width: 100%;
      border: 1px solid var(--border);
      border-radius: 6px;
      padding: 9px 10px;
      font: inherit;
      background: #fff;
      color: var(--text);
    }
    textarea { min-height: 76px; resize: vertical; }
    button {
      border: 1px solid var(--accent);
      background: var(--accent);
      color: white;
      border-radius: 6px;
      padding: 9px 12px;
      font: inherit;
      cursor: pointer;
    }
    button.secondary {
      background: #fff;
      color: var(--accent-strong);
    }
    button.warn {
      border-color: var(--warn);
      background: var(--warn);
    }
    .row { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
    .kv {
      display: grid;
      grid-template-columns: 116px minmax(0, 1fr);
      gap: 6px 10px;
      font-size: 13px;
    }
    .kv div:nth-child(odd) { color: var(--muted); }
    code, .path {
      background: var(--code);
      border-radius: 5px;
      padding: 2px 5px;
      overflow-wrap: anywhere;
    }
    .pill {
      display: inline-flex;
      align-items: center;
      border: 1px solid var(--border);
      border-radius: 999px;
      padding: 3px 8px;
      font-size: 12px;
      color: var(--muted);
      background: #fff;
    }
    .list {
      display: grid;
      gap: 8px;
      max-height: 300px;
      overflow: auto;
    }
    .item {
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 10px;
      display: grid;
      gap: 6px;
    }
    .item strong { font-size: 14px; }
    #log {
      min-height: 80px;
      white-space: pre-wrap;
      color: var(--muted);
      font-size: 13px;
    }
    @media (max-width: 900px) {
      main { grid-template-columns: 1fr; }
      .grid { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body>
  <header>
    <h1>Codex Session Keeper</h1>
    <p>本地工具页。选择源 provider 的会话包，切到目标 provider 后导入。不会展示 API key。</p>
  </header>
  <main>
    <div class="stack">
      <section>
        <h2>当前状态</h2>
        <div class="kv" id="current"></div>
        <div class="row" style="margin-top:12px">
          <button class="secondary" onclick="refresh()">刷新</button>
          <button class="secondary" onclick="backup()">备份当前状态</button>
        </div>
      </section>

      <section>
        <h2>Provider 快照</h2>
        <label>
          快照名称
          <input id="profileName" placeholder="old-relay / new-relay" />
        </label>
        <div class="row" style="margin-top:10px">
          <button onclick="saveProfile()">保存当前 provider</button>
        </div>
        <div class="list" id="profiles" style="margin-top:12px"></div>
      </section>
    </div>

    <div class="stack">
      <section>
        <h2>1. 从源 provider 备份会话包</h2>
        <div class="grid">
          <label>
            源 provider 标签
            <input id="sourceLabel" placeholder="old-relay" />
          </label>
          <label>
            备注
            <input id="exportNote" placeholder="before switching to new relay" />
          </label>
        </div>
        <div class="row" style="margin-top:10px">
          <button onclick="exportSessions()">导出当前会话包</button>
        </div>
      </section>

      <section>
        <h2>2. 切到目标 provider</h2>
        <p>选择已保存的 provider 快照，会先自动备份当前状态，再替换 config/auth。</p>
        <div class="row" style="margin-top:10px">
          <select id="targetProfile"></select>
          <button class="warn" onclick="activateSelected()">切到目标 provider</button>
        </div>
      </section>

      <section>
        <h2>3. 导入需要用的会话</h2>
        <div class="grid">
          <label>
            会话包路径
            <input id="packagePath" placeholder="C:\path\to\old-relay-sessions-..." />
          </label>
          <label>
            session_index 处理
            <select id="indexMode">
              <option value="append">append - 追加</option>
              <option value="replace">replace - 替换</option>
              <option value="skip">skip - 跳过</option>
            </select>
          </label>
        </div>
        <div class="row" style="margin-top:10px">
          <button onclick="importSessions()">导入到当前/目标 provider</button>
          <button class="secondary" onclick="copyCommand('codex resume')">复制 resume 命令</button>
          <button class="secondary" onclick="copyCommand('codex fork')">复制 fork 命令</button>
        </div>
      </section>

      <section>
        <h2>会话包</h2>
        <div class="list" id="exports"></div>
      </section>

      <section>
        <h2>日志</h2>
        <div id="log">Ready.</div>
      </section>
    </div>
  </main>
  <script>
    let state = null;

    function setLog(message) {
      document.getElementById('log').textContent = message;
    }

    async function api(path, body) {
      const res = await fetch(path, {
        method: body ? 'POST' : 'GET',
        headers: body ? {'content-type': 'application/json'} : {},
        body: body ? JSON.stringify(body) : undefined
      });
      const data = await res.json();
      if (!res.ok || data.ok === false) throw new Error(data.error || res.statusText);
      return data;
    }

    async function refresh() {
      state = await api('/api/state');
      const c = state.current;
      document.getElementById('current').innerHTML = `
        <div>Codex home</div><div class="path">${state.codex_home}</div>
        <div>Provider</div><div><span class="pill">${c.name}</span></div>
        <div>Model</div><div>${c.model}</div>
        <div>Base URL</div><div class="path">${c.base_url}</div>
        <div>Wire API</div><div>${c.wire_api}</div>
        <div>Sessions</div><div>${c.session_count}</div>
        <div>Latest</div><div class="path">${c.latest_session || 'none'}</div>
      `;
      const profiles = document.getElementById('profiles');
      profiles.innerHTML = state.profiles.map(p => `
        <div class="item">
          <strong>${p.name} ${p.current ? '<span class="pill">current</span>' : ''}</strong>
          <div class="path">${p.base_url}</div>
          <div class="row">
            ${p.current ? '' : `<button class="secondary" onclick="activateProfile('${p.name.replaceAll("'", "\\'")}')">激活</button>`}
          </div>
        </div>
      `).join('');
      const target = document.getElementById('targetProfile');
      target.innerHTML = '<option value="">当前 provider</option>' + state.profiles.filter(p => !p.current).map(p => `<option value="${p.name}">${p.name}</option>`).join('');
      const exportsEl = document.getElementById('exports');
      exportsEl.innerHTML = state.exports.length ? state.exports.map(e => `
        <div class="item">
          <strong>${e.name}</strong>
          <div>source: ${e.source_label || 'unknown'} · sessions: ${e.session_count}</div>
          <div class="path">${e.path}</div>
          <button class="secondary" onclick="usePackage('${e.path.replaceAll("\\", "\\\\").replaceAll("'", "\\'")}')">使用这个包</button>
        </div>
      `).join('') : '<p>暂无会话包。</p>';
    }

    async function saveProfile() {
      const name = document.getElementById('profileName').value.trim();
      if (!name) return setLog('请输入快照名称。');
      const data = await api('/api/profile/save-current', {name});
      setLog('已保存 provider 快照：' + data.path);
      await refresh();
    }

    async function activateProfile(name) {
      const data = await api('/api/profile/activate', {name});
      setLog('已切换 provider，切换前备份：' + data.backup);
      await refresh();
    }

    async function activateSelected() {
      const name = document.getElementById('targetProfile').value;
      if (!name) return setLog('目标为当前 provider，无需切换。');
      await activateProfile(name);
    }

    async function backup() {
      const data = await api('/api/backup', {});
      setLog('已备份当前状态：' + data.backup);
      await refresh();
    }

    async function exportSessions() {
      const source_label = document.getElementById('sourceLabel').value.trim() || state.current.name;
      const note = document.getElementById('exportNote').value.trim();
      const data = await api('/api/export', {source_label, note});
      setLog('已导出会话包：' + data.path);
      document.getElementById('packagePath').value = data.path;
      await refresh();
    }

    async function importSessions() {
      const package_path = document.getElementById('packagePath').value.trim();
      if (!package_path) return setLog('请输入会话包路径。');
      const target_profile = document.getElementById('targetProfile').value;
      const index_mode = document.getElementById('indexMode').value;
      const data = await api('/api/import', {package_path, target_profile, index_mode});
      setLog('已导入。导入前备份：' + data.backup + '\n下一步：运行 codex resume 或 codex fork。');
      await refresh();
    }

    function usePackage(path) {
      document.getElementById('packagePath').value = path;
      setLog('已选择会话包：' + path);
    }

    async function copyCommand(cmd) {
      await navigator.clipboard.writeText(cmd);
      setLog('已复制命令：' + cmd);
    }

    refresh().catch(err => setLog('加载失败：' + err.message));
  </script>
</body>
</html>
"""


def serve(host: str, port: int, codex_home: Path | None, open_browser: bool) -> int:
    state = KeeperState(codex_home)
    handler = type("BoundKeeperHandler", (KeeperHandler,), {"state": state})
    server = ThreadingHTTPServer((host, port), handler)
    url = f"http://{host}:{server.server_port}"
    print(f"Codex Session Keeper UI: {url}")
    print("Press Ctrl+C to stop.")
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        server.server_close()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Start the Codex Session Keeper local web UI.")
    parser.add_argument("--host", default="127.0.0.1", help="Bind host. Defaults to 127.0.0.1.")
    parser.add_argument("--port", type=int, default=8765, help="Bind port. Defaults to 8765.")
    parser.add_argument("--codex-home", type=Path, help="Codex home directory, defaults to CODEX_HOME or ~/.codex.")
    parser.add_argument("--no-open", action="store_true", help="Do not open the browser automatically.")
    args = parser.parse_args(argv)
    return serve(args.host, args.port, args.codex_home, not args.no_open)


if __name__ == "__main__":
    raise SystemExit(main())
