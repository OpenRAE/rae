# Factorial typed selections

This design extends ADR-084 and ADR-094 for issue #1665.
Issue #1666 owns compiler support and lifecycle verification.

## Contract architecture

`factorial-bindings-v1` keeps its shapes, serialization, and identity rules.
The new `factorial-treatments-v1` profile declares `level_effects`.
Each level contains scalar `bindings`, typed `selections`, or both.
Bindings reuse `ExperimentFactorLevelBindingModel`.
Selections reuse the closed `ExperimentSelectionOutcomeModel` union.
An alternative uses a `member` outcome.
Its node and inventory payload remains in SDL.

A selection template names the scenario target, family digest, and governed owner.
A generated selection descriptor adds the source factor, level, condition, and selection identity.
Condition criteria, admitted selections, and archival selections share that descriptor.
The admitted record also retains its existing policy and outcome fields.
The two outcomes and point identifiers must agree.
Plan validation checks the descriptor against the coordinate and pinned family.
Archive matching requires exact descriptors, including source joins.
Agreement checks use existing canonical JSON commitments.
Boolean outcomes remain distinct from numeric outcomes.

The authoring contract materializes the complete Cartesian allocation.
Selection-only conditions need no dummy bindings.
They retain `explicit-required` semantics through explicit typed selection criteria.
Supplied allocation and binding children must equal the generated children.
Author and expanded serialization remain bounded.

Condition identities retain the existing factor-to-level digest projection.
Scalar binding identities retain their existing projection.
A selection identity uses `selection-` and the full JCS/SHA-256 digest of
`[condition_id, factor_id, target.canonical_key()]`.
The prefix separates scalar and selection identities.
Selection contents remain covered by authoring, entry, and plan digests.
An optional plan `treatment_profile` explicitly identifies the new semantics.
Its absence preserves legacy plan bytes.
The current compiler rejects the new authoring profile until #1666 supplies support.
It also rejects manual typed selection criteria when no factorial profile is present.
The compiler must not produce a plan that drops those criteria.

## Admission rules

Every factor and level is author-declared.
Each executable level contributes at least one effect.
The existing dimension, level, condition, and logical-run limits remain in force.
The combined effect work limit is 10000.
It includes repeated fixed selections and nested subset or order members.
Counts are checked before product expansion.
The 8 MiB byte budget uses a conservative bound before condition construction.
Actual expanded bytes must also fit that budget.
Objects with no JSON representation are rejected without rendering their contents.

Factor effects and fixed configuration select every family point exactly once.
Only existing fixed policies with `purpose: fixed-configuration` may accompany this profile.
Their output bound is one.
They carry no factor provenance or binding claims.
Duplicate points fail even when their outcomes agree.
Scalar scenario bindings and typed selections cannot claim the same point.
SDL retains authority over target ownership, domain membership, and write conflicts.

Whole-scenario admission remains atomic.
One invalid requested combination rejects the entire design.
No condition is removed, renamed, or replaced.
Participant configurations include effective defaults in every condition.
Their validators check applicability against each selected scenario.
Distinctness compares effective scenario content and complete participant values.
Labels, member identities, policy identities, and provenance do not establish distinct effects.

Node configuration uses declared scalar parameters and the reviewed SDL structural slots.
The supported slots are `nodes.presence` and the listed runtime inventory collections.
Coupled node presence and inventory remain one SDL alternative.
Packages, environment entries, filesystem entries, and nested writes remain unsupported.
This extension needs no new SDL slot.

## Security and data flows

The assets are authored configuration, content commitments, secret references, and treatment identity.
Untrusted experiment input crosses the contract boundary through the existing bounded parser.
Closed models reject extra fields and scalarized structural payloads.
Shared source checks reject forged factor, level, condition, family, point, and owner claims.
Owner admission remains separate from contract shape validation.
The selected family and manifest registries remain the authorities.

```text
Experiment author [external entity]
  -- bounded design --> Authoring validation and materialization [process]
Authoring validation and materialization [process]
  -- typed criteria and commitments --> Authoring artifact [store]
Family and manifest owners [external entities]
  -- pinned declarations --> Family and manifest artifacts [stores]
Authoring artifact [store]
  -- typed treatments --> Owner admission and whole-scenario validation [process]
Family and manifest artifacts [stores]
  -- exact domains and defaults --> Owner admission and whole-scenario validation [process]
Owner admission and whole-scenario validation [process]
  -- complete admitted intent --> Sealed trial plan [store]
Run producer [external entity]
  -- realized selection descriptors --> Archival run [store]
Sealed trial plan and archival run [stores]
  -- exact commitments and source joins --> Archive validation [process]
```

The owner boundary prevents arbitrary document writes and cross-owner configuration.
The seal boundary detects content changes.
The archive boundary rejects missing or substituted selections.
Contract tests exercise those checks with changed source joins and valid-looking substitutions.
Compiler support must separately test owner resolution and complete scenario admission.

Portable records preserve ACT-620 descriptor and content commitments through existing participant configuration records.
Secret bindings retain opaque `SecretReferenceId` values.
Selections contain no secret resolver or private locator field.
The change adds no network access, shell execution, endpoint, authentication rule, or storage service.
Safe loader diagnostics exclude input values and owner exception messages.
Recorded intent and matching commitments do not prove runtime execution.

## Policy and supporting artifacts

The published authoring, study, run, and admitted-plan schemas own the new shapes.
Any embedding schema receives the same shared definitions.
Publication records retain schema hashes and change summaries.
The existing schema bundle, conformance registry, and repository policy tools enforce parity.
Source-bound research captures hold fresh observations for the delivered implementation.
They retain protocol and corpus pins without changing historical evidence.
These retained controls do not establish typed factorial compiler support.
Runtime mapping evidence also uses separate captures for each source identity.
Its existing publisher keeps the original bundle and earlier captures unchanged.
No new workflow gate or infrastructure policy is required.
The contract models provide the architecture as code.
No deployment diagram changes because no deployment component changes.
The data flow above and ADR-084 lifecycle cover the affected components.
No new ADR is required because the authority boundaries remain unchanged.

## References and document review

- [Pydantic documentation](https://docs.pydantic.dev/latest/concepts/unions/), version 2.12, “Discriminated unions”.
  The shared discriminator preserves typed outcome identity.
- [NIST SP 800-160 Volume 1 Revision 1](https://csrc.nist.gov/pubs/sp/800/160/v1/r1/final), “System Security Design”.
  Explicit boundaries connect ownership threats to controls and verification.
- [ASD-STE100 Issue 9](https://www.asd-ste100.org/assets/files/ASD-STE100_ISSUE9.pdf), sections 1, 5, 6, and 8.
  The review checks approved meanings, consistent technical names, sentence length, paragraph length, and document purpose.

This document describes the design.
The issue plan contains implementation tasks and verification commands.
