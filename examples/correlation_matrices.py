"""
Correlation matrices over the observable variables of the three testbeds' measured
datasets D (``testbeds/<name>/data/dataset.csv``): drop metadata and constant columns,
then write ``correlation_<name>.csv`` and a heatmap ``correlation_<name>.png`` each.

Usage:
  python correlation_matrices.py                       # all three testbeds, Pearson
  python correlation_matrices.py --method spearman
  python correlation_matrices.py --ics-data path.csv --out-dir figs
"""

from __future__ import annotations
import argparse
import os
from typing import List, Literal, cast
import matplotlib

matplotlib.use("Agg")   # headless backend
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Union of the three testbeds' METADATA_COLUMNS; every other dataset column is an
# observable variable (dataset_columns() = sorted throughput_nodes per testbed).
_METADATA_COLUMNS = {"window", "t_start", "duration", "client_ok_rate", "demand"}

_TESTBEDS = [
    ("it", "IT system", os.path.join("testbeds", "it_system", "data", "dataset.csv")),
    ("5g", "5G RAN", os.path.join("testbeds", "5g_ran", "data", "dataset.csv")),
    ("ics", "ICS", os.path.join("testbeds", "ics", "data", "dataset.csv")),
]

# annotate cells with the correlation value only for small matrices (e.g. ICS's 9x9)
_ANNOTATE_MAX_VARS = 15

CorrMethod = Literal["pearson", "spearman"]


def load_observables(path: str, name: str) -> pd.DataFrame:
    """Load a measured dataset, dropping metadata and constant columns (correlation undefined)."""
    if not os.path.isfile(path):
        raise FileNotFoundError(
            f"{name}: no measured dataset at {path} - collect it first with "
            f"'python scripts/testbed.py up' + 'python scripts/generate_dataset.py' "
            f"in the testbed directory.")
    data = pd.read_csv(path)
    observables = data[[c for c in data.columns if c not in _METADATA_COLUMNS]]
    constant = [c for c in observables.columns if observables[c].nunique() <= 1]
    if constant:
        print(f"{name}: dropping {len(constant)} constant column(s): {', '.join(constant)}")
    return observables.drop(columns=constant)


def correlation_matrix(observables: pd.DataFrame, method: CorrMethod) -> pd.DataFrame:
    """Pairwise correlation matrix of the observable variables (``pearson``/``spearman``)."""
    return observables.corr(method=method)


def plot_heatmap(corr: pd.DataFrame, title: str, path: str) -> None:
    """Save a heatmap of the correlation matrix (diverging colormap on [-1, 1])."""
    n = len(corr.columns)
    values = corr.to_numpy()
    side = float(np.clip(0.35 * n + 2.0, 5.0, 22.0))
    fig, ax = plt.subplots(figsize=(side, side * 0.9))
    image = ax.imshow(values, cmap="RdBu_r", vmin=-1.0, vmax=1.0)
    ax.set_xticks(range(n))
    ax.set_yticks(range(n))
    tick_size = 9.0 if n <= _ANNOTATE_MAX_VARS else max(3.0, 9.0 - 0.03 * n)
    ax.set_xticklabels(corr.columns, rotation=90, fontsize=tick_size)
    ax.set_yticklabels(corr.columns, fontsize=tick_size)
    if n <= _ANNOTATE_MAX_VARS:
        for i in range(n):
            for j in range(n):
                value = float(values[i, j])
                color = "white" if abs(value) > 0.6 else "black"
                ax.text(j, i, f"{value:.2f}", ha="center", va="center",
                        fontsize=8, color=color)
    fig.colorbar(image, ax=ax, fraction=0.046, pad=0.04, label="correlation")
    ax.set_title(f"{title}: correlation matrix of the observable variables")
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)
    print(f"Saved plot to {path}")


def run(key: str, title: str, data_path: str, method: CorrMethod, out_dir: str) -> None:
    """Compute and save the correlation matrix (CSV + heatmap) for one testbed."""
    observables = load_observables(data_path, title)
    print(f"{title}: {len(observables)} windows, {len(observables.columns)} observable variables")
    corr = correlation_matrix(observables, method)
    csv_path = os.path.join(out_dir, f"correlation_{key}.csv")
    corr.to_csv(csv_path)
    print(f"Saved matrix to {csv_path}")
    plot_heatmap(corr, title, os.path.join(out_dir, f"correlation_{key}.png"))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Correlation matrices of the observable variables for the three testbeds.")
    parser.add_argument("--it-data", default=os.path.join(_REPO_ROOT, _TESTBEDS[0][2]))
    parser.add_argument("--fiveg-data", default=os.path.join(_REPO_ROOT, _TESTBEDS[1][2]))
    parser.add_argument("--ics-data", default=os.path.join(_REPO_ROOT, _TESTBEDS[2][2]))
    parser.add_argument("--method", choices=["pearson", "spearman"], default="pearson")
    parser.add_argument("--out-dir", default=".")
    args = parser.parse_args()

    os.makedirs(args.out_dir, exist_ok=True)
    paths = {"it": args.it_data, "5g": args.fiveg_data, "ics": args.ics_data}
    errors: List[str] = []
    for key, title, _ in _TESTBEDS:
        print()
        try:
            run(key, title, paths[key], cast(CorrMethod, args.method), args.out_dir)
        except FileNotFoundError as e:
            print(e)
            errors.append(key)
    if errors:
        raise SystemExit(f"missing measured dataset(s) for: {', '.join(errors)}")


if __name__ == "__main__":
    main()
