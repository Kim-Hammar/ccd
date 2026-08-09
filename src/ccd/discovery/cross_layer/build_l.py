"""
Derive the cross-layer edges L = C union B by joining provenance and enactment with Gamma.

- **C** (capability edges): for each privilege-bearing host and each var it ``produces``,
  emit ``(frozenset({host.privilege_node}), var)`` -- holding the privilege confers control
  of that attacker-controlled variable. Reproduces the IT ``({P_i}, Tt_i)`` set.
- **B** (blocking edges): for each fired exploit that a ``link_var`` gates, resolve that
  variable through its enactment's ``name_map`` (captures the ICS ``G2c``/``G2e`` split of
  the recorded ``G2``) and emit ``(frozenset({var}), E)`` -- intervening on the variable
  blocks the exploit. An exploit with no ``link_var`` (e.g. the foothold) has no blocking
  edge.
"""

from __future__ import annotations
from typing import Dict, FrozenSet, Set, Tuple
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

    name_map: Dict[str, str] = {
        en.var: en.name_map for en in desc.enactments if en.name_map is not None}
    blocking: Set[CrossEdge] = set()
    for exploit_id, meta in gamma.exploit_meta.items():
        link_var = meta.get("link_var")
        if link_var is None:
            continue
        resolved = name_map.get(link_var, link_var)
        blocking.add((frozenset({resolved}), exploit_id))

    return frozenset(capability), frozenset(blocking)
