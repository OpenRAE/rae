# Shared semantic profiles

## Scope

This specification defines shared semantic profiles for RAES authoring,
exchange, processing, and execution surfaces.

Shared semantic profiles declare the compatible concept, contract, and
behavior assumptions required for interoperable artifact production,
publication, processing, and runtime operation.

## Decision record

ADR-012 in the [decision index](../../docs/decisions/adrs/README.md)
governs this specification.

## Profile model

Each semantic profile declares:

- a stable `profile_id`
- the `concept_catalog_version` it assumes
- phase-specific assumptions for `authoring`, `exchange`, `processing`, and
  `execution`

Each phase declares:

- `required_contracts`: the published contract identifiers required for that
  interoperability phase
- `required_concept_families`: the concept families whose meaning must be
  shared for that phase
- `required_bindings`: the required scope-to-family bindings where a governed
  artifact surface must bind its vocabulary explicitly
- `behavior_assumptions`: stable behavior-assumption identifiers and
  statements that describe the non-structural semantic expectations for that
  phase

`required_bindings` are only valid when they resolve to governed artifact
surfaces for that phase. In the initial profile, that means processor
manifest `v2` binding scopes for `processing` and backend manifest `v2`
binding scopes for `execution`. `authoring` and `exchange` do not currently
define governed binding surfaces and therefore do not declare
`required_bindings`.

## Initial profile

The initial GOV-920 profile is:

`contracts/profiles/semantic/reference-stack-v1.json`

It declares the shared assumptions for the current reference stack:

- SDL authoring and instantiation
- processor planning and coordination
- backend realization and execution
- typed runtime exchange envelopes

The reference stack profile is intentionally concrete. It is the first
repo-owned semantic profile, not a promise that the ecosystem will forever use
only one profile.

The reference stack requires the native `episodes` family in `exchange` and `execution`.
These phases exchange and execute participant episode state and history contracts.
Authoring and processing do not currently require the family.
ADR-013's amendment permits an optional `behavior_specifications.*.episode_policy` record of authored episode intent (DSL-120).
That record compiles to participant metadata, without asserting episode state or history.
The reference processor does not publish episode state/history contracts as a processing capability.

The profile records episode coverage through `required_contracts` and `required_concept_families`.
It does not use a `required_bindings` entry on `capabilities.supported_participant_contracts`.
That manifest scope also contains implementation, behavior, and provenance contracts.
It is not an episode-only binding surface.

The reference stack requires the native `runtime-inventory` concept family in the `authoring` phase.
SDL authoring and instantiation carry observed node runtime inventory under `nodes.*.runtime` in the `sdl-authoring-input-v1` and `instantiated-scenario-v1` contracts.
The profile records this through `required_concept_families` only, as with other authoring families.
Authoring does not define governed `required_bindings` surfaces, so runtime-inventory coverage is not expressed as a binding.

## Machine-readable artifacts

The JSON Schema for semantic profiles is published at:

`contracts/schemas/profiles/semantic-profile-v1.json`

The valid and invalid fixture corpus for semantic profiles is published under:

`contracts/fixtures/semantic-profile/semantic-profile-v1/`

<!-- vale RAES.HeadingCase = NO -->
## UCO alignment evidence

Semantic profiles compose RAES concept, contract, binding, and behavior
assumptions; they are not UCO profiles and do not adopt UCO authoring syntax.
`contracts/concept-authority/uco-alignment-v1.json` (schema `uco-alignment/v1`)
records the concept-authority relationship for adopted and adapted cyber-domain families.
A profile may require these families.
The artifact pins the reviewed UCO version and lists each adapted family's divergences.
See ADR-012 in the [decision index](../../docs/decisions/adrs/README.md).

<!-- vale RAES.HeadingCase = YES -->

## Relationship to other requirements

- GOV-917: canonical concept authority
- GOV-918: cross-artifact concept binding
- GOV-919: disciplined RAES-native extensions
- GOV-920: shared semantic profiles
- GOV-921: shared reference models
- GOV-922: controlled vocabularies and enumerations
