"""
Window-based measurement engine for the ICS testbed, shared by dataset generation and
Phi validation. Each window: sample demand, command magnitude, and a (mutually
exclusive) nominal operator configuration (likelier degraded at low demand -- the
confounder); enact it; settle; drive the SCADA command stream; read the three services'
/metrics and assemble one dataset row. ``pinned`` variables are held fixed every window
(validation of an enacted mode).
"""

from __future__ import annotations
import random
import time
from dataclasses import dataclass
from typing import Callable, List, Mapping, Optional
import pandas as pd
import ics_lib as il
import icsctl


@dataclass
class WindowConfig:
    windows: int = 600
    window_seconds: float = 6.0
    settle_seconds: float = 3.0
    warmup_seconds: float = 15.0
    seed: int = 0


def _drive_and_measure(state: il.WindowState, window_seconds: float) -> dict:
    """Drive the command stream for one window and read the three services' /metrics."""
    icsctl.drive_command(state.command, window_seconds)
    return {
        "web": icsctl.read_metrics(il.WEB_CONTAINER),
        "control": icsctl.read_metrics(il.CONTROL_CONTAINER),
        "process": icsctl.read_metrics(il.PROCESS_CONTAINER),
    }


def run_windows(
    config: WindowConfig,
    *,
    pinned: Optional[Mapping[str, int]] = None,
    on_row: Optional[Callable[[dict], None]] = None,
) -> pd.DataFrame:
    """Run ``config.windows`` measurement windows and return the collected dataset D.

    ``pinned`` holds the given operator variables fixed every window (validation of an
    enacted mode); ``on_row`` is called with each row (crash-safe incremental writes).
    """
    rng = random.Random(config.seed)
    rows: List[dict] = []

    # warmup: nominal config, discarded, so the control loop and process settle
    icsctl.apply({"W": 1, "G2": 1, "Chat": 1})
    warm = il.sample_window_state(rng, pinned)
    _drive_and_measure(warm, config.warmup_seconds)

    for k in range(config.windows):
        state = il.sample_window_state(rng, pinned)
        icsctl.apply(state.mode())
        time.sleep(config.settle_seconds)

        t_start = time.monotonic()
        metrics = _drive_and_measure(state, config.window_seconds)
        duration = time.monotonic() - t_start

        row = il.assemble_row(
            window=k, t_start=t_start, duration=duration, state=state,
            web_metrics=metrics["web"], control_metrics=metrics["control"],
            process_metrics=metrics["process"],
        )
        rows.append(row)
        if on_row is not None:
            on_row(row)
        if (k + 1) % 25 == 0:
            print(f"  window {k + 1}/{config.windows}  demand={state.demand_frac:4.2f}  "
                  f"I={row['I']:5.1f}  S={row['S']:5.1f}  P={row['P']:6.1f}")

    return pd.DataFrame(rows, columns=il.dataset_columns())
