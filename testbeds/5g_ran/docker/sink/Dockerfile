# Traffic sink / auxiliary node for the 5G cloud-RAN testbed.
#
# One image serves two roles in compose-ran.yml:
#   - the data-network sink (ccd5g-sink): terminates the per-class UDP flows behind the
#     UPF (UL receiver + DL load generator, scripts/udp_load.py mounted at runtime) and
#     hosts the DL 5QI admission filter + the per-flow byte counters (iptables);
#   - the Xn / near-RT RIC / non-RT RIC stubs: placeholder endpoints that make the
#     Xn/E2/A1 interface closures physically meaningful (mirroring the IT testbed's
#     mgmt_net) until FlexRIC lands.
FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 iptables iproute2 iputils-ping \
    && rm -rf /var/lib/apt/lists/*

CMD ["sleep", "infinity"]
