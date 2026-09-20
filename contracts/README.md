# Contracts

`contracts/` contains the machine-readable contract side of the repository.

The goal of this bucket is organizational clarity:

- `schemas/` contains published contract schemas
- `fixtures/` contains valid and invalid payload corpora for those contracts
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
listed, and every entry records its stability class and canonical content hash.

## Published-schema coverage

Publication proves a contract exists; it does not prove anything exercises it.
Every entry in the publication catalog must carry at least one of: a checked-in
artifact that the corpus router validates against that schema, a delivered
assurance artifact naming the schema in
`specs/formal/assurance-fulfillment.yaml`, or a validated `coverage`
association on the contract's publication record. A formal model is never
required, and a `waived_artifacts` entry is an unresolved obligation rather than
evidence. `tools/check_schema_coverage.py` enforces this over the whole
published inventory as the `policy / published schema coverage` stage, and
`--report` prints the covering leg per contract. The rule, the repair order, and
the `coverage` shape are documented in
[published-schema-coverage.md](../docs/explain/reference/published-schema-coverage.md).

## Schema authority direction (ADR-009 §7)

The published schemas under `contracts/schemas/` are the **hand-governed
normative authority**. Changes to a contract originate as edits to the published
schema, reviewed against the SDL prose specification — not as a side-effect of
regenerating from a reference implementation. The Python `schema_bundle()` and
`tools/generate_contract_schemas.py` are the reference implementation's output;
`tools/check_generated_schemas.py` runs that generation into a throwaway
directory and **proves the reference implementation still matches the published
normative schemas** (it never overwrites them). A schema change must update its
contract record with a contract-facing `last_change` ledger (summary + content
hash); a schema **removal** must add an independent tombstone record (schema path
+ summary) under `schema-publication/tombstones/`.
`tools/check_schema_publication.py --base-rev` and the
`schema-change-missing-manifest` policy rule reject a `contracts/schemas/`
change — including a removal — that lands without one, so a schema cannot
change without contract-level review. This is the steady state ADR-009 §7 calls for;
optional code generation *from* the normative schemas into implementation
bindings remains future work.

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

At the architecture level, the contract space spans more than just backend I/O.
It includes:

- processor-facing contracts and manifests
- backend-facing contracts and manifests
- participant-implementation declaration surfaces
- live runtime/control-plane contracts
- experiment, evidence, and provenance artifact boundaries

The control-plane `participant-context-view-v1` contract includes the SEM-214
meaning and comparability envelope for derived operational context views:
participant-local scope, audience scope, observation point, governed source
layers, transformation rule, evidence/provenance basis, semantic limitations,
and explicit comparability disclosure.

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
