"""
Runs the scalability evaluation of CCD mode selection (graph-only ``select_intervention``,
no inference) across three families of two-layer models of growing size:

- ``it``        -- IllustrativeExampleSystem(m): both layers grow linearly in m.
- ``5g``        -- FiveGSystem(num_du=D, num_cu=D): a denser causal graph (~D^2 midhaul
                   nodes), fixed attack graph.
- ``synthetic`` -- random_system(n): Erdos-Renyi random two-layer models, decoupled from
                   the hand-crafted examples, pushed to thousands of nodes.

All three are plotted on one axis (time vs two-layer graph size) with a quadratic
reference fitted on the synthetic series (the widest, cleanest O(n^2) sweep).

Usage: python scalability.py [max_m]     # optional cap on the IT sweep's m (default 500)
"""

from __future__ import annotations
import sys
import time
from typing import Callable, List, Tuple
import matplotlib

matplotlib.use("Agg")   # headless backend
import matplotlib.pyplot as plt
import numpy as np
from ccd.ccd import select_intervention
from ccd.system.illustrative_example_system import IllustrativeExampleSystem
from ccd.system.five_g_system import FiveGSystem
from ccd.system.system_model import SystemModel
from ccd.util.synthetic import random_system

_REPEATS = 5   # per point; report the best (min) time to reduce OS/GC noise
_M_VALUES = [2, 5, 10, 25, 50, 75, 100, 150, 200, 300, 400, 500]   # IT: |graph| ~ 10m+5
_FIVEG_SIZES = [4, 6, 8, 12, 16, 24, 32]                           # 5G: D = C (bilinear D*C)
_SYNTH_SIZES = [50, 100, 200, 400, 800, 1600, 3200]               # synthetic: |graph| ~ 2n
_SYNTH_SEEDS = 3

_SERIES_STYLE = {   # (color, marker, human label)
    "it": ("tab:blue", "o", "IT (illustrative), sweep $m$"),
    "5g": ("tab:green", "s", "5G cloud-RAN, sweep DUs/CUs"),
    "synthetic": ("tab:purple", "^", "synthetic Erdos-Renyi, sweep $n$"),
}


def _best_time(system: SystemModel, repeats: int = _REPEATS) -> float:
    """Best-of-``repeats`` wall-clock of ``select_intervention`` (after a warm-up)."""
    select_intervention(system)                    # warm-up (imports/JIT/caches)
    best = float("inf")
    for _ in range(repeats):
        start = time.perf_counter()
        select_intervention(system)
        best = min(best, time.perf_counter() - start)
    return best


def _graph_size(system: SystemModel) -> int:
    return system.graph.number_of_nodes() + system.attack_graph.number_of_nodes()


def sweep(build: Callable[[int], SystemModel], params: List[int],
          label: str) -> Tuple[np.ndarray, np.ndarray]:
    """Time ``select_intervention`` across ``params``; returns (graph_sizes, best_times)."""
    sizes, times = [], []
    for param in params:
        system = build(param)
        size, secs = _graph_size(system), _best_time(system)
        sizes.append(size)
        times.append(secs)
        print(f"  {label:10s} param={param:5d}  |V u U|+|P u E|={size:6d}  "
              f"CCD mode-selection = {secs:10.4f} s")
    return np.array(sizes), np.array(times)


def sweep_synthetic(sizes_n: List[int], seeds: int = _SYNTH_SEEDS) -> Tuple[np.ndarray, np.ndarray]:
    """Synthetic sweep: best time over ``seeds`` random models per n (their sizes coincide)."""
    sizes, times = [], []
    for n in sizes_n:
        best = float("inf")
        size = 0
        for seed in range(seeds):
            system = random_system(n, seed=seed)
            size = _graph_size(system)
            best = min(best, _best_time(system))
        sizes.append(size)
        times.append(best)
        print(f"  {'synthetic':10s} n={n:5d}  |V u U|+|P u E|={size:6d}  "
              f"CCD mode-selection = {best:10.4f} s")
    return np.array(sizes), np.array(times)


def plot(series: dict, coeffs: np.ndarray, path: str = "scalability.png") -> None:
    fig, ax = plt.subplots(figsize=(7.5, 5.0))
    all_sizes = np.concatenate([s for s, _ in series.values()])
    xs = np.linspace(all_sizes.min(), all_sizes.max(), 300)
    ax.plot(xs, np.polyval(coeffs, xs), "--", color="tab:orange", linewidth=1.8,
            label=r"quadratic fit  $O(n^2)$", zorder=1)
    for name, (sizes, times) in series.items():
        color, marker, label = _SERIES_STYLE[name]
        ax.plot(sizes, times, marker + "-", color=color, markersize=6, linewidth=1.5,
                label=label, zorder=2)

    ax.set_xlabel(r"Two-layer graph size  $|\mathbf{V} \cup \mathbf{U}| + |\mathbf{P} \cup \mathbf{E}|$")
    ax.set_ylabel("CCD computation time [s]")
    ax.set_title("Scalability of CCD mode selection")
    ax.grid(True, alpha=0.3)
    ax.legend(frameon=False)
    ax.margins(x=0.02)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    print(f"\nSaved plot to {path}")


def write_csv(series: dict, path: str = "scalability.csv") -> None:
    """Long-format CSV: one row per (system, graph_size) with the mode-selection time."""
    lines = ["system,graph_size,time_s"]
    for name, (sizes, times) in series.items():
        lines += [f"{name},{int(s)},{t:.6f}" for s, t in zip(sizes, times)]
    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")
    print(f"Saved data to {path}")


_PGF_MACROS = {"it": "\\ccdscalit", "5g": "\\ccdscalfiveg", "synthetic": "\\ccdscalsynth"}


def write_pgf(series: dict, coeffs: np.ndarray, path: str = "scalability.tex") -> None:
    """pgfplots tables: one ``\\pgfplotstableread{...}\\macro`` per model family
    (columns ``size time``) plus a quadratic reference ``\\ccdscalfit``."""
    lines = [
        "% CCD mode-selection scalability: time [s] vs two-layer graph size",
        "% |V u U| + |P u E|.  One table per model family + a quadratic reference.",
    ]
    for name, (sizes, times) in series.items():
        lines.append(f"% --- {name} ---")
        lines.append("\\pgfplotstableread{")
        lines.append("size time")
        lines += [f"{int(s)} {t:.6f}" for s, t in zip(sizes, times)]
        lines.append(f"}}{_PGF_MACROS[name]}")
        lines.append("")
    all_sizes = np.concatenate([s for s, _ in series.values()])
    xs = np.linspace(all_sizes.min(), all_sizes.max(), 200)
    lines += ["% --- quadratic fit O(n^2) ---", "\\pgfplotstableread{", "size fit"]
    lines += [f"{x:.3f} {y:.6f}" for x, y in zip(xs, np.polyval(coeffs, xs))]
    lines.append("}\\ccdscalfit")
    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")
    print(f"Saved pgfplots tables to {path}")


def main() -> None:
    m_values = _M_VALUES
    if len(sys.argv) > 1:
        max_m = int(sys.argv[1])
        m_values = [m for m in _M_VALUES if m <= max_m] or [max_m]

    print("IT sweep (illustrative system):")
    it = sweep(lambda m: IllustrativeExampleSystem(m), m_values, "it")
    print("5G sweep (D = C):")
    fiveg = sweep(lambda d: FiveGSystem(num_du=d, num_cu=d), _FIVEG_SIZES, "5g")
    print("synthetic sweep (Erdos-Renyi):")
    synthetic = sweep_synthetic(_SYNTH_SIZES)

    series = {"it": it, "5g": fiveg, "synthetic": synthetic}
    # quadratic reference fitted on the synthetic series (widest, cleanest O(n^2) sweep)
    coeffs = np.polyfit(synthetic[0], synthetic[1], 2)
    plot(series, coeffs)
    write_csv(series)
    write_pgf(series, coeffs)


if __name__ == "__main__":
    main()
