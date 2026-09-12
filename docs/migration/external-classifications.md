# External classification migration

Issue #989 replaces historical domain-shaped SDL classification fields with
standalone `external-concept-bindings/v1` documents. The canonical SDL reader
rejects those historical fields with `sdl.classification-migration-required`,
including under `migration_policy="accept"`: syntax formatting alone cannot
supply the missing assertion context.

The complete [inventory and conversion contract](../../specs/concept-authority/classification-migration.md)
distinguishes removed classifications from retained operational predicates.
The source lineage is SDL authoring input before #989; the target is the
revised draft `sdl-authoring-input-v1` plus #986 binding documents. This is an
assisted migration, not a claim of backward structural compatibility for the
canonical reader.

## Convert an artifact

1. Retain the original source and all existing binding artifacts. Supply
   canonical-spelling, uncomposed authoring source with concrete classification
   values. Convert modules individually and update their pinned import digests.
2. Use `raes.classification_migration.legacy_classification_source_digest()`
   to obtain the supported legacy source projection digest.
3. Author a complete `ExternalConceptBindingDocumentModel`. For every legacy
   association, provide its exact native subject, the source digest, explicit
   scheme authority/revision/locator/digest and concept id, and all assertion
   dimensions. Include an `authoring-input` source reference with that digest
   and the association JSON pointer in `ref_path`, for example
   `/nodes/web/vulnerabilities/0`. Do not replace a display key with a guessed
   concept id. Use the pinned source's actual id or an explicit authored map.
4. Supply the exact local `ExternalConceptSchemeSnapshotModel` objects. The
   standard ATT&CK, ATLAS and NIST adapters are optional helpers; no catalog is
   fetched by conversion. For CWE, supply an independently pinned source
   context. The old `CWE-NNN` string does not identify a source revision.
5. Call `migrate_sdl_classifications(source, bindings=document,
   scheme_snapshots=snapshots, existing_binding_documents=existing,
   policy=policy)`. Explicitly allow `declaration-removed` when removing
   vulnerability declarations. Allow `semantic-omission` only when intentionally
   omitting an unreferenced declaration. The normal default authorizes no loss.
6. Check `result.succeeded`. On success, retain `result.output`, every
   `result.binding_documents` entry and `result.report` together. Render the
   output with `raes.formatting.render_sdl_source()` and validate it normally.
   On refusal, no candidate SDL or sidecar is returned.

## Refusals and verification

`context-required` means the source lacks complete authored assertions.
`context-invalid` means a source pointer/subject is missing, duplicated,
stale or inconsistent. `loss-not-authorized` names a required loss decision.
`target-invalid` means the remaining configuration or a reference to a removed
declaration needs a separate native migration. `source-invalid` includes
unsupported lifecycle/import input and noncanonical historical values.
Routes resolve exactly as `nodes.<node>.runtime.applications.<application_id>.routes.<route_id>`;
ambiguous coordinates refuse rather than widening to the owning node.
`binding-admission-failed` requires current unambiguous
local scheme context. These codes use the `classification-migration.` prefix
and return bounded messages without source values.

The native projection, binding admission, transformation report, schema parity
and compatibility timeline are exercised by
`implementations/python/tests/test_classification_migration.py`. Source-catalog
integrity retains the existing ATT&CK/ATLAS/NIST checks. Run the repository's
normal verification command for a converted artifact before publication.

## Semantic changes and rollback

Externalization changes artifact digests. Existing binding documents must be
explicit inputs to conversion so their subjects can be retargeted and
readmitted. Recompute semantic comparison and projection reports against the
new exact frame. Keep configuration changes separate from interpretation,
review and confidence changes.

Participant-facing labels use ordinary content/disclosure controls. Eligibility
in a binding is not delivery, observation, authorization or understanding.

Rollback is to the retained source and its matching earlier reader and binding
artifacts. Do not copy an old digest onto converted data. The operation never
overwrites input, and a failed conversion leaves the original artifacts intact.

## Historical replay and examples

The versioned snapshot compatibility boundary removes only exact empty
classification defaults emitted by the old serializer, independently of whether
the snapshot also needs historical `vm` node conversion. This includes empty,
switch-only and compute-only snapshots. Its joined snapshot migration
authenticates the original digest before producing a new one. Nonempty retired
fields still fail with classification migration guidance; this is not implicit
assertion conversion or a relaxed canonical schema.

Frozen research evidence is not rewritten. Changed replay outputs require
versioned evidence with explicit deviations or independently verified,
field-specific equivalence. An old/current hash pair alone does not establish
that equivalence. The SDL lineage checker projects the retired vulnerability
subject to the removal authority while preserving the historical ledger.
The Port Authority example's former unreferenced declarations remain in the
example provenance inventory.

The [curated examples](classification-examples/README.md) retain historical
source pins and demonstrate generic bindings for exact node and route subjects
without pretending that old labels identify an authoritative CWE revision.
