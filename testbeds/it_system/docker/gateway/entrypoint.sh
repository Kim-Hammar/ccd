#!/bin/sh
# Install the (empty) CCD iptables chain used for link control (the N_i gateway->server
# blocks land here), then start the gateway. Guarded so restarts are idempotent.
set -e

iptables -N CCD 2>/dev/null || true
iptables -C OUTPUT -j CCD 2>/dev/null || iptables -I OUTPUT 1 -j CCD

exec "$@"
