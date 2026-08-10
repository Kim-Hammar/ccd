"""
Unit tests for the nmap scanner to identify the attack graph
"""

from __future__ import annotations
from ccd.discovery.attack.build_gamma import build_gamma
from ccd.discovery.attack.nmap_scanner import NmapScanner
from ccd.discovery.descriptor import Descriptor, ExploitTemplate, Host, ReachEdge


class _FakePortScanner:
    """A stand-in for ``nmap.PortScanner`` returning canned scan results by IP."""

    def __init__(self, results: dict):
        self._results = results
        self._scanned: dict = {}
        self.scan_calls: list = []

    def scan(self, hosts: str, arguments: str) -> None:
        self.scan_calls.append((hosts, arguments))
        self._scanned = {ip: self._results[ip] for ip in hosts.split() if ip in self._results}

    def all_hosts(self):
        return list(self._scanned)

    def __getitem__(self, ip: str) -> "_FakeHost":
        return _FakeHost(self._scanned[ip])


class _FakeHost:
    def __init__(self, protos: dict):
        self._protos = protos

    def all_protocols(self):
        return list(self._protos)

    def __getitem__(self, proto: str) -> dict:
        return self._protos[proto]


def _scanner(results: dict, host_ips: dict) -> NmapScanner:
    return NmapScanner(host_ips, scanner_factory=lambda: _FakePortScanner(results))


def test_open_services_become_facts_attributed_to_hosts():
    results = {
        "10.0.0.1": {"tcp": {80: {"state": "open", "name": "http", "product": "nginx",
                                  "version": "1.25"},
                             22: {"state": "closed", "name": "ssh"}}},
        "10.0.0.2": {"tcp": {8080: {"state": "open", "name": "http-proxy", "product": ""}}},
    }
    scanner = _scanner(results, {"web": ["10.0.0.1"], "app": ["10.0.0.2"]})
    facts = scanner.scan(["web", "app"])
    by_host = {f.host: f for f in facts}
    assert set(by_host) == {"web", "app"}
    assert by_host["web"].service == "http" and by_host["web"].port == 80
    assert by_host["web"].vulnerability == "nginx 1.25"
    assert len(facts) == 2


def test_scan_targets_only_requested_hosts_ips():
    results = {"10.0.0.1": {"tcp": {80: {"state": "open", "name": "http"}}},
               "10.0.0.9": {"tcp": {80: {"state": "open", "name": "http"}}}}
    scanner = _scanner(results, {"web": ["10.0.0.1"], "other": ["10.0.0.9"]})
    facts = scanner.scan(["web"])
    assert [f.host for f in facts] == ["web"]
    assert scanner._new_scanner  # sanity


def test_hosts_without_ips_scan_nothing():
    scanner = _scanner({}, {"web": []})
    assert scanner.scan(["web", "absent"]) == []


def test_from_descriptor_only_scans_container_hosts():
    desc = Descriptor(
        testbed="t",
        hosts=[Host("attacker", container="", ips=["10.0.0.254"]),
               Host("web", container="c-web", ips=["10.0.0.1"], privilege_node="P1")],
    )
    scanner = NmapScanner.from_descriptor(desc, scanner_factory=lambda: _FakePortScanner(
        {"10.0.0.1": {"tcp": {80: {"state": "open", "name": "http"}}}}))
    facts = scanner.scan(["attacker", "web"])
    assert [f.host for f in facts] == ["web"]


def test_mock_scan_grounds_netexploit_through_build_gamma():
    desc = Descriptor(
        testbed="t",
        hosts=[Host("attacker", container="", role="attacker", privilege_node="P0"),
               Host("web", container="c-web", ips=["10.0.0.1"], privilege_node="P1")],
        reachability=[ReachEdge("attacker", "web", "net", "tcp", 80)],
        exploit_templates=[ExploitTemplate("E1", "P0", "P1", "netexploit",
                                           via_reach_edge=["attacker", "web"],
                                           requires_service="http")],
        attained=["P0"],
        attacker_start_hosts=["attacker"],
    )
    open_scan = NmapScanner.from_descriptor(desc, scanner_factory=lambda: _FakePortScanner(
        {"10.0.0.1": {"tcp": {80: {"state": "open", "name": "http"}}}}))
    gamma = build_gamma(desc, open_scan)
    assert "E1" in gamma.exploits and gamma.graph.has_edge("E1", "P1")

    closed_scan = NmapScanner.from_descriptor(desc, scanner_factory=lambda: _FakePortScanner(
        {"10.0.0.1": {"tcp": {80: {"state": "closed", "name": "http"}}}}))
    gamma_closed = build_gamma(desc, closed_scan)
    assert "E1" not in gamma_closed.exploits
