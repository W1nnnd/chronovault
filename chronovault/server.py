"""Local dashboard server (standard library only, binds to 127.0.0.1)."""
from __future__ import annotations

import datetime as dt
import json
import mimetypes
import shutil
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from . import ledger
from .digest import build_state, render_digest
from .pipeline import run_scan

WEB = Path(__file__).resolve().parent / "web"


class App:
    def __init__(self, sources: list[Path], vault: Path, as_of: dt.date):
        self.sources = [Path(s).resolve() for s in sources]
        self.vault = vault.resolve()
        self.as_of = as_of
        self.lock = threading.Lock()
        self.last_log: list[dict] = []

    def con(self):
        return ledger.connect(self.vault / "vault.db")

    def state(self) -> dict:
        con = self.con()
        st = build_state(con, self.as_of)
        st["sources"] = [str(s) for s in self.sources]
        st["scan_log"] = self.last_log
        return st

    def scan(self) -> dict:
        with self.lock:
            def prog(e):
                self.last_log.append(e)
            self.last_log = []
            return run_scan(self.sources, self.vault, self.as_of, progress=prog)

    def reset(self) -> None:
        with self.lock:
            if self.vault.exists():
                shutil.rmtree(self.vault)
            self.vault.mkdir(parents=True, exist_ok=True)
            self.last_log = []


def make_handler(app: App):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):  # quiet
            pass

        def _send(self, code: int, body: bytes, content_type: str):
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, code: int, obj):
            self._send(code, json.dumps(obj).encode(), "application/json; charset=utf-8")

        def do_GET(self):
            u = urlparse(self.path)
            if u.path == "/api/state":
                return self._json(200, app.state())
            if u.path == "/api/digest":
                con = app.con()
                text = render_digest(build_state(con, app.as_of))
                return self._send(200, text.encode(), "text/markdown; charset=utf-8")
            if u.path.startswith("/api/file"):
                qs = parse_qs(u.query)
                sha = (qs.get("sha") or [None])[0]
                if not sha:
                    return self._json(400, {"error": "sha required"})
                con = app.con()
                row = con.execute("SELECT * FROM files WHERE sha256=?", (sha,)).fetchone()
                if not row:
                    return self._json(404, {"error": "not found"})
                return self._json(200, dict(row))
            if u.path.startswith("/source/"):
                sha = u.path.split("/source/", 1)[1]
                # path traversal guard: only serve by sha from ledger
                if ".." in sha or "/" in sha or "\\" in sha or len(sha) < 16:
                    return self._json(404, {"error": "not found"})
                con = app.con()
                row = con.execute("SELECT primary_path, name FROM files WHERE sha256=?", (sha,)).fetchone()
                if not row:
                    return self._json(404, {"error": "not found"})
                path = Path(row["primary_path"]).resolve()
                # must be under an authorized source
                if not any(str(path).startswith(str(s)) for s in app.sources):
                    return self._json(404, {"error": "not found"})
                if not path.is_file():
                    return self._json(404, {"error": "not found"})
                data = path.read_bytes()
                ctype = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
                return self._send(200, data, ctype)
            # static
            rel = u.path.lstrip("/") or "index.html"
            if ".." in rel or rel.startswith("/"):
                return self._json(404, {"error": "not found"})
            target = (WEB / rel).resolve()
            if not str(target).startswith(str(WEB.resolve())) or not target.is_file():
                return self._json(404, {"error": "not found"})
            ctype = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
            if target.suffix == ".js":
                ctype = "application/javascript; charset=utf-8"
            elif target.suffix == ".css":
                ctype = "text/css; charset=utf-8"
            elif target.suffix == ".html":
                ctype = "text/html; charset=utf-8"
            return self._send(200, target.read_bytes(), ctype)

        def do_POST(self):
            u = urlparse(self.path)
            length = int(self.headers.get("Content-Length") or 0)
            _ = self.rfile.read(length) if length else b""
            if u.path == "/api/scan":
                try:
                    rep = app.scan()
                    return self._json(200, {"ok": True, "report": rep, "state": app.state()})
                except Exception as exc:  # noqa: BLE001
                    return self._json(500, {"ok": False, "error": str(exc)})
            if u.path == "/api/reset":
                app.reset()
                return self._json(200, {"ok": True, "state": app.state()})
            return self._json(404, {"error": "not found"})

    return Handler


def serve(sources: list[Path], vault: Path, as_of: dt.date, port: int = 8765) -> ThreadingHTTPServer:
    app = App(sources, vault, as_of)
    # Ensure ledger exists
    if not (vault / "vault.db").exists():
        run_scan(sources, vault, as_of)
    httpd = ThreadingHTTPServer(("127.0.0.1", port), make_handler(app))
    print(f"ChronoVault dashboard on http://127.0.0.1:{httpd.server_address[1]}  (as of {as_of}, Ctrl+C to stop)")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
    return httpd
