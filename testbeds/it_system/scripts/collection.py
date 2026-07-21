"""
Window-based measurement engine shared by dataset generation and Phi validation.

Each window: sample a workload W (fluctuating around 100 req/s) and per-link states
(closed with probability ``p_close(W)``, more likely at low load -- the confounder),
synchronize the links, let the system settle, snapshot every ``/metrics`` endpoint,
drive Poisson load for the measure interval, snapshot again, and turn the counter
deltas into one dataset row. Links listed in ``pinned`` are forced (used by validation
to hold the enacted degraded mode fixed while the other links keep toggling nominally).
"""

from __future__ import annotations
import asyncio
import json
import time
import urllib.request
from dataclasses import dataclass
from typing import Callable, Dict, List, Mapping, Optional
import numpy as np
import pandas as pd
from aiohttp import ClientSession, ClientTimeout
import testbed_lib as tl
import linkctl
import loadgen


@dataclass
class WindowConfig:
    m: int
    windows: int = 600
    window_seconds: float = 6.0
    settle_seconds: float = 2.0
    w_low: float = 50.0
    w_high: float = 150.0
    seed: int = 0


def _metrics(url: str, timeout: float = 2.0) -> dict:
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def _snapshot(m: int) -> dict:
    """One atomic-per-endpoint snapshot of the gateway and every server's counters."""
    gw = _metrics(f"http://localhost:{tl.GATEWAY_HOST_PORT}/metrics")
    servers = {i: _metrics(f"http://localhost:{tl.SERVER_HOST_PORT_BASE + i}/metrics")
               for i in range(1, m + 1)}
    return {"t": time.monotonic(), "gw": gw, "servers": servers}


def _sample_links(m: int, w: float, rng: np.random.RandomState,
                  pinned: Mapping[str, int]) -> Dict[str, int]:
    """Nominal link states for a window: each N_i/M_i closed w.p. p_close(w); A_i open.
    Pinned links (the enacted mode) override the sample."""
    p = tl.p_close(w)
    state: Dict[str, int] = {}
    for i in range(1, m + 1):
        state[f"N{i}"] = int(rng.uniform() >= p)
        state[f"M{i}"] = int(rng.uniform() >= p)
    for i in range(2, m + 1):
        state[f"A{i}"] = 1
    state.update(pinned)
    return state


def _row(m: int, window: int, w_target: float, links: Mapping[str, int],
         before: dict, after: dict) -> Optional[dict]:
    """Turn a pair of counter snapshots into one dataset row, or None on a counter reset."""
    duration = after["t"] - before["t"]
    if duration <= 0:
        return None
    gw_att = np.array(after["gw"]["attempted"]) - np.array(before["gw"]["attempted"])
    gw_ok = np.array(after["gw"]["ok"]) - np.array(before["gw"]["ok"])
    if (gw_att < 0).any() or (gw_ok < 0).any():
        return None   # gateway restarted mid-window

    row: Dict[str, float] = {"window": window, "t_start": before["t"], "duration": duration}
    total = 0.0
    for i in range(1, m + 1):
        sb, sa = before["servers"][i], after["servers"][i]
        tt = sa["requests_completed_db"] - sb["requests_completed_db"]
        if tt < 0:
            return None   # server restarted mid-window
        th = float(gw_ok[i - 1])
        row[f"L{i}"] = float(gw_att[i - 1]) / duration
        row[f"N{i}"] = links[f"N{i}"]
        row[f"M{i}"] = links[f"M{i}"]
        row[f"Tt{i}"] = tt / duration
        row[f"Th{i}"] = th / duration
        total += th
    row["W"] = float(gw_att.sum()) / duration
    row["T"] = total / duration
    row["client_ok_rate"] = float(gw_ok.sum()) / duration
    return row


def run_windows(
    config: WindowConfig,
    *,
    pinned: Optional[Mapping[str, int]] = None,
    on_row: Optional[Callable[[dict], None]] = None,
) -> pd.DataFrame:
    """Run ``config.windows`` measurement windows and return the collected dataset D.

    ``pinned`` holds the given links fixed every window (validation of an enacted mode).
    ``on_row`` is called with each accepted row (used for crash-safe incremental writes).
    """
    pinned = pinned or {}
    rng = np.random.RandomState(config.seed)
    gateway_url = f"http://localhost:{tl.GATEWAY_HOST_PORT}/work"
    rows: List[dict] = []

    async def _drive(rate: float, duration: float, seed: int) -> None:
        timeout = ClientTimeout(total=2.0)
        async with ClientSession(timeout=timeout) as session:
            await loadgen.drive(gateway_url, rate, duration,
                                np.random.RandomState(seed), session=session)

    for k in range(config.windows):
        w = float(rng.uniform(config.w_low, config.w_high))
        links = _sample_links(config.m, w, rng, pinned)
        linkctl.apply(links, config.m)
        time.sleep(config.settle_seconds)

        before = _snapshot(config.m)
        asyncio.run(_drive(w, config.window_seconds, int(rng.randint(2**31))))
        after = _snapshot(config.m)

        row = _row(config.m, k, w, links, before, after)
        if row is None:
            print(f"  window {k}: counter reset detected, skipping")
            continue
        rows.append(row)
        if on_row is not None:
            on_row(row)
        if (k + 1) % 25 == 0:
            print(f"  window {k + 1}/{config.windows}  W~{w:5.1f}  T={row['T']:6.1f} req/s")

    return pd.DataFrame(rows, columns=tl.dataset_columns(config.m))
