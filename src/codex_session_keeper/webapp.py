from __future__ import annotations

import argparse
import json
import shutil
import threading
import webbrowser
from dataclasses import asdict, dataclass
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .cli import codex_paths, parse_simple_toml_values, stamp
from .sessions import (
    export_provider_sessions,
    import_session_package,
    migrate_provider,
    provider_counts,
    scan_sessions,
)


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def safe_name(value: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in "-_." else "-" for ch in value.strip())
    return cleaned.strip("-") or "profile"


@dataclass(frozen=True)
class ProviderProfile:
    name: str
    model: str
    base_url: str
    wire_api: str
    config_path: str
    auth_path: str
    current: bool


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
        )

    def profiles(self) -> list[ProviderProfile]:
        result = [self.current_profile()]
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
                    "source_provider": manifest.get("source_provider", ""),
                    "target_provider": manifest.get("target_provider", ""),
                    "session_count": manifest.get("session_count", 0),
                    "created_at": manifest.get("created_at", ""),
                }
            )
        return result

    def state_payload(self) -> dict[str, Any]:
        sessions = scan_sessions(self.paths.home)
        return {
            "codex_home": str(self.paths.home),
            "current": asdict(self.current_profile()),
            "profiles": [asdict(p) for p in self.profiles()],
            "provider_counts": provider_counts(sessions),
            "sessions": [
                {
                    "id": s.id,
                    "provider": s.provider,
                    "cwd": s.cwd,
                    "timestamp": s.timestamp,
                    "updated_at": s.updated_at,
                    "thread_name": s.thread_name,
                    "path": str(s.path),
                }
                for s in sessions[:500]
            ],
            "session_total": len(sessions),
            "exports": self.exports(),
        }


class KeeperHandler(BaseHTTPRequestHandler):
    state: KeeperState

    def log_message(self, format: str, *args: Any) -> None:
        return

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/":
            self.send_html(INDEX_HTML)
        elif parsed.path == "/api/state":
            self.send_json(self.state.state_payload())
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
                elif parsed.path == "/api/migrate-provider":
                    result = migrate_provider(
                        self.state.paths.home,
                        str(body.get("source_provider") or ""),
                        str(body.get("target_provider") or ""),
                        dry_run=bool(body.get("dry_run")),
                    )
                    self.send_json({"ok": True, **result})
                elif parsed.path == "/api/export-provider":
                    provider = str(body.get("provider") or "*")
                    target = str(body.get("rewrite_provider") or "") or None
                    safe = safe_name(provider if provider != "*" else "all")
                    out = self.state.export_dir / f"{safe}-sessions-{stamp()}"
                    manifest = export_provider_sessions(self.state.paths.home, provider, out, rewrite_provider=target)
                    self.send_json({"ok": True, "path": str(out), **manifest})
                elif parsed.path == "/api/import-package":
                    result = import_session_package(
                        self.state.paths.home,
                        Path(str(body.get("package_path") or "")),
                        target_provider=str(body.get("target_provider") or "") or None,
                        index_mode=str(body.get("index_mode") or "append"),
                    )
                    self.send_json({"ok": True, **result})
                else:
                    self.send_error(HTTPStatus.NOT_FOUND)
        except Exception as exc:
            self.send_json({"ok": False, "error": str(exc)}, status=400)

    def read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("content-length") or "0")
        if length <= 0:
            return {}
        return json.loads(self.rfile.read(length).decode("utf-8"))

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
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Codex Session Keeper</title>
  <style>
    :root {
      --bg: #f6f7f9;
      --panel: #ffffff;
      --text: #1f2933;
      --muted: #617083;
      --border: #d8dee7;
      --accent: #0f766e;
      --accent-strong: #115e59;
      --warn: #9f580a;
      --code: #eef2f6;
    }
    * { box-sizing: border-box; }
    body { margin: 0; font-family: "Segoe UI", system-ui, sans-serif; background: var(--bg); color: var(--text); }
    header { padding: 20px 28px 12px; border-bottom: 1px solid var(--border); background: var(--panel); }
    h1 { margin: 0 0 6px; font-size: 24px; letter-spacing: 0; }
    h2 { margin: 0 0 12px; font-size: 16px; letter-spacing: 0; }
    p { color: var(--muted); line-height: 1.5; margin: 0; }
    main { display: grid; grid-template-columns: 360px minmax(520px, 1fr); gap: 18px; padding: 18px; }
    section { background: var(--panel); border: 1px solid var(--border); border-radius: 8px; padding: 16px; }
    .stack { display: grid; gap: 14px; }
    .grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px; }
    label { display: grid; gap: 6px; color: var(--muted); font-size: 13px; }
    input, select { width: 100%; border: 1px solid var(--border); border-radius: 6px; padding: 9px 10px; font: inherit; background: #fff; color: var(--text); }
    button { border: 1px solid var(--accent); background: var(--accent); color: white; border-radius: 6px; padding: 9px 12px; font: inherit; cursor: pointer; }
    button.secondary { background: #fff; color: var(--accent-strong); }
    button.warn { border-color: var(--warn); background: var(--warn); }
    .row { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
    .kv { display: grid; grid-template-columns: 118px minmax(0, 1fr); gap: 6px 10px; font-size: 13px; }
    .kv div:nth-child(odd) { color: var(--muted); }
    .path, code { background: var(--code); border-radius: 5px; padding: 2px 5px; overflow-wrap: anywhere; }
    .pill { display: inline-flex; border: 1px solid var(--border); border-radius: 999px; padding: 3px 8px; font-size: 12px; color: var(--muted); background: #fff; }
    .list { display: grid; gap: 8px; max-height: 330px; overflow: auto; }
    .item { border: 1px solid var(--border); border-radius: 8px; padding: 10px; display: grid; gap: 6px; }
    .item strong { font-size: 14px; }
    #log { min-height: 80px; white-space: pre-wrap; color: var(--muted); font-size: 13px; }
    table { width: 100%; border-collapse: collapse; font-size: 13px; }
    th, td { border-bottom: 1px solid var(--border); padding: 7px; text-align: left; vertical-align: top; }
    th { color: var(--muted); font-weight: 600; }
    @media (max-width: 940px) { main { grid-template-columns: 1fr; } .grid { grid-template-columns: 1fr; } }
  </style>
</head>
<body>
  <header>
    <h1>Codex Session Keeper</h1>
    <p>本地 provider / 会话管理器。扫描本地 Codex 会话、批量切换会话 provider、按 provider 导出会话包，并支持在其他设备导入。</p>
  </header>
  <main>
    <div class="stack">
      <section>
        <h2>当前 Provider</h2>
        <div class="kv" id="current"></div>
        <div class="row" style="margin-top:12px">
          <button class="secondary" onclick="refresh()">刷新</button>
          <button class="secondary" onclick="backup()">备份当前状态</button>
        </div>
      </section>

      <section>
        <h2>Provider 快照</h2>
        <label>快照名称<input id="profileName" placeholder="old-relay / new-relay" /></label>
        <div class="row" style="margin-top:10px"><button onclick="saveProfile()">保存当前 provider</button></div>
        <div class="list" id="profiles" style="margin-top:12px"></div>
      </section>

      <section>
        <h2>Provider 分布</h2>
        <div id="counts" class="list"></div>
      </section>
    </div>

    <div class="stack">
      <section>
        <h2>批量切换会话 Provider</h2>
        <div class="grid">
          <label>源 provider<select id="sourceProvider"></select></label>
          <label>目标 provider<input id="targetProvider" placeholder="custom / newapi / openai" /></label>
        </div>
        <div class="row" style="margin-top:10px">
          <button class="secondary" onclick="dryRunMigrate()">预览</button>
          <button class="warn" onclick="migrateProvider()">切换所有匹配会话</button>
        </div>
      </section>

      <section>
        <h2>导出会话</h2>
        <div class="grid">
          <label>要导出的 provider<select id="exportProvider"></select></label>
          <label>导出时改写为 provider<input id="rewriteProvider" placeholder="可选目标 provider" /></label>
        </div>
        <div class="row" style="margin-top:10px">
          <button onclick="exportProvider()">导出 provider 会话包</button>
        </div>
      </section>

      <section>
        <h2>导入会话</h2>
        <div class="grid">
          <label>会话包路径<input id="packagePath" placeholder="C:\path\to\provider-sessions-..." /></label>
          <label>导入后绑定到 provider<input id="importTargetProvider" placeholder="可选 provider" /></label>
          <label>session_index 处理方式<select id="indexMode"><option value="append">append</option><option value="replace">replace</option><option value="skip">skip</option></select></label>
        </div>
        <div class="row" style="margin-top:10px">
          <button onclick="importPackage()">导入会话包</button>
          <button class="secondary" onclick="copyCommand('codex resume')">复制 codex resume</button>
          <button class="secondary" onclick="copyCommand('codex fork')">复制 codex fork</button>
        </div>
      </section>

      <section>
        <h2>会话包</h2>
        <div id="exports" class="list"></div>
      </section>

      <section>
        <h2>最近会话</h2>
        <div id="sessions"></div>
      </section>

      <section>
        <h2>日志</h2>
        <div id="log">就绪。</div>
      </section>
    </div>
  </main>
  <script>
    let state = null;
    const esc = (value) => String(value ?? '').replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
    function setLog(message) { document.getElementById('log').textContent = message; }
    async function api(path, body) {
      const res = await fetch(path, { method: body ? 'POST' : 'GET', headers: body ? {'content-type':'application/json'} : {}, body: body ? JSON.stringify(body) : undefined });
      const data = await res.json();
      if (!res.ok || data.ok === false) throw new Error(data.error || res.statusText);
      return data;
    }
    function providerOptions(includeAll = false) {
      const providers = Object.keys(state.provider_counts || {});
      return (includeAll ? ['*'] : providers).concat(includeAll ? providers : []).map(p => `<option value="${esc(p)}">${esc(p)}${p === '*' ? ' - 所有 provider' : ''}</option>`).join('');
    }
    async function refresh() {
      state = await api('/api/state');
      const c = state.current;
      document.getElementById('current').innerHTML = `
        <div>Codex 目录</div><div class="path">${esc(state.codex_home)}</div>
        <div>Provider</div><div><span class="pill">${esc(c.name)}</span></div>
        <div>模型</div><div>${esc(c.model)}</div>
        <div>Base URL</div><div class="path">${esc(c.base_url)}</div>
        <div>Wire API</div><div>${esc(c.wire_api)}</div>
        <div>会话总数</div><div>${state.session_total}</div>`;
      document.getElementById('sourceProvider').innerHTML = providerOptions(false);
      document.getElementById('exportProvider').innerHTML = providerOptions(true);
      document.getElementById('counts').innerHTML = Object.entries(state.provider_counts).map(([p, n]) => `<div class="item"><strong>${esc(p)}</strong><div>${n} 个会话</div></div>`).join('');
      document.getElementById('profiles').innerHTML = state.profiles.map(p => `<div class="item"><strong>${esc(p.name)} ${p.current ? '<span class="pill">current</span>' : ''}</strong><div class="path">${esc(p.base_url)}</div>${p.current ? '' : `<button class="secondary" onclick="activateProfile('${esc(p.name)}')">激活 config/auth</button>`}</div>`).join('');
      document.getElementById('exports').innerHTML = state.exports.length ? state.exports.map(e => `<div class="item"><strong>${esc(e.name)}</strong><div>${esc(e.source_provider || 'unknown')} -> ${esc(e.target_provider || e.source_provider || 'unknown')} · ${e.session_count} 个会话</div><div class="path">${esc(e.path)}</div><button class="secondary" onclick="usePackage('${esc(e.path).replaceAll("\\", "\\\\")}')">使用这个包</button></div>`).join('') : '<p>暂无会话包。</p>';
      document.getElementById('sessions').innerHTML = `<table><thead><tr><th>Provider</th><th>会话</th><th>工作目录</th><th>更新时间</th></tr></thead><tbody>${state.sessions.slice(0, 80).map(s => `<tr><td>${esc(s.provider)}</td><td>${esc(s.thread_name || s.id)}</td><td class="path">${esc(s.cwd)}</td><td>${esc(s.updated_at || s.timestamp)}</td></tr>`).join('')}</tbody></table>`;
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
      setLog('已激活 provider。切换前备份：' + data.backup);
      await refresh();
    }
    async function backup() {
      const data = await api('/api/backup', {});
      setLog('已创建备份：' + data.backup);
      await refresh();
    }
    async function dryRunMigrate() {
      const source_provider = document.getElementById('sourceProvider').value;
      const target_provider = document.getElementById('targetProvider').value.trim();
      if (!source_provider || !target_provider) return setLog('请选择源 provider 和目标 provider。');
      const data = await api('/api/migrate-provider', {source_provider, target_provider, dry_run: true});
      setLog(`预览：${data.matched} 个会话匹配 ${source_provider}；${data.changed} 个会话将切换到 ${target_provider}。`);
    }
    async function migrateProvider() {
      const source_provider = document.getElementById('sourceProvider').value;
      const target_provider = document.getElementById('targetProvider').value.trim();
      if (!source_provider || !target_provider) return setLog('请选择源 provider 和目标 provider。');
      const data = await api('/api/migrate-provider', {source_provider, target_provider});
      setLog(`已将 ${data.changed} 个会话从 ${source_provider} 切换到 ${target_provider}。\n备份：${data.backup}`);
      await refresh();
    }
    async function exportProvider() {
      const provider = document.getElementById('exportProvider').value;
      const rewrite_provider = document.getElementById('rewriteProvider').value.trim();
      const data = await api('/api/export-provider', {provider, rewrite_provider});
      document.getElementById('packagePath').value = data.path;
      setLog(`已导出 ${data.session_count} 个会话：${data.path}`);
      await refresh();
    }
    async function importPackage() {
      const package_path = document.getElementById('packagePath').value.trim();
      const target_provider = document.getElementById('importTargetProvider').value.trim();
      const index_mode = document.getElementById('indexMode').value;
      if (!package_path) return setLog('请输入会话包路径。');
      const data = await api('/api/import-package', {package_path, target_provider, index_mode});
      setLog(`已导入 ${data.imported} 个会话。\n备份：${data.backup}\n下一步：运行 codex resume 或 codex fork。`);
      await refresh();
    }
    function usePackage(path) { document.getElementById('packagePath').value = path; setLog('已选择会话包：' + path); }
    async function copyCommand(cmd) { await navigator.clipboard.writeText(cmd); setLog('已复制：' + cmd); }
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
    parser.add_argument("--codex-home", type=Path, help="Codex 目录 directory, defaults to CODEX_HOME or ~/.codex.")
    parser.add_argument("--no-open", action="store_true", help="Do not open the browser automatically.")
    args = parser.parse_args(argv)
    return serve(args.host, args.port, args.codex_home, not args.no_open)


if __name__ == "__main__":
    raise SystemExit(main())


