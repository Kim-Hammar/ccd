"""Unit tests for the dockerized IT-testbed system model (no docker required)."""

import numpy as np
import pandas as pd
import pytest
from ccd.ccd import ccd, select_intervention
from ccd.system.illustrative_example_system import IllustrativeExampleSystem
from ccd.system.it_testbed_system import ITTestbedSystem
from ccd.util.scenario_util import run_ccd_on_data

E = IllustrativeExampleSystem.E


def _testbed_like_dataset(m: int, steps: int, seed: int) -> pd.DataFrame:
    """A DGP producing the *testbed* schema: no eps/gam columns and measured Tt_i
    gated by N_i (a closed gateway link means the server carries no load)."""
    rng = np.random.RandomState(seed)
    workload = rng.uniform(50.0, 150.0, steps)
    p_close = np.clip(0.30 - 0.25 * (workload - 50.0) / 100.0, 0.05, 0.30)

    data: dict = {"W": workload}
    total = np.zeros(steps)
    for i in range(1, m + 1):
        load = np.maximum(0.0, workload / m + rng.normal(0.0, 1.0, steps))
        cap = rng.normal(80.0, 5.0, steps)
        n_open = (rng.uniform(0.0, 1.0, steps) > p_close).astype(int)
        m_open = (rng.uniform(0.0, 1.0, steps) > p_close).astype(int)
        carried = n_open * m_open * np.minimum(load, cap)   # measured Tt_i: N-gated
        throughput = n_open * carried                        # Th_i = N_i * Tt_i
        total += throughput
        data[f"L{i}"] = load
        data[f"N{i}"] = n_open
        data[f"M{i}"] = m_open
        data[f"Tt{i}"] = carried
        data[f"Th{i}"] = throughput
    data["T"] = total
    data["window"] = np.arange(steps)   # metadata column; must be ignored by the fit
    return pd.DataFrame(data)


# --- model structure ---------------------------------------------------------
@pytest.mark.parametrize("m", [2, 5, 10])
def test_throughput_graph_has_only_observed_nodes(m):
    """The DoWhy fit graph contains exactly the observable variables (no eps/gam)."""
    system = ITTestbedSystem(m)
    expected = (
        {"W", "T"}
        | {f"{p}{i}" for p in ("L", "N", "M", "Tt", "Th") for i in range(1, m + 1)}
    )
    assert set(system.throughput_graph().nodes) == expected
    # the noise roots remain part of the causal graph G, they are just unobserved
    assert all(f"eps{i}" in system.graph and f"gam{i}" in system.graph
               for i in range(1, m + 1))


@pytest.mark.parametrize("m", [2, 5, 10])
def test_measured_carried_load_is_gated_by_gateway_link(m):
    """The testbed graph has N_i -> Tt_i: measured db-completions are 0 when the
    gateway link is closed (unlike the simulator's counterfactual carried load)."""
    system = ITTestbedSystem(m)
    assert all(system.graph.has_edge(f"N{i}", f"Tt{i}") for i in range(1, m + 1))
    base = IllustrativeExampleSystem(m)
    assert not any(base.graph.has_edge(f"N{i}", f"Tt{i}") for i in range(1, m + 1))


@pytest.mark.parametrize("m", [2, 5, 10])
def test_mode_selection_matches_illustrative_example(m):
    """The added N_i -> Tt_i edges must not change mode selection in any scenario."""
    patched = frozenset(E(i) for i in range(2, m + 2))
    for kwargs in ({}, {"patched_exploits": patched},
                   {"patched_exploits": patched, "attacker_evicted": True}):
        u_testbed = select_intervention(ITTestbedSystem(m, **kwargs))
        u_base = select_intervention(IllustrativeExampleSystem(m, **kwargs))
        assert u_testbed is not None and u_base is not None
        assert u_testbed.variables == u_base.variables


def test_recovery_progression_is_monotone():
    m = 5
    patched = frozenset(E(i) for i in range(2, m + 2))
    d1 = set(select_intervention(ITTestbedSystem(m)).variables)
    d2 = set(select_intervention(ITTestbedSystem(m, patched_exploits=patched)).variables)
    d3 = set(select_intervention(
        ITTestbedSystem(m, patched_exploits=patched, attacker_evicted=True)).variables)
    assert d1 > d2 > d3
    assert d3 == set()


def test_generate_dataset_raises():
    """The testbed model has no simulator: D is measured on the containers."""
    with pytest.raises(NotImplementedError):
        ITTestbedSystem(3).generate_dataset()


# --- numeric round-trip (invokes DoWhy causal inference) ---------------------
def test_testbed_schema_roundtrip_is_feasible_and_matches_analytic():
    """A dataset with the testbed schema (N-gated Tt_i, no eps/gam, extra metadata
    column) flows through ccd() end-to-end and Phi-hat matches the analytic
    (m-1)/m throughput."""
    m = 3
    system = ITTestbedSystem(m)
    data = _testbed_like_dataset(m, steps=3000, seed=1)

    phi_nominal = float(data["T"].mean())
    alpha = 0.5 * phi_nominal
    analytic = sum(data[f"Th{i}"].mean() for i in range(2, m + 1))

    result = ccd(system, data, alpha=alpha, num_samples=3000)

    assert result.intervention is not None
    assert set(result.intervention.variables) == {"N1", "M1"} | {f"A{i}" for i in range(2, m + 1)}
    assert result.feasible
    assert result.phi == pytest.approx(analytic, rel=0.10)


def test_run_ccd_on_data_is_feasible_and_matches_run_scenario_mode(capsys):
    """Refactor guard: run_ccd_on_data on a given dataset selects the same mode and
    alpha as the simulator path and prints the report."""
    m = 3
    system = ITTestbedSystem(m)
    data = _testbed_like_dataset(m, steps=2000, seed=0)
    result = run_ccd_on_data(system, data, title="testbed refactor guard", num_samples=2000)
    out = capsys.readouterr().out
    assert result.intervention is not None
    assert set(result.intervention.variables) == {"N1", "M1", "A2", "A3"}
    assert result.alpha == pytest.approx(0.5 * float(data["T"].mean()))
    assert "Selected degraded mode" in out and "blocks" in out
