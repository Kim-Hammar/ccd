"""
Prompts for the LLM baselines

The prompts give an operator's view of the incident: the system's components and
networks, what the detection system reports, the controls that can be reconfigured
(with their machine-readable names and legal values), and the operational objective.
They deliberately withhold CCD's inputs -- the causal model, the attack graph, and the
cross-layer edges -- so the action list names each control without stating what its
reconfiguration propagates to, and the system description covers topology rather than
causal mechanism. Working out those effects is the task being evaluated.
"""

from __future__ import annotations
from typing import List
from ccd.system.five_g_system import FiveGSystem
from ccd.system.ics_system import CHAT, G2C, G2E, W
from ccd.system.ics_system import IcsSystem
from ccd.system.illustrative_example_system import IllustrativeExampleSystem


def _render(role: str, system_text: str, compromise: str, actions: List[str],
            objective: str, example: str) -> str:
    """Assemble the shared prompt skeleton."""
    action_lines = "\n".join(f"- {a}" for a in actions)
    return f"""You are {role}. An intrusion has just been detected; you must respond now
by choosing which (if any) of the actions listed below to apply.

== System ==
{system_text}

== Detected compromise ==
{compromise}

== Available actions ==
Each action pins one named control variable to one of its listed values; you may apply
any combination of actions. Omitting a variable leaves it at its nominal setting.
{action_lines}

== Objective ==
{objective}

== Response format ==
Respond with a single JSON object and nothing else, in exactly this shape:
{{"intervention": {{"<VARIABLE>": <value>}}, "justification": "<short explanation>"}}
"intervention" maps each variable you act on to its chosen value; an empty object
{{"intervention": {{}}, "justification": "..."}} means you take no action.
Format illustration only (not a recommendation): {example}
"""


def it_prompt(system: IllustrativeExampleSystem, phi_nominal: float, alpha: float) -> str:
    """The operator prompt for the IT system (gateway + ``m`` servers + database)."""
    m = system.m
    actions = []
    for i in range(1, m + 1):
        actions.append(f'"{system.N(i)}": 0 -- close the gateway link to server n_{i}')
    for i in range(1, m + 1):
        actions.append(f'"{system.M(i)}": 0 -- close the database link of server n_{i}')
    for i in range(2, m + 1):
        actions.append(f'"{system.A(i)}": 0 -- close the management connection to server n_{i}')
    return _render(
        role="the on-call security operator of an e-commerce IT service",
        system_text=(
            f"An internet-facing gateway distributes customer requests across {m} application "
            f"servers n_1..n_{m}, each of which runs a replica of the web service and has its "
            "own link to a shared database. Administrators reach the servers n_2..n_"
            f"{m} over a separate management network."),
        compromise=(
            "The intrusion detection system confirms code execution on server n_1. Database "
            "credentials are stored on that server, and it is also the host from which "
            "administrators reach the other servers. No other component shows signs of "
            "compromise."),
        actions=actions,
        objective=(
            "Prevent the attacker from extending its access beyond n_1 and from disrupting or "
            "corrupting the service, while keeping functionality at or above the critical level. "
            f"Functionality is Phi = the service throughput in req/s plus {system.KAPPA:g} for "
            "each management connection that remains open. Nominal functionality is "
            f"{phi_nominal:.2f}; you must keep Phi >= {alpha:.2f} "
            f"({system.alpha_fraction:.0%} of nominal). Among sufficient responses, prefer the "
            "least restrictive one."),
        example='{"intervention": {"N2": 0}, "justification": "..."}')


def five_g_prompt(system: FiveGSystem, phi_nominal: float, alpha: float) -> str:
    """The operator prompt for the 5G cloud-RAN (DU/CU split, core, RICs)."""
    dus = range(1, system.num_du + 1)
    cus = range(1, system.num_cu + 1)
    q = system.num_classes
    actions = []
    for i in dus:
        actions.append(f'"{system.Uu(i)}": 0 -- disable DU_{i}\'s radio interface')
    for i in dus:
        actions.append(f'"{system.QI(i)}": v -- set DU_{i}\'s 5QI admission threshold to v, '
                       f"the maximal admitted class; integer v in 0..{q}")
    for i in dus:
        actions.append(f'"{system.AT(i)}": j -- attach DU_{i} to CU_j, integer j in '
                       f"1..{system.num_cu} (nominally {i})")
    for j in cus:
        actions.append(f'"{system.NG(j)}": 0 -- close CU_{j}\'s midhaul link to the core')
    actions.append('"E2": 0 -- close the near-real-time RIC interface E2')
    actions.append('"A1": 0 -- close the non-real-time RIC interface A1')
    actions.append('"N6": 0 -- close the core user-plane interface N6')
    actions.append('"Xn": 0 -- close the inter-gNB interface Xn')
    return _render(
        role="the operator of a 5G cloud radio access network",
        system_text=(
            f"The network comprises {system.num_du} gNBs, each split into a distributed unit "
            "DU_i with its radio interface Uu_i and a centralized unit CU_j; DU_i is nominally "
            "attached to CU_i, and each CU connects to the 5G core over its own midhaul link "
            f"NG_j. User traffic is classified into 5QI priority classes 1..{q}, and each DU "
            "applies a 5QI admission threshold QI_i (nominally "
            f"{q}). The core connects to data networks over the N6 interface, the gNBs are "
            "interconnected over Xn, and the RAN is managed by a near-real-time RIC over the E2 "
            "interface and a non-real-time RIC over the A1 interface."),
        compromise=(
            "The intrusion detection system confirms two footholds: the attacker controls UE "
            "devices attached to DU_1 whose traffic falls in 5QI classes 7-10, and it has code "
            "execution on CU_3. It has not been observed beyond CU_3. From a compromised CU an "
            "attacker is generally able to reach the RAN management functions and the core "
            "network."),
        actions=actions,
        objective=(
            "Stop the attacker's traffic and prevent it from reaching the RICs, the core, or any "
            "further RAN component, while keeping functionality at or above the critical level. "
            "Functionality is Phi = the aggregate uplink and downlink throughput of the four DUs "
            f"in Mbit/s plus {system.OMEGA:g} for each of the two RIC interfaces (E2, A1) that "
            f"remains open. Nominal functionality is {phi_nominal:.2f}; you must keep Phi >= "
            f"{alpha:.2f} ({system.alpha_fraction:.0%} of nominal). Among sufficient responses, "
            "prefer the least restrictive one."),
        example='{"intervention": {"QI2": 3, "NG4": 0}, "justification": "..."}')


def ics_prompt(system: IcsSystem, phi_nominal: float, alpha: float) -> str:
    """The operator prompt for the ICS (Tennessee Eastman process)."""
    actions = [
        f'"{W}": 0 -- put the customer web server into static safe mode',
        f'"{G2E}": 0 -- close the gateway path from the enterprise network to the '
        "engineering station",
        f'"{G2C}": 0 -- close the gateway path from the enterprise network to the control '
        "server",
        f'"{CHAT}": 0 -- switch the field controllers from remote to local control mode',
    ]
    return _render(
        role="the control-room operator of a Tennessee Eastman chemical plant",
        system_text=(
            "The plant spans three networks. The enterprise network hosts a customer web portal "
            "on a web server behind the internet gateway. The supervisory network hosts the "
            "SCADA control server and an engineering station; the G2 gateway between the two "
            "networks enforces two separately closable policies, the path to the control server "
            f"({G2C}) and the path to the engineering station ({G2E}). The field network "
            "consists of the valve controllers that drive the chemical process; they run either "
            "in remote-control mode, following supervisory commands, or in local control mode."),
        compromise=(
            "The intrusion detection system confirms attacker code execution on the web server "
            "and on the SCADA control server; the engineering station and the field controllers "
            "show no signs of compromise."),
        actions=actions,
        objective=(
            "Prevent the attacker from propagating further and from unsafely manipulating the "
            "physical process, while keeping functionality at or above the critical level. "
            "Functionality is Phi = the integrity of the web service (0-1) plus the safety of "
            f"the physical process (0-1) plus {system.EPSILON:g} for each of the two gateway "
            f"policies that remains open. Nominal functionality is {phi_nominal:.2f}; you must "
            f"keep Phi >= {alpha:.2f} ({system.alpha_fraction:.0%} of nominal). Among sufficient "
            "responses, prefer the least restrictive one."),
        example='{"intervention": {"G2c": 0}, "justification": "..."}')
