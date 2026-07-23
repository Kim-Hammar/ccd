"""
Process container for the ICS testbed: the Tennessee Eastman process via ``tep2py``.

A background loop runs the tep2py simulation (base case + IDV(8) disturbance noise) for
the reactor pressure ``XMEAS(7)`` and adds a command-proportional shift from the valve
setpoint ``V``. ``P`` is the resulting pressure; ``S`` its margin to the 3000 kPa
shutdown limit (100 at the safe base, 0 at the limit). tep2py is the MATLAB-free
stand-in for pyTEP; it is a disturbance simulator (manipulated variables fixed at the
base point), hence the ``PRESSURE_GAIN`` shift models the command's effect.
"""

import contextlib
import io
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import numpy as np

try:
    from tep2py import tep2py
    _TEP_OK = True
except Exception:
    _TEP_OK = False

P_SHUTDOWN = 3000.0        # reactor high-pressure shutdown limit (kPa)
V_MAX = 60.0               # max nominal valve setpoint (matches the command magnitude)
PRESSURE_GAIN = 150.0      # operating-pressure shift at full command
SIM_STEPS = 10             # tep2py samples per run (3-min each -> 30 min sim)
PROC_DT = 2.0             # process control-loop period (s)


def _tep_pressure(disturbance: bool) -> float:
    """One tep2py run's final reactor pressure XMEAS(7); falls back to a nominal base."""
    if not _TEP_OK:
        return 2700.0 + float(np.random.normal(0.0, 8.0))
    try:
        idata = np.zeros((SIM_STEPS, 20), dtype=int)
        if disturbance:
            idata[:, 7] = 1                    # IDV(8): A,B,C feed composition random variation
        sim = tep2py(idata)
        with contextlib.redirect_stdout(io.StringIO()):
            sim.simulate()
        p = float(sim.process_data["XMEAS(7)"].iloc[-1])
        return p if np.isfinite(p) and p > 0 else 2700.0
    except Exception:
        return 2700.0


P_REF = _tep_pressure(disturbance=False)         # safe base-case reactor pressure
_lock = threading.Lock()
_state = {"valve": 0.0, "P": P_REF, "S": 100.0}


def _loop() -> None:
    while True:
        with _lock:
            v = _state["valve"]
        p = _tep_pressure(disturbance=True) + PRESSURE_GAIN * min(v, V_MAX) / V_MAX
        s = max(0.0, min(100.0, 100.0 * (P_SHUTDOWN - p) / (P_SHUTDOWN - P_REF)))
        with _lock:
            _state["P"], _state["S"] = p, s
        time.sleep(PROC_DT)


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
                p, s = _state["P"], _state["S"]
            self._send(200, {"P": p, "S": s, "t": time.time()})
        elif self.path == "/health":
            self._send(200, {"ok": True, "tep2py": _TEP_OK, "P_ref": P_REF})
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self) -> None:
        if self.path == "/actuate":
            valve = float(self._form().get("valve", 0.0))
            with _lock:
                _state["valve"] = valve
            self._send(200, {"valve": valve})
        else:
            self._send(404, {"error": "not found"})

    def log_message(self, *_args) -> None:
        pass


if __name__ == "__main__":
    threading.Thread(target=_loop, daemon=True).start()
    ThreadingHTTPServer(("0.0.0.0", 8080), Handler).serve_forever()
