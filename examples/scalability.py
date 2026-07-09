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
from ccd.illustrative_example_system import IllustrativeExampleSystem

# server counts to sweep; graph size |V u U u E| = 10*m + 3
_M_VALUES = [2, 5, 10, 25, 50, 75, 100, 150, 200, 300, 400, 500]
_REPEATS = 5   # per point; report the best (min) time to reduce OS/GC noise


def measure(m: int, repeats: int = _REPEATS) -> Tuple[int, float]:
    """Return (graph_size, best_seconds) for CCD mode selection on ``IllustrativeExampleSystem(m)``."""
    system = IllustrativeExampleSystem(m)
    graph_size = system.graph.number_of_nodes()   # |V u U u E|
    select_intervention(system)                    # warm up (import/JIT-free, but caches)
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
        times.append(secs)   # seconds
        print(f"m={m:4d}  |V u U u E|={size:5d}  CCD mode-selection = {secs:10.4f} s")
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

    ax.set_xlabel(r"Causal graph size  $|\mathbf{V} \cup \mathbf{U} \cup \mathbf{E}|$")
    ax.set_ylabel("CCD computation time [s]")
    ax.set_title("Scalability of CCD mode selection")
    ax.grid(True, alpha=0.3)
    ax.legend(frameon=False)
    ax.margins(x=0.02)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    print(f"\nSaved plot to {path}")


def write_pgf_tables(sizes: np.ndarray, times_s: np.ndarray, coeffs: np.ndarray,
                     path: str = "scalability_tables.tex") -> None:
    """Write pgfplots tables (empirical + quadratic fit) for use in a LaTeX document.

    Emits two ``\\pgfplotstableread{...}\\macro`` blocks: ``\\ccdtime`` (the measured CCD
    mode-selection time) and ``\\ccdquadraticfit`` (the least-squares quadratic fit,
    O(n^2)). In both, x is the causal graph size |V u U u E| and y is time in seconds.
    """
    xs_fit = np.linspace(sizes.min(), sizes.max(), 200)
    ys_fit = np.polyval(coeffs, xs_fit)

    lines = [
        "% CCD scalability data for pgfplots.",
        "% x = causal graph size |V u U u E|,  y = CCD mode-selection time [s].",
        "",
        "% --- empirical measurements ---",
        "\\pgfplotstableread{",
    ]
    lines += [f"{int(s)} {t:.6f}" for s, t in zip(sizes, times_s)]
    lines += ["}\\ccdtime", "", "% --- quadratic fit  O(n^2) ---", "\\pgfplotstableread{"]
    lines += [f"{x:.6f} {y:.6f}" for x, y in zip(xs_fit, ys_fit)]
    lines += ["}\\ccdquadraticfit", ""]

    with open(path, "w") as f:
        f.write("\n".join(lines))
    print(f"Saved pgfplots tables to {path}")


def main() -> None:
    m_values = _M_VALUES
    if len(sys.argv) > 1:
        max_m = int(sys.argv[1])
        m_values = [m for m in _M_VALUES if m <= max_m] or [max_m]
    sizes, times_s = run_sweep(m_values)
    # least-squares quadratic reference (paper's bound is quadratic in graph size)
    coeffs = np.polyfit(sizes, times_s, 2)
    plot(sizes, times_s, coeffs)
    write_pgf_tables(sizes, times_s, coeffs)


if __name__ == "__main__":
    main()
