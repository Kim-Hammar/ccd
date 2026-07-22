"""
The two-layer system model for the dockerized 5G cloud-RAN testbed
(``testbeds/5g_ran/``).

The testbed realizes the 5G example as a virtual network of containers running the real
RAN stack: srsRAN Project gNBs with a ZeroMQ virtual radio, srsUE terminals, and an
Open5GS 5G core. The two-layer model is identical to ``FiveGSystem`` -- same causal
graph, attack graph, cross-layer edges, and intervention hooks, so mode selection is
unchanged (unit tested). The only difference is the *source of the dataset D*: it is
measured on the running containers (``testbeds/5g_ran/scripts/generate_dataset.py``)
rather than simulated, so ``generate_dataset`` raises.

Measurement-driven graph deviations (analogous to the IT testbed's ``N_i -> Tt_i``
edges) are added here only if a variable measured on the real RAN turns out to be
physically gated in a way the simulator graph does not capture -- verified against
real data, not assumed.
"""

from __future__ import annotations
from dataclasses import dataclass
import pandas as pd
from ccd.system.five_g_system import FiveGSystem


@dataclass
class FiveGTestbedSystem(FiveGSystem):
    """The 5G cloud-RAN example instantiated on the dockerized srsRAN/Open5GS testbed."""

    # use_known_product_mechanisms stays True (inherited): the midhaul products
    # Ctil = NG_j * Chat are gated on the testbed exactly as in the reference model.

    def generate_dataset(self, steps: int = 10_000, seed: int = 0) -> pd.DataFrame:
        """The testbed model has no simulator: D is measured on the running containers."""
        raise NotImplementedError(
            "FiveGTestbedSystem has no simulator; collect the dataset on the testbed "
            "with testbeds/5g_ran/scripts/generate_dataset.py and pass the CSV to ccd()."
        )
