# Formal Semantic Validation And Reachability Evidence

This directory is the falsification/evidence gate for issues #168, #828, and #989 and
requirement ASR-530. It records exactly what the pinned RAES parser, semantic
validator, compiler, participant contracts, finite-domain satisfiability
analyzer, typed exploit-path analyzer, and existing regression fixtures
demonstrate. It also preserves the stronger claims they do not demonstrate.

The bundle keeps seven literature validation calls separate: schema validity,
semantic consistency, graph reachability, constraint satisfiability,
exploit-path validity, determinism/stability, and counterfactual necessity.
Schema evidence is bounded to the structural cases. Semantic, participant,
workflow-reachability, and parse-to-compile determinism evidence is partial.
The immutable issue-168 v1 record keeps whole-scenario satisfiability,
exploit-path validity, and counterfactual necessity `untested` at its pinned
revision. The issue-828 v2 protocol retains every v1 case and adds distinct
production satisfiable, unsatisfiable, valid-path, and invalid-path controls.
The exact `raes-finite-domain-satisfiability-v1` and
`raes-exploit-path-analysis-v1` profiles are `demonstrated` at the v2
revision. Semantic consistency, workflow reachability, and parse-to-compile
stability remain `partial`; counterfactual necessity remains `untested`.

## Bundle

- [`bundle-manifest.json`](bundle-manifest.json) is a stable index over
  immutable atomic releases in `bundles/`. Every release binds its exact
  protocol, corpus, execution snapshot, analysis, and selected evidence
  artifacts by repository path and SHA-256. The checker validates every
  indexed historical release; it does not independently combine the newest
  parts.
- [`protocol-v1.json`](protocol-v1.json) freezes the claim boundaries,
  entrypoints, allowed evidence, objective pass/fail rules, and participant
  obligations for the issue-168 baseline.
- [`corpus/manifest-v1.json`](corpus/manifest-v1.json) carries positive and
  single-defect negative cases for every claim class. Unsupported classes have
  explicit cases with no invented research-only model or fixture semantics.
- [`protocol-v2.json`](protocol-v2.json) and
  [`corpus/manifest-v2.json`](corpus/manifest-v2.json) preserve those cases and
  add the four governed production controls without reinterpreting the
  historical unsupported requests.
- [`execution-snapshot-v2.json`](execution-snapshot-v2.json) pins the RAES
  revision, Python/RAES/Z3 versions, fixed offline commands, all retained
  observations, complete production evidence joins, participant outcomes,
  digests, and limitations. It also pins the original issue-168 release as its
  comparison baseline and records an exact accepted disposition for each
  changed outcome, diagnostic, or result digest. This is now historical
  release 3.0.0, preserved byte-for-byte rather than compared to current code.
- [`analysis-v2.json`](analysis-v2.json) derives the ADR-021 status of each
  claim from the v2 observations and protocol ceilings.
- [`bundles/retest-v3.json`](bundles/retest-v3.json) preserves release 4.0.0.
  It reuses the preregistered v2 protocol and corpus, selects new v3 evidence
  envelopes, and binds [`execution-snapshot-v3.json`](execution-snapshot-v3.json)
  and [`analysis-v3.json`](analysis-v3.json) atomically. Nine exact deviations
  from release 3.0.0 are recorded. They include changed source/model/graph
  identities and a populated realization-designation record in the satisfiable
  witness; they are not asserted to be representation-only changes.
- [`bundles/retest-v4.json`](bundles/retest-v4.json) preserves release 5.0.0.
  It retains the v2 protocol, corpus, and production evidence while binding
  [`execution-snapshot-v4.json`](execution-snapshot-v4.json) and
  [`analysis-v4.json`](analysis-v4.json). The scoped-observation carrier changes
  alter the two compile-control digests; both deviations are recorded against
  release 4.0.0 without broadening the preregistered claims.
- [`bundles/retest-v5.json`](bundles/retest-v5.json) preserves release 6.0.0.
  It binds [`execution-snapshot-v5.json`](execution-snapshot-v5.json) and
  [`analysis-v5.json`](analysis-v5.json) to the final scoped-observation source
  state. The behavior-preserving remediation replays without result drift from
  release 5.0.0.
- [`bundles/retest-v6.json`](bundles/retest-v6.json) preserves release 7.0.0.
  It binds [`execution-snapshot-v6.json`](execution-snapshot-v6.json) and
  [`analysis-v6.json`](analysis-v6.json) to the tooling-policy configuration
  change. Every retained observation replays without result drift from release
  6.0.0.
- [`bundles/retest-v7.json`](bundles/retest-v7.json) preserves release 8.0.0.
  It binds [`execution-snapshot-v7.json`](execution-snapshot-v7.json) and
  [`analysis-v7.json`](analysis-v7.json) to the issue-1204 recursive realization
  source state after integration with the unified control-plane mutation
  lifecycle. Two compiler result digests change from the pinned release
  7.0.0 baseline; the replayed stability and distinguishability outcomes do not.
  The original protocol and unsupported claims remain unchanged.
- [`bundles/retest-v8.json`](bundles/retest-v8.json) preserves release 9.0.0.
  It binds [`execution-snapshot-v8.json`](execution-snapshot-v8.json) and
  [`analysis-v8.json`](analysis-v8.json) to the integrated Python dependency
  closures. Retained observations replay without drift from release 8.0.0.
  Previously pinned baseline captures retain their exact bytes; the new source
  identity is recorded here rather than repinning historical evidence.
- [`bundles/retest-v9.json`](bundles/retest-v9.json) preserves release 10.0.0.
  It binds [`execution-snapshot-v9.json`](execution-snapshot-v9.json) and
  [`analysis-v9.json`](analysis-v9.json) to the partial description contracts.
  Every retained observation replays without drift from release 9.0.0; prior
  captures and claim ceilings remain intact.
  Integration with the concurrent software work corrected this capture's stale
  baseline-release hash to the release 9.0.0 bytes already present on `dev`.
  Only that linkage and its enclosing digest changed; observations, timestamps,
  source-state provenance and claim ceilings were preserved.
- [`bundles/retest-v10.json`](bundles/retest-v10.json) preserves release 11.0.0.
  It binds [`execution-snapshot-v10.json`](execution-snapshot-v10.json) and
  [`analysis-v10.json`](analysis-v10.json) to generic software refinements.
  Exactly two compiler result digests change from release 10.0.0; their
  stability and distinguishability outcomes remain unchanged. Prior captures,
  the retained protocol and claim ceilings remain intact. This capture adds
  no native backend or downstream qualification claim.
- [`bundles/retest-v11.json`](bundles/retest-v11.json) preserves release 12.0.0.
  It binds [`execution-snapshot-v11.json`](execution-snapshot-v11.json) and
  [`analysis-v11.json`](analysis-v11.json) to partial inventory descriptions
  integrated with the software refinements. Retained outcomes and digests do
  not drift from release 11.0.0; no additional claim class is inferred.
- [`bundles/retest-v12.json`](bundles/retest-v12.json) preserves release 13.0.0.
  It binds [`execution-snapshot-v12.json`](execution-snapshot-v12.json) and
  [`analysis-v12.json`](analysis-v12.json) to the inventory lookup and validator
  maintainability refactor. Fresh replay retains the release-12 outcomes and
  result digests, with no new claim class or historical capture rewrite.
- [`bundles/retest-v13.json`](bundles/retest-v13.json) preserves release 14.0.0.
  It binds [`execution-snapshot-v13.json`](execution-snapshot-v13.json) and
  [`analysis-v13.json`](analysis-v13.json) to the typed selection implementation.
  Production commands and participant fixtures replay without observation
  drift from release 13.0.0; the preregistered claim limits remain unchanged.
- [`bundles/retest-v14.json`](bundles/retest-v14.json) preserves release 15.0.0.
  It binds [`execution-snapshot-v14.json`](execution-snapshot-v14.json) and
  [`analysis-v14.json`](analysis-v14.json) to the selection-helper refactor.
  Fresh production replay retains the release-14 observations and claim limits.
- [`bundles/retest-v15.json`](bundles/retest-v15.json) preserves release 16.0.0.
  It binds [`execution-snapshot-v15.json`](execution-snapshot-v15.json) and
  [`analysis-v15.json`](analysis-v15.json) to progressive semantic revision
  support. Fresh replay records two complete compiler digest changes, with
  identical bounded outcomes and explicit deviations from release 15.0.0.
- [`bundles/retest-v16.json`](bundles/retest-v16.json) preserves release 17.0.0.
  It binds [`execution-snapshot-v16.json`](execution-snapshot-v16.json) and
  [`analysis-v16.json`](analysis-v16.json) to unconstrained realization-evidence
  source semantics. Fresh replay retains every bounded outcome and records the
  two changed compiler digests as explicit deviations from release 16.0.0.
- [`bundles/retest-v17.json`](bundles/retest-v17.json) is prior release 18.0.0.
  It binds [`execution-snapshot-v17.json`](execution-snapshot-v17.json) and
  [`analysis-v17.json`](analysis-v17.json) to EXP-732 provenance validation.
  Fresh production and participant replay retains the release-17 outcomes and
  result digests with no deviations. The dedicated provenance regression suite
  does not promote this retained corpus to universal provenance assurance.
- [`bundles/retest-v18.json`](bundles/retest-v18.json) preserves release 19.0.0.
  It binds [`execution-snapshot-v18.json`](execution-snapshot-v18.json) and
  [`analysis-v18.json`](analysis-v18.json) to the combined materialization-attestation
  and EXP-732 provenance implementation. Fresh replay records compiled-representation
  deviations from release 18.0.0 with unchanged outcomes. The retained corpus does
  not establish native backend attestation fidelity or new experimental observations.
- [`bundles/retest-v19.json`](bundles/retest-v19.json) preserves release 20.0.0.
  It binds [`execution-snapshot-v19.json`](execution-snapshot-v19.json) and
  [`analysis-v19.json`](analysis-v19.json) to capture-proof authority integrated
  with apparatus provenance and materialization attestations. Fresh replay
  retains release-19 outcomes and digests without expanding claim limits.
  Earlier issue-1237 captures remain byte-exact in feature commits
  `2b21b5c88fc60c4545a302f4071cf8b781f04fe3` (release 18) and
  `c75805c56330d402a52bd7a578785bb343bf3c30` (release 19), while the incoming
  published captures above retain their original bytes.
- [`bundles/retest-v20.json`](bundles/retest-v20.json) preserves release 21.0.0.
  It binds [`execution-snapshot-v20.json`](execution-snapshot-v20.json) and
  [`analysis-v20.json`](analysis-v20.json) to the capture-dimension helper
  refactor. Fresh replay retains release-20 outcomes and digests with no new
  claim class; all previously published captures remain unchanged.
- [`bundles/retest-v21.json`](bundles/retest-v21.json) is current release 22.0.0.
  It binds [`execution-snapshot-v21.json`](execution-snapshot-v21.json) and
  [`analysis-v21.json`](analysis-v21.json) to the integrated capture-proof,
  capture-dimension, and EXP-731 refinement implementation. Fresh replay
  retains release-21 outcomes and digests without expanding the formal claim
  set; every earlier release remains byte-exact.
- [`satisfiability-analysis-v1.json`](satisfiability-analysis-v1.json) is the
  preserved issue-826 historical supplement. It remains selected atomically in
  release 2.0 and is not independently combined with newer evidence.
- [`satisfiability-execution-snapshot-v1.json`](satisfiability-execution-snapshot-v1.json)
  records fixed-argv, network-disabled commands and source/model/configuration
  digest observations for that historical supplement.
- [`evidence/`](evidence/) stores the complete published satisfiability and
  exploit-path evidence envelopes for the four v2 production controls. The
  exploit analyzer input retains the admitted snapshot separately in the
  versioned corpus; the result envelope binds it by digest.

The participant matrix includes positive and negative fixtures for hidden
world versus participant-visible projection, fail-closed action applicability,
shared-state effects, ordering before causality, evidence-labeled attribution,
participant-local outcome separation, and realization-profile honesty. These
fixtures support selected semantic claims; they are not counterfactual proof
or universal backend-fidelity evidence.

## Reproduction

Run the offline integrity and replay gate with:

```bash
implementations/python/.venv/bin/python tools/check_formal_semantic_validation.py
```

The checker uses bounded duplicate-safe JSON loading, repository-containment
checks, closed shapes, stable IDs, complete joins, and SHA-256 pins. It
validates historical releases for immutable shape and digest integrity without
misstating them as current-code observations. It then joins every retained
case in the current retest to its pinned baseline observation, requires an
exact structured disposition for every drift, and replays the current schema,
semantic, workflow, participant, and compile cases. For every new capability
case it parses the stored envelope through the published contract model, calls
the production analysis and replay APIs, invokes the fixed production CLI, and
requires all results and source/configuration/evidence digests to agree.
Checked-in labels, CLI exit status alone, mocks, or test-local analyzers cannot
satisfy the gate. It performs no network access, backend deployment, shell
evaluation, credential lookup, or environment-selected artifact loading.

Failed observations are evidence. A later product correction or RAES revision
creates a new execution snapshot and analysis; it does not overwrite this
record.

Current validation requires explicit release 18.0.0, rejects unsupported future
or duplicate revisions, and never accepts an old/new output-digest pair as a
substitute for replay. Historical releases (including the issue-826 supplement)
undergo pin, shape, control, and internal-join checks without executing current
code. Only the current release supports a current-code claim.

The two JSON files in [`historical-artifacts/`](historical-artifacts/) preserve
original baseline bytes recovered from Git revision
`106b195e3dc0048a647e845876e8eaefe08e3d1b`. They remain immutable recovery
material; the current release-10 linkage is described above. Validation admits
an archived copy only through the independently pinned archive record and an
exact requested digest, without network access or historical capture rewriting.

The current capture's `source_state` records a base Git commit, the modified
checkout state, and a deterministic digest of all reference-package Python
sources plus `pyproject.toml` and `uv.lock`. Source profile
`python-reference-source/v2` binds the Release Please version literal in
`raes/_version.py` as a placeholder, so a release version bump does not change
the digest; `v1` captures remain valid only as historical records. The base
commit is not represented as the exact clean capture revision. Validation recomputes the implementation
digest. A changed implementation requires a new explicitly supported release,
not rewriting history or extending a digest allowlist. Classification migration
is not a claim class in the retained preregistration and is not promoted to
`demonstrated` by these controls.

Release 13.0.0, [`bundles/retest-v12.json`](bundles/retest-v12.json), records
issue #1207's partial-inventory implementation against the same 20 corpus cases
and freshly executed participant checks. Outcome and result digests retain
their previous values; source identity and the Python version record this
capture's actual modified checkout. No new claim class is inferred.

The pre-synchronization issue-1207 capture is retained in feature commit
`b7d124a41518a7e9465f056ca25e25689eb4edda`, not selected as current evidence.
Synchronization preserves the incoming release-9/10/11 bytes, including the
baseline-link repair described above, and records the combined source in a new
release. Neither branch's historical observation is relabeled as a merged-tree
observation.

## Bounded conclusions

Issue #1237's pre-synchronization capture remains in feature commit
`2d402e4ae922b59d399dbfc336cc2856d153c44a`. It is not selected as current
evidence. Synchronization preserves the incoming release-17 bytes and records
the combined source in release 18. Neither branch's earlier observation is
relabeled as evidence for the merged tree.

The satisfiable witness and subset-minimal unsatisfiable core establish results
only for the declared finite-domain theory, translation, source, and pinned Z3
configuration. The core is not a general proof certificate. The exploit-path
witness and structured invalid-path evidence establish results only for the
admitted snapshot, normalized graph, query, transition semantics, and bounded
search profile. They do not establish backend execution, real-world
exploitability, or real-world non-exploitability.

The production exploit-path JSON loader currently accepts duplicate keys. The
research loader rejects duplicate keys at the artifact boundary, but this
release does not claim that the production input boundary is stronger.

The historical fallback is restricted by the immutable
[`pins-v1.json`](historical-artifacts/pins-v1.json) record. The baseline gate pins
that complete record's checksum independently of the submitted capture. It joins
each indexed release path to the exact original manifest and snapshot bytes;
new self-chosen archive digests cannot replace those observations. Future archive
records must append a reviewed version and retain this record unchanged.

Release 16 uses corpus revision 3 (`corpus/manifest-v3.json`) and production
evidence v4 for the canonical-profile cutover. Its reconstructed exploit-path
controls use current authoring and instantiated snapshot profiles v2. All four
production outcomes are unchanged; their new digests are recorded as explicit
deviations alongside the two compilation digests. Historical releases retain
their original byte and observation joins without current snapshot admission.

Release 17 retains corpus revision 3 and the four production evidence v4
records. It freezes their progressive-profile shapes for historical admission,
replays the same controls against current code, and records only the two
compiler representation digest changes caused by the realization-evidence
source correction. No outcome or preregistered claim strength changes.
