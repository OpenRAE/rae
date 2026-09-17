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
  [`analysis-v7.json`](analysis-v7.json) preserve release 7.0.0. They bind
  the integrated Python dependency closures to fresh source-state evidence,
  retaining the exact historical captures and original coverage denominator.
- [`execution-snapshot-v8.json`](execution-snapshot-v8.json) and
  [`analysis-v8.json`](analysis-v8.json) preserve release 8.0.0. They bind
  partial description contracts to freshly replayed evidence with the same
  preregistered classifications and missing-concept denominator.
- [`execution-snapshot-v9.json`](execution-snapshot-v9.json) and
  [`analysis-v9.json`](analysis-v9.json) preserve release 9.0.0. They bind
  generic software refinements to fresh source and package hashes. The retained
  protocol replays without changing its classifications or claims; this is not
  native backend or downstream qualification.
- [`execution-snapshot-v10.json`](execution-snapshot-v10.json) and
  [`analysis-v10.json`](analysis-v10.json) preserve release 10.0.0. They bind
  partial inventory descriptions integrated with software refinements to fresh
  source and package hashes, without changing the protocol's claim limits.
- [`execution-snapshot-v11.json`](execution-snapshot-v11.json) and
  [`analysis-v11.json`](analysis-v11.json) preserve release 11.0.0. Fresh
  replay of the inventory lookup and validator maintainability refactor retains
  the same classifications and claim limits while preserving prior captures.

- [`execution-snapshot-v12.json`](execution-snapshot-v12.json) and
  [`analysis-v12.json`](analysis-v12.json) preserve release 12.0.0. They bind
  the typed selection implementation to fresh source and package digests.
  The retained artifacts execute through their production boundaries; the
  recomputed analysis retains the original classifications and denominator.

- [`execution-snapshot-v13.json`](execution-snapshot-v13.json) and
  [`analysis-v13.json`](analysis-v13.json) preserve release 13.0.0. Fresh
  replay binds the selection-helper refactor to exact source and package
  digests, retaining the classifications, denominator, and claim limits.

- [`execution-snapshot-v14.json`](execution-snapshot-v14.json) and
  [`analysis-v14.json`](analysis-v14.json) preserve release 14.0.0. The
  progressive revision implementation is bound to fresh source and package
  digests. Artifact re-execution and the derived analysis retain the bounded
  classifications and denominator.

- [`execution-snapshot-v15.json`](execution-snapshot-v15.json) and
  [`analysis-v15.json`](analysis-v15.json) preserve release 15.0.0. They
  bind the unconstrained realization-evidence source semantics to fresh source
  and package digests while retaining the protocol's bounded classifications,
  denominator, and claim limits.

- [`execution-snapshot-v16.json`](execution-snapshot-v16.json) and
  [`analysis-v16.json`](analysis-v16.json) are prior release 16.0.0. They
  bind EXP-732 run, apparatus, measurement-channel, and augmentation-producer
  provenance validation to fresh source and package digests. Protocol replay
  retains the bounded classifications, denominator, and claim limits; the
  dedicated provenance regression suite does not broaden this corpus's claims.

- [`execution-snapshot-v17.json`](execution-snapshot-v17.json) and
  [`analysis-v17.json`](analysis-v17.json) preserve release 17.0.0. Fresh
  replay binds the combined materialization-attestation and EXP-732 provenance
  implementation to exact source and package digests. Classifications, the
  denominator and claim limits are unchanged; dedicated regression tests cover
  the operational-provenance boundary separately.

- [`execution-snapshot-v18.json`](execution-snapshot-v18.json) and
  [`analysis-v18.json`](analysis-v18.json) preserve release 18.0.0. Fresh
  replay binds capture-proof authority integrated with apparatus provenance
  and materialization attestations to exact source and package digests.
  Classifications, the denominator, and claim limits remain unchanged.

- [`execution-snapshot-v19.json`](execution-snapshot-v19.json) and
  [`analysis-v19.json`](analysis-v19.json) preserve release 19.0.0. Fresh
  replay binds the capture-dimension helper refactor to exact source and
  package digests, preserving classifications, denominator, and claim limits.

- [`execution-snapshot-v20.json`](execution-snapshot-v20.json) and
  [`analysis-v20.json`](analysis-v20.json) preserve release 20.0.0. Fresh
  replay binds the issue #959 correction of stale mandatory-profile guidance
  in the limitations document. Runtime implementation, classifications,
  denominator and claim limits are unchanged; earlier captures retain their
  exact bytes.

- [`execution-snapshot-v21.json`](execution-snapshot-v21.json) and
  [`analysis-v21.json`](analysis-v21.json) preserve release 21.0.0. They
  bind the integrated capture-proof authority, capture-dimension helpers, and
  EXP-731 evidence-requirement refinement to exact source and package digests
  while retaining the protocol's bounded classifications and claim limits.

- [`execution-snapshot-v22.json`](execution-snapshot-v22.json) and
  [`analysis-v22.json`](analysis-v22.json) preserve release 22.0.0. Fresh
  replay binds open-by-default augmentation scope integrated with EXP-731
  evidence refinements to exact source and package digests. Passing-stage
  pointers, classifications, denominator, and claim limits are retained. Native
  backend scope enforcement is not evaluated by this corpus.

- [`execution-snapshot-v23.json`](execution-snapshot-v23.json) and
  [`analysis-v23.json`](analysis-v23.json) preserve release 23.0.0. Fresh
  replay binds the augmentation-admission maintainability refactor to exact
  source and package digests. Classifications, passing-stage pointers, and
  claim limits remain unchanged; all earlier captures retain their exact bytes.

- [`execution-snapshot-v24.json`](execution-snapshot-v24.json) and
  [`analysis-v24.json`](analysis-v24.json) preserve release 24.0.0. Fresh
  replay binds the tightened composition type annotations to exact source and
  package digests. Outcomes, classifications, and claim limits are unchanged;
  all previously published captures remain byte-exact.

- [`execution-snapshot-v25.json`](execution-snapshot-v25.json) and
  [`analysis-v25.json`](analysis-v25.json) preserve release 25.0.0. Fresh
  replay binds ACT-612 participant relationships together with the integrated
  augmentation scope work to exact source and package digests. Outcomes,
  classifications, and claim limits remain unchanged; published captures remain
  byte-exact.

- [`execution-snapshot-v26.json`](execution-snapshot-v26.json) and
  [`analysis-v26.json`](analysis-v26.json) preserve release 26.0.0. Fresh
  replay binds authoring-adapter conformance on the merged participant-
  relationship and augmentation source tree to exact source and package
  digests. Classifications and claim limits remain unchanged; adapter transport
  behavior is not evaluated by this corpus.

- [`execution-snapshot-v27.json`](execution-snapshot-v27.json) and
  [`analysis-v27.json`](analysis-v27.json) are current release 27.0.0. Fresh
  replay binds the API-404 operational recovery-observation contract to exact
  source and package digests. Classifications and claim limits remain
  unchanged; crash recovery and EXP-715 experiment observation are not
  evaluated by this corpus.

Earlier issue-1242 captures remain byte-exact in feature commits
`77187a939a9872e5bd2fd93816f1fcd5ef6c5c08` (release 20) and
`1ab0580525136667bbc713d3c2f4a7820bab08da` (release 21). Their manifests
remain outside the active index at
`historical-artifacts/issue-1242-pre-sync-release-v20.json` and
`historical-artifacts/issue-1242-pre-refinement-sync-release-v21.json`.
Those paths and hashes describe files at the named commits, not the current
checkout. Incoming published captures retain their exact bytes.

Earlier issue-1237 captures remain in feature commits
`2d402e4ae922b59d399dbfc336cc2856d153c44a` (release 15),
`2b21b5c88fc60c4545a302f4071cf8b781f04fe3` (release 16), and
`c75805c56330d402a52bd7a578785bb343bf3c30` (release 17). Their manifests
remain outside the active index at
`historical-artifacts/issue-1237-pre-sync-release-v15.json`,
`historical-artifacts/issue-1237-pre-provenance-sync-release-v16.json`, and
`historical-artifacts/issue-1237-pre-materialization-sync-release-v17.json`.
Those paths and hashes describe files at the named commits, not the current
checkout. Incoming published captures retain their exact bytes.

Historical captures are checked for closed shapes, frozen analysis joins, and
exact archived source bytes, without executing current code. The eleven source
archives in `historical-artifacts/` are content-addressed JSON envelopes with
base64-encoded original bytes and the Git revision from which those bytes were
recovered. Recovery revisions are not substituted for the capture's declared
revision; a matching archive proves the frozen byte pin, not the historical
working-tree provenance. No network or Git history is required for validation.

Current validation requires release 27.0.0 and rejects duplicate or unsupported
future revisions. It executes current artifacts, requires exact source and
package hashes, and checks all passing stage pointers. `source_state` discloses
the base Git commit, modified checkout state, and exact implementation digest;
it does not claim the capture was made at a clean base commit. Implementation
changes require a new explicitly supported capture, never edits to an old
capture or old/new digest allowances.

Release 11.0.0 records issue #1207 in
[`execution-snapshot-v11.json`](execution-snapshot-v11.json) and
[`analysis-v11.json`](analysis-v11.json). All 16 retained concepts were checked
against current source and package digests. Classifications, the missing-concept
denominator and claim limits are unchanged; partial inventory acceptance is
not promoted into new claims outside the preregistered protocol.

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
