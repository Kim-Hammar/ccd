# `ccd.discovery` — automatic construction of the two-layer model ⟨Γ, G, L⟩

Constructs the two-layer model (attack graph Γ, causal graph G, cross-layer edges
L = C ∪ B) from a **testbed-agnostic descriptor** plus a nominal dataset and a
vulnerability scan, and diffs the result against the hand-authored `SystemModel`.
Implements `docs/two_layer_model_construction_plan.md`.

## Layout

The generic package consumes **only descriptors** — it never imports `ccd.system.*`
except in `evaluation/` (keeps construction non-circular):

- `descriptor.py` — the dataclasses + JSON load/validate/dump (leaf).
- `model.py` — `ConstructedModel`, mirroring `SystemModel`'s public attributes.
- `causal/` — `build_g` (PC + KCI over a symmetry-reduced representative slice), plus
  `structure_learning`, `orientation`, `validation` (wraps `validation_util.falsify`).
- `attack/` — `scanner` (`ScannerInterface`, `VulnFact`, `StaticScanner`),
  `nmap_scanner` (live `nmap -sV`), `datalog_rules` (MulVAL via pyDatalog), `build_gamma`.
- `cross_layer/build_l.py` — C from provenance × Γ, B from enactment × Γ.
- `pipeline.py` — `build_model`; `evaluation/{graph_diff,acceptance}.py`.

Each testbed exports a descriptor through a thin adapter over its pure library:
`testbeds/{it_system,ics,5g_ran}/scripts/descriptor.py`.

## Running

```bash
pip install -e '.[discovery]'          # causal-learn, pyDatalog, python-nmap
python -m pytest tests/test_discovery_*.py -q         # static scanner, no docker

# acceptance: diff the constructed model against the hand-built one (StaticScanner):
python -m ccd.discovery.evaluation.acceptance --testbed ics
python -m ccd.discovery.evaluation.acceptance --all         # every testbed in turn

# build and EXPORT the constructed model for downstream use:
python -m ccd.discovery.pipeline --testbed ics --out model.json
python -m ccd.discovery.pipeline --testbed ics --graphml-dir out/   # G + Gamma as GraphML
python -m ccd.discovery.pipeline --testbed 5g_ran --out m.json --permutations 5
```

`--out` writes one self-describing JSON document (both graphs, C, B, the role/privilege
sets, product functions, and any falsification summary); `--graphml-dir` writes G and Γ as
GraphML with a `kind` node attribute (enacted/product/measured, privilege/exploit) for
networkx / Gephi / yEd. In Python, `ccd.discovery.pipeline.build_model(desc, data)` returns
the `ConstructedModel` and `ccd.discovery.serialize` does the export.

## Acceptance status

| Testbed | Γ | C | B | G |
|---------|---|---|---|---|
| IT   | exact | exact | exact | exact (P=R=1.0) |
| ICS  | exact | exact | exact | recall 1.0, +1 borderline edge; not falsified |
| 5G   | exact | exact | exact | recall 0.92, precision 0.90; not falsified |

G is judged by **falsification**, not edge isomorphism (the plan's gate): gated products,
the demand confounder, and context-specific independencies make an exact match neither
expected nor the bar (5G especially). The interface→T edges `A1`/`E2` are absent from G
because they genuinely do not drive throughput in the data.

## Live nmap scan (`--live`)

Γ carries no signal in the nominal data, so its **topology** comes from the descriptor
(reachability + exploit templates + attained privileges P̃); a scan only grounds a
per-host *exploitability existence* predicate (`vulHost`) that a `netexploit` template
needs to fire. `credreuse` / `radioinject` / `conceded` moves need no scan.

`--live` swaps `StaticScanner`'s canned facts for a real `nmap -sV` over the running
containers:

```bash
sudo apt-get install -y nmap                 # the system binary (external prereq)
cd testbeds/ics/scripts && python testbed.py up
python -m ccd.discovery.evaluation.acceptance --testbed ics --live
```

**Honest behavior (as the plan documents).** A live scan reflects *actual* container
exploitability, which can differ from the curated Γ. On the ICS testbed the SCADA host
runs no service (the attacker software is not implemented — it is a passive stub), so its
`netexploit` (`E2`) is **not** scan-confirmed and Γ comes back with `E1/E3/E4` only. That
is the tool faithfully reporting what the scan can and cannot ground, not a defect. Use
`StaticScanner` (the default) to reproduce the full curated Γ for acceptance.
