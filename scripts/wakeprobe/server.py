"""WakeProbe test server on :3000. Logs every request; serves DIR under / and /app/.

    python3 scripts/wakeprobe/server.py [DIR]    default DIR: dist/wakeprobe

DIR holds WakeProbe.wgt and sssp_config.xml (pack.sh), plan.json (what the app
does next, e.g. {"wake_in_s": 180, "sleep_after_s": 30, "cycles": 3}) and
requests.log, where the app's reports end up.
"""

import json
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = WWW = Path(sys.argv[1] if len(sys.argv) > 1 else "dist/wakeprobe").resolve()
LOG = ROOT / "requests.log"
TYPES = {".html": "text/html", ".js": "application/javascript", ".xml": "application/xml",
         ".wgt": "application/widget", ".zip": "application/zip", ".png": "image/png", ".json": "application/json"}


def log(line: str) -> None:
    with LOG.open("a") as f:
        f.write(f"{time.strftime('%H:%M:%S')} {line}\n")


class H(BaseHTTPRequestHandler):
    def _common(self, body: bytes = b"") -> None:
        hdrs = {k: v for k, v in self.headers.items() if k.lower() in ("user-agent", "accept", "range", "content-type")}
        log(f"{self.client_address[0]} {self.command} {self.path} {json.dumps(hdrs)}" + (f" BODY {body.decode(errors='replace')}" if body else ""))

    def _send(self, code: int, data: bytes, ctype: str = "text/plain") -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(data)

    def do_OPTIONS(self) -> None:
        self._common()
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST")
        self.end_headers()

    def do_POST(self) -> None:
        body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
        self._common(body)
        self._send(200, b"ok")

    def do_HEAD(self) -> None:
        self.do_GET()

    def do_GET(self) -> None:
        self._common()
        path = self.path.split("?", 1)[0]
        if path == "/plan":
            plan = ROOT / "plan.json"
            self._send(200, plan.read_bytes() if plan.exists() else b"{}", "application/json")
            return
        if path.startswith("/app"):
            path = path[4:]
        name = path.strip("/") or "index.html"
        f = WWW / name
        if "/" in name or not f.is_file():
            self._send(404, b"not found")
            return
        self._send(200, f.read_bytes(), TYPES.get(f.suffix, "application/octet-stream"))

    def log_message(self, *args) -> None:
        pass


if __name__ == "__main__":
    log("server start")
    ThreadingHTTPServer(("0.0.0.0", 3000), H).serve_forever()
