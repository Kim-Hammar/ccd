"""
Load-balancing gateway for the IT-system testbed: a minimal async reverse proxy,
strict round-robin. Deliberately no health checks / no skip-on-failure, so the
per-server offered load stays ``L_i ~ W/m`` even when a link is closed (the causal
model has no ``N_i -> L_i`` edge); a closed link (iptables REJECT) fails fast and the
request counts as attempted but not ok. Per-backend monotonic counters drive the
causal variables: ``attempted[i]`` -> L_i, ``ok[i]`` -> Th_i. ``GET /metrics`` returns
an atomic JSON snapshot; ``/work`` is the client endpoint.
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
