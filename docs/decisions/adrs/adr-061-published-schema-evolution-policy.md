# ADR-061: Published Schema Evolution Policy

## Status

accepted

## Date

2026-06-14

## Classification

Classification: FM2
Required artifacts: ADR, manifest metadata, checker gate, regression tests
Waivers: none

## Context

`contracts/schemas/` publishes JSON Schema documents with versioned filenames,
but the repository did not define what the version suffix promises. A file named
`*-v1.json` could change structurally while keeping the same contract id, and
`contracts/schema-publication-manifest.json` only proved that every schema was
listed. It did not say whether a listed schema was stable, whether drift was
recorded, or what change must mint a new suffix.

This gap matters for GOV-901: versioning and compatibility rules must cover
contract surfaces, not only Python package or repository-layout compatibility.
ADR-010 remains the policy for repository realignment and internal package
compatibility. Published JSON Schemas need their own concrete policy because
independent processors, backends, profiles, and fixtures can target these
files.

## Decision

`contracts/schema-publication-manifest.json` is the only publication registry
for machine-readable schemas. Each entry records:

- `contract_id`: the published contract identifier, matching the schema
  filename stem;
- `schema_path`: the repo-relative schema path under `contracts/schemas/`;
- `stability`: one of `draft` or `stable`; and
- `content_hash`: the canonical JSON `sha256` digest of the schema content.

The manifest root records `hash_algorithm: sha256`. The digest is computed from
parsed JSON with deterministic key ordering, so formatting-only churn does not
change the recorded schema identity.

### Stability

`draft` means the schema is published for repository-internal coordination and
early consumers, but it is not compatibility-guaranteed. Draft schemas may
change under the same version suffix, but every checked-in change must update
the manifest hash so churn is visible in review.

`stable` means the schema is a compatibility surface. Stable schemas may accept
additive changes under the same suffix, but breaking changes require a new
version suffix and contract id, for example `example-contract-v1` to
`example-contract-v2`. The old stable schema stays available until a documented
deprecation or removal window completes.

The current checked-in schemas are `draft`. A `v1` or `v2` suffix identifies the
schema lineage; it does not by itself mean the schema is stable.

### Additive And Breaking Changes

For published JSON Schemas, additive changes include:

- adding an optional property;
- adding enum values;
- loosening validation constraints; and
- changing annotations such as descriptions, titles, examples, or comments.

Breaking changes include:

- removing a property;
- retyping a property or changing its `$ref`, composition, item, or constraint
  shape incompatibly;
- adding a newly required property;
- removing enum values;
- tightening `additionalProperties`;
- tightening ranges, patterns, formats, string lengths, array bounds, or object
  cardinality; and
- changing defaults or prose semantics when consumers could observe a different
  contract meaning.

When a change has both additive and breaking parts, treat the whole schema edit
as breaking.

### Version Bumps And Deprecation

A stable breaking change is delivered by adding a new schema file and contract
id with the next version suffix. The previous stable schema remains listed in
the manifest unless a later release removes it under an explicit deprecation
record. Deprecation records live in the relevant ADR or contract documentation
and release notes; this ADR sets the expectation, while the first automated
gate only enforces manifest shape, hashes, and stable in-place breaking edits.

### Enforcement

`tools/check_schema_publication.py` enforces the publication registry:

- every checked-in schema under `contracts/schemas/` is listed exactly once;
- every entry stays under `contracts/schemas/` and matches its filename stem;
- every entry declares `stability` and a canonical content hash; and
- when invoked with a base revision, an incompatible structural edit to a
  `stable` schema under the same `contract_id` fails.

The stable change classifier is intentionally conservative. Existing-property
schema fingerprint changes, property removals, newly required properties, enum
removals, and `additionalProperties` tightening are breaking until a future ADR
narrows the rule.

## Alternatives Considered

Extend ADR-010 to cover schemas. Rejected: ADR-010 is about repository
realignment and internal package compatibility. Stretching it would make the
published schema contract depend on an unrelated migration decision.

Create a second sidecar ledger. Rejected: a separate registry would drift from
the existing publication manifest. The manifest is already the canonical schema
inventory, so the policy metadata belongs there.

Declare all current `v1` and `v2` schemas stable. Rejected: the repository is
still evolving these surfaces, and issue #497 was opened because current
schemas mutate under constant suffixes. Calling them stable would make the
claim false on day one.

Block every stable schema change. Rejected: optional additions and loosening
changes can be compatible. Stable means compatibility-governed, not frozen.

## Consequences

Consumers can distinguish lineage version from stability. A current `v1` draft
schema can change, but the manifest records the exact content. A future stable
schema can evolve additively, while breaking changes must create a new suffix.

The checker remains filesystem and Git based. It does not call Ground Control,
does not read secrets, and does not depend on CI-only environment variables.

The initial classifier does not model every JSON Schema compatibility edge. It
prioritizes clear breaking cases and leaves more precise deprecation-window and
semantic compatibility checks for later policy work under GOV-901.

## Amendments

| Date | Commit/PR | Summary |
|------|-----------|---------|
| 2026-11-06 | #1929 | Publication records no longer store `content_hash`, and the manifest root no longer records `hash_algorithm`. A schema change needs no record edit; git holds the schema history. Breaking-change detection compares each `stable` schema with its base revision directly. Removal tombstones are unchanged. |
