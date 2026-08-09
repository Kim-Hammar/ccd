# srsRAN 4G srsUE built from source with ZeroMQ

FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
    cmake make gcc g++ pkg-config git ca-certificates \
    libfftw3-dev libmbedtls-dev libboost-program-options-dev libconfig++-dev libsctp-dev \
    libzmq3-dev iproute2 iputils-ping iperf3 iptables \
    && rm -rf /var/lib/apt/lists/*

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

RUN apt-get update && apt-get install -y --no-install-recommends python3 \
    && rm -rf /var/lib/apt/lists/*

CMD ["srsue", "--version"]
