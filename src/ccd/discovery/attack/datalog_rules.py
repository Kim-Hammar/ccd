"""
MulVAL-style attack-graph derivation over pyDatalog.

Assembles the descriptor's reachability + attained privileges + exploit templates and the
scanner's ``vulExists`` facts into a small Datalog program with the MulVAL interaction
rules, then runs it to a fixpoint. A ``netexploit`` needs network access plus a
scan-confirmed service; ``credreuse`` / ``radioinject`` fire from a compromised source
over reachability alone (the moves nmap cannot see); ``conceded`` templates fire on a
conceded target (the P-tilde concession that keeps a privilege live without an exploit).
Privileges enter as ``compromised`` seeds (P-tilde) and via ``hostPriv``.

The program is assembled as text (facts prefixed ``+``, then the fixed interaction rules)
and ``pyDatalog.load``-ed after ``pyDatalog.clear`` -- construction is single-threaded, so
clearing the single global knowledge base each call keeps runs isolated, and querying with
``pyDatalog.ask`` avoids leaking term names into this module's namespace.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, List, Optional, Sequence, Set
from pyDatalog import pyDatalog

if TYPE_CHECKING:
    from ccd.discovery.descriptor import Descriptor
    from ccd.discovery.attack.scanner import VulnFact

_NO_SERVICE = "-"          # placeholder service for scan-free (credreuse/radioinject) moves

# the fixed MulVAL interaction rules (independent of the testbed)
_RULES = """
fired(E) <= tmplNet(E,Pre,Dst,Svc) & compromised(Src) & hostPriv(Src,Pre) & reachable(Src,Dst) & vulExists(Dst,Svc)
fired(E) <= tmplOpen(E,Pre,Dst) & compromised(Src) & hostPriv(Src,Pre) & reachable(Src,Dst)
fired(E) <= tmplConceded(E,Pre,Dst) & compromised(Src) & hostPriv(Src,Pre) & reachable(Src,Dst) & conceded(Dst)
compromised(Dst) <= fired(E) & tmplNet(E,Pre,Dst,Svc)
compromised(Dst) <= fired(E) & tmplOpen(E,Pre,Dst)
compromised(Dst) <= fired(E) & tmplConceded(E,Pre,Dst)
"""

_TERMS = ("reachable, compromised, hostPriv, vulExists, conceded, "
          "tmplNet, tmplOpen, tmplConceded, fired, X")


@dataclass
class Derivation:
    """The fixpoint: which exploit templates fired and which hosts were compromised."""

    fired: Set[str] = field(default_factory=set)
    compromised: Set[str] = field(default_factory=set)


def _q(value: str) -> str:
    return "'" + value.replace("'", "") + "'"


def derive(desc: "Descriptor", vuln_facts: Sequence["VulnFact"]) -> Derivation:
    """Run the MulVAL derivation for ``desc`` grounded by ``vuln_facts``."""
    facts: List[str] = []
    priv_hosts = {}
    for host in desc.hosts:
        if host.privilege_node is not None:
            priv_hosts[host.id] = host.privilege_node
            facts.append(f"+hostPriv({_q(host.id)},{_q(host.privilege_node)})")
        if host.conceded:
            facts.append(f"+conceded({_q(host.id)})")
    for edge in desc.reachability:
        facts.append(f"+reachable({_q(edge.src_host)},{_q(edge.dst_host)})")
    for fact in vuln_facts:
        facts.append(f"+vulExists({_q(fact.host)},{_q(fact.service)})")

    # seed compromise: attacker start hosts + any host holding an attained privilege or conceded
    attained = set(desc.attained)
    seeds: Set[str] = set(desc.attacker_start_hosts)
    for host in desc.hosts:
        if host.privilege_node in attained or host.conceded:
            seeds.add(host.id)
    for host_id in seeds:
        facts.append(f"+compromised({_q(host_id)})")

    for tmpl in desc.exploit_templates:
        dst = tmpl.via_reach_edge[1] if tmpl.via_reach_edge else _target_host(desc, tmpl.post_privilege)
        if dst is None:
            continue
        if tmpl.exploit_class == "netexploit":
            svc = tmpl.requires_service or _NO_SERVICE
            facts.append(f"+tmplNet({_q(tmpl.id)},{_q(tmpl.pre_privilege)},{_q(dst)},{_q(svc)})")
        elif tmpl.exploit_class == "conceded":
            facts.append(f"+tmplConceded({_q(tmpl.id)},{_q(tmpl.pre_privilege)},{_q(dst)})")
        else:                                    # credreuse / radioinject
            facts.append(f"+tmplOpen({_q(tmpl.id)},{_q(tmpl.pre_privilege)},{_q(dst)})")

    pyDatalog.clear()
    pyDatalog.create_terms(_TERMS)
    pyDatalog.load("\n".join(facts) + "\n" + _RULES)
    return Derivation(fired=_ask("fired(X)"), compromised=_ask("compromised(X)"))


def _ask(query: str) -> Set[str]:
    answer = pyDatalog.ask(query)
    return set() if answer is None else {row[0] for row in answer.answers}


def _target_host(desc: "Descriptor", post_privilege: str) -> Optional[str]:
    """The host that holds ``post_privilege`` (fallback when a template has no reach edge)."""
    for host in desc.hosts:
        if host.privilege_node == post_privilege:
            return host.id
    return None
