#!/bin/sh
set -e

iptables -N CCD 2>/dev/null || true
iptables -C OUTPUT -j CCD 2>/dev/null || iptables -I OUTPUT 1 -j CCD

exec "$@"
