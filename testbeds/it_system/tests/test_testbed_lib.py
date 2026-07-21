"""Pure (docker-free) unit tests for the IT-system testbed library."""

import pytest
import testbed_lib as tl
from ccd.system.it_testbed_system import ITTestbedSystem


# --- compose generation ------------------------------------------------------
def test_generate_compose_structure():
    text = tl.generate_compose(3)
    for i in (1, 2, 3):
        assert f"container_name: ccd_server{i}" in text
        assert f"ipv4_address: 172.28.1.{100 + i}" in text     # service_net
        assert f"ipv4_address: 172.28.2.{100 + i}" in text     # db_net
        assert f"ipv4_address: 172.28.3.{100 + i}" in text     # mgmt_net (A_i meaningful)
        assert f"\"{tl.SERVER_HOST_PORT_BASE + i}:{tl.SERVER_PORT}\"" in text
    assert "container_name: ccd_gateway" in text
    assert f"ipv4_address: {tl.GATEWAY_SERVICE_IP}" in text
    assert text.count("cap_add: [NET_ADMIN]") == 4             # gateway + 3 servers
    assert "image: postgres:16" in text
    assert "pg_isready" in text
    assert '"172.28.1.101:5000,172.28.1.102:5000,172.28.1.103:5000"' in text


def test_generate_compose_is_deterministic():
    assert tl.generate_compose(4) == tl.generate_compose(4)


@pytest.mark.parametrize("m", [1, 0, tl.MAX_M + 1, 200])
def test_generate_compose_rejects_out_of_range_m(m):
    with pytest.raises(ValueError):
        tl.generate_compose(m)


# --- closure probability -----------------------------------------------------
def test_p_close_endpoints_and_monotonicity():
    assert tl.p_close(50) == pytest.approx(0.30)
    assert tl.p_close(150) == pytest.approx(0.05)
    assert tl.p_close(100) == pytest.approx(0.175)
    ws = [50, 70, 90, 110, 130, 150]
    vals = [tl.p_close(w) for w in ws]
    assert all(a >= b for a, b in zip(vals, vals[1:]))         # non-increasing
    assert tl.p_close(10) == pytest.approx(0.30)               # clipped low
    assert tl.p_close(500) == pytest.approx(0.05)              # clipped high


# --- link -> iptables mapping ------------------------------------------------
def test_rule_for_each_link_type():
    n = tl.rule_for("N3")
    assert n.container == "ccd_gateway" and "172.28.1.103" in n.rule_args and "5000" in n.rule_args
    m = tl.rule_for("M2")
    assert m.container == "ccd_server2" and "172.28.2.10" in m.rule_args and "5432" in m.rule_args
    a = tl.rule_for("A4")
    assert a.container == "ccd_server1" and "172.28.3.104" in a.rule_args


def test_rule_for_rejects_bad_links():
    with pytest.raises(ValueError):
        tl.rule_for("Z1")
    with pytest.raises(ValueError):
        tl.rule_for("A1")           # n_1 is the mgmt host; A_i requires i >= 2


def test_sync_commands_are_flush_first_and_idempotent():
    cmds = tl.sync_commands({"N1": 0, "M1": 0, "A2": 0}, m=3)
    by_container = {c[2]: c[-1] for c in cmds}
    # every controlled container is flushed first
    assert all(c[3] == "sh" and c[4] == "-c" for c in cmds)
    assert all(script.startswith("iptables -F CCD") for script in by_container.values())
    # the D_1 mode's rules land in the right containers
    assert "172.28.1.101" in by_container["ccd_gateway"]        # N1 at the gateway
    assert "172.28.2.10" in by_container["ccd_server1"]         # M1 at server 1
    assert "172.28.3.102" in by_container["ccd_server1"]        # A2 at server 1 (mgmt host)
    # calling twice yields identical commands (no incremental bookkeeping)
    assert tl.sync_commands({"N1": 0, "M1": 0, "A2": 0}, m=3) == cmds


def test_sync_commands_open_state_only_flushes():
    cmds = tl.sync_commands({"N1": 1, "M1": 1}, m=2)
    for c in cmds:
        assert c[-1] == "iptables -F CCD"                       # no closed rules -> just flush


def test_sync_commands_golden_d1_mode_m3():
    """Golden check of the enacted D_1 mode do(N1,M1,A2,A3=0) at m=3."""
    mode = {"N1": 0, "M1": 0, "A2": 0, "A3": 0}
    cmds = tl.sync_commands(mode, m=3)
    scripts = {c[2]: c[-1] for c in cmds}
    assert scripts["ccd_gateway"] == (
        "iptables -F CCD; iptables -A CCD -d 172.28.1.101 -p tcp --dport 5000 "
        "-j REJECT --reject-with tcp-reset"
    )
    assert scripts["ccd_server1"] == (
        "iptables -F CCD; "
        "iptables -A CCD -d 172.28.3.102 -j REJECT; "                # A2 (links sorted by name)
        "iptables -A CCD -d 172.28.3.103 -j REJECT; "                # A3
        "iptables -A CCD -d 172.28.2.10 -p tcp --dport 5432 -j REJECT --reject-with tcp-reset"  # M1
    )
    assert scripts["ccd_server2"] == "iptables -F CCD"
    assert scripts["ccd_server3"] == "iptables -F CCD"


# --- dataset schema ----------------------------------------------------------
@pytest.mark.parametrize("m", [2, 5, 10])
def test_dataset_columns_match_throughput_nodes(m):
    observed = set(tl.dataset_columns(m)) - set(tl.METADATA_COLUMNS)
    assert observed == ITTestbedSystem(m).throughput_nodes


def test_dataset_columns_order_is_stable():
    cols = tl.dataset_columns(2)
    assert cols[0] == "W"
    assert cols[-len(tl.METADATA_COLUMNS):] == tl.METADATA_COLUMNS
    assert "T" in cols
