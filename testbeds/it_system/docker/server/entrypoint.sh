#!/bin/sh
# Install the (empty) CCD iptables chain used for link control, then start the app.
# The chain is populated later by linkctl (nominal maintenance toggles and mode
# enactment). Guarded so restarts are idempotent.
set -e

iptables -N CCD 2>/dev/null || true
iptables -C OUTPUT -j CCD 2>/dev/null || iptables -I OUTPUT 1 -j CCD

exec "$@"
