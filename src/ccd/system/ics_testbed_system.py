"""
The two-layer system model for the dockerized industrial control system (ICS) testbed
(``testbeds/ics/``).

The testbed realizes the ICS example as containerized services -- a web server
(enterprise), a control server (supervisory), a command client, and a process container
running the **Tennessee Eastman process** via ``tep2py`` (the MATLAB-free Fortran TEP; the
paper's pyTEP needs a licensed MATLAB) -- with the G2 gateway realized as iptables
firewall rules between the enterprise and supervisory container networks. The two-layer
model is identical to ``IcsSystem`` (same causal graph, attack graph, cross-layer edges,
and hooks), so mode selection is unchanged (unit tested). The only difference is the
*source of the dataset D*: it is measured on the running containers
(``testbeds/ics/scripts/generate_dataset.py``) rather than simulated, so
``generate_dataset`` raises.

No measurement-driven graph deviation is needed (unlike the IT testbed's ``N_i -> Tt_i``
edge): every operator variable already gates its measured signal through an existing
graph parent -- ``Ctil = G2*C`` (the firewall drops the command), ``V = Chat*Ctil`` (the
control server withholds it in local mode), ``I = f(W)`` (web safe mode), ``S`` via
``P = f(V, ...)`` -- so the known products and the base deactivation rule already capture
the testbed's gating.
"""

from __future__ import annotations
from dataclasses import dataclass
import pandas as pd
from ccd.system.ics_system import IcsSystem


@dataclass
class IcsTestbedSystem(IcsSystem):
    """The ICS (Tennessee Eastman) example instantiated on the dockerized testbed."""

    # use_known_product_mechanisms stays True (inherited): the control-state and valve
    # products Ctil = G2*C and V = Chat*Ctil are gated on the testbed exactly as in the
    # reference model (the firewall / control mode make them exactly 0).

    def generate_dataset(self, steps: int = 10_000, seed: int = 0) -> pd.DataFrame:
        """The testbed model has no simulator: D is measured on the running containers."""
        raise NotImplementedError(
            "IcsTestbedSystem has no simulator; collect the dataset on the testbed with "
            "testbeds/ics/scripts/generate_dataset.py and pass the CSV to ccd()."
        )
