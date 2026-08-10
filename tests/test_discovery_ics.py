"""
Tests for  construction of the ICS model
"""

from __future__ import annotations
import os
import pandas as pd
import pytest
from ccd.discovery.attack.build_gamma import build_gamma
from ccd.discovery.attack.datalog_rules import derive
from ccd.discovery.attack.scanner import StaticScanner
from ccd.discovery.causal.build_g import build_g
from ccd.discovery.cross_layer.build_l import build_l
from ccd.discovery.evaluation.acceptance import accept
from ccd.discovery.evaluation.graph_diff import diff_cross_edges, diff_graphs
from ccd.system.ics_testbed_system import IcsTestbedSystem
from ccd.util.validation_util import load_dataset

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_ICS_DATA = os.path.join(_REPO_ROOT, "testbeds", "ics", "data", "dataset.csv")

pytestmark = pytest.mark.skipif(not os.path.exists(_ICS_DATA),
                                reason="ICS testbed dataset not collected")


@pytest.fixture(scope="module")
def ics_descriptor(testbed_loader):
    return testbed_loader("ics", "descriptor").build_descriptor()


@pytest.fixture(scope="module")
def ics_data() -> pd.DataFrame:
    return load_dataset(_ICS_DATA)


def test_descriptor_validates_and_renames_gateway(ics_descriptor):
    ics_descriptor.validate()
    assert ics_descriptor.column_rename() == {"G2": "G2c"}
    assert set(ics_descriptor.columns_by_source("derived")) == {"Ctil", "V"}
    assert set(ics_descriptor.columns_by_source("operator_controlled")) == {"W", "G2c", "Chat"}


def test_descriptor_has_conceded_control_server(ics_descriptor):
    control = ics_descriptor.host("control")
    assert control.conceded and control.privilege_node == "P3"
    e3 = next(e for e in ics_descriptor.exploit_templates if e.id == "E3")
    assert e3.exploit_class == "conceded" and e3.post_privilege == "P3"


def test_g_recovers_all_target_edges(ics_descriptor, ics_data):
    construction = build_g(ics_descriptor, ics_data.rename(columns={"G2": "G2c"}))
    diff = diff_graphs(construction.graph, IcsTestbedSystem().throughput_graph())
    assert diff.recall == 1.0
    assert construction.graph.has_edge("V", "P")
    assert construction.graph.has_edge("Ctil", "V")
    assert not construction.graph.has_edge("C", "P")
    assert not construction.graph.has_edge("C", "S")


def test_constructed_g_not_falsified(ics_descriptor, ics_data):
    from ccd.discovery.causal.validation import validate_graph
    construction = build_g(ics_descriptor, ics_data.rename(columns={"G2": "G2c"}))
    summary = validate_graph(construction.graph, ics_data.rename(columns={"G2": "G2c"}),
                             n_permutations=20)
    assert summary.falsified is False


def test_conceded_privilege_fires_without_scan(ics_descriptor):
    result = derive(ics_descriptor, [])
    assert "E3" in result.fired
    assert "E4" in result.fired
    assert "control" in result.compromised


def test_gamma_and_cross_layer_exact(ics_descriptor):
    gamma = build_gamma(ics_descriptor, StaticScanner.from_descriptor(ics_descriptor))
    target = IcsTestbedSystem()
    assert diff_graphs(gamma.graph, target.attack_graph).exact
    capability, blocking = build_l(ics_descriptor, gamma)
    assert diff_cross_edges(capability, target.capability_edges).exact
    assert diff_cross_edges(blocking, target.blocking_edges).exact
    assert (frozenset({"G2c"}), "E3") in blocking
    assert (frozenset({"G2e"}), "E2") in blocking


def test_acceptance_gamma_c_b_exact_g_validated(ics_descriptor, ics_data):
    model, report = accept(ics_descriptor, ics_data, with_attack=True)
    assert report.gamma is not None and report.gamma.exact
    assert report.capability is not None and report.capability.exact
    assert report.blocking is not None and report.blocking.exact
    assert report.g.recall == 1.0
    assert model.attacker_controlled == {"W", "C"}
    assert model.attacker_controlled == IcsTestbedSystem().attacker_controlled
