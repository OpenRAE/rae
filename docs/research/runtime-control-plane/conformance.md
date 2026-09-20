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
