"""
Load-balancing gateway for the IT-system testbed.

A minimal async reverse proxy that forwards each client request to the next backend
in strict round-robin order. There are deliberately **no health checks and no
skip-on-failure**: the gateway always attempts backend ``i`` on its turn, so the
per-server offered load stays ``L_i ~ W/m`` even when the gateway -> n_i link is
closed (matching the causal model's ``W -> L_i`` with no ``N_i -> L_i`` edge). A
closed link (iptables REJECT) fails fast, so the corresponding request is counted as
attempted but not ok.

Per-backend monotonic counters drive the causal variables:

* ``attempted[i]`` -> L_i (requests the gateway routed to n_i),
* ``ok[i]``        -> Th_i (end-to-end successes via n_i).

``GET /metrics`` returns an atomic JSON snapshot; ``GET /work`` is the client endpoint.
"""

from __future__ import annotations
import asyncio
import itertools
import os
import time
from aiohttp import ClientSession, ClientTimeout, web

BACKENDS = [b for b in os.environ.get("BACKENDS", "").split(",") if b]
CONNECT_TIMEOUT = float(os.environ.get("GATEWAY_CONNECT_TIMEOUT", "0.25"))
TOTAL_TIMEOUT = float(os.environ.get("GATEWAY_TOTAL_TIMEOUT", "2.0"))

_attempted = [0] * len(BACKENDS)
_ok = [0] * len(BACKENDS)
_rr = itertools.cycle(range(len(BACKENDS))) if BACKENDS else itertools.cycle([0])
_rr_lock = asyncio.Lock()


async def _next_index() -> int:
    async with _rr_lock:
        return next(_rr)


async def handle_work(request: web.Request) -> web.Response:
    i = await _next_index()
    _attempted[i] += 1
    session: ClientSession = request.app["session"]
    url = f"http://{BACKENDS[i]}/work"
    try:
        async with session.post(url) as resp:
            await resp.read()
            if resp.status == 200:
                _ok[i] += 1
                return web.json_response({"backend": i, "ok": True})
            return web.json_response({"backend": i, "ok": False}, status=502)
    except Exception:
        return web.json_response({"backend": i, "ok": False}, status=504)


async def handle_metrics(_request: web.Request) -> web.Response:
    return web.json_response({
        "attempted": list(_attempted),
        "ok": list(_ok),
        "t": time.time(),
    })


async def handle_health(_request: web.Request) -> web.Response:
    return web.json_response({"ok": True, "backends": len(BACKENDS)})


async def _make_app() -> web.Application:
    app = web.Application()
    timeout = ClientTimeout(total=TOTAL_TIMEOUT, connect=CONNECT_TIMEOUT)
    app["session"] = ClientSession(timeout=timeout)

    async def _close_session(app: web.Application) -> None:
        await app["session"].close()

    app.on_cleanup.append(_close_session)
    app.add_routes([
        web.post("/work", handle_work),
        web.get("/work", handle_work),
        web.get("/metrics", handle_metrics),
        web.get("/health", handle_health),
    ])
    return app


if __name__ == "__main__":
    web.run_app(_make_app(), host="0.0.0.0", port=8080)
