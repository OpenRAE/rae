# Contracts

Find published schemas, fixture corpora, profiles, and catalogs here.
These artifacts define portable contracts under the
[authority boundary](../specs/authority/authority-boundary.yaml).
Start with the [schema reference](schemas/README.md) for exact structures.
Use [local contract checks](../docs/develop/check-specification-contracts.md)
to compare the reference implementation with these artifacts.

The [participant control-context asset contracts](../specs/supply-chain/participant-control-context-assets.md)
define immutable instruction and policy versions, authorized lifecycle changes,
and selection evidence separate from disclosure and delivery. Private contents
stay outside these portable records.

The optional [execution and recovery requirements](../specs/sdl/execution-recovery.md)
profile carries complete authored policies and evidence definitions in native
phase plans. [Migration guidance](../docs/explain/reference/execution-recovery-migration.md)
explains scoped defaults, content commitments and explicit capability refusals.

The optional [backend operation and supervision family](../specs/formal/runtime-contracts/backend-operation-supervision.md)
publishes bounded requests, capability/willingness checks, correlated progress,
cancellation dispositions and effect evidence. The
[backend integration and migration guide](../docs/explain/reference/backend-operation-supervision.md)
explains the `operation-supervision` profile and its evidence limits.

The draft [inject trigger and occurrence contracts](../docs/explain/reference/inject-occurrence-contracts.md)
carry an external inject request, its claimed occurrence, per-binding readback
and participant correlation under
[ADR-112](../docs/decisions/adrs/adr-112-external-inject-triggering-and-execution.md).
They grant no trigger authority and execute nothing.

## Artifact families

- `schemas/` contains published contract schemas
- `fixtures/` contains valid and invalid payload corpora for those contracts.
  A `valid/` or `context-invalid/` fixture leaves out derived fields, such as a
  self-digest (`plan_digest`, `entry_digest`) or a derived identifier
  (`selection_id`). Readers fill them with
  `raes_contracts.contract_seals.seal_contract_fixture`, which computes each
  value the way the owning contract verifies it. An `invalid/` fixture stays as
  written, so it can test an absent or wrong derived value.
- `profiles/` contains capability profiles, the governed validation-profile
  catalog, and separately versioned scientific-completeness
  taxonomy/assessment declarations
- `concept-authority/` contains canonical concept, vocabulary, reference-model,
  and behavioral-relation catalogs
- `realization-envelopes/` contains configuration-bound backend realization
  declarations whose identity is carried through manifests, plans, and snapshots

`schema-publication-manifest.json` is the stable index for the authoritative
publication inventory. Each contract has an independent record under
`schema-publication/entries/`, so concurrent changes to unrelated contracts do
not rewrite one shared array. The contracts verification gate assembles those
records deterministically and checks that every entry points at
`contracts/schemas/`, every listed schema exists, every JSON Schema file is
listed, and every entry records its stability class.
Records contain `contract_id`, `schema_path`, and `stability`.
They contain no `content_hash` or `last_change`.
Git records schema history under the issue 1929 amendments to ADR-009 and ADR-061.

## Published-schema coverage

Publication establishes that a contract exists.
It does not establish that a check exercises it.
Every publication-catalog entry must have at least one of these evidence sources:

- A checked-in artifact that the corpus router validates against the schema.
- A delivered assurance artifact naming the schema in `specs/formal/assurance-fulfillment.yaml`.
- A validated `coverage` association on the publication record.

A formal model is never required.
A `waived_artifacts` entry is an unresolved obligation, not evidence. `tools/check_schema_coverage.py` enforces this over the whole
published inventory as the `policy / published schema coverage` stage, and
`--report` prints the covering leg per contract. The rule, the repair order, and
the `coverage` shape are documented in
[published-schema-coverage.md](../docs/explain/reference/published-schema-coverage.md).

## Schema authority direction (ADR-009 §7)

The published schemas under `contracts/schemas/` are the **hand-governed
normative authority**. Contract changes start with a reviewed published-schema edit.
The review compares the change with the SDL prose specification.
The reference implementation consumes that authority.
Its `raes_schemas.schema_bundle()` interface produces a comparison bundle.
`tools/check_generated_schemas.py` generates that bundle into a temporary directory.
It checks exact equality with the published schemas and never overwrites them.
A new schema adds one record
under `schema-publication/entries/`. A schema change does not edit its record:
git holds the schema history, and the pull request review covers the change. A
schema **removal** adds an independent tombstone record (schema path + summary)
under `schema-publication/tombstones/`. `tools/check_schema_publication.py
--base-rev` refuses an incompatible change to a `stable` schema and a removal
without a tombstone. This is the authority direction specified by ADR-009 §7.
Optional generation of implementation bindings *from* the schemas is not implemented.

Current checked-in schemas are marked `draft` in the manifest. A `v1` or `v2`
filename suffix identifies the schema lineage; it does not by itself promise a
stable compatibility surface. Stable schema evolution is governed by
[ADR-061](../docs/decisions/adrs/adr-061-published-schema-evolution-policy.md):
additive changes may stay under the same suffix, while breaking changes require
a new version suffix.

These assets are intentionally language-neutral. Any conformance runners or
implementation-specific validation helpers belong under `implementations/`,
not here.

The `authoring-adapter-*` contracts compose bounded authoring-path observations
and comparisons. Their fixed vectors under `fixtures/authoring-adapters-v1/`
compare canonical artifacts, diagnostics, transformation provenance and owner
semantic results independently. See the
[authoring-adapter contract](../specs/conformance/authoring-adapters.md) and
[consumer guide](../docs/explain/reference/authoring-adapter-conformance.md).

The contract space includes backend I/O and other artifact boundaries.
It includes:

- processor-facing contracts and manifests
- backend-facing contracts and manifests
- participant-implementation declaration surfaces
- live runtime/control-plane contracts
- experiment, evidence, and provenance artifact boundaries

The control-plane `participant-context-view-v1` contract carries SEM-214 meaning and comparability for derived operational context views.
Its envelope gives participant-local scope, audience scope, observation point, and governed source layers.
It also gives the transformation rule, evidence/provenance basis, semantic limitations, and explicit comparability disclosure.

The participant-runtime `participant-information-state-record-v1` contract
closes ACT-604's portable information-state reference at one exact participant,
episode, state cut, projection, memory scope, and information guarantee. Strong
claims resolve through the immutable
`participant-information-reconstruction-profile-v1` corpus and preserve every
visible occurrence as a typed source relation. Conformance, snapshot reload,
and backend ingestion fail closed unless a trusted resolver supplies the
occurrence history, typed sources, proof digest, exact-cut membership, and
projection/policy coordinates needed by the contextual invariant. The record
is not a mutable fact map, hidden-world snapshot, or operational-holdings
taxonomy; ACT-615 remains the owner of concrete holdings kinds and lifecycle.

The participant-runtime `runtime-fact-binding-plane-v1` contract defines typed
run-local fact declarations, immutable versions, compiled late-bound action
sinks, value-free binding provenance, and redacted participant/workflow
projections. It permits facts to fill only declared action `input.*` fields;
it does not permit runtime values to rewrite SDL variables, topology, workflow
structure, experiment factors, identities, or random streams.
The reference runtime obtains sinks, candidates, time, and authority from a
trusted per-action admission and delivers values through a one-shot dispatcher;
caller requests cannot inject policy or receive protected values.

The published experiment-core contract family includes task, run,
apparatus-context, study/collection, capture specification, raw evidence record,
and derived measure schemas under `contracts/schemas/experiment-core/`. These
contracts are archival design artifacts for scientific experiment records; they
do not add runtime execution, capture, storage, scheduling, statistical engines,
or API behavior by themselves. Claim-bearing study and benchmark records bind
their conclusions to `raes-behavioral-relations@rev1`, including population or
case scope, measurement projection, evidence boundary, limitations, and
explicit nonclaims.

The published `scenario-satisfiability-evidence-v1` contract binds exact SDL
source bytes, canonical authored semantics, a solver-neutral normalized model,
the pinned solver configuration, and exactly one satisfiable witness,
unsatisfiable core, or unsupported disclosure. Its claim is limited to the
ADR-086 finite-domain profile; it is not backend-realization or runtime-success
evidence.

`experiment-run-v1` is the canonical run provenance record. It carries the
task/run/apparatus context, result and evidence pointers, traceability links to
capture specs, evidence records, derived measures, and claims, plus
realized-form disclosures for underspecified concerns resolved during a run.

Within experiment-core contracts, identifier-bearing collections that require
uniqueness are object maps keyed by that identifier. This keeps uniqueness
portable in the published JSON Schemas rather than implementation-private.

Not every one of those surfaces is fully materialized in published schemas yet,
but they share the same language-neutral contract discipline.

This split follows the repository-structure decision captured in
[ADR-009](../docs/decisions/adrs/adr-009-normative-artifact-authority-and-repository-structure.md).

The canonical machine-readable manifest of the authority boundary
(ASR-517) lives at
[`specs/authority/authority-boundary.yaml`](../specs/authority/authority-boundary.yaml),
governed by
[ADR-019](../docs/decisions/adrs/adr-019-normative-authority-boundary-manifest.md)
and enforced by `tools/check_authority_boundary.py`.
The `provenance/` family contains revision-pinned SDL lineage, derivation, and
third-party notice dispositions governed by ADR-019 and ADR-080.
