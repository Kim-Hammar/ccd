"""Pure (docker-free) unit tests for the 5G cloud-RAN testbed library."""

import pytest
import ran_lib as rl
from ccd.system.five_g_testbed_system import FiveGTestbedSystem


# --- dataset schema ----------------------------------------------------------
def test_dataset_columns_match_throughput_nodes():
    """The collector's observed columns must equal the model's throughput_nodes."""
    cols = rl.dataset_columns()
    observed = [c for c in cols if c not in rl.METADATA_COLUMNS]
    assert set(observed) == FiveGTestbedSystem().throughput_nodes
    assert cols[-len(rl.METADATA_COLUMNS):] == rl.METADATA_COLUMNS


def test_dataset_columns_order_is_stable():
    assert rl.dataset_columns() == rl.dataset_columns()


# --- confounder --------------------------------------------------------------
def test_p_close_endpoints_and_monotonicity():
    assert rl.p_close(0.0) == pytest.approx(0.30)
    assert rl.p_close(1.0) == pytest.approx(0.05)
    assert rl.p_close(-1.0) == pytest.approx(0.30)     # clamped
    assert rl.p_close(2.0) == pytest.approx(0.05)      # clamped
    assert rl.p_close(0.3) > rl.p_close(0.7)           # closures likelier at low demand


# --- enactment mapping -------------------------------------------------------
def test_qi_threshold_rejects_only_subthreshold_class_ports():
    e = rl.enactment_for("QI1", 4)     # D(QI_1) = 4: reject classes 1, 2, 3
    assert e.kind == "iptables"
    assert e.container == rl.ue_container(1)
    ports = [rl.class_port(k) for k in (1, 2, 3)]
    for port in ports:
        assert any(f"--dport {port} " in a for a in e.rule_args)
    for port in (rl.class_port(4), rl.class_port(10)):
        assert not any(f"--dport {port} " in a for a in e.rule_args)


def test_qi_admit_all_produces_no_rules():
    e = rl.enactment_for("QI2", 1)     # nominal admit-all threshold: no class dropped
    assert e.rule_args == []


def test_ng_closes_cu_n2_and_n3():
    e = rl.enactment_for("NG3", 0)
    assert e.kind == "iptables"
    assert e.container == rl.cu_container(3)
    assert any("sctp" in a and str(rl.CORE_NGAP_PORT) in a for a in e.rule_args)
    assert any("udp" in a and str(rl.CORE_GTPU_PORT) in a for a in e.rule_args)


def test_at_reattach_is_control_plane():
    e = rl.enactment_for("AT3", 1)     # reattach DU_3 to CU_1
    assert e.kind == "reattach"
    assert e.container == rl.du_container(3)
    assert e.target_cu == 1
    assert e.rule_args == []


def test_interface_close():
    for var in ("E2", "N6", "Xn", "A1", "Uu"):
        e = rl.enactment_for(var, 0)
        assert e.kind == "iptables"
        assert e.rule_args


def test_enactment_rejects_bad_input():
    with pytest.raises(ValueError):
        rl.enactment_for("ZZ9", 0)
    with pytest.raises(ValueError):
        rl.enactment_for("E2", 1)          # interface only degrades to 0
    with pytest.raises(ValueError):
        rl.enactment_for("NG9", 0)         # CU out of range
    with pytest.raises(ValueError):
        rl.enactment_for("AT1", 9)         # target CU out of range


# --- sync_commands over the selected mode D_1 --------------------------------
def _d1_mode():
    return {"AT3": 1, "E2": 0, "NG3": 0, "QI1": 4}


def test_sync_commands_for_d1_are_flush_first_and_idempotent():
    cmds = rl.sync_commands(_d1_mode())
    # E2 (near-RT RIC), NG3 (CU_3), QI1 (UE_1) -> three iptables containers; AT3 excluded
    containers = [c[2] for c in cmds]
    assert rl.cu_container(3) in containers
    assert rl.ue_container(1) in containers
    assert "ccd5g-ric-nearrt" in containers
    assert rl.du_container(3) not in containers        # reattach is not an iptables rule
    for cmd in cmds:
        assert cmd[:2] == ["docker", "exec"]
        assert cmd[-1].startswith("iptables -F CCD")   # flush before re-add (idempotent)
    assert rl.sync_commands(_d1_mode()) == cmds


def test_sync_commands_reattachments_separated():
    reattach = rl.reattachments(_d1_mode())
    assert len(reattach) == 1
    assert reattach[0].container == rl.du_container(3)
    assert reattach[0].target_cu == 1
    # a nominal AT (DU_2 -> CU_2) is not a reattachment
    assert rl.reattachments({"AT2": 2}) == []


def test_sync_commands_empty_mode():
    assert rl.sync_commands({}) == []
    assert rl.reattachments({}) == []
