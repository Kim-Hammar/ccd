"""
Open-loop paced UDP load generator, run *inside* a testbed container (UE_i for uplink,
the sink for downlink) via ``docker exec python3 /udp_load.py '<json spec>'``.

The spec is ``{"duration": s, "payload_bytes": n, "flows": [{"id", "dst", "port",
"mbps"}, ...]}`` (built by ``ran_lib.ul_load_spec`` / ``dl_load_spec``). Each flow sends
fixed-size datagrams at its target rate, scheduled open-loop against a monotonic clock
(a min-heap of per-flow next-send times), so the offered rate does not react to loss.

Sends that fail are still *counted as offered*: an EPERM from a local iptables REJECT
(the 5QI admission filter) or an ICMP-induced error is precisely "offered but not
admitted/delivered", and the offered load L^{ik} must include it. The report on stdout,
``{"sent_bytes": {flow_id: bytes}}``, is the measured L for the window row.

Stdlib only: the RAN container images carry no third-party Python packages.
"""

import heapq
import json
import socket
import sys
import time


def run(spec: dict) -> dict:
    duration = float(spec["duration"])
    payload = b"x" * int(spec.get("payload_bytes", 1200))
    flows = spec["flows"]
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sent = {str(flow["id"]): 0 for flow in flows}

    start = time.monotonic()
    deadline = start + duration
    heap: list = []
    for n, flow in enumerate(flows):
        rate = float(flow["mbps"]) * 1e6 / 8.0            # bytes/s
        if rate <= 0:
            continue
        interval = len(payload) / rate
        # stagger flow starts across one interval to avoid synchronized bursts
        heapq.heappush(heap, (start + interval * (n + 1) / (len(flows) + 1), n, interval))

    while heap:
        next_t, n, interval = heapq.heappop(heap)
        if next_t >= deadline:
            continue
        now = time.monotonic()
        if next_t > now:
            time.sleep(next_t - now)
        flow = flows[n]
        try:
            sock.sendto(payload, (str(flow["dst"]), int(flow["port"])))
        except OSError:
            pass                                          # rejected/unreachable: still offered
        sent[str(flow["id"])] += len(payload)
        heapq.heappush(heap, (next_t + interval, n, interval))

    sock.close()
    return {"sent_bytes": sent}


if __name__ == "__main__":
    print(json.dumps(run(json.loads(sys.argv[1]))))
