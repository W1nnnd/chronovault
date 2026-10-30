import datetime as dt
import json
import threading
from http.client import HTTPConnection
from pathlib import Path

from chronovault.pipeline import run_scan
from chronovault.server import App, make_handler
from http.server import ThreadingHTTPServer


AS_OF = dt.date(2026, 10, 30)


def _get(url: str):
    # url like http://127.0.0.1:PORT/path
    host = url.split("/")[2]
    path = "/" + "/".join(url.split("/")[3:])
    h, p = host.split(":")
    c = HTTPConnection(h, int(p), timeout=5)
    c.request("GET", path)
    r = c.getresponse()
    body = r.read()
    return r.status, body


def test_dashboard_state_and_path_traversal_guard(sources, tmp_path):
    vault = tmp_path / "vault"
    run_scan(sources, vault, AS_OF)
    app = App(sources, vault, AS_OF)
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(app))
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    try:
        port = httpd.server_address[1]
        base = f"http://127.0.0.1:{port}"
        status, body = _get(base + "/api/state")
        assert status == 200
        state = json.loads(body)
        assert state["counts"]["files"] == 13
        status, _ = _get(base + "/../../etc/passwd")
        assert status == 404
        status, _ = _get(base + "/source/../etc/passwd")
        assert status == 404
    finally:
        httpd.shutdown()
