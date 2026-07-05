"""Run CCD on the paper's illustrative example.

Usage::

    python main.py [m]        # m = number of application servers (default 10)

Builds the gateway + m servers + database system, generates an observational dataset of
nominal operation, and runs CCD to select a degraded operating mode that contains the
attack while preserving throughput. Prints the selected mode and its estimated
functionality Phi-hat (via DoWhy causal inference), alongside a naive observational
estimate to illustrate why causal inference is needed.
"""

from __future__ import annotations

import sys
import warnings

warnings.filterwarnings("ignore")

from dowhy.gcm.config import disable_progress_bars

from ccd.ccd import ccd
from ccd.inference import naive_estimate
from ccd.simulator import generate_dataset
from ccd.system import SystemModel

disable_progress_bars()


def main(m: int = 10, steps: int = 10_000, seed: int = 0) -> None:
    print(f"Illustrative example: gateway + m={m} servers + database\n")

    system = SystemModel(m)
    data = generate_dataset(system, steps=steps, seed=seed)

    phi_nominal = float(data["T"].mean())
    alpha = 0.5 * phi_nominal

    result = ccd(system, data, alpha=alpha)

    print(f"Nominal functionality   Phi(M)      = {phi_nominal:8.2f} req/s")
    print(f"Critical level          alpha=0.5Phi = {alpha:8.2f} req/s\n")

    if result.intervention is None:
        print("CCD: no degraded mode satisfies the containment/functionality criteria.")
        return

    print(f"Selected degraded mode  u = {result.intervention}")
    print(f"  -> contains lateral movement (A_2..A_{m} closed) and DB access (M_1 closed),")
    print("     and isolates the compromised n_1 from the gateway (N_1 closed).\n")

    naive = naive_estimate(data, result.intervention.variables)
    print(f"Estimated functionality Phi-hat(M_u) [causal, do-intervention] = {result.phi:8.2f} req/s"
          f"  ({result.phi / phi_nominal:5.1%} of nominal)")
    print(f"Naive observational     E[T | links closed]                   = {naive:8.2f} req/s"
          f"  (biased: closures confounded with low workload)\n")

    verdict = "FEASIBLE (meets alpha)" if result.feasible else "INFEASIBLE (below alpha)"
    print(f"Result: {verdict}  ->  Phi-hat {'>=' if result.feasible else '<'} alpha")


if __name__ == "__main__":
    m_arg = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    main(m_arg)
