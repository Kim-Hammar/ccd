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


# --- config + compose generation ---------------------------------------------
def test_attachment_map_nominal_and_reattach():
    assert rl.attachment_map() == {1: 1, 2: 2, 3: 3, 4: 4}
    assert rl.attachment_map({3: 1}) == {1: 1, 2: 2, 3: 1, 4: 4}     # D_1's AT3=1
    with pytest.raises(ValueError):
        rl.attachment_map({3: 9})


def test_imsi_unique_per_ue():
    imsis = {rl.imsi(i) for i in range(1, rl.NUM_DU + 1)}
    assert len(imsis) == rl.NUM_DU
    assert rl.imsi(1) == "00101" + "0000000001"


def test_cu_config_has_unique_gnb_id_and_core_addr():
    for j in range(1, rl.NUM_CU + 1):
        cfg = rl.render_cu_config(j)
        assert f"\ngnb_id: {j}\n" in cfg           # top-level, not nested under cu_cp
        assert f"addr: {rl.AMF_IP}" in cfg
        assert f"bind_addr: {rl.cu_ip(j)}" in cfg


def test_du_config_targets_its_cu_and_pairs_zmq_with_ue():
    cfg = rl.render_du_config(3, 1)                 # DU_3 attached to CU_1 (D_1)
    assert "gnb_du_id: 3" in cfg
    assert "\ngnb_id: 1\n" in cfg                   # shares CU_1's gnb_id, not CU_3's
    assert f"cu_cp_addr: {rl.cu_ip(1)}" in cfg      # F1 to CU_1, not CU_3
    ports = rl.zmq_ports(3)
    assert f"tx_port=tcp://{rl.du_ip(3)}:{ports['tx']}" in cfg
    assert f"rx_port=tcp://{rl.ue_ip(3)}:{ports['rx']}" in cfg
    assert "pci: 3" in cfg
    assert "mcs_table: qam64" in cfg


def test_ue_config_mirrors_du_ports_and_has_unique_imsi():
    cfg = rl.render_ue_config(2)
    ports = rl.zmq_ports(2)
    assert f"tx_port=tcp://{rl.ue_ip(2)}:{ports['rx']}" in cfg     # UE tx binds on its rx port
    assert f"rx_port=tcp://{rl.du_ip(2)}:{ports['tx']}" in cfg     # UE rx connects to DU tx port
    assert f"imsi = {rl.imsi(2)}" in cfg


def test_ran_compose_structure_nominal():
    text = rl.render_ran_compose(rl.attachment_map())
    assert "name: ccd5g" in text
    for j in range(1, rl.NUM_CU + 1):
        assert f"container_name: {rl.cu_container(j)}" in text
        assert f"ipv4_address: {rl.cu_ip(j)}" in text
    for i in range(1, rl.NUM_DU + 1):
        assert f"container_name: {rl.du_container(i)}" in text
        assert f"container_name: {rl.ue_container(i)}" in text
        assert f"depends_on: [cu{i}]" in text       # DU_i waits on its nominal CU_i
        assert f"depends_on: [du{i}]" in text
    assert text.count("image: ccd-5g-gnb") == 8     # 4 CU + 4 DU
    assert text.count("image: ccd-5g-srsue") == 4


def test_ran_compose_reattach_changes_du_dependency():
    text = rl.render_ran_compose(rl.attachment_map({3: 1}))
    assert "depends_on: [cu1]" in text              # DU_3 now waits on CU_1
    assert "depends_on: [cu3]" not in text          # nothing attached to CU_3 anymore
