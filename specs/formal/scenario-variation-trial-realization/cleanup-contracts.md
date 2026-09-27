# Portable Clean-State And Cleanup Contracts

Status: normative contract semantics

Classification: FM2 (semantic graph / constraint)

Requirement: SCE-007

Supports: SCE-006

Decision: ADR-084

Published contracts:

- `trial-cleanup-plan-v1`
- `trial-cleanup-receipt-v1`
- `scheduler-isolation-proof-v1`

## Scope

These contracts carry schedule-independent clean-state intent from an admitted
trial entry to one execution attempt, then record the attempt's cleanup result.
They do not define scheduler queues, workers, placement algorithms, backend
drivers, workflow compensation, archival run identity, comparison, or scoring.

Let `P` be a `TrialCleanupPlanModel`, `A` an execution attempt, `R` a
`TrialCleanupReceiptModel`, and `I` a `SchedulerIsolationProofModel`.

## Identity And Authority

`P.plan_entry_id` identifies the admitted entry and `P.run_id` is its
preallocated archival run identity. `R.execution_attempt_id` identifies one
attempt and must be distinct from `R.run_id`. Scheduler job ids, control-plane
operation ids, workflow run ids, backend-native ids, and cleanup receipt ids
remain separate identities.

```text
R.cleanup_plan_ref = P.plan_id
R.plan_entry_id = P.plan_entry_id
R.run_id = P.run_id
R.execution_attempt_id != R.run_id
```

The cleanup plan is execution intent, not mutable scheduler state. The receipt
is immutable attempt evidence, not a replacement for `experiment-run-v1`.

## Resource And Clean-State Boundaries

Every clean-state requirement and cleanup obligation references a declared
`CleanupResourceBoundaryModel`. A boundary names an owner and portable resource
references. A clean-state claim can speak only about those boundaries and the
evidence probes it cites; it never asserts universal environmental reversal.

The clean-state modes are:

- `fresh`: a newly allocated boundary whose state is verified;
- `verified-reset`: an existing boundary restored and verified;
- `declared-reusable`: reuse supported by a declared claim and probes; and
- `fresh-range-required`: reuse is not admitted.

Fresh and reset modes require verification probes. Reusable state additionally
requires a reusable-state claim reference. Missing or unsupported evidence does
not become clean state by backend convention.

## Cleanup Obligations

Each obligation declares:

- owned resource boundaries;
- a portable action kind or versioned custom action profile;
- terminal triggers (`success`, `failure`, `cancellation`, `timeout`, `retry`,
  or `abort`);
- required or best-effort strength;
- ordering dependencies;
- idempotency or compensation posture;
- verification probes; and
- a positive timeout bound.

Map keys equal embedded ids, references resolve inside the plan, and the
dependency graph is acyclic. Required obligations always have verification
probes. Required cleanup cannot be downgraded to best effort after admission.

Workflow compensation remains governed by the workflow state machine. A
cleanup obligation may cite compensation evidence, but a workflow compensation
event is not by itself proof that owned resources were cleaned.

## Retry Safety

The first execution attempt and every later attempt have different attempt ids.
When more than one attempt is permitted after effects may have occurred:

- idempotent effects may use an idempotent retry policy;
- reset-based retry references required reset obligations triggered by retry
  that cover every boundary affected by non-idempotent work;
- compensation-based retry references declared compensation; and
- non-idempotent effects cannot repeat without reset or compensation.

The policy does not allocate a new archival `run_id` and cannot mutate the
admitted trial entry.

## Receipt Semantics

Primary trial outcome and cleanup status are orthogonal:

```text
trial_outcome in {succeeded, failed, cancelled, timed-out, aborted}
cleanup_status in {succeeded, failed, partial, unsupported, unverified, not-required}
```

For the trigger selected by the primary outcome, every required obligation has
a successful result. Failed or unverified results carry bounded failure
evidence or residual-state references. A successful result carries verification
evidence and cannot disclose residual state.

A `clean_state_claim` is permitted only when cleanup succeeded. Failed,
partial, unsupported, or unverified cleanup therefore invalidates clean or
reusable-state claims without rewriting the primary trial outcome.

## Backend Capability

`backend-manifest-v2` may declare `capabilities.cleanup`. The block names both
cleanup contract versions, supported action kinds, supported verification
methods, reusable-state support, and residual-state disclosure support.

The capability block and `supported_contract_versions` must agree. A backend
that cannot disclose residual state cannot claim reusable-state support.
Backend-private cleanup mechanics remain implementation details and cannot
satisfy admission without the portable declaration and receipt.

`require_cleanup_plan_capability()` is the fail-closed admission helper. It
rejects a plan when the backend omits cleanup capability, lacks a required
action or verification method, cannot support declared reusable state, or
cannot disclose residual state for required cleanup.

## Scheduler Isolation

`SchedulerIsolationProofModel.requested_parallelism` defaults to one. Serial
execution needs no parallel-isolation evidence. A value greater than one
requires independent evidence for all of:

- range instances;
- host capacity;
- ports;
- storage;
- control-plane locks;
- secret-resolution scope; and
- cleanup ownership and probe independence.

Secret-resolution scope is a governed isolation dimension for SCE-006: bounded
parallelism must prove that concurrent trials resolve governed secret references
through independent per-attempt scopes, never a shared broad worker credential
or resolver cache.

The requested bound cannot exceed the number of admitted entries named in the
proof. Missing or non-independent evidence rejects bounded parallelism; it does
not change trial identity or scenario meaning.

## Security And Disclosure

All three roots are closed `ContractModel` shapes. They carry ids, safe
resource references, bounded profile terms, and evidence references only. Raw
credentials, secret values, environment dumps, process arguments, backend
handles, daemon output, and tracebacks are not contract fields and are rejected
as additional properties.

## Verification

Executable coverage is in
`implementations/python/tests/test_sce_006_cleanup_contracts.py` and the fixture
corpora under `contracts/fixtures/plans/` and `contracts/fixtures/control-plane/`.
Published schemas carry
`x-raes-invariants` for cross-reference, retry, required-obligation, receipt,
and isolation rules that JSON Schema alone cannot fully join.
