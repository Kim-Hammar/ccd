"""
Window-based measurement engine shared by dataset generation and Phi validation.

Collection runs in phases, one per DU->CU attachment map (a reattach costs a ~30 s
DU+UE restart, so AT_i varies per phase, not per window). Each window: sample demand +
a nominal operator configuration (see ``ran_lib.sample_window_state``), sync the CCD
chains, settle, snapshot the CCDC counters, drive the per-class UDP flows, snapshot
again, and assemble the deltas into one dataset row. ``pinned`` variables are forced
every window (validation holds the enacted mode fixed while the rest toggles nominally);
windows whose counters went backwards (a container restarted) are dropped.
"""

from __future__ import annotations
import json
import random
import subprocess
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Mapping, Optional
import pandas as pd
import ran_lib as rl
import ranctl

# attachment maps cycled through during nominal collection: the identity plus single-DU
# reattachments, giving the Chat/AT mechanisms data support off the nominal attachment
# (incl. AT3=1, the reattachment D_1 uses).
DEFAULT_PHASES: List[Dict[int, int]] = [{}, {3: 1}, {1: 2}, {2: 4}, {4: 3}, {3: 2}]


@dataclass
class WindowConfig:
    windows: int = 600
    window_seconds: float = 6.0
    settle_seconds: float = 2.0
    warmup_seconds: float = 10.0
    seed: int = 0
    phases: List[Dict[int, int]] = field(default_factory=lambda: [dict(p) for p in DEFAULT_PHASES])


def _drive_loadgens(
    state: rl.WindowState,
    pdu_ips: Mapping[int, str],
    duration: float,
) -> Optional[Dict[str, Dict[str, float]]]:
    """Run the UL (per-UE) and DL (sink) load generators concurrently for one window.

    Returns ``{"U": {"i:k": bytes}, "D": {...}}`` of offered payload bytes, or None if
    any generator failed (window dropped).
    """
    procs = []
    for i in range(1, rl.NUM_DU + 1):
        spec = json.dumps(rl.ul_load_spec(i, state, duration))
        procs.append(("U", subprocess.Popen(
            ["docker", "exec", rl.ue_container(i), "python3", "/udp_load.py", spec],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)))
    dl_spec = json.dumps(rl.dl_load_spec(pdu_ips, state, duration))
    procs.append(("D", subprocess.Popen(
        ["docker", "exec", rl.SINK_CONTAINER, "python3", "/udp_load.py", dl_spec],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)))

    sent: Dict[str, Dict[str, float]] = {"U": {}, "D": {}}
    ok = True
    for direction, proc in procs:
        try:
            out, err = proc.communicate(timeout=duration + 30.0)
        except subprocess.TimeoutExpired:
            proc.kill()
            ok = False
            continue
        if proc.returncode != 0:
            print(f"  loadgen failed ({direction}): {err.strip()[:200]}")
            ok = False
            continue
        report = json.loads(out)
        sent[direction].update({k: float(v) for k, v in report["sent_bytes"].items()})
    return sent if ok else None


def _warmup(state: rl.WindowState, pdu_ips: Mapping[int, str], seconds: float) -> None:
    """Drive nominal load briefly (discarded) so the radio/queues settle."""
    if seconds > 0:
        _drive_loadgens(state, pdu_ips, seconds)


def run_windows(
    config: WindowConfig,
    *,
    pinned: Optional[Mapping[str, int]] = None,
    on_row: Optional[Callable[[dict], None]] = None,
) -> pd.DataFrame:
    """Run ``config.windows`` measurement windows (split across the attachment phases)
    and return the collected dataset D.

    ``pinned`` holds the given operator variables fixed every window (validation of an
    enacted mode); its iptables-kind assignments are re-applied through the same nominal
    sync, its AT_i assignments should already be reflected in ``config.phases``.
    ``on_row`` is called with each accepted row (crash-safe incremental writes).
    """
    rng = random.Random(config.seed)
    rows: List[dict] = []
    phases = config.phases
    per_phase = [config.windows // len(phases)] * len(phases)
    for extra in range(config.windows - sum(per_phase)):
        per_phase[extra] += 1

    window = 0
    for phase, n_windows in zip(phases, per_phase):
        at_map = rl.attachment_map(phase)
        print(f"Phase {phases.index(phase) + 1}/{len(phases)}: attachment {at_map}, "
              f"{n_windows} windows")
        # open every link first: a stale closure must not outlive its window, and the
        # reattachment needs a reachable core (a leftover NG DROP would cut the target
        # CU from the AMF and block the UE's re-registration indefinitely)
        ranctl.reset()
        ranctl.apply_attachment(at_map)
        ranctl.setup()
        pdu_ips = ranctl.ensure_attached(at_map)
        warm_state = rl.sample_window_state(rng, at_map, pinned)
        _warmup(warm_state, pdu_ips, config.warmup_seconds)

        for _ in range(n_windows):
            pdu_ips = ranctl.ensure_attached(at_map)
            state = rl.sample_window_state(rng, at_map, pinned)
            ranctl.apply(state.mode())
            time.sleep(config.settle_seconds)

            before = ranctl.snapshot()
            t_start = time.monotonic()
            sent = _drive_loadgens(state, pdu_ips, config.window_seconds)
            duration = time.monotonic() - t_start
            after = ranctl.snapshot()

            row = None
            if sent is not None:
                row = rl.assemble_row(window=window, t_start=t_start, duration=duration,
                                      state=state, sent_bytes=sent, before=before, after=after)
            if row is None:
                print(f"  window {window}: dropped (loadgen failure or counter reset)")
            else:
                rows.append(row)
                if on_row is not None:
                    on_row(row)
                if (window + 1) % 25 == 0:
                    total_t = sum(row[f"T_{i}_{d}"] for i in range(1, rl.NUM_DU + 1)
                                  for d in rl.DIRECTIONS)
                    print(f"  window {window + 1}/{config.windows}  "
                          f"demand={state.demand_frac:4.2f}  sum T={total_t:6.2f} Mbit/s")
            window += 1

    return pd.DataFrame(rows, columns=rl.dataset_columns())
