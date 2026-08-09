"""
Structural comparison of a constructed graph/edge-set against a hand-built target.

Reports edge precision/recall/F1 and (typed) isomorphism for the directed graphs G and
Gamma, and exact set-difference for the cross-layer edge sets C and B. This module is
pure graph/set math -- it takes already-extracted graphs and frozenset edge collections,
so it does not import ``ccd.system`` (the acceptance harness does that and hands the
pieces in).
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import FrozenSet, List, Set, Tuple
import networkx as nx

CrossEdge = Tuple[FrozenSet[str], str]


@dataclass
class EdgeDiff:
    """Precision/recall/F1 of a constructed edge set vs a target, with the discrepancies."""

    n_target: int
    n_constructed: int
    true_positive: int
    precision: float
    recall: float
    f1: float
    missing: List[Tuple[str, str]] = field(default_factory=list)      # in target, not built
    extra: List[Tuple[str, str]] = field(default_factory=list)        # built, not in target
    isomorphic: bool = False

    @property
    def exact(self) -> bool:
        return not self.missing and not self.extra


def _prf(target: Set, constructed: Set) -> Tuple[int, float, float, float]:
    tp = len(target & constructed)
    precision = tp / len(constructed) if constructed else (1.0 if not target else 0.0)
    recall = tp / len(target) if target else (1.0 if not constructed else 0.0)
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    return tp, precision, recall, f1


def diff_graphs(constructed: nx.DiGraph, target: nx.DiGraph) -> EdgeDiff:
    """Compare two directed graphs edge-wise (over the union of their nodes)."""
    c_edges = set(constructed.edges())
    t_edges = set(target.edges())
    tp, precision, recall, f1 = _prf(t_edges, c_edges)
    return EdgeDiff(
        n_target=len(t_edges), n_constructed=len(c_edges), true_positive=tp,
        precision=precision, recall=recall, f1=f1,
        missing=sorted(t_edges - c_edges), extra=sorted(c_edges - t_edges),
        isomorphic=nx.is_isomorphic(constructed, target))


def diff_cross_edges(constructed: FrozenSet[CrossEdge], target: FrozenSet[CrossEdge]) -> EdgeDiff:
    """Exact set-diff of cross-layer edges C or B (each ``(frozenset(reqs), var)``)."""
    c_set, t_set = set(constructed), set(target)
    tp, precision, recall, f1 = _prf(t_set, c_set)
    return EdgeDiff(
        n_target=len(t_set), n_constructed=len(c_set), true_positive=tp,
        precision=precision, recall=recall, f1=f1,
        missing=sorted(_fmt(e) for e in t_set - c_set),
        extra=sorted(_fmt(e) for e in c_set - t_set),
        isomorphic=(c_set == t_set))


def _fmt(edge: CrossEdge) -> Tuple[str, str]:
    reqs, var = edge
    return ("{" + ",".join(sorted(reqs)) + "}", var)
