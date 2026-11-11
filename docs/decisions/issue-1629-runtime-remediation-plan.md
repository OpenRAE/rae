# Issue 1629 runtime remediation plan

Status: broader scope approved by the user on 2026-10-28; implementation is in progress.
The [design and DFDs](issue-1629-shared-runtime-design.md) define the implemented system boundaries.

## Approved decision

Split engine lifetime from run context lifetime.
This work precedes the #1629 loop.
This affects shared admission and resource claims.
It also affects callbacks, store access, and shutdown.
The work is broader than connecting the existing trial compiler to an execution loop.
It preserves the existing runtime as the ecosystem's common execution engine.
Extend its existing Temporal path as part of this work.
Local and Temporal setups must share the run and sequence rules needed by #1629.
This revises the earlier proposal to deliver local execution first and defer the remote path.
Temporal is already selected and implemented for individual operations.
The missing work is shared run ownership and durable progress across runs.

The earlier coordinator recommendation is withdrawn.
Per-run stores remain fixed; callers retain one public runtime owner across the experiment.
The starting code had no safe context-selection boundary for that owner.
Merely replacing its current store and run fields would redirect delayed callbacks.
Wrapping separate controllers would preserve separate backend ownership and shutdown lifecycles.

## Delivery sequence

### 1. Record ownership and preserve current behavior

Amend ADR-104 with engine and run-context lifetime responsibilities after approval.
Update its amendment record, index, and acceptance-content pin through the repository's existing procedure.
Extend the existing FM3 supervision model with context ID and closure invariants.
Retain the current single-run constructor and `RuntimeManager` alias.
Keep source modules within the repository's size limit.

Affected surfaces: `control_plane.py`, `control_plane_configuration.py`, runtime architecture, and runtime lifetime migration documentation.
Evidence: existing single-run lifetime, scope, access control, teardown, and recovery tests remain green.
No multi-run behavior is enabled at this stage.

### 2. Extract explicit run contexts

Add an internal typed run context.
Move run ID, store access, and snapshots into it.
Also move operation maps, generations, and run-local bindings.
Pass that context through admission, state reads, dispatch, and settlement.
Keep callbacks bound to their original context.
Keep existing operation and snapshot validators at their current trust bounds.
Keep context handles subordinate to the engine's access control and mutation owner.

Affected surfaces: control-plane admission, operation context, durability, supervised execution, recovery, and participant/time modules.
Evidence: reject a command for another context; reject stale settlement; preserve receipts and reservations after reopen.
Drive an old callback after a second context exists and prove that it cannot change the second context.

### 3. Separate run closure from engine shutdown

Keep worker pools and execution adapters under the engine.
It also owns installed backends and resource claims.
Retain resource reservations with their original run and ledger references.
Retire a context only after its admitted cleanup and callback obligations permit closure.
Keep cancellation reachable during blocked effects.
Drain all contexts at engine shutdown without inventing cessation evidence.

Affected surfaces: `control_plane_composition.py`, `runtime_resource_ownership.py`, `control_plane_lifecycle.py`, and execution adapters.
Evidence: finish one run without closing the engine; reject a second owner of the same backend.
Reject resource reuse after uncertain effects, cleanup refusal, or a callback that has not exited.

### 4. Add durable experiment accounting through existing stores

Define versioned decision records and explicit store support for admitted multi-run work.
Reuse the existing local transaction, lease, path-security, and revision machinery.
Preserve run-store ID and old single-run data.
Persist the dispatch ID, order, and actor before effects.
Also persist the attempt deadline and replacement lineage.
Resolve lost commit acknowledgements by readback using the same IDs.
Refuse unsupported durable setups before starting any entry.

Affected surfaces: store protocols, store adapters, codecs, and migration checks.
Existing PostgreSQL single-run behavior must remain compatible.
Add the same multi-run records and atomic claims to the existing PostgreSQL adapter.
Keep these records separate from Temporal history and task delivery.
Both store paths must pass equivalent accounting and recovery tests.
Evidence: process interruption at decision/operation/archive bounds, duplicate requests, changed resume inputs, and ownership loss.

### 5. Extend local and Temporal driving through one set of rules

Define shared RAE decisions for the run and run-sequence lifecycle needed here.
Keep backend calls, store access, and live clocks outside replayed workflow code.
The local driver uses existing bounded execution adapters.
The remote driver uses Temporal's durable workflows, timers, and queues.
Reuse the current operation and control workflows for admitted effects.
Do not add a durable scheduler or copy execution rules into a second runner.

Use stable references to committed run and sequence decisions.
Keep full plans, participant settings, secrets, and raw evidence out of history.
Preserve current one-use grants and author-selected effect attempt limits.
Resolve policy through RAE's existing scenario scope and precedence rules.
Keep failure classes, effect evidence, cleanup obligations, delays, and total budgets bound to that policy.
Never replace an unsupported authored choice with Temporal defaults.
Recheck authority and semantic time when a workflow wakes or resumes.
Version the workflow inputs and preserve compatible replay for retained histories.
History rollover must retain run IDs, budgets, reservations, and pending controls.
Keep P0 local use free of a mandatory service.
Keep P3 unavailable; this work does not add multi-owner coordination.

Affected surfaces: the shared run driver, Temporal adapters and workers, store access, and supervision contracts.
Evidence: run the same admitted plan through both drivers and compare order, outcomes, and lineage.
In CI, restart workers between entries and after dispatch using real Temporal and PostgreSQL.
Check duplicate delivery, lost acknowledgements, cancellation during blocked effects, and replay after upgrade.
Verify that replay cannot repeat an effect, debit another attempt, or release an unknown reservation.
Inspect Temporal history for disallowed inputs and evidence.

### 6. Connect the experiment module to the shared engine

Use complete-plan admission, recorded allocation order, and existing entry realization.
Carry exact structural selections and participant settings into the installed execution path.
Propagate admitted trial guarantees and budgets into live operation admission.
Capture observations before cleanup and retain separate failure dispositions.
Use trusted evidence owners to establish cleanup and target reuse.
Use the existing replacement compiler with the full committed history.
Persist each child allocation and supersession decision before child dispatch.

Affected surfaces: runtime trial setup, existing trial-unit contracts, participant application/evidence bounds, and narrow processor import allowances.
Evidence: public-runtime tests cross model/prompt settings with node presence/settings.
Assertions inspect observed application, not only forwarded request fields.
Cover cancellation, uncertain effects, capture failure, cleanup refusal, replacement exhaustion, and retained originals.

### 7. Validate compatibility and publish for review

Run targeted tests for each changed boundary while coding.
Use Path A red-green tests for new behavior and regression tests for changed protections.
Run targeted documentation and file-local policy checks before publication.
Use CI for full suites, integration suites, fuzzing, and completion checks.
Complete the implement skill's review, publication, hosted checks, and readiness gates.
User approval remains needed for merge.

Relevant existing tests include:

- `test_issue_1660_runtime_lifetime.py` and `test_issue_1660_review_regressions.py`.
- `test_issue_1362_resource_ownership.py`, `test_issue_1362_commit_authority.py`, and `test_issue_1362_lost_ack.py`.
- `test_issue_1362_reconciliation.py` and `test_issue_1348_operation_supervision.py`.
- `test_issue_1362_temporal_adapter.py`; use `test_issue_1362_distributed_integration.py` only in CI.
- `test_issue_1627_trial_unit.py`, `test_issue_1628_trial_control_admission.py`, and `test_issue_1666_factorial_compilation.py`.
- `test_sce_006_batch_scheduler.py`, `test_sce_006_cleanup_contracts.py`, and `test_issue_1396_trial_replacement.py`.

## Scope and completion evidence

All workloads use the shared engine.
No new service or backend discovery is needed.
An ordinary run needs no experiment wrapper.
Serial run sequencing is required for both local and existing Temporal setups.
It does not enable coordinated P3, automatic owner failover, or unsupported mixed-backend realization.
Existing supported single-run workloads retain their semantics.

| Issue criterion. | Completion evidence. |
| --- | --- |
| Complete factorial plan through one runtime. | Same public owner executes all entries; backend observations show structural and participant treatment application. |
| Recorded allocation and identities. | Persisted dispatch order matches admission; restart cannot allocate a duplicate attempt. |
| Cleanup and failure distinctions. | Independent execution, capture, and cleanup outcomes survive interruption; unverified cleanup prevents reuse. |
| Admitted replacement policy. | Atomic ordinal claims, compiler-owned child identity, retained original runs, and explicit exhaustion. |
| Public runtime coverage. | Common engine tests cover ordinary SDL execution and factorial runs, including cancellation and recovery. |
| Local and Temporal behavior. | Both drivers preserve the same admitted order, run identity, attempt limits, cleanup rules, and replacement lineage. |

The main regression risks are cross-run state writes and premature resource release.
The staged tests target those risks before experiment sequencing is enabled.

Three tests define the core ownership change.
First, delay a result from run A, then open run B.
Deliver A's result and check that B's state does not change.
Next, leave an effect in A with unknown state.
Try to use the same target for B and check that the engine refuses.
Finally, end A after verified cleanup, then start B on the same engine.
Check that the engine is still open and that B has fresh state.
These tests must use the public runtime and its real store path.
They must not replace the state checks with mocks.

The user's approval covers this refactor, the shared local and Temporal drivers, and the #1629 loop.
A broader deployment or authority change needs a new decision.
