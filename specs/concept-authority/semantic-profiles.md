# Shared Semantic Profiles

## Scope

This specification defines shared semantic profiles for RAES authoring,
exchange, processing, and execution surfaces.

Shared semantic profiles declare the compatible concept, contract, and
behavior assumptions required for interoperable artifact production,
publication, processing, and runtime operation.

## Decision Record

[ADR-012](../../docs/decisions/adrs/adr-012-shared-concept-authority-and-raes-extension-discipline.md)
governs this specification.

## Profile Model

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

## Initial Profile

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

The reference stack requires the native `episodes` concept family in the
`exchange` and `execution` phases because those phases exchange and execute the
participant episode state and episode history contracts. Authoring and
processing do not require the family today. Since ADR-013's amendment, SDL may
carry an optional `behavior_specifications.*.episode_policy` record of authored
episode intent (DSL-120). That record compiles to participant metadata, not to
episode state or history, and the reference processor does not publish
participant episode state/history contracts as a processing capability. The
profile therefore records episode coverage through
`required_contracts` and `required_concept_families`, not through a
`required_bindings` entry on `capabilities.supported_participant_contracts`;
that manifest scope also contains implementation, behavior, and provenance
contracts and is not an episode-only binding surface.

The reference stack requires the native `runtime-inventory` concept family in
the `authoring` phase because SDL authoring and instantiation carry observed
node runtime inventory under `nodes.*.runtime` in the `sdl-authoring-input-v1`
and `instantiated-scenario-v1` contracts. As with the other authoring families,
the profile records this through `required_concept_families` only: `authoring`
does not define governed `required_bindings` surfaces, so runtime-inventory
coverage is not expressed as a binding.

## Machine-Readable Artifacts

The JSON Schema for semantic profiles is published at:

`contracts/schemas/profiles/semantic-profile-v1.json`

The valid and invalid fixture corpus for semantic profiles is published under:

`contracts/fixtures/semantic-profile/semantic-profile-v1/`

## UCO Alignment Evidence

Semantic profiles compose RAES concept, contract, binding, and behavior
assumptions; they are not UCO profiles and do not adopt UCO authoring syntax.
The concept-authority relationship behind the adopted and adapted cyber-domain
families a profile may require is recorded as machine-checkable evidence in
`contracts/concept-authority/uco-alignment-v1.json` (schema `uco-alignment/v1`),
which pins the reviewed UCO version and enumerates each adapted family's
divergences. See [ADR-012](../../docs/decisions/adrs/adr-012-shared-concept-authority-and-raes-extension-discipline.md).

## Relationship To Other Requirements

- GOV-917: canonical concept authority
- GOV-918: cross-artifact concept binding
- GOV-919: disciplined RAES-native extensions
- GOV-920: shared semantic profiles
- GOV-921: shared reference models
- GOV-922: controlled vocabularies and enumerations
