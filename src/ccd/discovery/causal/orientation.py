"""
Resolve residual undirected edges by descriptor tier order.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import FrozenSet, List, Mapping, Set, Tuple


@dataclass
class OrientationResult:
    """Oriented edges plus the within-tier undirected edges that could not be resolved."""

    directed: Set[Tuple[str, str]]
    unresolved: List[FrozenSet[str]] = field(default_factory=list)


def orient_by_tier(
    directed: Set[Tuple[str, str]],
    undirected: Set[FrozenSet[str]],
    tier_of: Mapping[str, int],
) -> OrientationResult:
    """Combine already-directed edges with tier-oriented former-undirected edges."""
    result_directed: Set[Tuple[str, str]] = set(directed)
    unresolved: List[FrozenSet[str]] = []
    for pair in undirected:
        u, v = sorted(pair)
        tu, tv = tier_of.get(u), tier_of.get(v)
        if tu is None or tv is None or tu == tv:
            unresolved.append(pair)
            continue
        if tu < tv:
            result_directed.add((u, v))
        else:
            result_directed.add((v, u))
    return OrientationResult(directed=result_directed, unresolved=unresolved)
