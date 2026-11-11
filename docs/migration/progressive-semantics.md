# Migrate progressive SDL semantics

## Versions and purpose

Source: `raes-legacy-semantics/384e8b19 source bytes`.
Target: `raes-progressive-semantics/v1 with current admission and observation contracts`.

## Before you start

Use RAES 11.0.2. Retain the original source and every linked binding document.
Obtain the author's explicit adoption decisions before constructing the context.
Resolve each authored sentinel and any removed classification first.
The helper returns a new artifact.
It does not rewrite files or invoke a backend.

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
from raes.semantic_migration import migrate_sdl_semantics
from raes.semantic_migration_context import SDLSemanticMigrationContext
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

The result carries `semantic_revision: raes-progressive-semantics/v1`.
It does not invent an OS or runtime. Save the report with the result. It records adoption,
not equivalence or backend readiness. Unsupported old shapes need their owning
migration or author correction before target admission succeeds.

Add a `sentinel_decisions` item for each explicitly authored typed `other` or `unknown`.
Include `pointer`, `interpretation`, and `rationale`.
For example, `/nodes/host/runtime/database_services/0/engine` may use
`knowledge` to retain `other`, or `exact-identity` with an author-confirmed
`identity: x-owner:private-db`. Exact identities cannot be sentinel aliases such
as `OTHER` or variable references such as `${engine}`. `delegated` requires an existing open realization scope.
Missing decisions, stale source digests, and invalid identities refuse without partial output. Private profile JSON is preserved literally.

Conversion does not promise the old meaning of omission or closed collections.
It does not promise old admission-quantifier or implicit evidence-floor meaning. Review the current policy explicitly.
A descriptive constraint does not request observation.
One supported completion does not prove universal envelope coverage.

## Select, compose and inspect

`read_versioned_sdl` and `format_versioned_sdl_source` require an explicit current revision.
Carry it in the source or supply it with the exact source-byte digest.
They reject old and unknown revisions. Ordinary current APIs accept untagged
current source without a historical interpretation mode.

Migrate each imported module independently.
Tag the root and every module with the same revision. The parser rejects mixed revision graphs.
Keep the root and its modules together for validation.

The SDL inspection result includes `semantic_axes`.
These describe authored constraint sections and realization/delegation policy.
They also describe observation requirements. Legacy
evidence requirements are labeled as legacy inputs to the current adapter.
Omitted or inherited demand is distinct from explicit no-data and operational-only
modes. Inspection reports authored policy without asserting backend capability.

For semantic diff, load `contracts/profiles/semantic-comparison/reference-v2.json`.
Pass `scenario_projection_version="2"` when building impact scopes and coordinates. The request binds that profile's exact digest. This preserves
omitted-versus-empty collections and private `description` values. Task projection
version 2 also compares observation demand. Current scenarios reject owner projection v1, including untagged sources.
Current tasks reject it too. Scenario coordinates and
impact scopes default to version 2.

Current authoring and instantiated snapshot digests use
`raes-sdl-semantic/v2` and `raes-sdl-instantiated-snapshot/v2`, including
untagged current sources. Old v1 snapshots are rejected. Reconstruct current snapshots and reissue digest-bound sidecars.
Relabeling an old digest is invalid.

## Coordinate classification migration

Follow [external classification migration](external-classifications.md) first
when the source contains removed built-in classifications. Render and review that result.
Bind the progressive context to those exact intermediate bytes.
Pass the returned `binding_documents` and the same pinned `scheme_snapshots` to
`migrate_sdl_semantics`. The operation retargets exact subject digests and checks binding admission.
It retains classification provenance. Supplying sidecars without
the required scheme context refuses the conversion.

Current execution checks admission independently.
It also checks observation capabilities and delivered results. Conversion cannot waive required operational inputs.
It cannot enable unsupported collection/export behavior.

## Check the result and recover

Success provides current SDL, linked binding documents, and an adoption report.
Keep them together under new content identities. Validate the rendered result before later admission.
Missing decisions, stale source digests, or unsupported input refuse without partial output.
Correct the source-bound decision and repeat conversion; do not relabel an old digest.
No native cleanup is needed for conversion.
Read [the revision specification](../../specs/evolution/progressive-semantics.md)
and [the artifact explanation](../public/concepts.md).
