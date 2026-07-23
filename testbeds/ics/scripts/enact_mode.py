"""
Enact a CCD-selected degraded mode (from ``ccd_result.json``) on the live ICS testbed:
G2 as an iptables REJECT on the control server, Chat/W as application modes. For
D_1 = do(W=0, G2=0, Chat=0) this seals the supervisory net from the enterprise,
switches the field controllers to local control, and puts the web server in safe mode.

Usage:
  python enact_mode.py --result ../data/ccd_result.json [--dry-run] [--reset]
"""

from __future__ import annotations
import argparse
import json
import icsctl


def main() -> None:
    parser = argparse.ArgumentParser(description="Enact a CCD mode on the ICS testbed.")
    parser.add_argument("--result", required=True, help="ccd_result.json from run_ccd.py")
    parser.add_argument("--dry-run", action="store_true", help="print the plan only")
    parser.add_argument("--reset", action="store_true",
                        help="restore nominal operation instead of enacting")
    args = parser.parse_args()

    if args.reset:
        icsctl.reset(dry_run=args.dry_run)
        print("Reset: gateway open, remote control, web up.")
        return

    with open(args.result) as f:
        result = json.load(f)
    mode = result.get("intervention")
    if not mode:
        print("Selected mode is empty (do()): nothing to enact -- full functionality.")
        icsctl.reset(dry_run=args.dry_run)
        return

    icsctl.apply({v: int(x) for v, x in mode.items()}, dry_run=args.dry_run)
    applied = ", ".join(f"{v}={mode[v]}" for v in sorted(mode))
    print(("[dry-run] " if args.dry_run else "") + f"Enacted mode: do({applied}).")


if __name__ == "__main__":
    main()
