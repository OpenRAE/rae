# Contracts

`contracts/` holds the published machine-readable contracts.
The SDL specifications state their meaning.
The contracts do not depend on one implementation language.
Runners and code that check them belong under `implementations/`.

| Directory | Contents |
| --- | --- |
| `schemas/` | Published contract schemas |
| `fixtures/` | Valid and invalid payload examples |
| `profiles/` | Capability and validation profiles; scientific completeness taxonomies and assessments |
| `concept-authority/` | Concept, vocabulary, reference-model and behavioral-relation catalogs |
| `realization-envelopes/` | Backend configuration bounds whose identity passes through manifests, plans and snapshots |
| `provenance/` | Revision-pinned SDL lineage, derivations and third-party notice records |

## Publication and coverage

`schema-publication-manifest.json` is the stable publication index.
Each contract has its own record under `schema-publication/entries/`.
Changes to separate contracts do not rewrite a shared array.
The contracts gate assembles the records in a fixed order.
It checks that each schema exists and each JSON Schema file is listed.
Each record must point into `contracts/schemas/`.
It must give the schema's stability class and canonical content hash.

Publication proves that a contract exists.
It does not prove that a runner exercises it.
Each published schema needs at least one coverage source:

- A checked-in artifact that the corpus router checks against the schema.
- A delivered assurance artifact that names the schema in `specs/formal/assurance-fulfillment.yaml`.
- A checked `coverage` association on the publication record.

A formal model is not required.
A `waived_artifacts` entry records an open obligation; it is not coverage evidence.
`tools/check_schema_coverage.py` checks the whole publication list.
Its `--report` flag prints the source of coverage for each contract.
The [coverage guide](../docs/explain/reference/published-schema-coverage.md)
states the rule, repair order and record shape.

## Schema authority

The published schemas are the **hand-governed normative authority** under
[ADR-009 §7](../docs/decisions/adrs/adr-009-normative-artifact-authority-and-repository-structure.md).
A contract change starts with an edit to its published schema.
Review that edit against the SDL prose specification.
Do not change a contract as a side effect of code generation.

The Python `schema_bundle()` and `tools/generate_contract_schemas.py` produce reference output.
`tools/check_generated_schemas.py` generates that output in a temporary directory.
It proves that Python still matches the published schemas.
It never overwrites them.

A schema edit must update its contract record's `last_change` ledger.
The ledger gives a summary and content hash.
A removal needs a separate tombstone under `schema-publication/tombstones/`.
That record gives the removed schema path and a summary.
`tools/check_schema_publication.py --base-rev` and the `schema-change-missing-manifest` rule enforce these records.
A schema cannot change without contract-level review.

The Go implementation generates transport bindings from the published schemas.
Its check compares the complete bindings and packaged corpus with fresh output.
The [Go guide](../implementations/go/README.md) explains schema checks and semantic checks as separate claims.

Current schemas are marked `draft`.
A `v1` or `v2` suffix identifies a lineage; it does not promise stable compatibility.
[ADR-061](../docs/decisions/adrs/adr-061-published-schema-evolution-policy.md)
governs stable evolution.
Additive changes can keep the suffix.
Breaking changes need a new suffix.

## Contract families

The [SDL semantic vectors](fixtures/sdl/semantic-vectors-v1/README.md) publish reviewed source inputs and expected semantic results.
Their native Go tests check the inventory and semantic comparisons without a Python recorder.
The [maintenance guide](../docs/develop/sdl-semantic-fixtures.md) gives direct JSON updates and packaging checks.

Contracts cover processor and backend manifests, participant declarations, live control-plane records, experiments, evidence and provenance.
Some surfaces do not yet have a published schema.
The same language-neutral rules apply to each surface.

The [control-context asset contracts](../specs/supply-chain/participant-control-context-assets.md)
keep instruction and policy versions immutable.
They separate authorized lifecycle changes and selection evidence from disclosure and delivery.
Private contents stay outside portable records.

The optional [execution and recovery profile](../specs/sdl/execution-recovery.md)
carries complete authored policies and evidence definitions in native phase plans.
The [migration guide](../docs/explain/reference/execution-recovery-migration.md)
explains scoped defaults, content commitments and explicit capability refusals.

The [backend operation family](../specs/formal/runtime-contracts/backend-operation-supervision.md)
carries bounded requests, capability and willingness checks, progress, cancellation results and effect evidence.
The [backend guide](../docs/explain/reference/backend-operation-supervision.md)
explains the optional `operation-supervision` profile and its evidence limits.

The draft [inject contracts](../docs/explain/reference/inject-occurrence-contracts.md)
carry an external request, its claimed occurrence, readback per binding and participant correlation.
[ADR-112](../docs/decisions/adrs/adr-112-external-inject-triggering-and-execution.md) governs them.
These records grant no trigger authority and execute nothing.

The [authoring-adapter contracts](../specs/conformance/authoring-adapters.md)
carry bounded observations and comparisons.
Their vectors under `fixtures/authoring-adapters-v1/` compare artifacts, diagnostics, transformation provenance and owner semantic results separately.
The [consumer guide](../docs/explain/reference/authoring-adapter-conformance.md) explains their use.

The `participant-context-view-v1` contract states SEM-214's meaning and comparability bounds.
It binds participant and audience scope, observation point, source layers and transformation rule.
It also states the evidence basis, semantic limits and comparability disclosure.

The `participant-information-state-record-v1` contract closes ACT-604's portable reference.
It names one exact participant, episode, state cut, projection, memory scope and information guarantee.
Strong claims use the immutable reconstruction-profile corpus.
Each visible occurrence remains a typed source relation.
A trusted resolver must supply occurrence history, typed sources, proof digest, exact-cut membership and projection/policy coordinates.
Conformance checks, snapshot reload and backend ingestion fail closed without them.
The record is not a mutable fact map or hidden-world snapshot.
ACT-615 still owns concrete holdings kinds and their lifecycle.

The `runtime-fact-binding-plane-v1` contract carries typed run-local facts and immutable versions.
It includes compiled action sinks, value-free provenance and redacted participant/workflow views.
Facts can fill only declared action `input.*` fields.
They cannot rewrite SDL variables, topology, workflows, experiment factors, identities or random streams.
Trusted per-action admission supplies sinks, candidates, time and authority.
A one-shot dispatcher delivers values.
Caller requests cannot inject policy or receive protected values.

The experiment-core family carries tasks, runs, apparatus context, studies, collections, capture specs, raw evidence and derived measures.
These are archival design records.
They do not add execution, capture, storage, scheduling, statistical engines or API behavior.
Study and benchmark claims bind to `raes-behavioral-relations@rev1`.
They state population or case scope, measurement projection, evidence bounds, limits and explicit nonclaims.

`experiment-run-v1` is the canonical run provenance record.
It links task, run and apparatus context with results, evidence and traceability records.
It also carries realized-form disclosures for concerns resolved during a run.
Identifier-bearing collections that need uniqueness use maps keyed by that identifier.
The published schema can thus enforce uniqueness across languages.

The `scenario-satisfiability-evidence-v1` contract binds exact SDL bytes, canonical semantics, a normalized model and pinned solver settings.
It carries one satisfiable witness, unsatisfiable core or unsupported disclosure.
Its claim stays within ADR-086's finite-domain profile.
It does not prove backend realization or runtime success.

## Authority boundary

[ADR-009](../docs/decisions/adrs/adr-009-normative-artifact-authority-and-repository-structure.md)
governs this directory split.
The machine-readable ASR-517 authority manifest is
[`specs/authority/authority-boundary.yaml`](../specs/authority/authority-boundary.yaml).
[ADR-019](../docs/decisions/adrs/adr-019-normative-authority-boundary-manifest.md)
governs it; `tools/check_authority_boundary.py` checks it.
ADR-019 and ADR-080 also govern the provenance records.
