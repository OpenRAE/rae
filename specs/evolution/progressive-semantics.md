# Progressive SDL semantic revisions

This specification defines the GOV-903 breaking semantic cutover for issue #1210.
It applies the [evolution policy](versioning-deprecation-and-migration.md) and
[ADR-105](../../docs/decisions/adrs/adr-105-recursive-partial-description-semantics.md).

## Breaking revision boundary

`raes-progressive-semantics/v1` selects the current recursive contract. Current
source can carry `semantic_revision: raes-progressive-semantics/v1`; this field
survives composition, instantiation, rendering and snapshots. It is metadata,
not a realization dimension. Every module in an import graph must carry the same
selection; mixed tagged/untagged or unsupported graphs are refused.

This release does not provide legacy interpretation, legacy execution or frozen
legacy schema readers. Ordinary `parse_sdl`, formatting and snapshot APIs use
current semantics, including for untagged source. Old omission, collection,
sentinel, admission and evidence-floor interpretations are not compatibility
promises. This change may break existing artifacts and callers.

The explicit version-aware reader requires the current carried revision or the
current revision plus the SHA-256 digest of exact UTF-8 source bytes. Unsupported
or contradictory selections fail before current normalization. Older source
requires explicit migration or author edits. Package versions, module versions
and `sdl-yaml/v1` remain independent identities.

## Author-authorized adoption

The operation `adopt-progressive-sdl-semantics/v1` accepts a bounded, closed
`sdl-semantic-migration-context-v1` tied to the exact source-byte digest. Its
source label `raes-legacy-semantics/384e8b19` identifies the pre-progressive
migration input; it does not certify that input against an old schema. The
context requires explicit recursive-constraint adoption and names both
`backend-realization-preparation-v1` and `observation-demand-v1`. These choices
record adoption of changed permission and obligation semantics. They neither
negotiate backend support nor grant execution permission.

Every explicitly authored typed `other` or `unknown` leaf requires an exact
JSON-pointer decision with a rationale. `knowledge` preserves the sentinel;
`exact-identity` supplies an author-selected value admitted by the field owner,
excluding case-normalized sentinel aliases and whole-field variable references;
`delegated` removes the leaf only under an already authored open scope. There
is no inferred product identity, new open scope or per-property waiver. Omitted
sentinels and arbitrary strings inside private JSON are not scanned as decisions.

Conversion validates the input's supported spelling and structure through current
owners, applies the explicit decisions, and re-admits the target. Unsupported
old shapes require author correction or their owning migration. Conversion
retains authored field presence, private JSON and exact APT repository values;
it makes no claim to preserve old interpretation. It does not synthesize OS,
packages or observation demand. Constraints, delegation and requested observations
remain separate. Inherited demand, explicit no-data and operational-only demand
retain their distinct current contracts. Old implicit evidence floors are not
silently reconstructed in the target.

Imports must be migrated independently before composition. Classification removal
and external assertions use the existing #989 migration owner first. Supplied
binding documents are retargeted atomically and admitted against supplied pinned
scheme snapshots; missing admission context refuses the whole result. Removed
classification syntax is not guessed or discarded.

## Identity and comparison

`raes-versioned-sdl/v1` canonical bytes use RFC 8785 over an object containing
`profile`, `semantic_revision`, `contract_id` and `payload`. This identity is
separate from the exact-source provenance digest. Version-aware formatting
requires a current selection and returns formatted bytes with a rebound digest.

The transformation report's `sdl-progressive-migration-digest-pair/v1` means:
`source_digest` is SHA-256 of exact UTF-8 source bytes and `target_digest` is the
current `raes-sdl-semantic/v2` canonical SDL digest. The derivation additionally
binds the author context and supplied binding/scheme documents. Refusal returns
no target or sidecars. Cross-version preservation is `not-applicable`; successful
target admission proves neither behavioral compatibility nor operational
interoperability. Reprocessing a tagged current result without legacy context is
a semantic no-op.

`contracts/profiles/semantic-comparison/reference-v2.json` selects scenario and
task owner projection version `2` within the existing digest-bound comparison
protocol. Scenario v2 retains authored presence, recursive constraints and literal
private JSON, removing only model-owned SDL editorial descriptions. Its coordinate
profile `raes-canonical-sdl/v2` hashes an RFC 8785 object with `profile` and the
authored `scenario` dump. Task v2 includes observation demand while retaining
value-based defaults: omission and an explicitly supplied default have the same
semantics and task coordinate. Select
these versions consistently when deriving impact scopes and requests. Current
scenarios, tagged or untagged, and current tasks require owner projection v2.
Scenario coordinates and scope construction default to v2. Existing comparison records
retain their own profile identity; they do not certify the new semantics.

Historical research admission is limited to eight independently pinned original
production-evidence records. A policy-pinned manifest authenticates their frozen
closed shapes; computed joins and corpus membership are checked before projecting
recorded identities. This integrity check provides no legacy execution capability.

## Capability boundaries

Current admission owns supported completion, delivered-state validation and
observation capability checks. Mandatory observation combined with mutation and
export without a governed delivery owner remain subject to existing refusal
rules. Migration must not claim those capabilities or upgrade evidence strength.
Diagnostics do not echo private values.
