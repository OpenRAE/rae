# Issue 2046: Validate the complete plan once for batch instantiation

Date: 2026-11-21.
Source revision: `253cd3b4bb7acaca647724292ee4f2a3b89b4152`.
The supplied issue is the delivery contract. This work has no requirement UID.
This note records design guardrails, not an implementation plan or a delivered API.

## Decision and ownership

Add a supported batch instantiation boundary in `raes_processor.trial_realization`.
Bind one complete validated plan and its exact expanded family for that batch.
Select entries by `plan_entry_id` from the owned plan, never from detached entry objects.
Keep the existing single-entry boundary safe for independently supplied models.
Share the entry-selection and provenance logic between both paths.
Do not introduce a public validation-bypass argument.

[ADR-084](adrs/adr-084-scenario-variation-and-deterministic-trial-realization.md)
already assigns these responsibilities.
[ADR-121](adrs/adr-121-strict-package-layers.md) fixes the dependency direction.
No new ADR, portable root, schema, admission profile, or exception family is needed.
The batch boundary belongs above neutral contracts and SDL selection.
It is not a runtime coordinator or an authorization credential.

The public seam takes a plan, family, and entry selection for one batch.
Keep entry selection independent of worker count, deployment configuration, and transport.
A subset must retain each entry's existing identity and the complete plan digest.
Do not create or reseal a smaller plan to represent a chunk.
Use `admitted_trial_plan.canonical_entry_order()` when offering a whole-plan traversal.
It preserves recorded allocation order when present; sorting coordinates alone does not.
Document order, duplicate-request behavior, result ownership, and failure behavior for explicit entry selections.

## Integrity and ownership invariants

**Complete validation precedes consumption.**
Use `revalidate_admitted_trial_plan()` on caller-held plan state before exposing a result.
Retain validation of every entry, including entries outside a requested subset.
`AdmittedTrialPlanModel` owns map-key agreement, identity uniqueness, cleanup joins, profile agreement, allocation reconstruction, treatment consistency, admission count, and complete-plan integrity.
`AdmittedTrialEntryModel` owns resolved selections, entry provenance, configuration joins, and entry integrity.
Neither an entry digest nor a successful earlier parse replaces these checks.

**Validation and use refer to the same owned state.**
`ContractModel` has `extra="forbid"`; it does not freeze models or validate assignment.
Plans, entries, families, and their nested collections can change after construction.
A shallow copy, a frozen outer dataclass, or a mapping proxy alone does not protect nested values.
Capture independent state, validate that state, then retain exclusive ownership throughout consumption.
Do not expose mutable plan, family, entry, or provenance aliases through the public interface or returned scenarios.
Mutation of one returned scenario must not affect later results.

Caller changes after capture cannot alter the batch's snapshot.
Changed input supplied to a new batch must undergo full validation again.
A retained batch must not accept replacement plans, families, or entry objects alongside its entry IDs.
If iteration is lazy, state when capture and validation occur.
No result can precede complete-plan validation.
Caller mutation during capture is not a supported synchronization mechanism.
Do not claim protection against hostile code inspecting private Python state or arbitrary concurrent writes.

**Family identity and semantics remain SDL-owned.**
Require an admitted `ExpandedScenario`, its exact name and `canonical_sdl_digest()`, and matching `trial_parallelism`.
Compute identity from the same owned family used for selection.
Preserve field presence, aliases, expansion provenance, and omitted-default mutation rejection.
The canonical digest uses `exclude_unset=True`; a matching digest alone cannot certify changed omitted defaults.
`select_scenario_family()` retains its public selection checks and whole-scenario semantic admission for every result.
`ExpandedScenarioBindingTargetResolver.validate_selection()` retains typed treatment target and family checks.
Do not set a semantic-admission flag manually or rebuild an expanded family as an authored root.

**Lineage has one authority.**
Reuse `TrialInstantiationProvenance`, coordinate provenance, and admitted selection and binding records.
Keep plan ID/digest, entry ID/digest, preallocated `run_id`, family identity, and record digests unchanged.
Reuse canonical helpers; do not substitute ordinary JSON hashing or list positions for canonical identity.
A self-consistent seal proves content integrity, not trust in original experiment intent.
`trial_compiler.readmit_admitted_trial_plan()` remains the source-aware replay boundary when independently trusted compilation inputs are required.
Batch preparation does not replace that boundary or silently add recompilation to each entry.

## Cross-cutting layers and canonical incumbents

Package paths below start at `implementations/python/packages/`.

| Layer | Incumbent and required fit |
| --- | --- |
| External ingress | `raes_contracts/contracts/admitted_trial_plan_ingress.py` owns parsing and reconstruction. Preserve `parse_admitted_trial_plan_json()` and its 32 MiB limit. `json_ingress.py` rejects duplicate members, non-finite numbers, invalid roots, and excessive decoder nesting. Do not route external bytes through a less strict batch parser. The byte limit is not a general bound on caller-held models. |
| Closed contract shapes | Reuse `ContractModel`, admitted-plan components, existing strict field types, validators, and canonical serializers. Keep `contracts/schemas/plans/admitted-trial-plan-v1.json` and its publication record unchanged. An internal ownership boundary must not change portable list/map shapes, omission rules, profiles, or digest bytes. |
| SDL validation and configuration | Reuse `raes/selected_scenario.py`, `family_admission.py`, `canonical.py`, and `instantiate.py`. These retain selection domains, structural conflicts, references, field presence, and whole-scenario semantics. `runtime_environment.py`, `runtime_generated_value.py`, and `runtime_configuration.py` retain environment shape and sensitivity checks through that admission. Do not flatten typed values into arbitrary environment dictionaries or weaken literal/`value_from` exclusivity. |
| Secret and runtime-fact handling | Instantiation must not resolve secrets, fetch facts, read ambient credentials, or normalize participant configurations again. Retain sealed configuration records. Runtime resolution remains in `raes_runtime/runtime_fact_binding_policy.py` and `runtime_fact_dispatch.py`, with their scope, freshness, provenance, and sink checks. A generated value cannot acquire `operator_secret` classification through batching. |
| Authentication and authorization | This pure in-process API adds no transport or principal surface. Plan seals and batch ownership confer no runtime authority. Existing execution continues through `control_plane_admission.py`, `control_plane_plan_authorization.py`, and operation context. HTTP callers retain `control_plane_api/_auth.py`, target/run scopes, route authority, limits, and denial audit. No new endpoint or bearer token is needed. |
| Safe errors and observability | Preserve `AdmittedTrialPlanIngressError`, `InvalidInputError`, `NotFoundError`, and SDL selection errors. Keep existing single-entry failure categories and validation-before-lookup behavior. Follow ADR-116 and `docs/develop/exceptions-and-logging.md`. Chain expected translations without copying validator input or exception text into messages. Reuse `operational_logging.get_logger()` if a log is necessary; libraries do not configure logging. HTTP `_responses.py` and existing 422/500 handlers retain redacted envelopes. No payload dumps, per-entry duplicate failure logs, or new timing service. |
| Runtime and persistence | `trial_scheduler.py` owns canonical dispatch and parallelism bounds; `BatchSchedule` is not proof of current plan integrity. `runtime_experiment.py` owns runtime composition. `ControlPlaneStore` and the existing trial ledger retain attempts, authorization, evidence, and durable state. Batch preparation creates no ledger record, queue, archive, database, or persistence format. A process-local snapshot is not a restart token. |
| Host and OS | The batch boundary needs no subprocess, shell, listener, filesystem acquisition, environment variable, or credential loader. Keep data in process. Do not put source content or resolved secrets in argv, logs, temporary files, or external services. Concrete backend execution and containment remain downstream. |
| Package and repository policy | `tools/policy/adr_policy.yaml` already allows runtime imports of public processor trial modules. Keep neutral contracts independent of processor and SDL imports. Retain ADR-117 structural checks, `.ground-control.yaml`, `.gc/plan-rules.md`, authority boundaries, and canonical nox lanes. Schema evolution, if separately needed, remains governed by ADR-061 and the schema publication ledger. |

## Work bound, reuse, and extension seam

The batch must perform a bounded number of complete-plan reconstructions, dumps, and digest traversals, independent of consumed entry count.
For validation cost `V(plan)` and entry work `I(entry, family)`, the intended bound is:

```text
V(plan) + sum(I(entry, family) for each requested entry)
```

This is not a claim that all validation or realization is linear.
Canonical sorting and allocation reconstruction retain their existing costs.
Whole-scenario selection, family hashing within typed treatment checks, and actual realization remain entry work.
Do not move a whole-plan copy, comparison, digest, or source scan inside the entry loop.
Do not retain every realized scenario merely to keep the validated plan alive.
Preserve the existing ingress and compiler limits without confusing their scopes.
The compiler's default `max_coordinates=10_000` and runtime's 4,096-entry capacity are not interchangeable batch-instantiation limits.
If results stream, document partial progress, error timing, and snapshot lifetime.
Instantiation has no execution effects; a result is not permission to start a trial.

The extension seam is entry selection over one owned plan/family pair.
It supports subsets and bounded result consumption without a global cache or scheduler dependency.
Do not add a general validation-session framework for this issue.
`raes/_incremental_reuse.py::ValidationSession` reuses SDL pass results under separate ownership preconditions; it does not certify admitted-plan integrity.
`raes_contracts/immutable_history.py` owns append-only histories, not trial plans.
Do not import their private helpers or reuse history commitments as plan digests.
Use standard copying and encapsulation before introducing another immutable collection or parallel contract model.

The current full realizer reconstructs once directly and again through the single-entry instantiator.
Its typed-authoring path also scans the complete plan in `trial_compiler/sources.py::validate_authoring_selections()`.
`RuntimeExperiment` invokes full realization for every scheduled entry.
Wrapping that loop around a new instantiation API does not remove these other costs automatically.
Any reuse inside full realization must retain experiment/task/capture pins, source joins, apparatus and envelope checks, and planning scope.
Mixed-composition realization still fails closed.
Do not claim an optimized runtime batch unless that exact path is separately demonstrated.

## Runtime trial handoff

On 2026-11-23 the user added the runtime trial handoff to this issue.
`TrialUnitRequest` rebuilt the full plan when it was made.
It rebuilt the plan again at each `replace()` check.
Each trial phase also hashed the full plan into its operation commitment.
So a batch of N entries did full-plan work N times.

Check the full plan once at each trust boundary.
After that, share one read-only plan and check only entry values.

- `raes_contracts.trial_unit.AdmittedTrialPlanView` owns one rebuilt plan.
  Each read returns a copy. No caller can change the plan.
- `TrialUnitRequest.plan` is the view. A request made from a plan model makes its own view.
- `RuntimeExperiment` makes one view for the batch. Each replacement child plan gets its own view.
- An operation commitment holds the view as its `plan_id` and `plan_digest`.
  The view checked that seal over the full plan.
- Commitment digests for trial requests change.
  An operation that was recorded before this change does not match after it.

A remote worker still checks the full plan once, because it runs in a separate process.

## Acceptance evidence and boundaries

Use structural work counts rather than deployment timing thresholds.
Count complete-plan work across multiple batch sizes and subset consumption.
Keep scenario size controlled, and distinguish plan reconstruction from legitimate per-entry semantic admission.
Assert equivalent instantiated content and full lineage against the existing single-entry path.
Include an invalid unrequested entry, nested selection mutation, stale plan/entry seals, map-key mismatch, unknown ID, wrong family, and changed parallelism.
Retain rejection of correctly resealed but semantically inconsistent treatment targets.
Exercise input and output mutation between results, lazy capture timing if applicable, and independent batches with colliding IDs.
No state may cross batches merely because plan IDs or declared digests match.

Reuse fixtures and focused cases in `test_sce_002_trial_realization.py` and `test_sce_002_admitted_trial_plan.py`.
Structural and typed-treatment regressions already live in `test_issue_1625_structural_variation.py` and `test_issue_1666_factorial_admission.py`.
Use targeted mutation testing for removed integrity, identity, membership, and ownership checks during implementation.
Run explicit affected cases locally; full suites and repository-wide verification belong in CI.
The documentation style guide owns changed-path prose checks.

Non-goals are changing ingress, published schemas, digest profiles, scientific identities, compiler selection policy, retry semantics, scheduling, parallel execution, or backend behavior.
No active experiment, deployment, external caller repository, private reproduction record, or private timing evidence is changed by this issue.
Avoid digest-keyed global caches, caller-controlled validated flags, detached-entry fast paths, duplicate validators, and alternate exception hierarchies.
