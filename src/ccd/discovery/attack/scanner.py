"""
Vulnerability-scan interface for grounding the attack graph.
"""

from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING, Dict, List, Optional, Sequence

if TYPE_CHECKING:
    from ccd.discovery.descriptor import Descriptor


@dataclass(frozen=True)
class VulnFact:
    """One scan finding."""

    host: str
    service: str
    port: Optional[int] = None
    vulnerability: str = ""
    privilege_gained: str = ""


class ScannerInterface(ABC):
    """Grounds host exploitability for ``build_gamma``."""

    @abstractmethod
    def scan(self, hosts: Sequence[str]) -> List[VulnFact]:
        """Return the vulnerability facts observed on ``hosts`` (host ids)."""


class StaticScanner(ScannerInterface):
    """A canned-facts scanner (no docker) for CI and reproducible construction."""

    def __init__(self, facts: Sequence[VulnFact]):
        self._facts = list(facts)

    def scan(self, hosts: Sequence[str]) -> List[VulnFact]:
        wanted = set(hosts)
        return [f for f in self._facts if f.host in wanted]

    @classmethod
    def from_descriptor(cls, desc: "Descriptor") -> "StaticScanner":
        """Synthesize the canned facts a ``netexploit`` template's target needs."""
        facts: List[VulnFact] = []
        for tmpl in desc.exploit_templates:
            if tmpl.exploit_class != "netexploit" or tmpl.requires_service is None:
                continue
            dst = tmpl.via_reach_edge[1] if tmpl.via_reach_edge else None
            if dst is None:
                continue
            port = _port_for(desc, tmpl.via_reach_edge)
            facts.append(VulnFact(
                host=dst, service=tmpl.requires_service, port=port,
                vulnerability=f"synthetic-{tmpl.id}", privilege_gained=tmpl.post_privilege))
        return cls(facts)


def _port_for(desc: "Descriptor", reach_edge: Optional[List[str]]) -> Optional[int]:
    """The reachability edge's port, if the descriptor records one for this pair."""
    if not reach_edge:
        return None
    src, dst = reach_edge[0], reach_edge[1]
    ports: Dict[tuple, Optional[int]] = {
        (r.src_host, r.dst_host): r.port for r in desc.reachability}
    return ports.get((src, dst))
