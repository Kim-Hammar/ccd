"""
Correlation matrices over the observable variables of the three testbeds' measured datasets D
"""

from __future__ import annotations
import argparse
import os
from typing import List, Literal, Optional, cast
import matplotlib

matplotlib.use("Agg")   # headless backend
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_METADATA_COLUMNS = {"window", "t_start", "duration", "client_ok_rate", "demand"}

_TESTBEDS = [
    ("it", "IT system", os.path.join("testbeds", "it_system", "data", "dataset.csv")),
    ("5g", "5G RAN", os.path.join("testbeds", "5g_ran", "data", "dataset.csv")),
    ("ics", "ICS", os.path.join("testbeds", "ics", "data", "dataset.csv")),
]

_ANNOTATE_MAX_VARS = 15
_IT_CHAIN_COLUMNS = ["W", "L1", "N1", "M1", "Tt1", "Th1", "Th2", "T"]
_FIVEG_CHAIN_COLUMNS = [
    "QI1", "L_1_1_D", "Ladm_1_D", "AT1", "Chat_1_1_D", "NG1", "Ctil_1_1_D", "T_1_D",
]
_ICS_CHAIN_COLUMNS = ["W", "I", "C", "G2", "Ctil", "Chat", "V", "S"]
CorrMethod = Literal["pearson", "spearman"]


def load_observables(path: str, name: str) -> pd.DataFrame:
    """Load a measured dataset, dropping metadata and constant columns."""
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


def select_columns(observables: pd.DataFrame, columns: List[str], flag: str) -> pd.DataFrame:
    """Reindex the observables to ``columns`` (an explicit ordered subset)."""
    missing = [c for c in columns if c not in observables.columns]
    if missing:
        raise SystemExit(f"{flag}: not in the dataset (or constant): {', '.join(missing)}")
    return observables[columns]


def parse_columns(spec: str, chain: List[str], flag: str) -> Optional[List[str]]:
    """Parse a column-subset flag."""
    stripped = spec.strip().lower()
    if stripped == "chain":
        return list(chain)
    if stripped == "all":
        return None
    columns = [part.strip() for part in spec.split(",") if part.strip()]
    if not columns:
        raise SystemExit(f"invalid {flag}: empty column list")
    return columns


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
    ax.set_title(f"{title}:\ncorrelation matrix of the observable variables")
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)
    print(f"Saved plot to {path}")


def run(key: str, title: str, data_path: str, method: CorrMethod, out_dir: str,
        it_columns: Optional[List[str]] = None,
        fiveg_columns: Optional[List[str]] = None,
        ics_columns: Optional[List[str]] = None) -> None:
    """Compute and save the correlation matrix (CSV + heatmap) for one testbed."""
    observables = load_observables(data_path, title)
    if key == "it" and it_columns is not None:
        observables = select_columns(observables, it_columns, "--it-columns")
        suffix = "server-1 chain + Th2" if it_columns == _IT_CHAIN_COLUMNS else "subset"
        title = f"{title} ({suffix})"
    if key == "5g" and fiveg_columns is not None:
        observables = select_columns(observables, fiveg_columns, "--fiveg-columns")
        suffix = "DU-1 downlink chain" if fiveg_columns == _FIVEG_CHAIN_COLUMNS else "subset"
        title = f"{title} ({suffix})"
    if key == "ics" and ics_columns is not None:
        observables = select_columns(observables, ics_columns, "--ics-columns")
        suffix = "P omitted" if ics_columns == _ICS_CHAIN_COLUMNS else "subset"
        title = f"{title} ({suffix})"
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
    parser.add_argument("--it-columns", default="chain",
                        help="column subset for the IT matrix ('chain', 'all', or comma-separated names)")
    parser.add_argument("--fiveg-columns", default="chain",
                        help="column subset for the 5G matrix ('chain', 'all', or comma-separated names)")
    parser.add_argument("--ics-columns", default="chain",
                        help="column subset for the ICS matrix ('chain', 'all', or comma-separated names)")
    args = parser.parse_args()
    it_columns = parse_columns(args.it_columns, _IT_CHAIN_COLUMNS, "--it-columns")
    fiveg_columns = parse_columns(args.fiveg_columns, _FIVEG_CHAIN_COLUMNS, "--fiveg-columns")
    ics_columns = parse_columns(args.ics_columns, _ICS_CHAIN_COLUMNS, "--ics-columns")

    os.makedirs(args.out_dir, exist_ok=True)
    paths = {"it": args.it_data, "5g": args.fiveg_data, "ics": args.ics_data}
    errors: List[str] = []
    for key, title, _ in _TESTBEDS:
        print()
        try:
            run(key, title, paths[key], cast(CorrMethod, args.method), args.out_dir,
                it_columns=it_columns, fiveg_columns=fiveg_columns, ics_columns=ics_columns)
        except FileNotFoundError as e:
            print(e)
            errors.append(key)
    if errors:
        raise SystemExit(f"missing measured dataset(s) for: {', '.join(errors)}")


if __name__ == "__main__":
    main()
