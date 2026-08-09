"""
Derive the cross-layer edges L = C union B by joining provenance and enactment with Gamma.

- **C** (capability edges): for each privilege-bearing host and each var it ``produces``,
  emit ``(frozenset({host.privilege_node}), var)`` -- holding the privilege confers control
  of that attacker-controlled variable. Reproduces the IT ``({P_i}, Tt_i)`` set.
- **B** (blocking edges): for each fired exploit that a ``link_var`` gates, emit
  ``(frozenset({link_var}), E)`` -- intervening on the (model-side) variable blocks the
  exploit. An exploit with no ``link_var`` (e.g. the foothold) has no blocking edge. The
  ICS ``G2c``/``G2e`` split of the recorded ``G2`` is already model-side here (the split
  lives in the exploit templates' ``link_var``s); the ``name_map`` only renames the
  *dataset* column and is applied during G construction, not here.
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
