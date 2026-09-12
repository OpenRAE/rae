# Standardized Specification Coverage

This directory is the falsification/evidence bundle for issues #164 and #989 and
requirement ASR-530. It tests a bounded claim: whether RAES can represent a
preregistered set of cyber-agent evaluation environment requirements through
portable SDL, experiment, and apparatus surfaces without requiring backend
deployment vocabulary in core SDL.

The result is **partial**, not demonstrated. All ten issue-defined
load-bearing concepts passed their owning production boundaries, but three
supplemental concepts have no tested carrier in this preregistered matrix: participant tool and
affordance declarations, solver-backed constraint satisfiability, and
federated cyber object/event exchange. Those gaps are preserved as evidence;
this run does not repair them.

## Immutable bundles

- [`bundle-manifest.json`](bundle-manifest.json) is a stable index over
  immutable capture manifests in `bundles/`. The checker validates every
  capture and selects the highest revision deterministically; publishing a new
  capture never rewrites another branch's manifest.
- [`protocol-v1.json`](protocol-v1.json) preregisters four source strata, four
  representative requests, sixteen atomic concepts, expected carriers and
  classifications, stage obligations, load-bearing status, classification
  rules, and objective pass/fail criteria.
- [`execution-snapshot-v1.1.json`](execution-snapshot-v1.1.json) records historical commit
  `9347f64b26e3bb71d5459759c3d4bd473c76b446`, historical digests of the SDL,
  processor, and contract implementation surfaces, exact repository artifacts,
  production entrypoints, typed pointers, diagnostics, and observed outcomes.
- [`analysis-v1.1.json`](analysis-v1.1.json) is recomputed from the protocol and
  bound to the complete snapshot digest, and records the ADR-021 evidence
  status.

- [`execution-snapshot-v2.json`](execution-snapshot-v2.json) and
  [`analysis-v2.json`](analysis-v2.json) preserve release 2.0.0.
- [`execution-snapshot-v3.json`](execution-snapshot-v3.json) and
  [`analysis-v3.json`](analysis-v3.json) preserve release 3.0.0.
- [`execution-snapshot-v4.json`](execution-snapshot-v4.json) and
  [`analysis-v4.json`](analysis-v4.json) preserve release 4.0.0.
- [`execution-snapshot-v5.json`](execution-snapshot-v5.json) and
  [`analysis-v5.json`](analysis-v5.json) preserve release 5.0.0. They
  bind the tooling-policy configuration change to exact source-state
  provenance; the protocol, artifact pins, package surfaces, outcomes, and
  missing-concept denominator remain unchanged.
- [`execution-snapshot-v6.json`](execution-snapshot-v6.json) and
  [`analysis-v6.json`](analysis-v6.json) preserve release 6.0.0, with
  exact current artifact pins, package digests, and source-state provenance
  after integration with the unified control-plane mutation lifecycle.
  The original protocol and missing-concept denominator remain unchanged.
- [`execution-snapshot-v7.json`](execution-snapshot-v7.json) and
  [`analysis-v7.json`](analysis-v7.json) are current release 7.0.0. They bind
  the integrated Python dependency closures to fresh source-state evidence,
  retaining the exact historical captures and original coverage denominator.

Historical captures are checked for closed shapes, frozen analysis joins, and
exact archived source bytes, without executing current code. The ten source
archives in `historical-artifacts/` are content-addressed JSON envelopes with
base64-encoded original bytes and the Git revision from which those bytes were
recovered. Recovery revisions are not substituted for the capture's declared
revision; a matching archive proves the frozen byte pin, not the historical
working-tree provenance. No network or Git history is required for validation.

Current validation requires release 7.0.0 and rejects duplicate or unsupported
future revisions. It executes current artifacts, requires exact source and
package hashes, and checks all passing stage pointers. `source_state` discloses
the base Git commit, modified checkout state, and exact implementation digest;
it does not claim the capture was made at a clean base commit. Implementation
changes require a new explicitly supported capture, never edits to an old
capture or old/new digest allowances.

The source strata are a cyber-range survey, the CybORG autonomous-agent
benchmark, the VSDL cyber-range DSL, and the SISO Cyber Data Exchange Model.
The protocol stores bounded paraphrases and precise citations; it does not copy
papers, standards, private literature, or compared-system source trees.

## Outcome

| Classification | Count | Interpretation |
| --- | ---: | --- |
| Directly expressible | 10 | Typed SDL or experiment fields preserve the concept at every applicable stage. |
| Profile or manifest constraint | 2 | Apparatus selection and clock context remain outside core SDL in validated contracts. |
| Deliberately backend specific | 1 | Provider provisioning mechanics remain a realization concern. |
| Missing | 3 | No carrier was tested in this preregistered matrix; prose and metadata do not substitute for evidence. |

The survey-derived request passes for topology, roles, objectives, workflows,
evidence expectations, and apparatus constraints. The other three requests
remain partial because each contains one missing concept. No unallowed backend
vocabulary occurrence was observed in a directly expressible concept.

This does not prove universal cyber-range coverage, language usability,
scientific adequacy, independent backend implementation, backend substitution,
live realization fidelity, or behavioral equivalence. The execution uses the
pinned reference processor and published contracts; no range, participant,
cloud, hypervisor, or federation was executed.

## Reproduction

Run the focused offline gate with:

```bash
implementations/python/.venv/bin/python tools/check_specification_coverage.py
```

The checker uses bounded duplicate-key-safe JSON loading and repository path
containment, verifies content digests and exact cross-record joins, executes
the pinned SDL artifacts through `parse_sdl_file()`, semantic validation,
`instantiate_scenario()`, `admit_instantiated_scenario()`, and
`compile_runtime_model()`, validates the named experiment/profile contracts,
resolves every passing typed pointer, and rejects stale or dishonest analysis.
It also rejects post-execution reclassification, any non-passing load-bearing
stage, implementation-surface drift, and analysis that is not bound to the
complete snapshot.
It performs no network access, shell evaluation, live backend access, dynamic
plugin loading, or environment-selected semantic binding. The same checker
runs once in the canonical nox contracts graph.

Protocol changes create a new protocol revision. Re-execution against a new
RAES implementation creates a new immutable snapshot and analysis. A later product
fix must not overwrite this result or remove a missing concept from the
denominator.

This retest does not preregister or demonstrate classification-migration
correctness, nor does it infer ecosystem-wide absence of capabilities from the
three untested carrier slots.
