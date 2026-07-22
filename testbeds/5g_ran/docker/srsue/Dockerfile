# srsRAN 4G srsUE built from source with ZeroMQ, used as the 5G SA UE that attaches to
# the srsRAN Project gNB over the virtual (ZMQ) radio.
#
# Full make + make install (not just the srsue target): the ZMQ RF driver is a runtime-
# loaded plugin (libsrsran_rf_zmq.so) that must be built and installed for srsue to
# open the zmq device.
FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
    cmake make gcc g++ pkg-config git ca-certificates \
    libfftw3-dev libmbedtls-dev libboost-program-options-dev libconfig++-dev libsctp-dev \
    libzmq3-dev iproute2 iputils-ping iperf3 iptables \
    && rm -rf /var/lib/apt/lists/*

# Pinned master commit: release_23_11 does not compile on Ubuntu 24.04 (gcc 13), and
# this commit is the build the ZMQ sync gate was verified with.
WORKDIR /opt
RUN git clone https://github.com/srsRAN/srsRAN_4G.git \
    && cd srsRAN_4G && git checkout 6bcbd9e5bf8686aa7085202cd847c5ddd64a9c16
WORKDIR /opt/srsRAN_4G/build
ARG MAKE_JOBS=32
RUN cmake ../ -DENABLE_ZEROMQ=ON -DCMAKE_BUILD_TYPE=Release \
    -DENABLE_UHD=OFF -DENABLE_BLADERF=OFF -DENABLE_SOAPYSDR=OFF \
    && make -j"${MAKE_JOBS}" \
    && make install \
    && ldconfig

# python3 runs the in-container UDP load generator (scripts/udp_load.py): the uplink
# flows must originate inside the UE's network namespace to traverse tun_srsue.
RUN apt-get update && apt-get install -y --no-install-recommends python3 \
    && rm -rf /var/lib/apt/lists/*

CMD ["srsue", "--version"]
