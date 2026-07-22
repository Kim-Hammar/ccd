"""
SCADA command client for the ICS testbed, run inside the ``scada`` container (enterprise
net) via ``docker exec``. Sends the supervisory setpoint command ``C`` to the control
server across the G2 gateway, repeatedly for the window duration, so that when the gateway
is open the control server's most recent command stays fresh (``Ctil = C``) and when it is
closed (iptables REJECT) every send fails and ``Ctil`` decays to 0.

Prints the number of commands the control server accepted (failures are counted as offered
but not accepted). Stdlib only.
"""

import argparse
import time
import urllib.request


def main() -> None:
    parser = argparse.ArgumentParser(description="Send supervisory setpoint commands.")
    parser.add_argument("--url", required=True, help="control server /command URL")
    parser.add_argument("--level", type=float, required=True, help="setpoint magnitude C")
    parser.add_argument("--duration", type=float, default=6.0)
    parser.add_argument("--interval", type=float, default=0.5)
    args = parser.parse_args()

    end = time.monotonic() + args.duration
    accepted = 0
    while time.monotonic() < end:
        try:
            req = urllib.request.Request(args.url, data=f"level={args.level}".encode())
            urllib.request.urlopen(req, timeout=1.0).read()
            accepted += 1
        except Exception:
            pass
        time.sleep(args.interval)
    print(accepted)


if __name__ == "__main__":
    main()
