# Migrate revised control producers and readers

Use this checklist with the [current support reference](../explain/reference/revised-control-semantics.md).
There is no global control-v2 switch or universal archive converter.
Each selected path must support its own semantics, contracts, profiles, and installed owners.

## Select the authoring meaning

1. Retain the original SDL and its content digest.
2. Decide whether the control declaration remains legacy, becomes a finite script, or becomes a reusable policy.
3. For a finite script, use the existing [conversion helper](mixed-control-finite-script-conversion.md).
4. Resolve every reported ambiguity before publishing the converted artifact.
5. For reusable control, record the explicit author decision permitting repeated applications.
6. Supply fresh occurrence identities, revisions, order, and evidence for each new application.

The rev1 declaration requires `semantics: mixed-control-policy-occurrence/rev1` and an explicit `form`.
Removing fixed coordinates alone is not a valid conversion.
A reusable edge authorizes no automatic execution.
An exact retry retrieves the retained receipt; it does not request another cycle.
The [adoption contract](reusable-mixed-control.md) governs source-preserving conversion and historical meaning.

## Coordinate contracts and interfaces

| Change | Producer and installation action | Reader and compatibility action |
| --- | --- | --- |
| API-409 occurrences | Select rev1 semantics and `participant-control-occurrence-v2`; install the compiled policy and live-cut resolver | Route v1/v2 independently. Retain each episode's original policy and admissions. |
| API-424 evaluation | Negotiate selection/evaluation v2 content hashes and `ParticipantControlProviderV2.resolve_stage` | Validate complete coverage, exact predecessor inputs, required support, state authorization, and commit receipt. Keep v1 history interpretation. |
| Inject execution | Construct the closed trigger request with exact plan, binding, placement, input, occurrence, key, and expected head | Read occurrence, per-binding outcome, and successful correlation independently. Never upgrade a queued receipt to an effect. |
| Participant delivery | Install the matching compiled delivery model and trusted projection/crossing owners | Join the exact world result, participant, episode, audience, binding, and accepted control occurrence when required. |
| Mixed execution | Install exact mixed binding/service pins through `MixedRuntimeBinding.backend_installations` | Authenticate stage producers; validate committed clocks, mappings, reports, and owner readback. Historical callback success is not stage evidence. |
| Opacity harness | Supply `reported_observation()`, fresh `backend_readback()` and pinned probe points | Compare reported and measured transcripts. Missing or disagreeing evidence cannot establish a native claim. |

Use the existing [schema publication manifest](../../contracts/schema-publication-manifest.json) for exact contract content identities.
Do not infer support from a method name, equal revision strings, or a manifest declaration alone.
An older consumer must refuse an unsupported lineage or content pin.
It must preserve the original bytes.

The detailed boundaries remain in these guides:

- [Control applicability and evaluation](control-applicability-and-evaluation.md): complete apparatus, coverage, mandatory inputs, optional loss, and effects.
- [External inject adoption](../explain/sdl/external-inject-compatibility.md): occurrence claims, original authoring, and consumer joins.
- [External inject operation](../public/guides/external-injects.md): executing provider installation, delivery, scheduled placement, and capture.
- [Mixed backend execution](mixed-backend-execution.md): independent service roles and stage settlement.
- [Opacity observed evidence](participant-opacity-observed-evidence.md): backend-harness interface changes and bounded claims.

## Select profiles and recovery choices

1. Pin semantic, profile, protocol, schema-content, implementation, and store-reader identities separately.
2. Check every required obligation against the selected implementation's effective support.
3. Keep required dependency inputs even when their content is advisory.
4. Keep optional unavailability distinct from missing required coverage.
5. Install each selected effect owner before admitting required effects.
6. Check the complete arrangement against the support table.

P0, P1, and P2 retain their existing process, durability, and transport guarantees.
No new P3, multi-owner, or exactly-once-effects guarantee follows from these contracts.
The inject guide records the applicable local and PostgreSQL ledger versions.
The applicability guide records v2 evaluation reader admission.
These internal versions do not replace wire or semantic pins.

Authored `execution_policy` preserves complete scoped choices through compilation and planning.
Omission grants no new repetition permission.
The [execution and recovery guide](../explain/reference/execution-recovery-migration.md) defines bounded retry and unsupported continuation choices.
Transport retries, durable queues, and backend idempotency cannot authorize another scenario effect.

## Preserve active work and history

1. Quiesce admission before replacing a live policy or apparatus interpretation.
2. Finish or reconcile pending work through its existing owner and authorization path.
3. Preserve uncertain effects, claims, budgets, and the original admitted plan.
4. Admit a new episode or apparatus only through its existing lifecycle.
5. Read each archived record with its original discriminator and pinned context.
6. Report unsupported or unverifiable reconstruction when required historical context is missing.

Restart does not grant redispatch. A new identifier does not reset a surviving causal budget.
Migration evidence appends facts; it does not rewrite past outcomes or fabricate cessation.
The [executable examples](../examples/revised-control.md) check repeated control, world effects, refusals, and the supported mixed arrangements.
They verify RAE behavior through test providers. Downstream native qualification remains separate.
