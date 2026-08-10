"""
Derive the cross-layer edges L = C union B by joining provenance and enactment with Gamma.
"""

from __future__ import annotations
from typing import FrozenSet, Set, Tuple
from ccd.discovery.attack.build_gamma import GammaConstruction
from ccd.discovery.descriptor import Descriptor

CrossEdge = Tuple[FrozenSet[str], str]


def build_l(desc: Descriptor, gamma: GammaConstruction) -> Tuple[FrozenSet[CrossEdge], FrozenSet[CrossEdge]]:
    """Return ``(C, B)`` for ``desc`` given the constructed ``gamma``."""
    capability: Set[CrossEdge] = set()
    for host in desc.hosts:
        if host.privilege_node is None:
            continue
        for var in host.produces_vars:
            capability.add((frozenset({host.privilege_node}), var))

    blocking: Set[CrossEdge] = set()
    for exploit_id, meta in gamma.exploit_meta.items():
        link_var = meta.get("link_var")
        if link_var is not None:
            blocking.add((frozenset({link_var}), exploit_id))

    return frozenset(capability), frozenset(blocking)
