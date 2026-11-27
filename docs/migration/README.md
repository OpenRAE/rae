# Select a migration task

Select your source and target first.
Then edit the artifact or replace its runtime owner.
These routes apply to Python RAES 11.0.2.
Keep contract, semantic, profile, and store revisions separate.
None is a package version.
No universal migration command combines them.

## Convert an authored file

Retain original source bytes, sidecars, content pins, and the matching reader.
The supported helpers return new artifacts.
They do not overwrite files or execute a backend.
Keep successful output and its report together.
Use new content identities.

| Your source | Task and target |
| --- | --- |
| The source has removed classification fields. | [Move classifications](external-classifications.md) to native SDL plus `external-concept-bindings/v1`. |
| The source uses old implicit policy. | [Adopt progressive semantics](progressive-semantics.md) through an explicit `raes-progressive-semantics/v1` context. |
| The source uses `Agent.entity` or `Objective.agent/entity`. | [Migrate identity and assignment](participant-identity.md) to affiliations, owner, and assigned participant. |
| The source has fixed-coordinate mixed control. | [Convert to a finite script](mixed-control-finite-script-conversion.md) under `mixed-control-policy-occurrence/rev1`. |
| A reference fails eligibility checks. | [Rewrite intended references](reference-eligibility.md) using the current purpose catalogue. |
| The source selects autonomous execution v1. | [Opt into v2 activity](autonomous-execution-v2.md), if that semantic change is intended. V1 remains supported. |
| The source selects autonomous execution v2. | [Opt into v3 resource budgets](autonomous-execution-v3.md), if the installed pool and measurement owners support them. |
| The source has separate per-role behavior specifications. | [Combine tool profiles](participant-tool-profiles.md) when their nonbinding fields match. |

For classifications followed by progressive adoption, use the exact preceding output bytes for each step.
A stale digest, missing decision, or ambiguous subject stops conversion.
Correct that input through its owner.
Do not weaken validation to force a result.
Then [validate and inspect the new scenario](../public/sdl/validate-compile-plan.md).
No native cleanup is needed for a source-only conversion.

## Coordinate runtime and backend adoption

Use [revised-control migration](revised-control.md) to coordinate producers, readers, and installed owners.
It preserves historical meanings and exact content pins.
It does not change meanings inside a live episode.

| Task | Required boundary |
| --- | --- |
| [Adopt governed participant crossings](participant-information-flow-control.md) | Select legacy, opt-in, or required paths. Rollback changes after governed writes. |
| [Declare participant execution controls](participant-execution-control.md) | Match action, target, and implementation offers. Supply `participant-shared-time/v1` evidence when required. |
| [Retain one runtime owner](runtime-lifetime.md) | Keep scoped runs. Use local schema 12 or PostgreSQL schema 5. |
| [Update an opacity harness](participant-opacity-observed-evidence.md) | Supply fresh independent readback and exact probe points. Compare reports with measured evidence. |
| [Replace removed concrete backends](concrete-backends.md) | Start from RAES 7.0.0. Use an external distribution for current native work. |

Stop affected admission first.
Reconcile pending work through its original owner before changing a live binding.
Preserve uncertain effects, receipts, budgets, store history, and original run identity.
A restart, new episode, or new retry key does not authorize another native effect.
The native owner must establish cessation and cleanup before resource reuse.

External deployment remains unverified here.
It needs the exact release pairing and installed services.
It also needs authorized commands, readback, and cleanup evidence.

## Look up an adoption contract

These references give compatibility rules.
They do not install providers or supply universal converters.

- [Reusable mixed control](reusable-mixed-control.md): Keep fixed-coordinate/v1 history separate from explicit rev1 forms and occurrence v2.
- [Control applicability and evaluation](control-applicability-and-evaluation.md): Negotiate selection, evaluation, and provider v2 separately.
- [IFC profile variability](ifc-profile-variability.md): Keep exact profile identities and each owner's obligations. Retain original meaning.
- [Mixed-backend execution](mixed-backend-execution.md): Use explicit service bindings. Check stage reports and settlement rules.
- [Participant tool support](participant-tool-support.md): Check processor/backend declarations, exact semantic support, and finite capacities.
- [Required capture admission](required-capture-admission.md): Match atomic offers. Check evidence content before claiming satisfaction.

After admission, use the [runtime task guides](../public/guides/control-plane.md)
and [experiment records procedure](../public/guides/experiment-records.md).
Read [participant-control boundaries](../public/participant-control-explanation.md) for the separate authority and evidence planes.

## Prepare for the Go cutover

The [Go cutover migration](go-cutover.md) records the deprecation of the `raes` Python distribution.
It names the Go replacement surfaces and their publishers.
The Python import API has no Python replacement.

## Read retained historical records

The [RAES identity cutover record](raes-rename.md) retains the 1.1.0-to-2.0.0 boundary and later naming history.
Its retirement plans do not confirm a published package.
Use the current guides above for current commands.

The [classification example introduction](classification-examples/README.md) identifies three retained JSON artifacts.
The example labels are not an authoritative CWE catalogue.
The historical inventory keeps exact source commits and digests.
It also retains removed declarations and associations.
Do not rewrite it to match a new artifact.

## Historical repository moves

The following paths record the completed layout change:

- root `schemas/` to `contracts/schemas/`
- root `conformance/fixtures` and `conformance/profiles` to `contracts/`
- `docs/adrs/` to `docs/decisions/adrs/`
- `docs/sdl/` to `docs/explain/sdl/`
- Python implementation code and tests to `implementations/python/`

These are historical moves, not instructions to create another directory tree.
[ADR-010](../decisions/adrs/adr-010-repository-realignment-order-and-compatibility-policy.md)
records the original reconciliation order.
Current contracts and code retain their existing authority.
