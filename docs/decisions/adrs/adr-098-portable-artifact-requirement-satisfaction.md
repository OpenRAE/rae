# ADR-098: Portable Artifact Requirement Satisfaction

## Status

accepted

## Date

2026-07-27

## Classification

Classification: FM2

Required artifacts: ADR, normative specification, published contracts and
fixtures, compiler/planner/runtime integration, and whole-tree verification.

Waivers: no provider registry, artifact graph, acquisition adapter, build
service, credential surface, or second realization planner is introduced.

## Context

`Source` has historically been a provider-neutral name/version selector.
Different backends may resolve that selector to a local image, imported
package, registry object, or dynamically prepared artifact, but the SDL has not
been able to distinguish an exact immutable requirement from bounded selection
or backend-owned realization. A name and version alone therefore cannot prove
that two backends realized the same artifact, and `Source.build` records
observed image provenance rather than authoring a future build obligation.

ADR-070 already defines exact, constrained, and open realization posture,
compiled realization demand, backend capability admission, and runtime
non-approximation disclosure. ADR-071 and ADR-077 already own reusable-asset
trust policy and associated-artifact manifests. Artifact satisfaction must join
those authorities without creating a parallel artifact ontology or treating
mutable provider locations as scenario identity.

## Decision

Add an optional, versioned `artifact_requirement` to the existing `Source`
concern. Absence preserves the historical selector semantics. Presence uses the
existing `ExplicitnessClass`:

- `exact` names exactly one digest-bound artifact identity. It permits no
  candidate, constraint, locked-input, or materialization alternative and only
  the `exact-artifact` mechanism. Failure to obtain that artifact is rejection,
  never fallback, rebuild, or substitution.
- `constrained` declares a non-empty bounded authority domain using typed
  constraints, immutable candidates, locked inputs, or digest-bound
  materialization specifications.
- `open` delegates output artifact selection to a backend that explicitly
  advertises open realization support. It cannot carry candidates, artifact
  constraints, or materialization alternatives, though immutable input and
  trust requirements remain valid.

An artifact identity consists of a provider-neutral id, version, SHA-256
digest, and media type. A `Source` selector is not integrity evidence; for an
exact requirement its name/version must match the immutable artifact identity.
`Source.build` remains observed provenance and cannot satisfy or expand an
authored materialization requirement.

Satisfaction mechanisms are versioned digest-bound profiles. The contract
governs a small portable base vocabulary and admits namespaced
`x-<authority>:<term>` extensions. Acquisition (`pull`, `copy`, `import`,
`local-lookup`, or `none`) and timing (`publication`, `pack-ingestion`,
`backend-preparation`, or `realization`) remain independent properties. Backend
manifests advertise mechanism-indexed acquisition/timing combinations under
the existing `realization_support` declaration so they cannot imply unsupported
Cartesian products.

The processor lowers a present requirement into the existing
`CompiledRealizationRequirement` graph at the owning node, content, feature
binding, condition binding, inject, or event address. The existing planner
performs capability admission, supplemented by caller-supplied operational
availability facts. Mutable registry, region, account, channel, and locator
facts are not semantic identity and are not persisted in the requirement.
Availability and verified trust facts are partitioned by canonical compiled
address so requirement-local candidate, constraint, and locked-input ids
cannot collide across resources.

At execution, the backend returns a typed artifact satisfaction disclosure on
the resource payload. The existing runtime non-approximation gate validates it
before snapshot persistence and attaches it to the existing
`RealizationProvenanceEntry`. Exact substitution or omission is
`runtime.backend-contract-invalid`. The disclosure records artifact,
mechanism, acquisition, timing, backend identity, integrity/authenticity,
admission, provenance, and evidence references, but no mutable location or
channel. Admission binds the backend identity and mechanism route to the
selected manifest, candidate ids to their authored immutable identities,
materialization selections to their locked inputs, and every trust/evidence
reference to the processor-owned verified context. A selected materialization
specification discloses its authored specification digest, which must also be
present in the address-scoped trusted availability context.

The published `artifact-requirement-v1` schema, SDL schemas,
`backend-manifest-v2`, and `runtime-snapshot-v1` are the portable surfaces.
Their reference models, generated schemas, conformance fixtures, and schema
publication ledgers change together. The contract-specific Source schema makes
`artifact_requirement` structurally mandatory. Cross-object equality and
reference joins that JSON Schema cannot express use the existing governed
`x-raes-invariants` profile and importable validator surface.

## Alternatives Considered

Treat every `Source` name/version as exact. Rejected: a selector is neither a
content identity nor proof of availability, and `*` is intentionally a
selector.

Add a top-level artifact graph or universal registry. Rejected: the concern is
owned by existing `Source` instances and existing compilation addresses; a
second graph would duplicate identity, planning, and lifecycle authority.

Use `Source.build` as a materialization request. Rejected: it is observed build
provenance. Reinterpreting it would silently turn evidence into executable
authority.

Publish separate booleans and lists for mechanisms, acquisition, and timing.
Rejected: their Cartesian product would overclaim backend support.

Persist provider locations in scenario or satisfaction identity. Rejected:
locations are mutable operational facts, may expose host/account information,
and do not identify artifact bytes.

## Consequences

Authors can state portable exact, bounded, or delegated artifact intent without
naming a cloud, hypervisor, registry, image service, or build farm. Backends
must disclose the exact mechanism combinations they implement and must return
evidence sufficient for the runtime gate to reject silent approximation.

Artifact availability remains an operational input. This decision does not
perform network acquisition, credential lookup, archive extraction, image
building, signature verification, or registry mutation. Those operations stay
with authorized backend and trust-policy owners.

## References

- [ADR-008](adr-008-processor-layer-and-execution-artifact-boundaries.md)
- [ADR-061](adr-061-published-schema-evolution-policy.md)
- [ADR-070](adr-070-realization-envelope-semantics.md)
- [ADR-071](adr-071-reusable-asset-trust-and-integrity-policy.md)
- [ADR-077](adr-077-associated-artifact-manifest-boundary.md)
- Portable Artifact Requirement Satisfaction:
  `specs/supply-chain/artifact-requirement-satisfaction.md`

## Amendments

| Date | Commit/PR | Summary |
| --- | --- | --- |
| 2026-10-31 | #1776 | The `x-raes-invariants` profile no longer publishes importable validator paths. |
