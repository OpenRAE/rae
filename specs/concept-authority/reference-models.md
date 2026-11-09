# Shared reference models

## Scope

This specification defines shared reference models for recurrent
federation-relevant structures carried in RAES artifact surfaces.

Shared reference models do not redefine concept authority and do not replace
artifact-local schemas. They declare which published structure definitions are
the shared reusable models for recurrent objects such as assets, identities,
relationships, observables, actions or events, and tools or artifacts.

## Decision record

ADR-012 in the [decision index](../../docs/decisions/adrs/README.md)
governs this specification.

## Reference model catalog

Each reference-model catalog declares:

- a stable `schema_version`
- a keyed `models` map

Each model declares:

- a human-readable `title`
- a `description`
- the authoritative `concept_family` it belongs to
- an `authoritative_schema` binding that identifies the published contract
  schema definition and the governed instance path where that structure is
  used
- optional `reused_schemas` bindings for equivalent reused structures in other
  published contracts
- `key_fields` that must exist on the referenced schema definition

Reference-model bindings must resolve to real published contract schemas, real
schema definitions, and real governed instance collections. Reference models
are intentionally anchored to existing schema authority instead of restating
object structure inline.

## Initial catalog

The initial GOV-921 catalog is:

`contracts/concept-authority/reference-models-v1.json`

It declares the shared reference models for the current recurrent SDL object
slice:

- scenario nodes as asset-bearing structures
- scenario accounts as identity-bearing structures
- scenario relationships as directed relationship structures
- scenario conditions as observable structures
- scenario events as action or event structures
- scenario content as tool or artifact structures
- node runtime inventory as observed runtime configuration state under
  `nodes.*.runtime`

## Participant episode lineage

Participant episodes belong to the native `episodes` concept family, not an SDL reference model entry.
The external lineage is the reinforcement-learning environment episode used by Gymnasium and OpenAI Gym.
This bounded interaction sequence starts after initialization or reset.
It ends at a terminal, timeout, or truncation boundary.
RAES narrows that lineage to participant-runtime contracts by requiring stable
`participant_address`, per-episode `episode_id`, explicit lifecycle state, and
append-only state/history surfaces.

[ADR-013](../../docs/decisions/adrs/adr-013-participant-episode-lifecycle-boundaries.md)
is the internal authority.
It gives participant episode state its own processor/runtime contract surface.
This surface remains separate from workflow state, evaluation state, operation receipts, backend process restarts, tasks, runs, and scenarios.
Participant-local actions and observations also remain separate.

## Node runtime inventory

`nodes.*.runtime` is cataloged as the `scenario-node-runtime` reference model in
the native `runtime-inventory` concept family.
It is the largest recurrent SDL structure and receives most new inventory fields.
Its anchor is the published `RuntimeConfiguration` definition
(`#/$defs/RuntimeConfiguration`) in both `sdl-authoring-input-v1` and
`instantiated-scenario-v1` rather than restated inline.

The `runtime` node field is optional, so its published shape is a nullable
`anyOf` of the `RuntimeConfiguration` reference and `null`. Reference-model
binding resolution looks through that nullable-optional wrapper to the
underlying definition, which lets optional surfaces participate as reference
models while bindings still resolve to real published schema definitions. The
governance decision path for adding a new runtime inventory field is documented
under Extension Discipline in [concept-authority.md](./concept-authority.md).

## Machine-readable artifacts

The JSON Schema for the catalog format is published at:

`contracts/schemas/concept-authority/reference-models-v1.json`

The valid and invalid fixture corpus for reference models is published under:

`contracts/fixtures/concept-authority/reference-models-v1/`

<!-- vale RAES.HeadingCase = NO -->
## UCO alignment evidence

Reference models bind recurrent RAES structures to RAES concept families; they
do not inherit UCO class structure. The concept-authority relationship behind
the adopted and adapted cyber-domain families those models reference is recorded
separately as machine-checkable evidence in
`contracts/concept-authority/uco-alignment-v1.json` (schema `uco-alignment/v1`).
That artifact pins the reviewed UCO version and maps each adopted and adapted
family to the UCO object types it aligns to, enumerating adapted-family
divergences explicitly. See ADR-012 in the [decision index](../../docs/decisions/adrs/README.md).

<!-- vale RAES.HeadingCase = YES -->

## Relationship to other requirements

- GOV-917: canonical concept authority
- GOV-918: cross-artifact concept binding
- GOV-919: disciplined RAES-native extensions
- GOV-920: shared semantic profiles
- GOV-921: shared reference models
- GOV-922: controlled vocabularies and enumerations
