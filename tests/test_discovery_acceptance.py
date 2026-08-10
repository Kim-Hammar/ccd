"""
Comparison between the inferred model vs the designed model
"""

from __future__ import annotations
import os
import pandas as pd
import pytest
from ccd.discovery.evaluation.acceptance import accept
from ccd.system.it_testbed_system import ITTestbedSystem

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_IT_DATA = os.path.join(_REPO_ROOT, "testbeds", "it_system", "data", "dataset.csv")

pytestmark = pytest.mark.skipif(not os.path.exists(_IT_DATA),
                                reason="IT testbed dataset not collected")


@pytest.fixture(scope="module")
def it_model_and_report(testbed_loader):
    desc = testbed_loader("it_system", "descriptor").build_descriptor(10)
    data = pd.read_csv(_IT_DATA)
    return accept(desc, data, with_attack=True)


def test_all_layers_reconstructed_exactly(it_model_and_report):
    _model, report = it_model_and_report
    assert report.g.exact and report.g.isomorphic
    assert report.gamma is not None and report.gamma.exact
    assert report.capability is not None and report.capability.exact
    assert report.blocking is not None and report.blocking.exact


def test_constructed_model_derives_correct_attacker_set(it_model_and_report):
    model, _report = it_model_and_report
    target = ITTestbedSystem(10)
    assert model.attacker_controlled == target.attacker_controlled
    assert model.attacker_controlled == {"Tt1"}
    assert model.attained == target.attained


def test_product_functions_carried_over(it_model_and_report):
    model, _report = it_model_and_report
    expected = {f"Th{i}": frozenset({f"N{i}", f"Tt{i}"}) for i in range(1, 11)}
    assert model.product_functions == expected
    assert "T" not in model.product_functions
