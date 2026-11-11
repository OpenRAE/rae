# One runtime owner for the interaction lifetime

Date: 2026-10-27. Contract: issue #1660.
This note defines design rules, not proof that the work is complete.
The downstream LilRAE failure is supplied context.
This review does not prove native backend interoperability.

## One owner

[ADR-104 section 11](adrs/adr-104-runtime-control-plane-architecture.md) replaces the two independent controllers.
Use `RuntimeControlPlane` as the lifetime owner.
Reuse its claim, operation ledger, state writer, audit, recovery, and commit rules.
Move manager lifecycle work under that owner.
A public facade may delegate to it.
The facade must not hold another snapshot, claim, scheduler, or backend call path.
Do not nest controllers or suppress their ownership checks.
Do not add a third controller class.

Keep the existing phase order and checks.
Preserve preparation, augmentation, time setup, participant binding, and ordered teardown.
Reuse these modules:

- `manager.py`, `manager_destroy.py`, and `manager_augmentation.py`.
- `participant_execution_control.py` and the `participant_scheduler*` modules.
- `time_control.py` and `apply_failure.py`.

Each phase starts from its committed predecessor.
Keep completed phase records when a later phase fails.
An apply is not one atomic external transaction.
Release the short state permit while backend work runs.
Keep the separate effect reservation until release is proved.
Never overwrite newer state with a cached manager snapshot.

The user's clarification makes the existing failure rules authoritative.
Use `specs/sdl/execution-recovery.md` and supervision sections S5–S6.
Legacy unconditional rollback is not an alternative policy.
Deletion after a failed stop must follow those same rules.
Refuse unsupported authored recovery choices before effects.
Keep exclusion when effects or cessation are unknown.
Compensation and cleanup need their existing separate admission and proof.

## Preserve the other owners

The runtime is trusted host code.
SDL meaning stays in `raes`.
Pure compile and plan work stays in the public `raes_processor` APIs.
Backends own native effects, readiness, credentials, and containment under ADR-036/115.
`RuntimeTarget` is a binding, not a controller.

Keep participant acting control, workflows, trial placement, and apparatus delivery distinct.
ADR-102/108/113 and the [trial ownership note](issue-1624-trial-orchestration-ownership-preflight.md) define those boundaries.
One runtime per interaction does not mean one process-global singleton.
Keep target and run scopes immutable.
Keep experiment, trial, attempt, and operation identities distinct.
Multiple trials do not permit retargeting an open store.
A second controller must not continue work on the same resources.
Required cleanup and admitted reuse remain gates between scopes.

## Fresh evaluation

The same owner must evaluate evidence collected after apply.
Use its current committed snapshot and original run context.
Keep the existing `EvaluationPlan`, `Evaluator.start()`, result, snapshot, and receipt contracts.
Preserve run and instantiation bindings for generated values.
Do not resample those values.
Do not reapply provisioning or restart unrelated work.

Define refresh at the public planner seam.
Replanning unchanged declarations can produce only `UNCHANGED` operations.
The stub skips those operations.
Another submission alone does not prove fresh evaluation.
Do not fabricate creates, clear the snapshot, or edit an authorized phase silently.
Consumers must not need private phase plans.
Any new plan field needs normal contract publication and admission.

A fresh request needs a fresh operation identity.
An exact retry returns the retained receipt without another call.
Keep exact plan-digest authorization and base-snapshot checks.
Preserve materialization source, augmentation authority, observation demand, execution policy, and compiler context.
Expose results from checked, committed state.
Raw backend dictionaries cannot replace admitted evidence.

Inventory refresh is a separate read-only provisioning operation.
It is not evaluation, evidence capture, recovery observation, or resource rewrite authority.
Fresh evaluation does not resolve an indeterminate effect.
Use the existing linked resolution path.

## Select needed components

Reuse `RuntimeTargetComponents`, `RuntimeTargetDescriptor`, `BackendRegistry`, and `BackendManifest`.
Reuse typed control-plane, profile, store, and provider settings.
Select needs from the compiled model and plans.
Use existing factory settings, not backend-name switches or a new plugin registry.
Consider the whole interaction, including later evaluation.
Do not construct a service merely to avoid calling it.
The provisioner remains required.
Evaluator, orchestrator, participant, time, observation, and recovery services remain optional.

Target shape checks require exact manifest and component agreement.
Do not remove declarations to hide missing support.
Missing required support must fail before effects.
Keep crossing, information-state, and final-sink checks when components are omitted.
Scenario needs and an operating profile are separate choices.

Keep package exports lazy.
Local embedding must not start unused HTTP, database, distributed, clock, or participant services.
Keep `anyio` in core and the existing database and Temporal dependencies optional.
Do not add a mandatory service, loader, discovery step, or environment switch.
Preserve public methods and constructor options.
Record any intended break through ADR-075 and the deprecation ledger.

## Existing checks and helpers

Paths below are relative to `implementations/python/packages/`.
Unqualified modules are in `raes_runtime`.

| Boundary | Required controls |
| --- | --- |
| SDL and values | Reuse the parser, compiler, `PlanScope`, environment, and generated-value checks. Keep classification, redaction, and literal/value-source rules. Environment names must be nonempty and exclude `=`. Keep operator secrets outside SDL. |
| Settings and target | Reuse `ControlPlaneConfiguration`, `OperationSupervisionConfiguration`, and target validators. Reject unknown options, bad provider signatures, scope mismatch, and missing resolvers. Reject explicit store plus initial snapshot. Bounds must remain strict positive integers. Preserve profile claims and nonclaims. |
| HTTP and identity | Reuse strict security defaults, sealed routes, request bounds, and the call executor. Keep bearer and trusted-proxy checks. Bind actors, roles, and subjects to their target and scope. Propagate identity through convenience methods. Do not expose the runtime, store, or privileged tokens to participants. |
| Plan input | Keep manager provenance checks and `RuntimePlanAuthorizationMixin`. Bound inputs before hashing or copying. Isolate backend arguments. Recheck admission at dispatch. Keep preparation, augmentation, materialization, account, artifact, and observation checks. Registration does not bypass another check. |
| Backend output | Reuse `_validated_backend_result()` and snapshot, effect, evaluation, workflow, proposition, and participant validators. Check history, time, information-state, crossing, and final-sink rules before commit. Check late and partial results too. Native success or valid JSON alone is insufficient. |
| Ownership and calls | Reuse `RuntimeResourceClaim`, `RuntimeLifecycleMixin`, `RuntimeMutationAuthority`, and `LocalExecutionAdapter`. Keep one writer and snapshot. Keep bounded work and control capacity distinct. Keep fork rejection and drain order. A timeout, disconnect, cancellation, or failed close does not prove cessation. Retain deployment fences across processes and hosts. |
| Store | Reuse atomic commits, revision CAS, codecs, recovery, and authoritative error readback. Claim before dispatch. Commit the checked snapshot, terminal record, and actor audit together. Poison readiness when readback cannot prove the cut. Do not add a shadow state store or automatic replay. |
| Secrets | Reuse value-free account projections, exact live retry proof, and HMAC command commitments. Restart does not recreate invocation permission. Keep secrets out of audit, engine history, logs, URLs, argv, and error text. Keep typed host settings and separate credentials. |
| Files | Keep private modes, safe paths, link/type/owner checks, and bounded protected archives. Keep owner leases and offline maintenance. Do not raw-open or chmod live SQLite sidecars. Keep configured TLS. Selecting a runtime does not authorize deployment or transfer to a new host. |
| Errors and evidence | Reuse `Diagnostic`, portable diagnostic payloads, shared HTTP handlers, and `AuditEvent`. Keep stable value-free errors. Do not disclose raw exceptions, SQL, paths, request bodies, or credentials. Preserve the primary response if audit fails. Audit, telemetry, observations, and experiment records remain distinct. Hashes alone do not prove authenticity. |

## Verification and repository rules

Reuse stub targets, `runtime_plan_fixtures.py`, and existing manager/control-plane tests.
Keep ownership, supervision, state, privacy, import, inventory, scope, and profile tests.
The decisive test uses one owner to apply, read later evidence, and tear down.
It must show a changed committed evaluation.
Unrelated service call counts must stay unchanged.
A same-key retry must not call the backend again.

Cover missing components, minimal imports, stale snapshots, wrong run or actor, and invalid results.
Cover blocked callbacks, failed close, and uncertain effects through public APIs.
The absence of an ownership exception alone is not enough.
Update active consumer guidance and conformance examples.
Keep historical captures and assessments as history.

Use repo policy before and after edits.
Keep ADR-036 import boundaries, the 500-line source cap, and authority paths.
Run only targeted local checks.
Full, integration, fuzz, and completion suites belong in CI/CD.
This issue has no requirement UID.
Do not invent one to satisfy a gate.
Keep ADR-059 amendment records and content pins in sync.
Published schema changes need the ADR-009/061 ledger and generator parity.
Release-please owns versions and the changelog.

## Non-goals

Do not change SDL meaning or native backend realization.
Do not add another controller, schema family, scheduler, workflow engine, or store.
Do not add a generic policy language or plugin framework.
Do not add cross-target, cross-run, or tenant multiplexing.
Do not claim coordinated profiles or exactly-once effects.
Do not expand participant access or deploy a new service.
Do not claim native interoperability from a stub test.
