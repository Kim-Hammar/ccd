"""
Prompts for the LLM baselines

The prompts give an operator's view of the incident: the system's components and
networks, where the detection system has localized the attacker, the controls that can be
reconfigured
(with their machine-readable names and legal values), and the operational objective.
They deliberately withhold CCD's inputs -- the causal model, the attack graph, and the
cross-layer edges -- so the action list names each control without stating what its
reconfiguration propagates to, the system description covers topology rather than causal
mechanism, and the detected compromise is pure localization: which components are known
to be compromised and which are not, never where the attacker could move next. Working
out those effects is the task being evaluated.
"""

from __future__ import annotations
from typing import List
from ccd.system.five_g_system import FiveGSystem
from ccd.system.ics_system import CHAT, G2C, G2E, W
from ccd.system.ics_system import IcsSystem
from ccd.system.illustrative_example_system import IllustrativeExampleSystem


def _render(role: str, system_text: str, compromise: str, actions: List[str],
            objective: str, example: str, model: str = "") -> str:
    """Assemble the shared prompt skeleton. ``model``, when given, adds the
    dependency/attack-path sections used by the with-model prompt variants."""
    action_lines = "\n".join(f"- {a}" for a in actions)
    model_section = f"\n{model}\n" if model else ""
    return f"""You are {role}. An intrusion has just been detected; you must respond now
by choosing which (if any) of the actions listed below to apply.

== System ==
{system_text}

== Detected compromise ==
{compromise}
{model_section}
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


def it_prompt(system: IllustrativeExampleSystem, _phi_nominal: float, _alpha: float) -> str:
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
            "The intrusion detection system confirms code execution on server n_1. No other "
            "component shows signs of compromise."),
        actions=actions,
        objective="Contain the attack while maintaining system functionality.",
        example='{"intervention": {"N2": 0}, "justification": "..."}')


def five_g_prompt(system: FiveGSystem, _phi_nominal: float, _alpha: float) -> str:
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
            "execution on CU_3. It has not been observed beyond CU_3."),
        actions=actions,
        objective="Contain the attack while maintaining system functionality.",
        example='{"intervention": {"QI2": 3, "NG4": 0}, "justification": "..."}')


def ics_prompt(system: IcsSystem, _phi_nominal: float, _alpha: float) -> str:
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
            "The intrusion detection system confirms code execution on the web server and on the "
            "SCADA control server. The engineering station and the field controllers show no "
            "signs of compromise."),
        actions=actions,
        objective="Contain the attack while maintaining system functionality.",
        example='{"intervention": {"G2c": 0}, "justification": "..."}')


# --- with-model variants -----------------------------------------------------
# These add, in natural language, the information CCD receives as structured input:
# the causal dependencies between system variables (including the known gating
# functions) and the attack paths with the controls that block them. They are the
# ablation against the baseline prompts above, which withhold both.

def it_prompt_with_model(system: IllustrativeExampleSystem, phi_nominal: float,
                         alpha: float) -> str:
    """The IT prompt plus the causal dependencies and the attack paths."""
    m = system.m
    base = it_prompt(system, phi_nominal, alpha)
    model = f"""== How the system fits together ==
The offered customer workload is split evenly across the {m} servers, so each server
receives about a {m}-th of it. A server carries the load it receives only while its own
database link is open; if that link is closed the server carries nothing. What the
service actually delivers from a server is its carried load gated by the gateway link:
closing the gateway link to a server drops that server's contribution to zero. Total
service throughput is the sum over the {m} servers. The management connections are
separate: they carry no customer traffic, and each one that stays open is itself worth
{system.KAPPA:g} req/s-equivalents of functionality.

== Known attack paths ==
The attacker's foothold on n_1 came from an exploit against a misconfigured
administration service, and holding it lets the attacker drop or corrupt the load that
n_1 carries. Two further moves are available from that foothold:
- Lateral movement to any other server n_i, carried out over the management connection
  to that server. Closing the management connection to n_i (A{{i}} = 0) makes this move
  impossible for n_i.
- Use of the database credentials found on n_1, exercised over n_1's own database link,
  which would give the attacker the shared database. Closing n_1's database link
  (M1 = 0) makes this move impossible.
Compromising a server would in turn let the attacker drop or corrupt the load that
server carries."""
    return base.replace("\n== Available actions ==", f"\n{model}\n\n== Available actions ==")


def five_g_prompt_with_model(system: FiveGSystem, phi_nominal: float, alpha: float) -> str:
    """The 5G prompt plus the causal dependencies and the attack paths."""
    base = five_g_prompt(system, phi_nominal, alpha)
    q = system.num_classes
    model = f"""== How the system fits together ==
Traffic reaches the network per DU and per 5QI class. A DU admits a class only while its
radio interface is enabled and the class index is at most that DU's admission threshold:
raising the threshold admits more classes, lowering it rejects the classes above it, and
disabling the radio admits nothing at all. The admitted load of a DU is carried to
exactly the one CU that the DU is attached to -- reattaching a DU moves its whole load to
the new CU, and a DU carries nothing through any CU it is not attached to. Traffic
reaches the core through the midhaul link of the CU that carries it: closing a CU's
midhaul drops the traffic of every DU currently attached to that CU, and drops nothing
from DUs attached elsewhere. Beyond the core, all traffic passes the core user-plane
interface N6 and the inter-gNB interface Xn, so closing either stops every DU's
throughput. Delivered throughput is summed over the four DUs in both directions. The two
RIC interfaces carry no user traffic; each one that stays open is itself worth
{system.OMEGA:g} Mbit/s-equivalents of functionality.

== Known attack paths ==
The attacker's UEs on DU_1 inject traffic in 5QI classes 7-10, which the network carries
as ordinary load for those classes; admitting classes only up to 6 on DU_1 removes that
traffic. Holding CU_3 lets the attacker manipulate whatever load CU_3 carries. Two
further moves are available from CU_3:
- Reaching the near-real-time RIC, carried out over the E2 interface. Closing E2
  (E2 = 0) makes this move impossible.
- Reaching the core network, carried out over CU_3's own midhaul link. Closing that
  midhaul (NG3 = 0) makes this move impossible.
Reaching either of those would in turn put the wider RAN within the attacker's reach.
Classes are indexed 1..{q}, with higher indices being the classes the attacker uses."""
    return base.replace("\n== Available actions ==", f"\n{model}\n\n== Available actions ==")


def ics_prompt_with_model(system: IcsSystem, phi_nominal: float, alpha: float) -> str:
    """The ICS prompt plus the causal dependencies and the attack paths."""
    base = ics_prompt(system, phi_nominal, alpha)
    model = f"""== How the system fits together ==
Web-service integrity depends only on the state of the web server: it is preserved while
the server serves its content unmodified, and lost both when the server is put into
static safe mode and when its responses are tampered with. Supervisory commands issued at
the control server reach the field controllers only while the gateway path to the control
server is open -- closing that path leaves the controllers with no supervisory input. The
valves act on that input only in remote-control mode; in local control mode they follow
their local control loop instead, holding the process at its safe operating point. The
state of the physical process, and hence its safety, is driven by whatever the valves
act on together with the local actuation and random disturbances. The gateway path to the
engineering station carries none of this; it matters only in that each gateway path left
open is itself worth {system.EPSILON:g} of functionality.

== Known attack paths ==
The attacker's foothold on the web server came from an exploit against the web
application, and holding it lets the attacker tamper with the web responses. Putting the
web server into static safe mode (W = 0) removes the application that exploit targets.
From the web server two lateral moves are available:
- To the engineering station, carried out over the gateway path to that station. Closing
  it (G2e = 0) makes this move impossible.
- To the control server, carried out over the gateway path to the control server. Closing
  it (G2c = 0) makes this move impossible. The detection system already reports the
  control server as compromised.
Holding the control server lets the attacker issue malicious supervisory commands, and
from there one further move is available: driving the field controllers themselves.
Switching the controllers to local control mode (Chat = 0) makes that move impossible."""
    return base.replace("\n== Available actions ==", f"\n{model}\n\n== Available actions ==")
