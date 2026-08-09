"""
5G cloud-RAN construction tests -- phase 3: ~196 causal columns with four index
dimensions (DU, CU, class, direction) via multi-dimensional symmetry reduction, the
midhaul product plus known admission/attachment/aggregation mechanisms, the demand
confounder conditioned out, and an attack chain with scan-invisible footholds
(radio injection, control-plane credential reuse). Docker-free (committed dataset +
StaticScanner).

G is not expected to match edge-for-edge (the plan's honest risk: gated products, the
demand confounder, and context-specific independencies); the acceptance gate is that
Gamma/C/B reconstruct exactly and G's data-supported structure is recovered with high
recall. Full-graph falsification is checked out-of-band (too slow for the suite).
"""

from __future__ import annotations
import os
import pandas as pd
import pytest
from ccd.discovery.attack.build_gamma import build_gamma
from ccd.discovery.attack.datalog_rules import derive
from ccd.discovery.attack.scanner import StaticScanner
from ccd.discovery.cross_layer.build_l import build_l
from ccd.discovery.evaluation.graph_diff import diff_cross_edges, diff_graphs
from ccd.system.five_g_testbed_system import FiveGTestbedSystem

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_5G_DATA = os.path.join(_REPO_ROOT, "testbeds", "5g_ran", "data", "dataset.csv")

pytestmark = pytest.mark.skipif(not os.path.exists(_5G_DATA),
                                reason="5G testbed dataset not collected")


@pytest.fixture(scope="module")
def g5_descriptor(testbed_loader):
    return testbed_loader("5g_ran", "descriptor").build_descriptor()


# --- descriptor ----------------------------------------------------------------
def test_descriptor_scale_and_provenance(g5_descriptor):
    g5_descriptor.validate()
    assert len(g5_descriptor.node_set) == 196
    # midhaul is the only gated product; admission/attachment/aggregation are sum/gate
    kinds = {m.kind for m in g5_descriptor.product_mechanisms}
    assert kinds == {"product", "sum", "gate"}
    assert g5_descriptor.confounders == ["demand"]


# --- attack layer (exact, incl. scan-invisible moves) --------------------------
def test_scan_invisible_footholds_fire(g5_descriptor):
    # With an empty scan, the scan-invisible moves still fire from the attained
    # P-tilde = {P0,P1,P2}: EX1 (radio injection, P0->P1) and EX4 (control-plane credreuse,
    # P2->P4). The netexploit EX3 (near-RT RIC) needs its scan fact, so it does not fire,
    # and EX5 (which needs the P3 that EX3 would grant) is gated behind it.
    result = derive(g5_descriptor, [])
    assert "EX1" in result.fired            # radioinject, no vulExists
    assert "EX4" in result.fired            # credreuse from the attained P2, no vulExists
    assert "EX3" not in result.fired and "EX5" not in result.fired
    # grounding the RIC service lets EX3 fire, and then EX5 follows
    scanner = StaticScanner.from_descriptor(g5_descriptor)
    grounded = derive(g5_descriptor, scanner.scan(["cu3", "ric_nearrt"]))
    assert {"EX3", "EX5"} <= grounded.fired


def test_gamma_capability_blocking_exact(g5_descriptor):
    gamma = build_gamma(g5_descriptor, StaticScanner.from_descriptor(g5_descriptor))
    target = FiveGTestbedSystem()
    assert diff_graphs(gamma.graph, target.attack_graph).exact
    capability, blocking = build_l(g5_descriptor, gamma)
    assert diff_cross_edges(capability, target.capability_edges).exact
    assert diff_cross_edges(blocking, target.blocking_edges).exact
    # multi-dimensional capability: P1 holds DU_1's attacker UE classes, P2 CU_3's loads
    assert (frozenset({"P1"}), "UE_1_7") in capability
    assert (frozenset({"P2"}), "Chat_1_3_U") in capability
    # blocking: only E2/NG3 gate an exploit; the footholds EX1/EX2/EX5 do not
    assert blocking == frozenset({(frozenset({"E2"}), "EX3"), (frozenset({"NG3"}), "EX4")})


# --- full construction (one build; ~35 s) --------------------------------------
@pytest.fixture(scope="module")
def g5_result(g5_descriptor):
    from ccd.discovery.evaluation.acceptance import accept
    data = pd.read_csv(_5G_DATA)
    return accept(g5_descriptor, data, with_attack=True)


def test_attack_layers_reconstructed_exactly(g5_result):
    _model, report = g5_result
    assert report.gamma is not None and report.gamma.exact
    assert report.capability is not None and report.capability.exact
    assert report.blocking is not None and report.blocking.exact


def test_g_high_recall_via_symmetry_and_mechanisms(g5_result):
    _model, report = g5_result
    # the data-supported structure is recovered with high recall; some interface->T edges
    # are absent in the data (A1/E2 do not drive throughput) and a few gated edges are
    # borderline, so exact isomorphism is not expected
    assert report.g.recall >= 0.90
    assert report.g.precision >= 0.85


def test_constructed_g_has_product_and_aggregation_structure(g5_result):
    model, _report = g5_result
    g = model.graph
    # midhaul gated product (F-tilde) and the admission/attachment/aggregation mechanisms
    assert g.has_edge("NG1", "Ctil_1_1_U") and g.has_edge("Chat_1_1_U", "Ctil_1_1_U")
    assert g.has_edge("L_1_1_U", "Ladm_1_U")          # admission sum
    assert g.has_edge("Cbar_1_U", "Chat_1_1_U")       # attachment gate
    assert g.has_edge("Ctil_1_1_U", "C_1_U")          # CU aggregation
    # and the genuinely-discovered edges
    assert g.has_edge("Ladm_1_U", "Cbar_1_U")
    assert g.has_edge("C_1_U", "T_1_U")
    # only the midhaul carries over as a gated product function
    assert model.product_functions["Ctil_1_1_U"] == frozenset({"NG1", "Chat_1_1_U"})


def test_derived_attacker_set_matches(g5_result):
    model, _report = g5_result
    assert model.attacker_controlled == FiveGTestbedSystem().attacker_controlled
    assert model.attained == FiveGTestbedSystem().attained
