"""
Enact a CCD-selected degraded mode on the live 5G RAN testbed.

Reads the mode from ``ccd_result.json`` (written by ``run_ccd.py``) and enacts it:
the ``AT_i`` assignments as control-plane DU reattachments (regenerate the compose,
recreate the DU+UE pair against the new CU) and everything else as iptables rules via
the CCD chains -- including the E2 block, which has no throughput effect but realizes
the containment of the attack graph (it is the only blocker of exploit EX3). This is
the actual containment step of the recovery procedure.

For D_1 = do(AT3=1, E2=0, NG3=0, QI1=4): DU_3 reattaches to CU_1, the near-RT RIC link
closes, CU_3's midhaul is severed, and DU_1's 5QI admission threshold rises to 4
(rejecting the attacker-controlled classes 1-3).

Usage:
  python enact_mode.py --result ../data/ccd_result.json [--dry-run] [--reset]
"""

from __future__ import annotations
import argparse
import json
import ran_lib as rl
import ranctl


def enact(mode: dict, *, dry_run: bool = False) -> None:
    """Apply ``mode`` (operator variable -> degraded value) to the live RAN."""
    reattach = {int(e.container[len("ccd5g-du"):]): e.target_cu
                for e in rl.reattachments(mode)}
    ranctl.apply_attachment(rl.attachment_map(reattach), dry_run=dry_run)
    ranctl.apply(mode, dry_run=dry_run)


def main() -> None:
    parser = argparse.ArgumentParser(description="Enact a CCD mode on the 5G testbed.")
    parser.add_argument("--result", required=True, help="ccd_result.json from run_ccd.py")
    parser.add_argument("--dry-run", action="store_true", help="print the plan only")
    parser.add_argument("--reset", action="store_true",
                        help="restore nominal operation instead of enacting")
    args = parser.parse_args()

    if args.reset:
        ranctl.apply_attachment(rl.attachment_map(), dry_run=args.dry_run)
        ranctl.reset(dry_run=args.dry_run)
        print("Reset: nominal attachment, all links open.")
        return

    with open(args.result) as f:
        result = json.load(f)
    mode = result.get("intervention")
    if not mode:
        print("Selected mode is empty (do()): nothing to enact -- full functionality.")
        ranctl.apply_attachment(rl.attachment_map(), dry_run=args.dry_run)
        ranctl.reset(dry_run=args.dry_run)
        return

    enact({v: int(x) for v, x in mode.items()}, dry_run=args.dry_run)
    applied = ", ".join(f"{v}={mode[v]}" for v in sorted(mode))
    print(("[dry-run] " if args.dry_run else "") + f"Enacted mode: do({applied}).")


if __name__ == "__main__":
    main()
