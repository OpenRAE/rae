# Issue #1624 — Trial orchestration ownership preflight

Date: 2026-10-25

Requirement: SCE-006. Scope: guidance for the ownership wording correction in
the variation reference's authority matrix and SCE-006. This note does not make
that correction or implement scheduling.

## Decision and scope

[ADR-084 §1](adrs/adr-084-scenario-variation-and-deterministic-trial-realization.md)
already gives the processor orchestration over public SDL/planner APIs and the
runtime live execution. [ADR-113 §§1–4](adrs/adr-113-reusable-execution-machinery.md)
retains RAE's admission, authored order/time, retry permission, supervised
dispatch and outcome authority when reusing execution machinery. Backend
providers execute concrete effects and supply observations. No new ADR is
needed.

The upcoming correction must make those owners explicit in both row 8 of
[the variation reference](../explain/reference/scenario-variation-and-trial-realization.md)
and the governed requirement statement. The external scheduler/APTL supplies
placement, isolation (including the effective parallelism bound), timeouts and
cleanup over the existing single-scenario path. These duties confer no scenario
orchestration or interpretation authority. Keep serial default, deterministic
identity/order, clean or declared reusable initial state, bounded timeouts,
verified cleanup, and the prohibition on private comparison/scoring intact.
“Orchestration” in `OrchestrationPlan` retains its processor/runtime meaning;
calling an external resource allocator an orchestrator must not transfer it.

The [#785 preflight](issue-785-sce-006-isolated-batch-trial-scheduling-preflight.md)
provides the wider isolation and evidence rationale. Its historical requests
for a secret-scope dimension, canonical ordering helper and attempt receipt are
now satisfied by the incumbents below. Its warning about raw 409 exception text
is also superseded by `_conflict_detail()`. Do not recreate those mechanisms or
treat its proposed attempt wrapper as permission for an APTL lifecycle.

## Canonical seams and cross-cutting gates

Package paths below are relative to `implementations/python/packages/`;
unqualified runtime modules belong to `raes_runtime`.
The wording change introduces no API, credential, environment, process or store
surface. These existing gates must remain visible in the resulting ownership
model; any later execution adapter must pass them through its owning layer.

| Layer | Incumbents and required fit |
| --- | --- |
| Plan ingress, schema and integrity | `raes_contracts/admitted_trial_plan_ingress.py`: external bytes use `parse_admitted_trial_plan_json()`; caller-held models use `revalidate_admitted_trial_plan()`. Retain bounded strict JSON, closed `ContractModel` shapes, whole-plan semantic/digest validation and exact entry membership before dispatch. Published `contracts/schemas/plans/admitted-trial-plan-v1.json` is the portable authority. No detached-entry ingress, alternate DTO/parser/canonicalizer or copied validation. |
| Ordering, realization and lifecycle | `raes_processor/trial_scheduler.py` owns pure scheduling policy; `raes_contracts/contracts/trial_coordinate_order.py:canonical_entry_order()` owns canonical order. `TrialRealizationInputs` and `realize_admitted_trial_entry()` in `raes_processor/trial_realization.py` consume the sealed entry through SDL admission and processor planning; the latter returns typed plans, not a completed execution. `RuntimeManager`/`RuntimeControlPlane`, existing workflow/participant/time logic, and `BackendOperationProvider` retain effect admission, execution, supervision and result validation. External placement never substitutes for those owners. |
| Isolation, initial state and evidence | `SchedulerIsolationProofModel`, `TrialCleanupPlanModel`, `TrialCleanupReceiptModel`, `validate_scheduler_isolation_proof()`, `validate_trial_cleanup_receipt()` and `validate_batch_execution_receipt()` own portable checks. `BatchExecutionReceiptModel` and published `contracts/schemas/control-plane/batch-execution-receipt-v1.json` record an attempt. The sealed ceiling is separate from `AllocatorGrant.effective_parallelism`; proof/receipt reference strings do not establish live leases. The allocator must prove current independent range, host capacity, ports, storage, control-plane locks, secret scope and cleanup ownership, and quarantine unverified resources. Serial execution still requires clean-state evidence. |
| Configuration and component admission | Reuse `ControlPlaneConfiguration`, `control_plane_composition.py`, `control_plane_profiles.py`, `registry_target_validation.py`, backend manifests/capability admission, and authored execution/cleanup policy. Preserve typed scopes, installed-provider shape checks, profile/store capabilities and contextual willingness. Ambient environment or worker defaults cannot widen admitted bounds or select another policy/profile. This correction needs no new config or dependency. |
| Authentication and authorization | `ControlPlaneSecurityConfig.strict_defaults()`, `control_plane_api/_auth.py`, `control_plane_admission.py`, `control_plane_plan_authorization.py`, `control_plane_operation_context.py` and `control_plane_api_guards.py` retain target/run/actor scope, role admission, exact-plan permission, request/offload limits, sealed route authority, no-store responses and denial audit. Plan ids, task tokens and receipts are not credentials. Plan visibility does not authorize dispatch, evidence access, secret resolution, cancellation or cleanup. Keep the HTTP request bound distinct from the larger plan-ingress bound. |
| Secret, environment and disclosure shapes | Reuse `raes_contracts/secret_references.py`, runtime fact binding/dispatch, participant crossing/final-sink checks, and `raes/runtime_{environment,generated_value,configuration,values}.py`. Retain environment name uniqueness, sensitivity/provenance, literal versus `value_from` exclusivity, generated-value classification and authorized run-local sink/freshness checks. Resolve references only at authorized execution; keep values and sensitive locators out of plans, worker/history payloads, proofs, receipts, logs and audit. Never share resolved caches or secret mounts across allegedly isolated trials. |
| Host and process exposure | Existing backend containment, `raes_backend_protocols/naming.py`, store path hardening and embedder process supervision remain responsible for safe resource names, private work/storage, owned ports, permissions and controlled environment. Any later process adapter needs fixed argv, bounded calls and safe paths; no shell interpolation, token/secret in argv, broad environment inheritance or new listener. Hostile workloads remain outside trusted workers. A process kill or caller timeout alone does not prove remote effects ceased. |
| Persistence, recovery and observability | `ControlPlaneStore`/`AtomicControlPlaneStore`, `control_plane_durability.py`, store codecs/migrations, revision/history CAS, `RuntimeOwnerLease`, `RuntimeResourceClaim` and supervised operation settlement retain scoped claims, generations, atomic terminal/snapshot/audit commits and restart reconciliation. External queue state cannot replace the RAE ledger or archival `ExperimentRunModel`/study evidence; reuse `raes_operations/run_artifacts.py` for its existing archive role. Use `AuditEvent`, module loggers and operation/attempt correlation; logs are not execution truth. Engine history records progress, not RAE semantic outcomes. |
| Exceptions and public envelopes | Reuse `AdmittedTrialPlanIngressError`, shared `Diagnostic`/`DiagnosticModel`, `portable_diagnostic_payload()`, `backend_result_diagnostics.py`, `control_plane_api/_responses.py:_conflict_detail()` and `_operation_routes.py`'s redacted validation/500 handlers. Preserve stable denial/conflict envelopes. Raw validator inputs, native exception text, host paths, argv, stdout/stderr and tracebacks must not enter errors or telemetry. No new exception hierarchy, logger framework or audit stream. |

## Reliability, extensibility and anti-patterns

Batch placement order is distinct from authored in-scenario execution order.
Worker availability/completion order cannot change canonical coordinates,
preallocated `run_id`, factors or random streams. Plan/entry/run, attempt,
operation and engine identities remain distinct. Transport replay reconciles the
existing scoped idempotency claim; effect retry or a fresh trial needs its
existing authored permission and identity rules.
Per-trial evaluation remains on the existing `EvaluationPlan`/runtime path;
cross-trial comparison and scoring remain experiment/study concerns.

Timeout enforcement uses RAE's authorized control/supervision path and backend
cessation evidence. `operation_execution_adapter.py:LocalExecutionAdapter`
bounds callers while retaining occupied slots until callbacks exit; it does not
prove interruption. Keep effect/control/store capacity separate. Preserve
unknown-effect reservations; cleanup or reuse must wait for the required
cessation/fencing and probe evidence. Compensation, backend teardown return,
engine cancellation and successful trial outcome are not verified cleanup.
Process-local `RuntimeResourceClaim`/locks and a local store's single-owner lease
do not prove multi-host resource isolation. `participant_scheduler*` schedules
actions within a scenario, not range instances across trials.

The extension seam is the existing one-entry realization handoff plus the
configured RAE execution adapter/provider and allocator grant. A new transport
or allocator changes delivery/lease mechanics while retaining semantic owners.
Use the sealed requested ceiling, a validated deployment cap, live owned
capacity and eligible entry count to bound effective parallelism. Existing
entry/cleanup policy supplies budgets; scheduler wall time must not replace
scenario time. A new ordering profile belongs with the owning versioned order
policy and receipt validator, not a scheduler-local sort. ADR-113's distributed
selection does not mandate a service for local execution or authorize deployment
from this documentation correction. Downstream allocator/host claims require
that repository's own evidence; this preflight inspects this repository only.

Non-goals are runtime changes, new lifecycle/queue/store abstractions, duplicate
schemas or validators, experiment selection/resampling, run-id allocation,
comparison/scoring, distributed rollout and expanded conformance claims.

## Repository workflow and review boundary

SCE-006 needs an explicit phase in `tools/policy/requirement_order.yaml`.
The existing requirement-governance evaluator rejects requirements without a phase.
An isolated-batch-scheduling phase keeps SCE-006 subject to existing status and traceability checks.
This mapping adds no predecessor, ownership exception, or new enforcement mechanism.

Keep the authority matrix and governed SCE-006 wording aligned with the accepted
ADRs; do not amend accepted ADRs or hand-edit generated requirement projections
to repair the contradiction. ADR-036 import boundaries,
`specs/authority/authority-boundary.yaml`, `.ground-control.yaml`,
`.gc/plan-rules.md`, `tools/check_repo_policy.py`, requirement governance,
`noxfile.py`, `tools/verification_plan.py` and `.github/workflows/ci.yml` remain
the canonical gates. A later portable contract change additionally requires
ADR-009/061 schema publication, manifest ledger and `schema_bundle()` parity;
this wording correction needs no schema revision.

Verification for the correction is ownership consistency and targeted document
policy/link checks. Existing `test_sce_006_batch_scheduler.py`,
`test_sce_006_cleanup_contracts.py` and `test_sce_002_trial_realization.py` are the
behavioral incumbents if later work changes those seams. Do not add tests that
only assert prose spelling or run full/integration/fuzz/completion suites
locally. Use `RAES_REQUIREMENT_UID=SCE-006` on this issue-number branch; CI keeps
the repository-wide gates.
