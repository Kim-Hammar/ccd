"""
Scalability evaluation of CCD's causal-inference step.

Usage: python inference_scalability.py
"""

from __future__ import annotations

import time
from typing import Dict, List, Tuple

import matplotlib

matplotlib.use("Agg")   # headless backend
import matplotlib.pyplot as plt
import numpy as np

from dowhy.gcm.config import disable_progress_bars

from ccd.inference import estimate_phi
from ccd.simulator import generate_dataset
from ccd.illustrative_example_system import IllustrativeExampleSystem

disable_progress_bars()

_M_VALUES = [5, 10, 20, 40]                      # -> graph sizes 53, 103, 203, 403
_DATASET_SIZES = [500, 1000, 2000, 4000, 8000]   # |D|, number of rows
_DO: Dict[str, int] = {"N1": 0, "M1": 0}         # throughput-relevant links of the degraded mode
_REPEATS = 2                                      # per point; report the best (min) time
_MACROS = ["\\ccdinfsmall", "\\ccdinfmedium", "\\ccdinflarge", "\\ccdinfxlarge"]
_COLORS = ["tab:blue", "tab:orange", "tab:green", "tab:red"]


def measure(system: IllustrativeExampleSystem, size: int, repeats: int = _REPEATS) -> float:
    """Best-of-``repeats`` seconds to estimate Phi from a dataset of ``size`` rows."""
    data = generate_dataset(system, steps=size, seed=0)
    graph = system.throughput_graph()
    best = float("inf")
    for _ in range(repeats):
        start = time.perf_counter()
        estimate_phi(data, graph, _DO, num_samples=size)
        best = min(best, time.perf_counter() - start)
    return best


def run_sweep() -> Tuple[List[int], List[np.ndarray]]:
    """Return (graph_sizes, [times_per_curve]); times aligned with ``_DATASET_SIZES``."""
    graph_sizes, curves = [], []
    for m in _M_VALUES:
        system = IllustrativeExampleSystem(m)
        n = system.graph.number_of_nodes()
        graph_sizes.append(n)
        times = []
        for size in _DATASET_SIZES:
            secs = measure(system, size)
            times.append(secs)
            print(f"|V u U u E|={n:4d}  |D|={size:5d}  inference = {secs:7.3f} s")
        curves.append(np.array(times))
    return graph_sizes, curves


def plot(graph_sizes: List[int], curves: List[np.ndarray],
         path: str = "inference_scalability.png") -> None:
    xs = np.array(_DATASET_SIZES)
    fig, ax = plt.subplots(figsize=(7.5, 5.0))
    for n, times, color in zip(graph_sizes, curves, _COLORS):
        ax.plot(xs, times, "o-", color=color, markersize=6, linewidth=1.6,
                label=fr"$|\mathbf{{V}} \cup \mathbf{{U}} \cup \mathbf{{E}}| = {n}$")
    ax.set_xlabel(r"Dataset size  $|\mathcal{D}|$  (rows)")
    ax.set_ylabel("Causal-inference time [s]")
    ax.set_title("Scalability of CCD's causal-inference step")
    ax.grid(True, alpha=0.3)
    ax.legend(frameon=False, title="causal graph size")
    ax.margins(x=0.02)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    print(f"\nSaved plot to {path}")


def write_pgf_tables(graph_sizes: List[int], curves: List[np.ndarray],
                     path: str = "inference_scalability_tables.tex") -> None:
    """Write one pgfplots table per curve (x = dataset size |D|, y = inference time [s])."""
    lines = [
        "% CCD causal-inference scalability data for pgfplots.",
        "% x = dataset size |D| (rows),  y = causal-inference time [s].",
        "",
    ]
    for n, times, macro in zip(graph_sizes, curves, _MACROS):
        lines.append(f"% --- causal graph size |V u U u E| = {n} ---")
        lines.append("\\pgfplotstableread{")
        lines += [f"{int(size)} {t:.6f}" for size, t in zip(_DATASET_SIZES, times)]
        lines += [f"}}{macro}", ""]

    with open(path, "w") as f:
        f.write("\n".join(lines))
    print(f"Saved pgfplots tables to {path}")


def main() -> None:
    graph_sizes, curves = run_sweep()
    plot(graph_sizes, curves)
    write_pgf_tables(graph_sizes, curves)


if __name__ == "__main__":
    main()
