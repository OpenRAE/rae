# Issue #1348 — Operation Lifecycle, Supervision and Recovery

Date: 2026-09-22. Decision authority: ADR-104 amendment #1348.
Requirement: API-404. Classification: FM3.

## Decision

RAE is the shared product runtime that drives LilRAE, BigRAE and other backends.
Backend-specific realization and contextual willingness remain backend duties.
Admitted author requirements govern execution and recovery choices. A backend
that cannot or will not establish a required guarantee is not admitted for that
operation. Runtime durability never supplies permission to retry, resume or
allocate another trial.

Adopt the [supervision semantics](../../specs/formal/runtime-control-plane/supervision.md)
as the normative extension of ADR-104's operation model. Preserve its existing
state vocabulary, one owning writer, actor/run isolation, atomic terminal cut,
revision CAS, scoped idempotency, quarantine and immutable terminal history.
Separate short state mutations from retained external-execution reservations.
Supervision has a bounded path to the same authority while backend work blocks;
conflicting effects remain excluded until their scope is reconciled. Backend
cessation evidence, not local lock release or deadline expiry, discharges that
reservation.

Cancellation request, backend acceptance, refusal, cessation and final outcome
are separate facts. Complete, known partial, absent and unknown effects are
classified independently from the desired result. An exception or rejected
snapshot cannot establish absence; a validated applied effect cannot establish
success until every admitted requirement and final result/release gate passes.
Operational supervision covers every external callback, including admission and
recovery observers, as well as bounded commit settlement and drain. Semantic
time and apparatus time retain separate authority.

## Evidence and context

The issue's [diagnosis at revision 077f7d04](https://github.com/OpenRAE/rae/blob/077f7d04/docs/research/runtime-refactor/diagnosis.md)
identifies the retained mutation permit; its
[agreed boundaries](https://github.com/OpenRAE/rae/blob/077f7d04/docs/research/runtime-refactor/README.md)
establish the shared runtime, author choice, contextual backend refusal and
selectable future physical-OT concerns. Those historical files are not present
on this branch. The [ecosystem program](https://github.com/OpenRAE/hub/issues/3)
assigns concrete backend product responsibilities without replacing RAE's shared
scenario runtime. The [preflight](issue-1348-operation-lifecycle-preflight.md)
maps these concerns to current code and existing semantic owners.

## Canonical requirement disposition

The requirements remain authoritative in `docs/requirements/<UID>/requirement.md`.
This table records the change/retain decision; it is not another requirement
catalog. Only API-404 is changed by this delivery. Other statements and statuses
are retained because the new interpretation composes their existing authority.

| Owner | Disposition and relationship |
| --- | --- |
| [API-404](../requirements/API-404/requirement.md), C1–C4 | Clarify state serialization versus external execution, no implicit continuation, outcome evidence and profile nonclaims. Preserve existing clause/profile identifiers, ACTIVE status and implementation traceability. Add design evidence separately. |
| API-402, API-403, RUN-304 | Retain portable submission, status and history ownership. Correlated supervision and known-partial evidence need explicit versioned carriers before executable support is claimed. No wire enum changes here. |
| RUN-300 | Retain the processing lifecycle: shared RAE drives backend execution while preserving authored meaning. No backend-local scenario orchestrator is required. |
| DSL-113, SEM-203 | Retain authored workflow control, retry limits, branch/join semantics and execution history. Transport retries and startup observation are not workflow attempts. |
| SEM-204 | Retain explicit compensation registration, triggers, reverse completion order and independent outcome. A compensation history entry does not prove an external compensating effect. |
| SEM-227, SEM-228, SEM-229, RUN-317, RUN-318, API-421 | Retain clock/domain/segment, progression and capability authority. Apparatus budgets neither reinterpret authored time nor survive restart as portable monotonic timestamps. RUN-318 remains DRAFT. |
| EXP-706, EXP-712, SCE-002 | Retain trial allocation, run identity and evidence-bounded replay claims. Failure requiring a new trial cannot be converted into continuation of the old trial. |
| SCE-006, SCE-007 | Retain admitted attempt timeout/cancellation/retry controls, after-effect posture, independent cleanup, isolation and clean-state evidence. A distinct attempt preserves the entry/run identity; a new trial does not. |
| ASR-532 | Retain trusted-predecessor isolation and strict backend result validation. Rejected results establish a portable-state protection, not proof of absent external effects. |
| RUN-310, RUN-311, SEM-222 | Retain participant supervisory and episode/termination semantics. Operation-level interruption neither invents a participant nor rewrites episode history. |
| RUN-316 | Retain operational observability separate from participant observations and experiment evidence. Readiness is not a backend effect witness. |

## Contract and implementation disposition

This delivery defines the decision and bounded abstract witnesses. It does not
implement the execution mechanism or publish new guarantees through the profile
catalog. The following gaps are explicit acceptance obligations for realizing
the decision, not features claimed by the current implementation:

| Existing surface | Required realization of the decision |
| --- | --- |
| `RuntimeMutationAuthority`, `_ControlPlaneCallExecutor`, `RuntimeLifecycleMixin` | Separate state-permit ownership from conflicting-effect reservation; reserve bounded supervision capacity through admission, audit, workers, observation and shutdown. Current drain and external calls can remain blocked. |
| `OperationAdmissionContext`, backend manifest/protocol and `RuntimeTarget` | Bind selected requirements, supported operation kinds, contextual willingness and scoped invocation/control identities. Preserve registry shape validation and fail-closed admission. |
| Existing operation carriers and recovery observer | Add governed carriers for correlated control dispositions, residual scope, cessation evidence and continuation points where absent. Current absent/applied/indeterminate observation is not a general partial-effect or resumable-work protocol. |
| `backend_calls`, result-admission and final release paths | Preserve predecessor isolation and classify unobservable effects honestly. A failed `ApplyResult` or generic exception cannot stand for known absence. Success must include the final admitted gates. |
| `ControlPlaneStoreCommitAdapter`, durability/readback, leases | Retain atomic terminal publication and immutable parents; bind late evidence and linked resolution without treating CAS or administrative acceptance as external fencing. |
| Workflow and SCE-007 execution controls | Drive concrete interruption/compensation/reset/cleanup through their existing owners and verify results. Existing recorded compensation alone does not demonstrate execution. |

Use ADR-009/061 publication, `ContractModel`, `schema_bundle()`, the schema change
ledger, compatibility validation and strict store migrations for any resulting
carrier changes. No free-form metadata policy, duplicate cleanup schema, new
exception hierarchy, generic durable-execution engine or second store is selected.
Default P0 operations do not need experiment or participant wrappers. Required
physical-OT protections remain selectable future capabilities, never universal
CTF or simulation obligations and never implied certification.

## Alternatives and consequences

Keeping external execution and all control mutations under one logical permit
cannot service a stop request during a blocked call. Simply offloading a thread
or releasing that permit at a deadline permits unfenced late effects. A second
supervisor store would split authority. Automatic durable replay would violate
authored trial and after-effect retry semantics. These alternatives are rejected.

The selected design preserves useful storage guarantees while making supervision
and effect uncertainty explicit. The cost is a retained reservation/quarantine,
correlated evidence and capability admission at more boundaries. An uncooperative
backend can leave a scope unavailable; no portable promise eliminates that
constraint. A stronger bounded interruption requirement requires a backend that
can establish it, not a stronger interpretation of the same timeout.

## Verification and fulfillment boundary

The finite oracle and
[`test_issue_1348_operation_supervision.py`](../../implementations/python/tests/test_issue_1348_operation_supervision.py)
exercise the design's admission, terminal, cancellation, publication and
continuation relations, including 64 combinations of effect knowledge,
quiescence, validation, satisfaction and cancellation. The model is not a
production implementation and its trusted evidence inputs are not backend proofs.
The existing lifecycle, profile-alignment and SCE-007 tests retain their narrower
runtime/contract claims. ADR pin and requirement-governance checks validate the
publication boundaries.

Issue acceptance maps to the formal supplement: AC1 to S2–S5; AC2 to S6 and
S4/S5; AC3 to S1/S2; AC4 to this disposition, ADR-104 and its amended model.
API-404-C1 maps to S1–S3/S5, C2 to S4–S6, C3 to bounded authenticated supervision
under S1/S2, and C4 to the explicit nonclaims above. API-404 remains ACTIVE for
its existing profile clauses; these design artifacts do not certify the listed
implementation gaps as solved.
