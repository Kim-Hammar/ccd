#!/bin/sh
# Install the (empty) CCD iptables chain used for the G2 gateway (the enterprise-subnet
# REJECT lands here), then start the control server. Guarded so restarts are idempotent.
set -e

iptables -N CCD 2>/dev/null || true
iptables -C INPUT -j CCD 2>/dev/null || iptables -I INPUT 1 -j CCD

exec "$@"
