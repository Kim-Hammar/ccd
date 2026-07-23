"""
Enact a CCD-selected degraded mode (from ``ccd_result.json``) on the live testbed by
closing the mode's links via iptables -- including the A_i management-link blocks,
which have no throughput effect but realize the attack-graph containment.

Usage:
  python enact_mode.py --result ../data/ccd_result.json [--dry-run] [--reset]
"""

from __future__ import annotations
import argparse
import json
import linkctl


def main() -> None:
    parser = argparse.ArgumentParser(description="Enact a CCD mode on the testbed.")
    parser.add_argument("--result", required=True, help="ccd_result.json from run_ccd.py")
    parser.add_argument("--dry-run", action="store_true", help="print the iptables plan only")
    parser.add_argument("--reset", action="store_true", help="open all links instead of enacting")
    args = parser.parse_args()

    with open(args.result) as f:
        result = json.load(f)
    m = int(result["m"])

    if args.reset:
        linkctl.reset(m, dry_run=args.dry_run)
        print("Reset: all links open.")
        return

    mode = result.get("intervention")
    if not mode:
        print("Selected mode is empty (do()): nothing to enact -- full functionality.")
        linkctl.reset(m, dry_run=args.dry_run)
        return

    linkctl.reset(m, dry_run=args.dry_run)
    linkctl.apply({v: int(x) for v, x in mode.items()}, m, dry_run=args.dry_run)
    closed = ", ".join(sorted(mode))
    print(("[dry-run] " if args.dry_run else "") + f"Enacted mode: closed {closed}.")


if __name__ == "__main__":
    main()
