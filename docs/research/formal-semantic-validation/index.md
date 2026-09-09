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
- [`bundles/retest-v3.json`](bundles/retest-v3.json) is current release 4.0.0.
  It reuses the preregistered v2 protocol and corpus, selects new v3 evidence
  envelopes, and binds [`execution-snapshot-v3.json`](execution-snapshot-v3.json)
  and [`analysis-v3.json`](analysis-v3.json) atomically. Nine exact deviations
  from release 3.0.0 are recorded. They include changed source/model/graph
  identities and a populated realization-designation record in the satisfiable
  witness; they are not asserted to be representation-only changes.
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

Current validation requires explicit release 4.0.0, rejects unsupported future
or duplicate revisions, and never accepts an old/new output-digest pair as a
substitute for replay. Historical releases (including the issue-826 supplement)
undergo pin, shape, control, and internal-join checks without executing current
code. Only the current release supports a current-code claim.

The current capture's `source_state` records a base Git commit, the modified
checkout state, and a deterministic digest of all reference-package Python
sources plus `pyproject.toml` and `uv.lock`. The base commit is not represented
as the exact clean capture revision. Validation recomputes the implementation
digest. A changed implementation requires a new explicitly supported release,
not rewriting history or extending a digest allowlist. Classification migration
is not a claim class in the retained preregistration and is not promoted to
`demonstrated` by these controls.

## Bounded conclusions

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
