"""
Attack-layer (Gamma) and cross-layer (L = C union B) construction tests for the IT
testbed. Docker-free: uses the ``StaticScanner`` canned facts, so no live nmap / running
containers are needed.
"""

from __future__ import annotations
import pytest
from ccd.discovery.attack.build_gamma import build_gamma
from ccd.discovery.attack.datalog_rules import derive
from ccd.discovery.attack.scanner import StaticScanner, VulnFact
from ccd.discovery.cross_layer.build_l import build_l
from ccd.discovery.evaluation.graph_diff import diff_cross_edges, diff_graphs
from ccd.system.it_testbed_system import ITTestbedSystem


@pytest.fixture(scope="module")
def it_descriptor(testbed_loader):
    return testbed_loader("it_system", "descriptor").build_descriptor(10)


def test_static_scanner_grounds_netexploits_only(it_descriptor):
    scanner = StaticScanner.from_descriptor(it_descriptor)
    facts = scanner.scan([h.id for h in it_descriptor.hosts if h.container])
    # one fact per netexploit target (server1 foothold + servers 2..10 lateral) -> 10 hosts
    hosts = {f.host for f in facts}
    assert hosts == {f"server{i}" for i in range(1, 11)}
    # the credreuse DB move is NOT scan-grounded
    assert "db" not in hosts


def test_derive_reaches_full_chain(it_descriptor):
    scanner = StaticScanner.from_descriptor(it_descriptor)
    facts = scanner.scan([h.id for h in it_descriptor.hosts if h.container])
    result = derive(it_descriptor, facts)
    assert result.fired == {f"E{i}" for i in range(1, 12)}      # E1..E11
    assert "db" in result.compromised and "server5" in result.compromised


def test_credreuse_needs_no_scan_but_netexploit_does(it_descriptor):
    # empty scan: the netexploit moves (foothold E1, laterals E2..E10) cannot fire, but the
    # DB credreuse E11 still fires from the already-attained P1 -- credreuse needs no scan.
    result = derive(it_descriptor, [])
    assert "E1" not in result.fired
    assert not any(f"E{i}" in result.fired for i in range(2, 11))
    assert result.fired == {"E11"}
    # grounding server1's service lets the foothold fire (and the full chain follows)
    result = derive(it_descriptor, [VulnFact(host="server1", service="http")])
    assert "E1" in result.fired


def test_gamma_isomorphic_to_target(it_descriptor):
    gamma = build_gamma(it_descriptor, StaticScanner.from_descriptor(it_descriptor))
    diff = diff_graphs(gamma.graph, ITTestbedSystem(10).attack_graph)
    assert diff.isomorphic and diff.exact
    assert gamma.privileges == {f"P{i}" for i in range(0, 12)}
    assert gamma.exploits == {f"E{i}" for i in range(1, 12)}


def test_cross_layer_edges_exact(it_descriptor):
    gamma = build_gamma(it_descriptor, StaticScanner.from_descriptor(it_descriptor))
    capability, blocking = build_l(it_descriptor, gamma)
    target = ITTestbedSystem(10)
    assert diff_cross_edges(capability, target.capability_edges).exact
    assert diff_cross_edges(blocking, target.blocking_edges).exact
    # spot-check the semantics: P_i controls Tt_i; A_i blocks E_i; M1 blocks E11; E1 unblocked
    assert (frozenset({"P3"}), "Tt3") in capability
    assert (frozenset({"A3"}), "E3") in blocking
    assert (frozenset({"M1"}), "E11") in blocking
    assert not any(e == "E1" for _reqs, e in blocking)


def test_foothold_has_no_blocking_edge(it_descriptor):
    # E1 (P0->P1) carries no link_var, so no blocking edge -- the under-detection foothold
    gamma = build_gamma(it_descriptor, StaticScanner.from_descriptor(it_descriptor))
    assert "link_var" not in gamma.exploit_meta["E1"]
    _capability, blocking = build_l(it_descriptor, gamma)
    assert (frozenset(), "E1") not in blocking
