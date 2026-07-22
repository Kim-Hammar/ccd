"""Pure (docker-free) unit tests for the ICS testbed library."""

import random
import pytest
import ics_lib as il
from ccd.system.ics_testbed_system import IcsTestbedSystem


# --- dataset schema ----------------------------------------------------------
def test_dataset_columns_match_throughput_nodes():
    """The collector's observed columns must equal the model's throughput_nodes."""
    cols = il.dataset_columns()
    observed = [c for c in cols if c not in il.METADATA_COLUMNS]
    assert set(observed) == IcsTestbedSystem().throughput_nodes
    assert cols[-len(il.METADATA_COLUMNS):] == il.METADATA_COLUMNS


def test_dataset_columns_order_is_stable():
    assert il.dataset_columns() == il.dataset_columns()


# --- confounder --------------------------------------------------------------
def test_p_close_endpoints_and_monotonicity():
    assert il.p_close(0.0) == pytest.approx(0.30)
    assert il.p_close(1.0) == pytest.approx(0.05)
    assert il.p_close(-1.0) == pytest.approx(0.30)     # clamped
    assert il.p_close(2.0) == pytest.approx(0.05)      # clamped
    assert il.p_close(0.3) > il.p_close(0.7)           # degradations likelier at low demand


# --- enactment mapping -------------------------------------------------------
def test_g2_closure_rejects_the_enterprise_subnet_at_control():
    e = il.enactment_for("G2", 0)
    assert e.kind == "iptables"
    assert e.container == il.CONTROL_CONTAINER
    assert any(il.ENTERPRISE_SUBNET in a and "REJECT" in a for a in e.rule_args)


def test_g2_open_produces_no_rules():
    assert il.enactment_for("G2", 1).rule_args == []


def test_chat_and_w_are_application_modes():
    chat0 = il.enactment_for("Chat", 0)
    assert chat0.kind == "mode" and chat0.container == il.CONTROL_CONTAINER and chat0.mode == "local"
    assert il.enactment_for("Chat", 1).mode == "remote"
    w0 = il.enactment_for("W", 0)
    assert w0.kind == "mode" and w0.container == il.WEB_CONTAINER and w0.mode == "safe"
    assert il.enactment_for("W", 1).mode == "up"


def test_enactment_rejects_bad_input():
    with pytest.raises(ValueError):
        il.enactment_for("ZZ", 0)
    with pytest.raises(ValueError):
        il.enactment_for("G2", 2)          # binary only


# --- sync_commands / mode_settings over the selected mode D_1 ----------------
def _d1_mode():
    return {"W": 0, "G2": 0, "Chat": 0}


def test_sync_commands_only_g2_is_iptables_on_control():
    cmds = il.sync_commands(_d1_mode())
    assert len(cmds) == 1                              # only the control container's chain
    cmd = cmds[0]
    assert cmd[:3] == ["docker", "exec", il.CONTROL_CONTAINER]
    assert cmd[-1].startswith("iptables -F CCD")       # flush before re-add (idempotent)
    assert il.ENTERPRISE_SUBNET in cmd[-1]
    assert il.sync_commands(_d1_mode()) == cmds


def test_sync_commands_open_gateway_is_just_a_flush():
    cmds = il.sync_commands({"W": 1, "G2": 1, "Chat": 1})
    assert cmds == [["docker", "exec", il.CONTROL_CONTAINER, "sh", "-c", "iptables -F CCD"]]


def test_mode_settings_separates_chat_and_w_from_g2():
    settings = il.mode_settings(_d1_mode())
    assert [(e.container, e.mode) for e in settings] == [
        (il.WEB_CONTAINER, "safe"), (il.CONTROL_CONTAINER, "local")]
    # G2 is not an application mode
    assert all(e.var != "G2" for e in settings)


# --- nominal window sampling ------------------------------------------------------
def test_sample_window_state_maintenance_is_mutually_exclusive():
    rng = random.Random(0)
    for _ in range(500):
        state = il.sample_window_state(rng)
        assert sum(1 for v in state.operator.values() if v == 0) <= 1   # at most one degraded
        assert state.command >= 0.0


def test_sample_window_state_never_produces_the_joint_degraded_config():
    """Mutual exclusion -> do(W=0,G2=0,Chat=0) never occurs, so naive conditioning is undefined."""
    rng = random.Random(1)
    assert not any(all(il.sample_window_state(rng).operator[v] == 0 for v in il.OPERATOR_VARS)
                   for _ in range(3000))


def test_sample_window_state_respects_pinning():
    rng = random.Random(2)
    for _ in range(50):
        state = il.sample_window_state(rng, {"G2": 0, "Chat": 0})
        assert state.operator["G2"] == 0 and state.operator["Chat"] == 0


def test_sample_window_state_confounds_degradation_with_demand():
    rng = random.Random(3)
    windows = {True: 0, False: 0}
    degraded = {True: 0, False: 0}
    for _ in range(6000):
        s = il.sample_window_state(rng)
        high = s.demand_frac > 0.5
        windows[high] += 1
        degraded[high] += 1 if any(v == 0 for v in s.operator.values()) else 0
    assert degraded[False] / windows[False] > degraded[True] / windows[True]


def test_sample_window_state_rejects_unknown_pin():
    with pytest.raises(ValueError):
        il.sample_window_state(random.Random(0), {"BOGUS": 0})


# --- row assembly -------------------------------------------------------------
def test_assemble_row_maps_metrics_onto_the_schema():
    state = il.WindowState(demand_frac=0.4, command=37.0, operator={"W": 1, "G2": 0, "Chat": 1})
    row = il.assemble_row(
        window=5, t_start=1.0, duration=6.0, state=state,
        web_metrics={"W": 1, "I": 86.0}, control_metrics={"Chat": 1, "Ctil": 0.0, "V": 0.0},
        process_metrics={"P": 2700.0, "S": 100.0},
    )
    assert set(row) == set(il.dataset_columns())
    assert row["G2"] == 0.0 and row["C"] == 37.0            # G2/C from the enacted config
    assert row["W"] == 1.0 and row["I"] == 86.0             # web metrics
    assert row["Ctil"] == 0.0 and row["V"] == 0.0           # control metrics (gateway shut)
    assert row["P"] == 2700.0 and row["S"] == 100.0         # process metrics
    assert row["window"] == 5.0 and row["demand"] == 0.4


# --- compose generation ------------------------------------------------------
def test_generate_compose_structure():
    text = il.generate_compose()
    assert "name: ccd-ics" in text
    for container in (il.WEB_CONTAINER, il.SCADA_CONTAINER, il.CONTROL_CONTAINER,
                      il.PROCESS_CONTAINER):
        assert f"container_name: {container}" in text
    assert il.ENTERPRISE_SUBNET in text and il.PLANT_SUBNET in text
    assert "cap_add: [NET_ADMIN]" in text               # the control server (G2 firewall)
    assert text.count("build:") == 4
