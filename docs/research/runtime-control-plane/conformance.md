# Runtime control-plane conformance

CP-9 exercises the reference compositions against
[ADR-104](../../decisions/adrs/adr-104-runtime-control-plane-architecture.md)
and the [FM3 operation model](../../../specs/formal/runtime-control-plane/README.md).
The suite is selected with one pytest marker, including the retained #1092 / PR
#1136 crash-consistency regressions. Specialized tests keep their existing owners.

From the repository root, run all selected default, integration, and property
cases in the locked environment:

```shell
RAES_REQUIREMENT_UID=API-404 uv run --project implementations/python --all-extras --frozen python -m pytest implementations/python/tests -m control_plane_conformance -q
```

The explicit marker expression replaces pytest's default exclusions. A plain
pytest run omits the process-loss and fuzz cases and is not a complete CP-9 run.
CI's existing integration lane runs the process cases; the default shards run
the deterministic matrix and security cases. The generated sequences also
belong to the existing fuzz lane, which must be reported separately from the
unit/integration CI graph. No Docker daemon or external service is required.

## Reference compositions and limits

| Composition | Shared evidence | Process-loss interpretation |
| --- | --- | --- |
| P0: core with in-memory store | Scoped retries, actor/scope isolation, one mutation authority, revision CAS, coherent reads, lifecycle and atomic terminal audit | A new process has no run, receipt, snapshot, or retained claim. An external effect can survive and an explicit new submission can invoke it again. No durability or persisted deduplication. |
| P1: core with local SQLite store | P0 in-process guarantees plus lease ownership, target/run pinning, strict durable carriers, backup/restore | An abrupt owner exit leaves no committed claim, interrupted work, or the complete snapshot/record/audit cut. Startup classifies without invoking again. |
| P2: authenticated ASGI adapter over a P1 core | P1 plus transport authentication, spoofing rejection, actor-bound disclosure, revision-bearing reads and lifespan ownership | The same durable owner boundaries are exercised through HTTP submission and status reads. Multiple clients do not imply multiple service owners. |

The composition factory is test-only. It does not publish capability discovery
or a second production profile registry; CP-10 owns that surface.

## Evidence map

Paths below are relative to `implementations/python/tests/`.

| Obligation | Executable evidence |
| --- | --- |
| Abrupt claim, dispatch/effect, terminal write, commit and response boundaries | `test_issue_1187_control_plane_process_loss.py`; a spawned child acknowledges the exact cut and blocks before its supervisor kills it. Partial claim and snapshot/record/audit writes delegate to the real SQLite transaction. |
| Reconciliation, repeated reopen and interrupted recovery commits | The same process suite plus `test_issue_1179_startup_reconciliation.py`; independently retained backend events and snapshots distinguish absence/applied observations from no observation. |
| Shared P0/P1/P2 idempotency, concurrency, isolation, CAS/cache coherence and restored receipts | `test_issue_1187_control_plane_profiles.py` |
| Every legal/illegal state pair, bounded generated sequences, all operation kinds and exact retry | `test_issue_1187_control_plane_lifecycle_properties.py`; its independent FM3 oracle also detects a deliberately disabled transition guard. |
| Well-hashed malformed carriers and integrity failures | `test_issue_1187_control_plane_durable_carriers.py` plus the #1092, #1181 and #1182 codec tests; rejection preserves the invalid offline history and performs no backend invocation. |
| Authentication configuration, provider redaction and audit-failure responses | `test_issue_1187_control_plane_security_conformance.py`, `test_runtime_control_plane_api.py`, `test_issue_1093_request_rejection_offload.py`, and the marked required-observation failure case in `test_issue_1212_observation_demand.py` |
| Operation-family entry points, snapshot-bearing/operation-only commits, participant heads and cross-family serialization | `test_issue_1181_unified_control_plane_mutations.py`, `test_runtime_control_plane.py`, `test_runtime_control_plane_api.py`, `test_run_310_supervisory_lifecycle.py`, and `test_run_319_participant_flow_policy.py` |
| Lease/process admission, scope pinning, filesystem/WAL/migration discipline | `test_issue_1092_control_plane_crash_consistency.py` and `test_issue_1183_store_ownership_leases.py` |
| CAS, store-authoritative idempotency and cache readback | `test_issue_1180_snapshot_revision_cas.py` and `test_issue_1184_atomic_idempotency_claims.py` |
| Recovery operations, health, restore rollback and secondary-audit failures | `test_issue_1186_control_plane_recovery_operations.py` |

The abrupt-process matrix uses an admitted empty provisioning plan and a
reference stub without a realization envelope. Its independent effect witness
records dispatch, applied outcome, and the actual neutral snapshot. This keeps
the observation within its existing authority: recovery may not invent a
provisioning plan or authorize new resource/realization state from an observer's
assertion. Existing rejection cases cover semantically invalid applied results.
The logical snapshot revision still changes only with the atomic terminal cut.
Per-family entry-point tests and store tests over every `OperationKind` complement
this common mutation-path crash matrix; they are not separate end-to-end crash
claims for every possible participant or backend operation.

Test results are finite evidence for the named composition, case, and platform.
Report platform skips, selected lanes and failures explicitly. Process termination
does not establish power-loss durability on arbitrary filesystems. A simulated
Windows lock branch on POSIX does not establish native Windows behavior.

The suite makes no P3 coordination, multi-owner/tenant service, exactly-once
external-effect, tamper-evidence, or universal recovery-proof claim. Payload
digests detect corruption; a writer able to replace both content and digest is
not thereby authenticated. ASGI tests do not verify deployment TLS, trusted-proxy
header stripping, external backend recovery, or a matching backend backup.

## API-404 clause verification

[API-404](../../requirements/API-404/requirement.md) states the clauses and
the profiles each clause binds. `profile_declaration()` holds each profile's
guarantee and nonclaim identifiers. The table maps each clause to the landed
code, conformance cases, and operator guidance behind it. Code paths are
relative to `implementations/python/packages/raes_runtime/`, and test paths to
`implementations/python/tests/`.

A P1 core, and so the P2 server over it, can select one of two durable stores:
the SQLite store (`control_plane_store_local.py`) or the PostgreSQL ledger
(`control_plane_store_postgresql.py`). Both declare every store capability
that P1 requires. The rows also cite the supervised-execution path that
issue #1362 added. Each row holds every `raes_runtime` code file, test and
document that an API-404 trace line names for that clause.

| Clause | Profiles | Implementation | Conformance cases | Operator guidance |
| --- | --- | --- | --- | --- |
| `API-404-C1` | P0, P1, P2 | `control_plane.py`, `control_plane_configuration.py`, `control_plane_operation_context.py`, `control_plane_admission.py`, `control_plane_mutation.py`, `control_plane_execution.py`, `control_plane_store.py`, `control_plane_store_revision.py`, `control_plane_store_memory.py`, `control_plane_store_local_snapshot.py`, `control_plane_store_postgresql.py`, `control_plane_store_postgresql_mutations.py`, `control_plane_supervised_execution.py`, `control_plane_supervision.py`, `operation_invocation_ledger.py`, `operation_transcript_policy.py`, `operation_execution_adapter.py`, `operation_command_commitment.py`, `operation_result_finalization.py`, `operation_reconciliation.py`, `operation_worker_authority.py`, `operation_temporal_worker.py`, `runtime_resource_ownership.py`, `manager_lifecycle.py` | `test_issue_1187_control_plane_profiles.py`, `test_issue_1187_control_plane_lifecycle_properties.py`, `test_issue_1184_atomic_idempotency_claims.py`, `test_issue_1180_snapshot_revision_cas.py`, `test_issue_1181_unified_control_plane_mutations.py`, `test_issue_1189_control_plane_profile_declarations.py`, `test_issue_1435_profile_clause_verification.py`, `test_issue_1362_postgresql_store.py`, `test_issue_1362_state_authority.py`, `test_issue_1362_runtime_supervision.py`, `test_issue_1362_bounded_execution.py`, `test_issue_1362_invocation_ledger.py`, `test_issue_1362_provider_execution.py`, `test_issue_1362_reconciliation.py`, `test_issue_1362_distributed_authority.py`, `test_issue_1362_commit_authority.py`, `test_issue_1362_temporal_worker.py`, `test_issue_1362_runtime_imports.py`, `test_issue_1362_review_regressions.py`, `test_issue_1362_control_budget.py`, `test_issue_1362_review_round_two.py`, `test_issue_1362_command_privacy.py`, `test_issue_1362_observation_retention.py`, `test_issue_1362_distributed_integration.py`, `test_issue_1362_resource_ownership.py` | [Control-plane operating profiles](../../explain/sdl/runtime-architecture.md#control-plane-operating-profiles) |
| `API-404-C2` | P1, P2 | `control_plane_store_local.py`, `control_plane_store_local_records.py`, `control_plane_store_local_scope.py`, `control_plane_store_local_codec.py`, `control_plane_store_records.py`, `control_plane_store_lease.py`, `control_plane_durability.py`, `control_plane_recovery.py`, `control_plane_store_postgresql.py`, `control_plane_store_postgresql_mutations.py`, `control_plane_store_postgresql_schema.py`, `control_plane_store_local_invocations.py`, `control_plane_supervised_execution.py`, `operation_invocation_ledger.py`, `operation_transcript_policy.py`, `operation_command_commitment.py`, `operation_result_finalization.py`, `operation_reconciliation.py`, `operation_worker_authority.py`, `operation_temporal.py`, `operation_temporal_worker.py` | `test_issue_1187_control_plane_process_loss.py`, `test_issue_1187_control_plane_durable_carriers.py`, `test_issue_1179_startup_reconciliation.py`, `test_issue_1183_store_ownership_leases.py`, `test_issue_1092_control_plane_crash_consistency.py`, `test_issue_1187_control_plane_profiles.py`, `test_issue_1362_postgresql_store.py`, `test_issue_1362_invocation_ledger.py`, `test_issue_1362_reconciliation.py`, `test_issue_1362_distributed_authority.py`, `test_issue_1362_lost_ack.py`, `test_issue_1362_temporal_worker.py`, `test_issue_1362_review_regressions.py`, `test_issue_1362_control_budget.py`, `test_issue_1362_review_round_two.py`, `test_issue_1362_command_privacy.py`, `test_issue_1362_observation_retention.py`, `test_issue_1362_distributed_integration.py`, `test_issue_1435_profile_clause_verification.py` | [Control-plane operations](../../explain/sdl/control-plane-operations.md), [Supervised execution](../../public/guides/supervised-execution.md) |
| `API-404-C3` | P2 | `control_plane_api/__init__.py`, `control_plane_api/_auth.py`, `control_plane_api/_offload.py`, `control_plane_api/_operation_routes.py`, `control_plane_api/_responses.py`, `control_plane_api_guards.py`, `control_plane_api_participant_retrieval.py`, `control_plane_security.py`, `control_plane_api/_supervision_routes.py`, `control_plane_supervision.py`, `operation_execution_adapter.py` | `test_issue_1187_control_plane_security_conformance.py`, `test_issue_1359_runtime_api_trust_boundary.py`, `test_issue_1093_request_rejection_offload.py`, `test_runtime_control_plane_api.py`, `test_issue_1187_control_plane_profiles.py`, `test_issue_1362_runtime_supervision.py`, `test_issue_1362_supervision_http.py`, `test_issue_1362_http_capacity.py`, `test_issue_1362_review_regressions.py`, `test_issue_1362_review_round_two.py`, `test_issue_1362_distributed_integration.py` | [Serve the runtime control plane](../../public/guides/control-plane.md) |
| `API-404-C4` | P0, P1, P2; P3 is unavailable | `control_plane_profiles.py` | `test_issue_1189_control_plane_profile_declarations.py`, `test_issue_1185_api_404_profile_alignment.py`, `test_issue_1187_control_plane_process_loss.py` | [Control-plane operating profiles](../../explain/sdl/runtime-architecture.md#control-plane-operating-profiles), [Supervised execution](../../public/guides/supervised-execution.md) and the limits above |

Each property #8 names is checked on every profile that guarantees it:

- **Actor binding.** Retry, readback and disclosure stay with the submitting
  actor on P0, and on P1 and P2 with the SQLite store
  (`test_issue_1187_control_plane_profiles.py::test_profile_scoped_retry_status_audit_and_cache_coherence`).
  The PostgreSQL ledger finds a retained claim only for the actor that made it
  (`test_issue_1435_profile_clause_verification.py::test_postgresql_ledger_claims_stay_with_the_submitting_actor`).
- **Target and run binding.** A selected P0 store refuses another target
  (`test_issue_1189_control_plane_profile_declarations.py::test_selected_p0_uses_canonical_declaration_and_binds_one_scope`)
  and another run
  (`test_issue_1435_profile_clause_verification.py::test_selected_p0_store_cannot_be_rebound_to_another_run`).
  A P1 or P2 SQLite store refuses both
  (`test_issue_1187_control_plane_profiles.py::test_profile_lease_scope_and_restore_keep_receipts_and_claims`).
  A selected P1 core refuses a PostgreSQL ledger bound to another target or
  run at admission, before it reads an operation or changes the ledger
  (`test_issue_1435_profile_clause_verification.py::test_selected_p1_refuses_a_postgresql_ledger_for_another_scope`).
  The ledger also refuses a record for another target or run before it writes
  (`test_issue_1362_postgresql_store.py::test_postgresql_mutation_admits_exact_record_scope_before_writing`).
  On every profile, an evaluation plan for another run that carries no
  operations or observation demands leaves no record, effect, audit or revision
  change. The same plan for the admitted run adds one record, one terminal
  audit and one evaluator start in the backend-effect witness, and moves the
  snapshot revision from 0 to 1
  (`test_issue_1435_profile_clause_verification.py::test_request_for_another_run_changes_nothing`).
  On P2, the provisioning, orchestration and evaluation routes check planner
  authorization for a plan that carries operations or observation demands,
  before the core's run check (`control_plane_api/_operation_routes.py`). So P2
  refuses an unregistered evaluation plan for another run that carries an
  operation with 403 and the route's `planner-authorization-mismatch` denial
  audit. P0 and P1 refuse it on the run check with no audit. No profile adds a
  record or effect, and the revision stays 0
  (`test_issue_1435_profile_clause_verification.py::test_plan_with_operations_for_another_run_leaves_no_record_or_effect`).
  The run refusal itself is not an admission denial, which the
  [CP-2 preflight](../../decisions/issue-1181-unified-control-plane-mutations-preflight.md)
  defines as an `accepted=False` receipt plus the bounded denial audit and no
  stored operation. P0 and P1 raise `ValueError` and P2 answers 409, with no
  receipt. The
  [CP-5 preflight](../../decisions/issue-1183-store-ownership-lease-preflight.md)
  requires a request for another run to fail before claim or disclosure, and
  `operation_admission_context()` refuses it before building the operation
  context that the core's admission-denial audit records.
- **Atomic state and audit.** Every operation kind commits its terminal state
  with exactly one actor-bound audit on P0 and P1
  (`test_issue_1187_control_plane_lifecycle_properties.py::test_each_operation_kind_commits_one_immutable_actor_bound_terminal_cut`),
  and so does an HTTP submission on P2
  (`test_issue_1187_control_plane_profiles.py::test_profile_scoped_retry_status_audit_and_cache_coherence`).
  With the PostgreSQL ledger, an operation delivered through the HTTP server
  keeps exactly one terminal audit after a duplicate delivery
  (`test_issue_1362_distributed_integration.py::test_real_delivery_control_and_reopening_preserve_the_consumed_fence`).
- **Retained idempotency.** P1 and P2 with the SQLite store keep receipts and
  claims across restore
  (`test_issue_1187_control_plane_profiles.py::test_profile_lease_scope_and_restore_keep_receipts_and_claims`).
  The PostgreSQL ledger returns the original receipt for a retry after
  process loss
  (`test_issue_1362_distributed_integration.py::test_actual_process_loss_never_reissues_a_consumed_grant`).
  P0 loses them with its process
  (`test_issue_1187_control_plane_process_loss.py::test_p0_process_loss_loses_run_and_claim_even_when_external_effect_survives`).
- **Ownership.** A P0 store has one live owner
  (`test_issue_1189_control_plane_profile_declarations.py::test_selected_p0_store_has_one_active_owner_and_releases_it_on_close`).
  P1 and P2 admit one SQLite lease owner and refuse a second
  (`test_issue_1187_control_plane_profiles.py::test_profile_lease_scope_and_restore_keep_receipts_and_claims`).
  A selected P1 core refuses a PostgreSQL ledger that another session owns,
  and one ledger object admits only one runtime
  (`test_issue_1435_profile_clause_verification.py::test_selected_p1_admits_one_postgresql_ledger_owner`).
- **Revision checks.** A stale snapshot write fails on every profile
  (`test_issue_1187_control_plane_profiles.py::test_profile_scoped_retry_status_audit_and_cache_coherence`).
  The PostgreSQL ledger refuses a stale terminal commit before it writes
  (`test_issue_1362_postgresql_store.py::test_postgresql_terminal_boundary_rejects_stale_revision_before_any_write`).
- **Startup classification.** P1 and P2 with the SQLite store classify
  interrupted work without replay
  (`test_issue_1187_control_plane_process_loss.py::test_process_loss_preserves_atomic_cut_and_classifies_without_replay`).
  The PostgreSQL ledger does the same after an abrupt loss at each grant,
  dispatch and terminal boundary
  (`test_issue_1362_distributed_integration.py::test_actual_process_loss_never_reissues_a_consumed_grant`).
  It does not apply to P0, which keeps no state across process loss.

The two `test_issue_1362_distributed_integration.py` cases need a live
PostgreSQL database and Temporal service. They run only in the CI
`runtime-supervision` job and the canonical integration lane, which set
`RAES_EXECUTION_INTEGRATION=1`. They compose the ledger without a selected
profile. The `test_issue_1435_profile_clause_verification.py` ledger cases
select P1 and use an in-memory stand-in for the database connection.

P2 serves a selected P1 core and adds no store of its own. So its C1 and C2
evidence is the evidence for the P1 core's store, SQLite or PostgreSQL, plus
the HTTP cases.
`test_issue_1435_profile_clause_verification.py` derives each clause's profiles
from `profile_declaration()`: the available profiles whose guarantees include
the clause's identifiers, or every available profile for C4. It fails if that
set, this table and an independently written expectation disagree. It also
fails if an Implementation or Conformance cell holds an entry that is not a
cited file, if the section cites a file or test that does not exist, or if a
link names a missing page or heading. An API-404 trace line that names clauses
must appear in each named row. Its code file must be in the Implementation
cell, its test in the Conformance cell, and its documentation in the Operator
guidance cell. The check reads code under `raes_runtime`, tests under
`implementations/python/tests/` and pages under `docs/`. It skips other traced
files, such as CI workflows.
