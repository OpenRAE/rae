<a id="external-classification-migration"></a>

# Move historical classifications to binding documents

## Versions and purpose

Source: `Pre-989 canonical-spelling, uncomposed SDL with historical classification fields`.
Target: `Current sdl-authoring-input-v1 plus external-concept-bindings/v1 sidecars`.

## Before you start

Use RAES 11.0.2 and retain exact source bytes and existing sidecars.
Supply independently pinned scheme snapshots.
Supply explicit assertion dimensions.
Obtain authority for each declaration removal.
Obtain authority for each semantic omission too.
The converter fetches no catalogues.
It does not overwrite source or change runtime state.

Issue #989 replaces historical domain-shaped SDL classification fields.
Standalone `external-concept-bindings/v1` documents carry their assertions separately. The canonical SDL reader
rejects those historical fields with `sdl.classification-migration-required`,
including under `migration_policy="accept"`.
Formatting syntax alone cannot supply the missing assertion context.

The complete [inventory and conversion contract](../../specs/concept-authority/classification-migration.md)
distinguishes removed classifications from retained operational predicates.
The source lineage is SDL authoring input before #989.
The target is revised draft `sdl-authoring-input-v1` plus #986 binding documents. This is an assisted migration.
It does not claim backward structural compatibility for the canonical reader.

## Convert an artifact

1. Retain the original source and all existing binding artifacts.
   Use canonical spelling and uncomposed authoring source.
   Supply concrete classification values. Convert modules individually and update their pinned import digests.
2. Use `raes.classification_migration.legacy_classification_source_digest()`
   to obtain the supported legacy source projection digest.
3. Author a complete `ExternalConceptBindingDocumentModel`. For each legacy association, supply its exact native subject and source digest.
   Supply explicit scheme authority, revision, locator, digest, and concept ID.
   Supply all assertion dimensions. Include an `authoring-input` source reference with that digest.
   Put the association's JSON pointer in `ref_path`, for example `/nodes/web/vulnerabilities/0`. Do not replace a display key with a guessed
   concept id. Use the pinned source's actual id or an explicit authored map.
4. Supply the exact local `ExternalConceptSchemeSnapshotModel` objects. The standard ATT&CK, ATLAS, and NIST adapters are optional helpers.
   Conversion fetches no catalogue. For CWE, supply an independently pinned source
   context. The old `CWE-NNN` string does not identify a source revision.
5. Call `migrate_sdl_classifications(source, bindings=document,
   scheme_snapshots=snapshots, existing_binding_documents=existing,
   policy=policy)`. Explicitly allow `declaration-removed` when removing
   vulnerability declarations. Allow `semantic-omission` only when intentionally
   omitting an unreferenced declaration. The normal default authorizes no loss.
6. Check `result.succeeded`. On success, retain `result.output` and `result.report` together.
   Keep every `result.binding_documents` entry with them. Render the
   output with `raes.formatting.render_sdl_source()` and validate it normally.
   On refusal, no candidate SDL or sidecar is returned.

## Refusals and verification

`context-required` means the source lacks complete authored assertions.
`context-invalid` reports a bad source pointer or subject.
It can be missing, duplicated, stale, or inconsistent. `loss-not-authorized` names a required loss decision.
`target-invalid` requires a separate native migration.
The remaining configuration or a reference to a removed declaration needs correction. `source-invalid` includes unsupported lifecycle/import input.
It also includes noncanonical historical values.
Routes resolve exactly as `nodes.<node>.runtime.applications.<application_id>.routes.<route_id>`.
Ambiguous coordinates refuse. They do not expand to the owning node.
`binding-admission-failed` requires current unambiguous
local scheme context. These codes use the `classification-migration.` prefix.
Their bounded messages omit source values.

Run `implementations/python/tests/test_classification_migration.py` for native projection, binding admission, and the transformation report.
It also checks schema parity and the compatibility timeline. Source-catalog
integrity retains the existing ATT&CK/ATLAS/NIST checks. Before publication, run the targeted checks for the converted artifact.
Run full verification in CI.

## Semantic changes and rollback

Externalization changes artifact digests. Supply existing binding documents explicitly to conversion.
This lets conversion retarget and readmit their subjects. Recompute semantic comparison and projection reports against the
new exact frame. Keep configuration changes separate from changes to interpretation.
Keep review and confidence changes separate too.

Participant-facing labels use ordinary content/disclosure controls. Eligibility in a binding is not delivery or observation.
It does not grant authority. It does not establish understanding.

For rollback, use the retained source.
Use its matching earlier reader and binding artifacts. Do not copy an old digest onto converted data. The operation never overwrites input.
Failed conversion leaves the original artifacts intact.

## Historical replay and examples

The versioned snapshot reader removes only exact empty classification defaults from the old serializer.
This rule applies whether or not the snapshot also needs historical `vm` node conversion. This includes empty,
switch-only and compute-only snapshots. Its joined snapshot migration authenticates the original digest.
Only then does it produce a new digest. Nonempty retired fields still fail with classification migration guidance.
This is not implicit assertion conversion. It does not relax the canonical schema.

Frozen research evidence is not rewritten. Changed replay outputs require versioned evidence.
It must record explicit deviations or independently verified, field-specific equivalence. An old/current hash pair alone does not establish
that equivalence. The SDL lineage checker projects the retired vulnerability subject to the removal authority.
It preserves the historical ledger.
The Port Authority example's former unreferenced declarations remain in the
example provenance inventory.

The [curated examples](classification-examples/README.md) retain historical source pins.
They show generic bindings for exact node and route subjects.
Old labels do not identify an authoritative CWE revision.

## Check the result and recover

Success returns validated native SDL and the source-bound report.
Keep every returned sidecar with them.
On refusal, read its diagnostic code.
Correct the context, source, or explicit loss policy.
Recompute changed content identities and rebind consumers before publication.
No native resources are created, so no backend cleanup is needed.
Read the [classification migration contract](../../specs/concept-authority/classification-migration.md)
and [classification example boundary](classification-examples/README.md).
