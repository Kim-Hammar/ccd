# srsRAN Project (5G gNB) built from source with the ZeroMQ RF driver.
# ZMQ lets us run the radio link entirely in software (no SDR hardware), which is how
# the RAN is virtualized in the testbed.
#
# srsRAN Project transitioned to OCUDU (Dec 2025) and the GitHub default branch is an
# archived stub, so we build from the last tagged srsRAN Project release (release_25_10).
FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
    cmake make gcc g++ pkg-config git ca-certificates \
    libfftw3-dev libmbedtls-dev libsctp-dev libyaml-cpp-dev libgtest-dev \
    libzmq3-dev iproute2 iputils-ping iperf3 iptables \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /opt
RUN git clone --depth 1 --branch release_25_10 https://github.com/srsRAN/srsRAN_Project.git
WORKDIR /opt/srsRAN_Project/build
# Build the monolithic gnb plus the split apps (srscu + srsdu, F1 interface) used for
# the 4-DU/4-CU topology; make install would build every target incl. tests.
ARG MAKE_JOBS=32
RUN cmake ../ -DENABLE_EXPORT=ON -DENABLE_ZEROMQ=ON -DENABLE_UHD=OFF \
    -DCMAKE_BUILD_TYPE=Release \
    && make -j"${MAKE_JOBS}" gnb srscu srsdu \
    && cp apps/gnb/gnb /usr/local/bin/gnb \
    && cp apps/cu/srscu /usr/local/bin/srscu \
    && cp apps/du/srsdu /usr/local/bin/srsdu

CMD ["gnb", "--version"]
