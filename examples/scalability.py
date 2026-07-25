"""
Runs the scalability evaluation of CCD.

Usage: python scalability.py [max_m]     # default sweep up to m = 500
"""

from __future__ import annotations
import sys
import time
from typing import List, Tuple
import matplotlib

matplotlib.use("Agg")   # headless backend
import matplotlib.pyplot as plt
import numpy as np
from ccd.ccd import select_intervention
from ccd.system.illustrative_example_system import IllustrativeExampleSystem

# server counts to sweep; two-layer graph size (|V u U| = 8m+2, |P u E| = 2m+3) is linear in m
_M_VALUES = [2, 5, 10, 25, 50, 75, 100, 150, 200, 300, 400, 500]
_REPEATS = 5   # per point; report the best (min) time to reduce OS/GC noise


def measure(m: int, repeats: int = _REPEATS) -> Tuple[int, float]:
    """Return (graph_size, best_seconds) for CCD mode selection on ``IllustrativeExampleSystem(m)``."""
    system = IllustrativeExampleSystem(m)
    graph_size = system.graph.number_of_nodes() + system.attack_graph.number_of_nodes()
    select_intervention(system)                    # warm-up run
    best = float("inf")
    for _ in range(repeats):
        start = time.perf_counter()
        select_intervention(system)
        best = min(best, time.perf_counter() - start)
    return graph_size, best


def run_sweep(m_values: List[int]) -> Tuple[np.ndarray, np.ndarray]:
    sizes, times = [], []
    for m in m_values:
        size, secs = measure(m)
        sizes.append(size)
        times.append(secs)
        print(f"m={m:4d}  |V u U| + |P u E|={size:5d}  CCD mode-selection = {secs:10.4f} s")
    return np.array(sizes), np.array(times)


def plot(sizes: np.ndarray, times_s: np.ndarray, coeffs: np.ndarray,
         path: str = "scalability.png") -> None:
    xs = np.linspace(sizes.min(), sizes.max(), 200)
    fit = np.polyval(coeffs, xs)

    fig, ax = plt.subplots(figsize=(7.5, 5.0))
    ax.plot(xs, fit, "--", color="tab:orange", linewidth=1.8,
            label=r"quadratic fit  $O(n^2)$", zorder=1)
    ax.plot(sizes, times_s, "o-", color="tab:blue", markersize=6, linewidth=1.5,
            label="measured (CCD mode selection)", zorder=2)

    ax.set_xlabel(r"Two-layer graph size  $|\mathbf{V} \cup \mathbf{U}| + |\mathbf{P} \cup \mathbf{E}|$")
    ax.set_ylabel("CCD computation time [s]")
    ax.set_title("Scalability of CCD mode selection")
    ax.grid(True, alpha=0.3)
    ax.legend(frameon=False)
    ax.margins(x=0.02)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    print(f"\nSaved plot to {path}")


def write_csv(sizes: np.ndarray, times_s: np.ndarray, coeffs: np.ndarray,
              path: str = "scalability.csv") -> None:
    """Write the scalability data as CSV: one row per measured graph size with the
    CCD mode-selection time and the O(n^2) least-squares fit evaluated at that size.
    ``size`` = two-layer graph size |V u U| + |P u E|, ``time_s`` in seconds."""
    lines = ["size,time_s,quadratic_fit"]
    fit = np.polyval(coeffs, sizes)
    lines += [f"{int(s)},{t:.6f},{f:.6f}" for s, t, f in zip(sizes, times_s, fit)]
    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")
    print(f"Saved data to {path}")


def main() -> None:
    m_values = _M_VALUES
    if len(sys.argv) > 1:
        max_m = int(sys.argv[1])
        m_values = [m for m in _M_VALUES if m <= max_m] or [max_m]
    sizes, times_s = run_sweep(m_values)
    # least-squares quadratic reference (the complexity bound is quadratic in graph size)
    coeffs = np.polyfit(sizes, times_s, 2)
    plot(sizes, times_s, coeffs)
    write_csv(sizes, times_s, coeffs)


if __name__ == "__main__":
    main()
