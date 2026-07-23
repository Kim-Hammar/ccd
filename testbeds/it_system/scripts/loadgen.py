"""
Open-loop Poisson HTTP load generator for the IT-system testbed.

Arrivals are scheduled against a monotonic clock (``next_t += Exp(1/rate)``), so the
offered rate does not drift with per-request latency. The number of requests sent is
recorded by the collection engine as the measured workload ``W``.
"""

from __future__ import annotations
import asyncio
import time
from typing import Optional
import numpy as np
from aiohttp import ClientSession, ClientTimeout


async def drive(
    gateway_url: str,
    rate: float,
    duration: float,
    rng: np.random.RandomState,
    *,
    session: Optional[ClientSession] = None,
    request_timeout: float = 2.0,
) -> int:
    """Send Poisson(``rate``) arrivals to ``gateway_url`` for ``duration`` seconds and
    return the number dispatched. Outcomes are ignored (the gateway's counters are the
    source of truth); this only paces arrivals."""
    own_session = session is None
    if session is None:
        session = ClientSession(timeout=ClientTimeout(total=request_timeout))

    tasks: list[asyncio.Task] = []
    sent = 0
    start = time.monotonic()
    next_t = start
    try:
        while True:
            next_t += rng.exponential(1.0 / rate) if rate > 0 else duration
            now = time.monotonic()
            if next_t - start >= duration:
                break
            if next_t > now:
                await asyncio.sleep(next_t - now)
            tasks.append(asyncio.create_task(_fire(session, gateway_url)))
            sent += 1
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
    finally:
        if own_session:
            await session.close()
    return sent


async def _fire(session: ClientSession, url: str) -> None:
    try:
        async with session.post(url) as resp:
            await resp.read()
    except Exception:
        pass
