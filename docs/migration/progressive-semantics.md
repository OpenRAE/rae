# Migrate progressive SDL semantics

This is a breaking cutover to the current progressive contract. Legacy readers
and execution are not provided. Untagged input to ordinary parsing, formatting
and snapshot APIs uses current semantics. The
[revision specification](../../specs/evolution/progressive-semantics.md) defines
the supported migration and its limits.

## Adopt current semantics

Review the source before creating its adoption context. This example uses a
small closed model with no ambiguous sentinel leaves:

```python
from raes import render_sdl_source
from raes.semantic_migration import SDLSemanticMigrationContext, migrate_sdl_semantics
from raes.semantic_revisions import source_byte_digest

source = "name: example\nnodes: {host: {type: compute}}\n"
context = SDLSemanticMigrationContext(
    source_digest=source_byte_digest(source),
    adopt_recursive_constraints=True,
    admission_contract="backend-realization-preparation-v1",
    observation_contract="observation-demand-v1",
    rationale="Author adopts explicit current admission and observation policy.",
)
result = migrate_sdl_semantics(source, context=context)
assert result.succeeded
current_source = render_sdl_source(result.output).content
```

The result carries `semantic_revision: raes-progressive-semantics/v1` and does
not invent an OS or runtime. Save the report with the result. It records adoption,
not equivalence or backend readiness. Unsupported old shapes need their owning
migration or author correction before target admission succeeds.

For every explicitly authored typed `other` or `unknown`, add a
`sentinel_decisions` item containing `pointer`, `interpretation` and `rationale`.
For example, `/nodes/host/runtime/database_services/0/engine` may use
`knowledge` to retain `other`, or `exact-identity` with an author-confirmed
`identity: x-owner:private-db`. Exact identities cannot be sentinel aliases such
as `OTHER` or variable references such as `${engine}`. `delegated` requires an existing open realization
scope; missing decisions, stale source digests and invalid identities refuse
without partial output. Private profile JSON is preserved literally.

Old omission, closed collection, admission-quantifier and implicit evidence-floor
meanings are not promised after conversion. Review the current policy explicitly.
A descriptive constraint does not request observation, and one supported completion
does not prove universal envelope coverage.

## Select, compose and inspect

`read_versioned_sdl` and `format_versioned_sdl_source` require an explicit current
revision, carried in the source or supplied with its exact source-byte digest.
They reject old and unknown revisions. Ordinary current APIs accept untagged
current source without a historical interpretation mode.

Migrate each imported module independently and tag the root and every module
with the same revision. The parser rejects mixed revision graphs.

The existing SDL inspection result includes `semantic_axes`: authored constraint
sections, realization/delegation policy and observation requirements. Legacy
evidence requirements are labeled as legacy inputs to the current adapter.
Omitted or inherited demand is distinct from explicit no-data and operational-only
modes. Inspection reports authored policy without asserting backend capability.

For semantic diff, load `contracts/profiles/semantic-comparison/reference-v2.json`
and pass `scenario_projection_version="2"` when building impact scopes and
coordinates. The request binds that profile's exact digest. This preserves
omitted-versus-empty collections and private `description` values. Task projection
version 2 also compares observation demand. Current scenarios, including untagged
sources, and current tasks reject owner projection v1. Scenario coordinates and
impact scopes default to version 2.

Current authoring and instantiated snapshot digests use
`raes-sdl-semantic/v2` and `raes-sdl-instantiated-snapshot/v2`, including
untagged current sources. Old v1 snapshots are rejected. Reconstruct current
snapshots and reissue digest-bound sidecars; relabeling an old digest is invalid.

## Coordinate classification migration

Follow [external classification migration](external-classifications.md) first
when the source contains removed built-in classifications. Render that result,
review it and bind the progressive context to those exact intermediate bytes.
Pass the returned `binding_documents` and the same pinned `scheme_snapshots` to
`migrate_sdl_semantics`. The operation retargets exact subject digests and checks
binding admission, retaining classification provenance. Supplying sidecars without
the required scheme context refuses the conversion.

Current execution independently checks admission, observation capabilities and
delivered results. Conversion cannot waive required operational inputs or enable
unsupported collection/export behavior.
