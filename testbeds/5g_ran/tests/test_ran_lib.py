"""Pure (docker-free) unit tests for the 5G cloud-RAN testbed library."""

import random
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


# --- flow-port plan ------------------------------------------------------------
def test_flow_ports_unique_per_du_and_class():
    ports = {rl.flow_port(i, k) for i in range(1, rl.NUM_DU + 1)
             for k in range(1, rl.NUM_CLASSES + 1)}
    assert len(ports) == rl.NUM_DU * rl.NUM_CLASSES    # (DU, class) attribution by port
    assert rl.flow_port(1, 1) == 5101
    with pytest.raises(ValueError):
        rl.flow_port(5, 1)
    with pytest.raises(ValueError):
        rl.flow_port(1, 11)


# --- enactment mapping -------------------------------------------------------
def test_qi_threshold_filters_both_directions_pre_radio():
    """D(QI_1) = 4 rejects classes 1-3: uplink at UE_1's egress, downlink at the sink."""
    enacts = rl.enactments_for("QI1", 4)
    assert [e.container for e in enacts] == [rl.ue_container(1), rl.SINK_CONTAINER]
    for e in enacts:
        assert e.kind == "iptables"
        ports = [rl.flow_port(1, k) for k in (1, 2, 3)]
        for port in ports:
            assert any(f"--dport {port} " in a for a in e.rule_args)
        for port in (rl.flow_port(1, 4), rl.flow_port(1, 10), rl.flow_port(2, 1)):
            assert not any(f"--dport {port} " in a for a in e.rule_args)
    # the sink-side (downlink) rules are scoped to the PDU subnet so they never match
    # uplink arriving on the same ports
    assert all(rl.PDU_SUBNET in a for a in enacts[1].rule_args)


def test_qi_admit_all_produces_no_rules():
    for e in rl.enactments_for("QI2", 1):    # nominal admit-all threshold: nothing dropped
        assert e.rule_args == []


def test_ng_closes_n3_both_directions_and_drops_n2():
    (e,) = rl.enactments_for("NG3", 0)
    assert e.kind == "iptables"
    assert e.container == rl.cu_container(3)
    n3 = [a for a in e.rule_args if str(rl.CORE_GTPU_PORT) in a]
    assert len(n3) == 2 and any(f"-d {rl.UPF_IP}" in a for a in n3) \
        and any(f"-s {rl.UPF_IP}" in a for a in n3)      # GTP-U severed both ways
    n2 = [a for a in e.rule_args if "sctp" in a]
    assert n2 and all("DROP" in a for a in n2)           # NGAP: DROP, never REJECT (SCTP abort)


def test_at_reattach_is_control_plane():
    (e,) = rl.enactments_for("AT3", 1)       # reattach DU_3 to CU_1
    assert e.kind == "reattach"
    assert e.container == rl.du_container(3)
    assert e.target_cu == 1
    assert e.rule_args == []


def test_interface_close():
    for var in ("E2", "N6", "Xn", "A1", "Uu"):
        enacts = rl.enactments_for(var, 0)
        assert enacts
        for e in enacts:
            assert e.kind == "iptables"
            assert e.rule_args
    # Uu blocks each DU's own ZMQ pair (no fictional radio container)
    assert [e.container for e in rl.enactments_for("Uu", 0)] == \
        [rl.du_container(i) for i in range(1, rl.NUM_DU + 1)]
    # N6 severs the UPF's ogstun forwarding in both directions
    (n6,) = rl.enactments_for("N6", 0)
    assert n6.container == rl.UPF_CONTAINER
    assert any("-i ogstun" in a for a in n6.rule_args)
    assert any("-o ogstun" in a for a in n6.rule_args)


def test_enactment_rejects_bad_input():
    with pytest.raises(ValueError):
        rl.enactments_for("ZZ9", 0)
    with pytest.raises(ValueError):
        rl.enactments_for("E2", 1)          # interface only degrades to 0
    with pytest.raises(ValueError):
        rl.enactments_for("NG9", 0)         # CU out of range
    with pytest.raises(ValueError):
        rl.enactments_for("AT1", 9)         # target CU out of range


# --- sync_commands over the selected mode D_1 --------------------------------
def _d1_mode():
    return {"AT3": 1, "E2": 0, "NG3": 0, "QI1": 4}


def test_sync_commands_cover_every_controlled_container():
    """Sync is complete: every controlled container is flushed (reopening needs no
    bookkeeping), and each script creates the CCD chain before touching it."""
    cmds = rl.sync_commands(_d1_mode())
    containers = [c[2] for c in cmds]
    assert sorted(containers) == sorted(rl.controlled_containers())
    for cmd in cmds:
        assert cmd[:2] == ["docker", "exec"]
        assert "iptables -N CCD" in cmd[-1]            # self-ensuring
        assert "iptables -F CCD" in cmd[-1]            # flush before re-add (idempotent)
    assert rl.sync_commands(_d1_mode()) == cmds


def test_sync_commands_route_d1_rules_to_the_right_containers():
    scripts = {c[2]: c[-1] for c in rl.sync_commands(_d1_mode())}
    assert f"--dport {rl.flow_port(1, 1)}" in scripts[rl.ue_container(1)]        # QI1 UL
    assert f"--dport {rl.flow_port(1, 3)}" in scripts[rl.SINK_CONTAINER]         # QI1 DL
    assert str(rl.CORE_GTPU_PORT) in scripts[rl.cu_container(3)]                 # NG3
    assert "-j REJECT" in scripts[rl.RIC_NEARRT_CONTAINER]                       # E2
    assert "-A CCD" not in scripts[rl.du_container(3)]      # reattach is not an iptables rule
    # untouched containers still get a flush so stale rules are removed
    assert scripts[rl.cu_container(1)].endswith("iptables -F CCD")


def test_sync_commands_reattachments_separated():
    reattach = rl.reattachments(_d1_mode())
    assert len(reattach) == 1
    assert reattach[0].container == rl.du_container(3)
    assert reattach[0].target_cu == 1
    # a nominal AT (DU_2 -> CU_2) is not a reattachment
    assert rl.reattachments({"AT2": 2}) == []


def test_sync_commands_empty_mode_is_a_full_reset():
    cmds = rl.sync_commands({})
    assert sorted(c[2] for c in cmds) == sorted(rl.controlled_containers())
    for cmd in cmds:
        assert cmd[-1].endswith("iptables -F CCD")     # flush only, no rules
    assert rl.reattachments({}) == []


# --- byte-counter plan ----------------------------------------------------------
def test_count_rules_attribute_by_destination_and_port():
    du_rules = rl.count_rules(rl.du_container(2))
    assert len(du_rules) == rl.NUM_CU                  # F1-U uplink, one per CU
    assert all(str(rl.F1U_PORT) in a for a in du_rules)
    ue_rules = rl.count_rules(rl.ue_container(1))
    assert len(ue_rules) == rl.NUM_CLASSES             # downlink delivered, one per class
    assert all(rl.PDU_SUBNET in a for a in ue_rules)
    sink_rules = rl.count_rules(rl.SINK_CONTAINER)
    assert len(sink_rules) == 2 * rl.NUM_DU * rl.NUM_CLASSES   # UL delivered + DL admitted
    assert rl.count_rules(rl.cu_container(1)) == []
    assert len(rl.count_setup_commands()) == len(rl.counter_containers())


def test_parse_counters_reads_iptables_nvx_output():
    text = "\n".join([
        "Chain CCDC (3 references)",
        "    pkts      bytes target     prot opt in     out     source               destination",
        "     100    120000 RETURN     udp  --  *      *       0.0.0.0/0            "
        f"{rl.cu_ip(1)}         udp dpt:{rl.F1U_PORT}",
        "       0         0 RETURN     udp  --  *      *       0.0.0.0/0            "
        f"{rl.PDU_SUBNET}      udp dpt:{rl.flow_port(1, 2)}",
        "      12     14400 RETURN     udp  --  *      *       0.0.0.0/0            "
        f"{rl.PDU_SUBNET}      udp dpt:{rl.flow_port(1, 2)}",
    ])
    parsed = rl.parse_counters(text)
    assert parsed[(rl.cu_ip(1), rl.F1U_PORT)] == 120000
    assert parsed[(rl.PDU_SUBNET, rl.flow_port(1, 2))] == 14400   # duplicates summed
    assert rl.parse_counters("garbage\n") == {}


# --- nominal window sampling ------------------------------------------------------
def test_sample_window_state_respects_pinning_and_keeps_uu_open():
    rng = random.Random(7)
    at_map = rl.attachment_map({3: 1})
    pinned = _d1_mode() | {"E2": 0}
    for _ in range(50):
        state = rl.sample_window_state(rng, at_map, pinned)
        assert state.ifaces["Uu"] == 1                 # never physically toggled
        assert state.qi[1] == 4 and state.ng[3] == 0 and state.ifaces["E2"] == 0
        assert state.at == at_map
        assert set(state.mode()) == {v for v in rl.dataset_columns()
                                     if v in FiveGTestbedSystem().operator_controlled}
        assert all(v > 0 for v in state.offered_mbps["U"].values())


def test_sample_window_state_confounds_closures_with_demand():
    rng = random.Random(0)
    lo = [rl.sample_window_state(rng, rl.attachment_map()) for _ in range(4000)]
    closed = {True: 0, False: 0}
    windows = {True: 0, False: 0}
    for s in lo:
        high = s.demand_frac > 0.5
        windows[high] += 1
        closed[high] += sum(1 for v in s.ng.values() if v == 0)
    assert closed[False] / windows[False] > closed[True] / windows[True]


def test_sample_window_state_rejects_unknown_pin():
    with pytest.raises(ValueError):
        rl.sample_window_state(random.Random(0), rl.attachment_map(), {"BOGUS": 0})


# --- load specs + row assembly ------------------------------------------------------
def _fixed_state():
    return rl.WindowState(
        demand_frac=0.5,
        qi={1: 4, 2: 1, 3: 1, 4: 1},
        at={1: 1, 2: 2, 3: 1, 4: 4},                   # D_1's AT3=1
        ng={1: 1, 2: 1, 3: 0, 4: 1},
        ifaces={"Uu": 1, "N6": 1, "Xn": 1, "E2": 0, "A1": 1},
    )


def test_load_specs_target_flow_ports():
    state = _fixed_state()
    state.offered_mbps = {d: {(i, k): 1.0 for i in range(1, 5) for k in range(1, 11)}
                          for d in rl.DIRECTIONS}
    ul = rl.ul_load_spec(2, state, 6.0)
    assert all(f["dst"] == rl.SINK_IP for f in ul["flows"])
    assert {f["port"] for f in ul["flows"]} == {rl.flow_port(2, k) for k in range(1, 11)}
    dl = rl.dl_load_spec({i: f"10.45.0.{i + 1}" for i in range(1, 5)}, state, 6.0)
    assert len(dl["flows"]) == rl.NUM_DU * rl.NUM_CLASSES
    assert {f["dst"] for f in dl["flows"]} == {f"10.45.0.{i + 1}" for i in range(1, 5)}


def _mb(mbps, duration=6.0):
    """Bytes that measure as ``mbps`` Mbit/s over ``duration``."""
    return mbps * duration * 1e6 / 8.0


def _synthetic_snapshots(state, duration=6.0):
    """Counters consistent with 1 Mbit/s per admitted class flow on every chain stage."""
    sent = {d: {f"{i}:{k}": _mb(1.0, duration) for i in range(1, 5) for k in range(1, 11)}
            for d in rl.DIRECTIONS}
    before = {c: {} for c in rl.counter_containers()}
    after = {}
    for i in range(1, 5):
        admitted = [k for k in range(1, 11) if k >= state.qi[i]]
        after[rl.du_container(i)] = {
            (rl.cu_ip(state.at[i]), rl.F1U_PORT): _mb(1.0 * len(admitted), duration)}
        delivered_dl = len(admitted) if state.ng[state.at[i]] else 0
        after[rl.ue_container(i)] = {
            (rl.PDU_SUBNET, rl.flow_port(i, k)): _mb(1.0, duration)
            for k in admitted[:delivered_dl]}
    sink = {}
    for i in range(1, 5):
        for k in range(1, 11):
            if k >= state.qi[i]:
                sink[(rl.PDU_SUBNET, rl.flow_port(i, k))] = _mb(1.0, duration)
                if state.ng[state.at[i]]:
                    sink[(rl.SINK_IP, rl.flow_port(i, k))] = _mb(1.0, duration)
    after[rl.SINK_CONTAINER] = sink
    return sent, before, after


def test_assemble_row_maps_counters_onto_the_schema():
    state = _fixed_state()
    sent, before, after = _synthetic_snapshots(state)
    row = rl.assemble_row(window=3, t_start=1.0, duration=6.0, state=state,
                          sent_bytes=sent, before=before, after=after)
    assert row is not None
    assert set(row) == set(rl.dataset_columns())
    assert row["L_1_1_U"] == pytest.approx(1.0)
    # QI_1 = 4: classes 1-3 offered but not admitted
    assert row["Ladm_1_U"] == pytest.approx(7.0)
    assert row["Ladm_2_D"] == pytest.approx(10.0)
    # attachment: DU_3 carried on CU_1 only
    assert row["Chat_3_1_U"] == pytest.approx(10.0)
    assert row["Chat_3_3_U"] == 0.0
    assert row["Cbar_3_D"] == pytest.approx(10.0)
    assert row["Chat_3_1_D"] == pytest.approx(10.0)
    # midhaul: NG_3 = 0 zeroes CU_3's Ctil, so DU_3 (on CU_1) is unaffected but any DU
    # still attached to CU_3 loses its carried load
    assert row["Ctil_3_1_U"] == pytest.approx(10.0)
    assert row["C_3_U"] == pytest.approx(10.0)
    assert row["Cbar_3_U"] == pytest.approx(10.0)
    assert row["Ctil_3_3_U"] == 0.0
    assert row["T_3_U"] == pytest.approx(10.0)
    assert row["T_3_D"] == pytest.approx(10.0)
    # operator + metadata columns recorded
    assert row["QI1"] == 4.0 and row["AT3"] == 1.0 and row["NG3"] == 0.0 and row["E2"] == 0.0
    assert row["window"] == 3.0 and row["duration"] == 6.0 and row["demand"] == 0.5


def test_assemble_row_detects_counter_reset():
    state = _fixed_state()
    sent, before, after = _synthetic_snapshots(state)
    reset_before = dict(before)
    reset_before[rl.SINK_CONTAINER] = {(rl.SINK_IP, rl.flow_port(4, 10)): 10**12}
    row = rl.assemble_row(window=0, t_start=0.0, duration=6.0, state=state,
                          sent_bytes=sent, before=reset_before, after=after)
    assert row is None


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
    assert rl.parse_du_target_cu(cfg) == 1          # ranctl reads the attachment back
    ports = rl.zmq_ports(3)
    assert f"tx_port=tcp://{rl.du_ip(3)}:{ports['tx']}" in cfg
    assert f"rx_port=tcp://{rl.ue_ip(3)}:{ports['rx']}" in cfg
    assert "pci: 3" in cfg
    assert "sector_id: 3" in cfg                    # unique NR-CGI under a shared gnb_id
    assert "mcs_table: qam64" in cfg
    with pytest.raises(ValueError):
        rl.parse_du_target_cu("no f1 here")


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
    # sink + Xn/RIC stubs (E2/A1/Xn enactment endpoints), loadgen mounted where it runs
    for container, ip in ((rl.SINK_CONTAINER, rl.SINK_IP), (rl.XN_CONTAINER, rl.XN_IP),
                          (rl.RIC_NEARRT_CONTAINER, rl.RIC_NEARRT_IP),
                          (rl.RIC_NONRT_CONTAINER, rl.RIC_NONRT_IP)):
        assert f"container_name: {container}" in text
        assert f"ipv4_address: {ip}" in text
    assert text.count("image: ccd-5g-sink") == 4
    assert text.count("udp_load.py:/udp_load.py:ro") == rl.NUM_DU + 1   # 4 UEs + sink


def test_ran_compose_reattach_changes_du_dependency():
    text = rl.render_ran_compose(rl.attachment_map({3: 1}))
    assert "depends_on: [cu1]" in text              # DU_3 now waits on CU_1
    assert "depends_on: [cu3]" not in text          # nothing attached to CU_3 anymore
