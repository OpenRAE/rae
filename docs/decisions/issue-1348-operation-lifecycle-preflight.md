# Issue 1348 Operation Lifecycle, Supervision, and Recovery Preflight

Date: 2026-09-22

Status: architecture preflight, not the lifecycle decision or an implementation
plan. Scope: supplied issue #1348 and
[API-404](../requirements/API-404/requirement.md). This note identifies
constraints and unresolved decisions for that work. It changes no runtime
guarantee, requirement, schema, or accepted ADR. The historical
`docs/research/runtime-refactor/` references in
the issue are absent from this checkout; no claims about their contents or the
external ecosystem issue are made here.

## Findings that the decision must address

- `raes_runtime/control_plane_mutation.py` releases its condition mutex during
  external work but retains the logical mutation permit. The HTTP executor in
  `control_plane_api/_offload.py` shields the worker and waits for settlement on
  cancellation. Both executor close and `RuntimeLifecycleMixin.close()` drain
  without a deadline. Responsive bookkeeping is not bounded execution.
- `cancel_workflow()` acquires that same mutation authority and updates the
  workflow result/history. It cannot interrupt the backend holding the permit.
  A successful cancellation *operation* and a cancelled *workflow* already have
  different states; neither establishes cessation of external work.
- `backend_calls._invoke_backend_apply()` converts exceptions into failed
  `ApplyResult`s with the trusted predecessor. Execution paths then classify
  `success=false` as `FAILED`. This protects portable state, but an exception or
  rejected result after invocation does not prove absence of external effects.
  Reconcile this gap with ASR-532 rather than weakening result validation.
- Startup recovery invokes the optional observer under the mutation authority.
  An observer, admission extension, or other backend callback can also stall.
  Bounding only the ordinary apply call leaves the lifecycle
  problem unsolved. Store admission/lease waits and commit settlement need
  distinct treatment from external-effect interruption.
- `control_plane_workflows.maybe_apply_compensation()` derives compensation
  state and history; it does not invoke a compensating backend workflow.
  Those records alone cannot prove external rollback or cleanup. Any concrete
  compensation work also needs supervision under the existing semantic owner.
- The recovery protocol has only absent, applied, and indeterminate
  classifications; applied results require a validated snapshot. It does not
  establish a general checkpoint/resume or known-partial-effect protocol.
  `ACCEPT_CURRENT_SNAPSHOT` resolution is administrative acceptance, not proof
  of backend quiescence, rollback, or permission to repeat an effect.

Paths naming Python modules below are relative to
`implementations/python/packages/`.

## Decision boundaries

**One runtime, distinct authorities.** RAE remains the shared runtime driving
backends. Authors govern required semantics; RAE validates and admits the
requirements, owns operation supervision and portable state; backends own
concrete realization and contextual willingness. Embedders own process and
deployment lifecycle. Capability declaration, installed component shape,
per-request willingness, and observed satisfaction are separate facts.
Unsupported or refused required semantics must fail admission without weaker
fallback. Refusal after invocation must account for effects already possible.

**Preserve the existing operation authority.** Build on
[ADR-104](adrs/adr-104-runtime-control-plane-architecture.md) and its
[FM3 operation model](../../specs/formal/runtime-control-plane/README.md),
`raes_contracts/operation_lifecycle.py`, `OperationAdmissionContext`, and the
receipt/status carriers. Denial is pre-claim audit, not another persisted state;
accepted acknowledgement is not completion. Preserve write-ahead intent,
immutable actor/target/run/request binding, one terminal outcome, and atomic
snapshot/terminal-record/audit publication with revision CAS. External effects
are outside that transaction; no store transaction spans backend work.

The incumbent persisted states are `ACCEPTED`, `RUNNING`, `SUCCEEDED`, `FAILED`,
`CANCELLED`, and `INDETERMINATE`; the FM3 transition matrix and
`is_operation_transition_allowed()` are their authorities. A requested stop,
expired deadline, or running compensation is not a new operation state by
default. Keep operation outcome, workflow outcome, cleanup outcome, and runtime
readiness distinct. P0 preserves these rules only while its process lives;
write-ahead ordering must not be described as P0 crash persistence.

**Separate admission, interruption, and settlement.** The final decision needs
an explicit account of waiting before claim, accepted-before-invocation,
executing, backend return, terminal commit, and restart reconciliation. Stopping
admission prevents new work; cancelling a waiter may prevent invocation;
interrupting executing work requires a backend-supported guarantee. Receipt
delivery, request disconnect, worker cancellation, elapsed deadline, and process
exit prove none of effect absence, rollback, or remote cessation.

A supervision request must remain serviceable while the affected call holds
the permit; simply enqueueing cancellation behind it cannot meet that goal.
Define how a bounded supervision signal reaches the existing operation owner
without becoming a second mutation authority. This includes saturated HTTP
mutation queues, worker capacity, rejection audit, startup observation, and
shutdown admission, not just the core mutex. Preserve authentication and bounded
resources on that path. A supervisor's request needs its own actor provenance;
it must not overwrite the admitted operation's immutable actor or context.
A timeout must not release the permit or store lease and admit overlapping
effects while the old worker can still act. Distinguish inability to commit
stale state (CAS) from inability to produce further external effects. A local
lease does not fence a remote job.
The design must settle cancellation-versus-completion races, late results,
repeated cancellation, shutdown escalation, and unknown commit acknowledgements
without a second terminal transition. Recovery-required readiness and retained
ownership must have an explicit outcome when cessation cannot be established.
An expired commit budget cannot be reported as a failed commit: use existing
readback and durability-poison semantics when the acknowledgement is unknown.
Restart, backup/restore, or administrative resolution cannot discharge an
external effect that may still arrive.

**Separate failure, partial effects, and uncertainty.** A known failure can
include validated partial effects; an unobservable outcome cannot be relabelled
as known failure or cancellation. Failed result admission preserves the trusted
predecessor without claiming the external target is unchanged. The decision
must specify how known partial state, unknown residual effects, compensation
failure, and recovery observation are represented through existing carriers,
and identify any actual carrier gap explicitly. An observed applied effect is
not success unless it satisfies the admitted operation's full requirements.
Retain immutable indeterminate parents, linked authorized resolution, scoped
claims, quarantine, and no automatic replay. Observing absence at one instant
is insufficient when a surviving worker may apply the effect later.

**Authored permission is independent of durability.** Resolve these distinctions
in the final decision, using existing semantic owners:

| Action | Existing authority and constraint |
| --- | --- |
| Transport retry | Actor-scoped idempotency returns the same admitted work; it does not authorize another invocation. Changing a key is not permission to repeat an effect. |
| Workflow retry or compensation | Authored workflow control and compensation govern attempts, triggers, ordering, and history. Durability must not synthesize another retry loop or implicit rollback. |
| Another admitted execution attempt | SCE-007's `ExecutionRetryPolicyModel` governs attempt limits and after-effect posture (`disallow`, `idempotent`, `reset`, `compensate`). A permitted attempt has a distinct `execution_attempt_id` under the same admitted entry/run; required reset or compensation must be established before repeating effects. This does not allocate a new trial. |
| Resumption | Requires authored permission plus an established compatible continuation point, state, time, and effect boundary. A snapshot or durable `RUNNING` record alone is insufficient. Specify refusal when continuity cannot be proved. |
| Termination | Distinguish stopping admission, ending workflow control, participant episode termination, stopping execution, and verified cleanup; each has its own observable outcome. |
| New trial | ADR-068/ADR-084 and admitted trial allocation govern a new execution coordinate and run identity, clean or declared reusable initial state, isolation, and cleanup. It is not a renamed operation retry. |

Use the existing authored policies and their normative defaults; do not infer
additional permission from durability. When a requested guarantee cannot be
established, distinguish pre-effect rejection from post-effect
failure/indeterminacy and any trial-validity consequence.
Existing P1/P2 recovery may end indeterminate without an observer; that remains
different from admitting an operation that explicitly requires provable
recovery or interruption when the backend cannot provide it.

`TrialExecutionAuthorityModel` already carries attempt timeout, cancellation,
and cleanup authority; `AdmittedExecutionControlModel` carries the admitted
controls. Reuse these with `TrialCleanupPlanModel`, `TrialCleanupReceiptModel`,
`require_cleanup_plan_capability()`, and the
[SCE-007 cross-object invariants](../../specs/formal/scenario-variation-trial-realization/cleanup-contracts.md).
They cover required reset boundaries, capability/contract-version agreement,
cleanup evidence, and independent primary/cleanup outcomes. Failed, partial,
unsupported, or unverified cleanup invalidates a clean/reusable-state claim;
it must not be hidden by an operation's terminal receipt. These trial contracts
apply to admitted trial execution, not as a mandatory wrapper for every P0
embedder operation. A missing continuation guarantee remains an explicit gap,
not permission to create a duplicate retry or cleanup schema.

**Keep clocks separate.** Use apparatus monotonic time for local elapsed bounds
and the incumbent UTC timestamp format for durable operational records. Define
queue, execution, observation, commit, and drain budgets separately, including
their start points and expiry consequences; a monotonic deadline cannot be
persisted as a portable restart clock. Authored semantic deadlines retain the
time-model clock/domain/segment authority. Reuse `control_plane_timeouts.py`
and the [timeout preflight](issue-1102-workflow-timeout-reconciliation-preflight.md)
for strict timestamp/duration validation; pausing or resetting scenario time
must not disable apparatus supervision.

## Cross-cutting layers and canonical incumbents

| Layer | Incumbent and required boundary |
| --- | --- |
| Authoring, parsing, compilation | `raes` SDL models/validators, `raes_processor/compiler`, workflow formal semantics and time/trial contracts retain semantic authority. Carry any selected lifecycle requirement through the admitted plan and request commitment; do not introduce transport-only policy or encode it in free-form metadata. Reuse source limits and closed models. |
| Workflow, time, trial and cleanup joins | `WorkflowExecutionContract`, `workflow_result_contracts.py`, `TimeModelDeclarationModel`/`validate_time_runtime_transition()`, `TimeCapabilities`, `revalidate_admitted_trial_plan()`, and the SCE-007 models/helpers above own these checks. Validate identities, policy references, reset coverage, evidence, and required capabilities across objects; JSON Schema shape validation alone cannot discharge these invariants. Preserve scheduler isolation, including per-attempt secret scope, through `validate_scheduler_isolation_proof()`. |
| Trusted composition and capability shape | `ControlPlaneOptions`/`ControlPlaneConfiguration`, `control_plane_profiles.py`, `RuntimeTarget`, registry `_validate_runtime_target_shape()`, `registry_target_validation.py`, and `BackendManifest` parsing own config, profile, component presence, and invocation signatures. Any added optional protocol must agree with its manifest and installed component. Recovery support is operation-kind-specific; method presence alone is not negotiation. P3 remains unavailable. |
| Authentication and authorization | `ControlPlaneSecurityConfig.strict_defaults()`, `_ControlPlaneApiAuth`, typed `ControlPlaneIdentity`, `control_plane_plan_authorization.py`, and `operation_admission_context()` bind role, target/run, subject and disclosure scope. Direct callers retain the trusted-embedder boundary. Cancellation, status, recovery and resolution must reauthorize; identifiers, tokens in payloads, and existing receipts confer no authority. A supervisor never widens the original operation scope. |
| Request and value validation | `RequestSizeLimitMiddleware`, bounded `_ControlPlaneCallExecutor`, closed API/contract models, `backend_input_contracts.py`, `runtime_value_limits.py`, and native semantic validators remain mandatory before isolation, hashing, callbacks, and publication. Bound pending supervision as well as effects; queued work must recheck current admission before invocation. Reject malformed durations and policy variants rather than coercing them. |
| Secret and environment bindings | `SecretReferenceId`, `runtime_fact_dispatch.py`/`runtime_fact_binding_policy.py`, `raes/runtime_environment.py`, `_stateful_resource_references.py`, and planner `stateful_admission.py` already own reference resolution, visibility/freshness, generated-value exclusivity, sensitivity, and closed environment delivery projections. A generated `value_from` excludes a literal value and `operator_secret` classification; redacted/operator-secret values cannot contain raw material. Supervision needs no new env-binding dictionary or secret loader. If continuation rebinds an existing input, reapply those gates and current authority; do not persist resolved credentials for replay. |
| Backend input/result admission | `backend_calls.py`, `_validated_backend_result()`, native workflow/participant/time validators, realization authority, and `specs/formal/runtime-contracts/backend-result-admission.md` own isolated predecessors, plan/domain ownership, changed-address accounting, credential egress and safe projection. Apply them to recovery and late-result handling too; a neutral observer response is not trusted merely because it is typed. |
| Persistence and ownership | `RuntimeMutationAuthority`, `RuntimeLifecycleMixin`, `RuntimeDurabilityMixin`, `ControlPlaneStoreCommitAdapter`, atomic claims, `TerminalCommitMode`, snapshot CAS, strict record/snapshot/audit codecs, `RuntimeOwnerLease`, and `control_plane_store_paths.py` own state and publication. Preserve WAL/integrity/scope admission, lease-before-inspection, commit readback/poisoning, publish-after-commit, and close-before-lease-release. Extend these boundaries rather than adding a supervisor store or lock. |
| Diagnostics, exceptions and observability | Reuse `Diagnostic`/`DiagnosticModel`, canonical terminal diagnostics, `backend_result_diagnostics.py`, `_responses._conflict_detail()`, `_operation_routes.py` exception handlers, bounded `AuditEvent`, rejection audit, module loggers and `control_plane_health.py`. Preserve the redacted `422` request-validation and `500` internal-error envelopes and coarse conflict mapping. Emit stable value-free codes; no exception text/classes, validation input echoes, raw bodies, paths, native output, tokens, environment, or traceback leakage. Public health stays a bounded status/reason projection; authorized operational views, audit, participant history and archival evidence remain separate. No new exception hierarchy or audit channel. |
| Host/process exposure | Process supervision and TLS/proxy deployment remain embedder responsibilities. No new shell, executable path, argv, environment-variable or network surface is needed for the decision. A later isolation mechanism must use the owning backend's driver boundary, scoped process/job identity and safe secret injection; never place tokens in argv, inherit/dump a broad environment, execute request-supplied commands, or assume killing a local process terminates remote effects. Preserve private store paths and descriptor/lease checks. |

The existing credential-sensitive retry proof is intentionally ephemeral
(`control_plane_operation_context.py`, `control_plane_admission.py`): after
restart, a matching public commitment alone cannot prove exact credential-bearing
input. Supervision or resumption must not bypass this boundary or make that
proof durable by retaining secret values.

## Extensibility and publication boundary

The seam belongs between admitted semantic requirements and the existing
backend protocol/manifest/target composition. Select requirements per operation
kind and admitted run context; keep support, current willingness, and outcome
evidence distinct. Operational supervision budgets belong in typed runtime
configuration, independently of authored temporal meaning and the existing
admitted attempt controls. Define their precedence without silently shortening
or weakening a required execution guarantee. Support declarations must bind the
operation kind and admitted requirements; contextual refusal must still be
checked before effects and after any wait that can make willingness stale.
This permits a future backend with cooperative interruption, observation, or resumable work
without hard-coding backend names or making every target implement it. Do not
select a generic supervisor framework, new policy language, or checkpoint
schema before demonstrating a gap in the existing contracts.

The following are affected canonical requirement owners to disposition in the
issue's final decision, not a claim that their statements were changed here.
Their repository authority is `docs/requirements/<UID>/requirement.md`:

| Owners | Review obligation |
| --- | --- |
| API-404 (C1–C4), API-403, API-402, RUN-300, RUN-304 | State authority, supervision, portable outcome, restart, authenticated served admission and nonclaim boundaries. |
| DSL-113, SEM-203, SEM-204 | Authored workflow retry, completion, cancellation interaction and explicit compensation. |
| SEM-227–229, RUN-317–318, API-421 | Operational versus semantic clocks, bounds, progression and restart continuity. |
| EXP-706, EXP-712, SCE-002, SCE-006, SCE-007 | New-trial versus attempt identity, replay claims, admitted allocation, after-effect retry, clean-state/isolation and evidenced cleanup. |
| ASR-532 | Preserve rejected-result isolation while honestly classifying possible external effects. |
| RUN-310, RUN-311, SEM-222 | Preserve participant supervision and episode/reset semantics; generic operation supervision does not replace them. |
| RUN-316 | Operational supervision, readiness and diagnostics remain separate from participant observation and experiment evidence. |

Publish explicit change/retain dispositions; do not copy requirements into a
new normative catalog or mark guarantees implemented by writing prose.
ADR-104 sections 4–7 and 9, its FM3 model, and the recovery/profile runbooks need
consistency review with that final decision. In particular, address no-replay,
unbounded drain, optional observation, administrative resolution, and any
authored continuation permission explicitly. ADR-059 requires any accepted ADR
change to include an amendment row and matching `adr-index.yaml` pin/record.
The older design disposition's shorthand description of SEM-222 is not its
canonical title; use the requirement itself when assigning ownership.

If later executable work changes a portable carrier, reuse `ContractModel`,
`schema_bundle()`, published schemas, publication entries/manifest change ledger,
fixtures, compatibility checks and strict store migrations together. ADR-009
makes the published schema authoritative; a Python enum or codec edit alone
cannot publish a lifecycle change. This preflight needs none of those changes.

## Assurance, non-goals, and anti-patterns

Reuse the existing `test_issue_1182_operation_lifecycle_contract.py`,
`test_issue_1181_unified_control_plane_mutations.py`,
`test_issue_1179_startup_reconciliation.py`, `test_issue_1184_atomic_idempotency_claims.py`,
`test_issue_1187_*`, `test_runtime_workflow_timeout_reconciliation.py`,
`test_workflow_semantics_properties.py`, `test_sem_227_shared_time_model.py`,
`test_sce_006_cleanup_contracts.py`, and admitted-trial tests.
Later execution evidence must distinguish queue cancellation, a backend that
never returns or refuses interruption, cancellation/commit races, partial
effects before exception, late effects after deadline/process loss, blocked
recovery observation, store acknowledgement loss, cross-actor/scope denial,
required cleanup failure, and exhausted/disallowed after-effect retry.
Use independent effect witnesses and deterministic synchronization, not sleeps
or mocks that equate a cancelled future with a stopped backend. Design-set
structural tests are not runtime or liveness proof.

Repository workflow remains `.ground-control.yaml`, `.gc/plan-rules.md`,
`noxfile.py`, repo policy, requirement governance, ADR pins and schema gates.
Use `RAES_REQUIREMENT_UID=API-404` on this issue branch. Canonical gates include
`tools/check_repo_policy.py`, `tools/check_requirement_governance.py`,
`tools/check_adr_immutability.py`, `tools/check_generated_schemas.py`,
`tools/check_schema_publication.py`, and `tools/check_schema_coverage.py`;
run the gates relevant to the artifacts actually changed.
Use proportionate local checks and existing CI; add no verification script,
invented requirement UID, release version edit, or changelog fragment for this
documentation-only preflight.

Out of scope here: implementing #1348's decision, amending its requirements or
ADR-104, runtime code, new schemas, a job service, separate workflow/recovery
engine, storage product, P3/multi-owner coordination, automatic replay, generic
rollback, or backend containment/certification. `RuntimeManager` remains a
separate direct-execution facade, not a bypass for a quarantined control plane
sharing its target. Do not equate durable state with safe retry, local CAS with
external fencing, workflow compensation with infrastructure rollback, operation
identity with trial identity, or administrative acceptance with physical safety.
Physical-OT protection remains a selectable future concern, never a universal
execution prerequisite.
