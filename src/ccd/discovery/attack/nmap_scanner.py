"""
Live ``nmap -sV`` scanner: the real vulnerability grounding for ``build_gamma``.

Maps each descriptor host to its container IPs and runs an nmap service/version scan over
them (via ``python-nmap``), emitting one :class:`VulnFact` per open service found. It
grounds only the host-exploitability *existence* predicate ``vulHost`` -- a ``netexploit``
template fires when its target exposes some scanned service -- so exact service names need
not match the abstract exploits (the plan's honest framing: nmap sees services/versions,
not exploits). Requires the ``nmap`` system binary and the testbed containers up (their IPs
reachable from where this runs); ``StaticScanner`` is the docker-free CI substitute.
"""

from __future__ import annotations
from typing import TYPE_CHECKING, Callable, Dict, List, Mapping, Optional, Sequence
from ccd.discovery.attack.scanner import ScannerInterface, VulnFact

if TYPE_CHECKING:
    from ccd.discovery.descriptor import Descriptor

# default: service/version detection; -Pn (skip host discovery -- containers often drop
# ping); -T4 for speed on a local bridge. A connect scan works without root.
DEFAULT_ARGUMENTS = "-sV -Pn -T4"


class NmapScanner(ScannerInterface):
    """Grounds host exploitability with a live ``nmap -sV`` over the containers' IPs."""

    def __init__(
        self,
        host_ips: Mapping[str, Sequence[str]],
        *,
        arguments: str = DEFAULT_ARGUMENTS,
        scanner_factory: Optional[Callable[[], object]] = None,
    ):
        self._host_ips = {h: list(ips) for h, ips in host_ips.items()}
        self._arguments = arguments
        self._scanner_factory = scanner_factory

    @classmethod
    def from_descriptor(cls, desc: "Descriptor", **kwargs: object) -> "NmapScanner":
        """Scan every host that has a container and at least one IP."""
        host_ips = {h.id: list(h.ips) for h in desc.hosts if h.container and h.ips}
        return cls(host_ips, **kwargs)  # type: ignore[arg-type]

    def _new_scanner(self) -> object:
        if self._scanner_factory is not None:
            return self._scanner_factory()
        import nmap                                   # deferred: only needed for a live scan
        return nmap.PortScanner()

    def scan(self, hosts: Sequence[str]) -> List[VulnFact]:
        """Run the scan over ``hosts`` (descriptor host ids) and return the open services."""
        ip_to_host: Dict[str, str] = {}
        for host in hosts:
            for ip in self._host_ips.get(host, []):
                ip_to_host[ip] = host
        if not ip_to_host:
            return []

        scanner = self._new_scanner()
        scanner.scan(hosts=" ".join(sorted(ip_to_host)), arguments=self._arguments)  # type: ignore[attr-defined]

        facts: List[VulnFact] = []
        for ip in scanner.all_hosts():                # type: ignore[attr-defined]
            host_id = ip_to_host.get(ip)
            if host_id is None:
                continue
            entry = scanner[ip]                       # type: ignore[index]
            for proto in entry.all_protocols():
                for port, info in entry[proto].items():
                    if info.get("state") != "open":
                        continue
                    version = f"{info.get('product', '')} {info.get('version', '')}".strip()
                    facts.append(VulnFact(
                        host=host_id, service=info.get("name") or proto, port=int(port),
                        vulnerability=version))
        return facts
