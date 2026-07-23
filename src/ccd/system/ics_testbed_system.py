"""
The two-layer system model for the dockerized industrial control system (ICS) testbed
(``testbeds/ics/``).

The two-layer model is identical to ``IcsSystem`` (same graphs, cross-layer edges, and
hooks), so mode selection is unchanged (unit tested). Only the source of ``D`` differs:
it is measured on the running containers (the Tennessee Eastman process via ``tep2py``
-- the paper's pyTEP needs a licensed MATLAB -- with the G2 gateway as iptables rules;
``testbeds/ics/scripts/generate_dataset.py``), so ``generate_dataset`` raises.

No measurement-driven graph deviation is needed (unlike the IT testbed's
``N_i -> Tt_i``): every operator variable already gates its measured signal through an
existing parent (``Ctil = G2*C``, ``V = Chat*Ctil``, ``I = f(W)``), so the known
products and the base deactivation rule capture the testbed's gating.
"""

from __future__ import annotations
from dataclasses import dataclass
import pandas as pd
from ccd.system.ics_system import IcsSystem


@dataclass
class IcsTestbedSystem(IcsSystem):
    """The ICS (Tennessee Eastman) example instantiated on the dockerized testbed."""

    # use_known_product_mechanisms stays True (inherited): Ctil = G2*C and
    # V = Chat*Ctil are physically gated on the testbed exactly as in the reference model

    def generate_dataset(self, steps: int = 10_000, seed: int = 0) -> pd.DataFrame:
        """The testbed model has no simulator: D is measured on the running containers."""
        raise NotImplementedError(
            "IcsTestbedSystem has no simulator; collect the dataset on the testbed with "
            "testbeds/ics/scripts/generate_dataset.py and pass the CSV to ccd()."
        )
