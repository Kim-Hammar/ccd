"""
Enterprise web server for the ICS testbed: reports its state ``W`` (1 = up, 0 = safe
read-only mode) and the web integrity ``I`` (high when up, reduced in safe mode).
``do(W=0)`` is realized by POSTing ``/admin/mode mode=safe``.
"""

import json
import random
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

I_UP, I_SAFE, I_SD = 88.0, 48.0, 3.0
_lock = threading.Lock()
_state = {"mode": "up"}                         # "up" or "safe"


def _integrity() -> float:
    base = I_UP if _state["mode"] == "up" else I_SAFE
    return max(0.0, min(100.0, base + random.gauss(0.0, I_SD)))


class Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, obj: dict) -> None:
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _form(self) -> dict:
        n = int(self.headers.get("Content-Length", 0) or 0)
        raw = self.rfile.read(n).decode() if n else ""
        return dict(p.split("=", 1) for p in raw.split("&") if "=" in p)

    def do_GET(self) -> None:
        if self.path == "/metrics":
            with _lock:
                up = _state["mode"] == "up"
                integ = _integrity()
            self._send(200, {"W": 1 if up else 0, "I": integ, "t": time.time()})
        elif self.path == "/health":
            self._send(200, {"ok": True})
        elif self.path.startswith("/status"):
            with _lock:
                mode = _state["mode"]
            self._send(200, {"service": "enterprise-web", "mode": mode, "dynamic": mode == "up"})
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self) -> None:
        if self.path == "/admin/mode":
            mode = self._form().get("mode", "up")
            with _lock:
                _state["mode"] = "up" if mode == "up" else "safe"
                current = _state["mode"]
            self._send(200, {"mode": current})
        else:
            self._send(404, {"error": "not found"})

    def log_message(self, *_args) -> None:
        pass


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 8080), Handler).serve_forever()
