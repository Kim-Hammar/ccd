"""
Supervisory control server for the ICS testbed. Ctil is the most recent command that
actually arrived from the SCADA client; with the G2 gateway closed (iptables REJECT)
nothing arrives and it decays to 0, realizing Ctil = G2 * C. V is Ctil in remote mode
and 0 in local mode, realizing V = Chat * Ctil (do(Chat=0) = POST /admin/mode
mode=local). A background thread forwards V to the process container.
"""

import json
import os
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PROCESS_URL = os.environ.get("PROCESS_URL", "http://127.0.0.1:8080")
FRESH = 2.0                                     # a command older than this is treated as gone
_lock = threading.Lock()
_state = {"mode": "remote", "last_command": 0.0, "last_t": -1e9}   # mode: "remote"/"local"


def _snapshot() -> tuple:
    """(Chat in {0,1}, Ctil, V) from the current control state."""
    with _lock:
        remote = _state["mode"] == "remote"
        fresh = (time.monotonic() - _state["last_t"]) < FRESH
        ctil = _state["last_command"] if fresh else 0.0
    v = ctil if remote else 0.0
    return (1 if remote else 0), ctil, v


def _pusher() -> None:
    """Forward the valve setpoint V to the process every second (the control loop)."""
    while True:
        _, _, v = _snapshot()
        try:
            req = urllib.request.Request(PROCESS_URL + "/actuate", data=f"valve={v}".encode())
            urllib.request.urlopen(req, timeout=1.0).read()
        except Exception:
            pass
        time.sleep(1.0)


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
            chat, ctil, v = _snapshot()
            self._send(200, {"Chat": chat, "Ctil": ctil, "V": v, "t": time.time()})
        elif self.path == "/health":
            self._send(200, {"ok": True})
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self) -> None:
        if self.path == "/command":
            level = float(self._form().get("level", 0.0))
            with _lock:
                _state["last_command"] = level
                _state["last_t"] = time.monotonic()
            self._send(200, {"accepted": True})
        elif self.path == "/admin/mode":
            mode = self._form().get("mode", "remote")
            with _lock:
                _state["mode"] = "remote" if mode == "remote" else "local"
                current = _state["mode"]
            self._send(200, {"mode": current})
        else:
            self._send(404, {"error": "not found"})

    def log_message(self, *_args) -> None:
        pass


if __name__ == "__main__":
    threading.Thread(target=_pusher, daemon=True).start()
    ThreadingHTTPServer(("0.0.0.0", 8080), Handler).serve_forever()
