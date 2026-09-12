---
id: API-404
title: "Secure, Durable, And Idempotent Control-Plane Semantics"
status: ACTIVE
type: FUNCTIONAL
priority: MUST
wave: 1
created_at: 2026-04-03T05:55:58.825305Z
updated_at: 2026-09-11T05:07:15.000000Z
---

# API-404 — Secure, Durable, And Idempotent Control-Plane Semantics

## Statement

The control-plane contract shall support authenticated and authorized access, durable operation state, idempotent submission behavior, and auditable lifecycle actions.

## Rationale

Requirement inventory phase. Status audit deferred until the full canonical graph is complete.

## Traceability

- IMPLEMENTS → GITHUB_ISSUE `8` (API-404: Secure, Durable, And Idempotent Control-Plane Semantics)
- IMPLEMENTS → GITHUB_ISSUE `1151` (design(runtime): define the runtime control-plane architecture)
- DOCUMENTS → ADR `docs/decisions/adrs/adr-104-runtime-control-plane-architecture.md` (ADR-104: Runtime Control-Plane Architecture)
- DOCUMENTS → DOCUMENTATION `docs/research/runtime-control-plane/index.md` (Runtime control-plane architecture design set)
- DOCUMENTS → SPEC `specs/formal/runtime-control-plane/README.md` (ADR-104 FM3 abstract operation model and invariants)
- TESTS → TEST `implementations/python/tests/test_issue_1151_runtime_control_plane_design.py` (Structural acceptance gate for the design set)
- IMPLEMENTS → GITHUB_ISSUE `1182` (CP-1: Operation lifecycle contract)
- IMPLEMENTS → GITHUB_ISSUE `1181` (CP-2: Unified control-plane mutation commits)
- DOCUMENTS → GITHUB_ISSUE `1179` (CP-3: Startup reconciliation)
- IMPLEMENTS → GITHUB_ISSUE `1180` (CP-4: Snapshot revision compare-and-swap)
- DOCUMENTS → GITHUB_ISSUE `1183` (CP-5: Store lease admission)
- DOCUMENTS → GITHUB_ISSUE `1092` (CP-6: Transactional local store)
- DOCUMENTS → GITHUB_ISSUE `1184` (CP-7: Atomic idempotency claims and cache demotion)
- DOCUMENTS → GITHUB_ISSUE `1188` (CP-8: Served profile alignment)
- DOCUMENTS → GITHUB_ISSUE `1187` (CP-9: Crash and profile conformance suite)
- DOCUMENTS → GITHUB_ISSUE `1189` (CP-10: Profile declaration and capability discovery)
- DOCUMENTS → GITHUB_ISSUE `1185` (CP-11: API-404 requirement update)
- DOCUMENTS → GITHUB_ISSUE `1186` (CP-12: Recovery runbook and operator tooling)
- IMPLEMENTS → GITHUB_ISSUE `1090` (Fail-closed bearer-token authentication and target binding)
- IMPLEMENTS → GITHUB_ISSUE `1091` (Bounded pre-routing HTTP request admission)
- DOCUMENTS → GITHUB_ISSUE `1093` (In-process HTTP offload and rejection-audit slice)
- IMPLEMENTS → SPEC `contracts/schemas/control-plane/operation-receipt-v1.json` (Operation receipt JSON Schema — submission acknowledgment contract)
- IMPLEMENTS → SPEC `contracts/schemas/control-plane/operation-status-v1.json` (Operation status JSON Schema — durable operation state contract)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/operation_lifecycle.py` (Closed operation states, transitions, stable terminal diagnostics, and immutable admission context)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/operation_carriers.py` (Closed transport carriers and canonical terminal-diagnostic constraints)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/control_plane_operation_context.py` (Value-free canonical request commitment and authenticated actor binding)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/control_plane_admission.py` (Central actor-bound denial auditing and exact idempotency ownership checks)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/control_plane_store_record_migration.py` (Versioned legacy operation-record migration and denial-only disposition)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/control_plane_api/_auth.py` (Fail-closed bearer and verified-proxy authentication)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/control_plane_api/_offload.py` (Bounded worker offload and mutation admission)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/control_plane_api_guards.py` (Bounded fail-closed request-size admission and rejection-audit offload)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/control_plane_security.py` (HTTP admission and pending-work limits)
- DOCUMENTS → DOCUMENTATION `docs/decisions/issue-1093-control-plane-offload-preflight.md` (In-process ASGI offload and rejection semantics)
- TESTS → TEST `implementations/python/tests/test_runtime_control_plane.py` (Core control-plane unit tests)
- TESTS → TEST `implementations/python/tests/test_runtime_control_plane_api.py` (HTTP/JSON control-plane API tests — auth, idempotency, durability, audit)
- TESTS → TEST `implementations/python/tests/test_issue_1182_operation_lifecycle_contract.py` (Closed transition matrix, malformed carriers, immutability, denial, semantic idempotency, and schema governance)
- TESTS → TEST `implementations/python/tests/test_issue_1093_request_rejection_offload.py` (Non-blocking, saturation-bounded, fail-closed request rejection audit tests)
- IMPLEMENTS → GITHUB_ISSUE `1092` (Make the local control plane crash-consistent and explicitly single-process)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/control_plane_mutation.py` (Operation-family-neutral logical mutation authority and guarded extension callback boundary)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/control_plane_execution.py` (Write-ahead RUNNING claims, guarded backend validation and execution, and terminal commit routing)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/control_plane_store.py` (Provider-neutral store contracts, transition validation, and actor-bound audit provenance)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/control_plane_store_memory.py` (In-memory actor-bound atomic terminal commits with explicit revision outcomes)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/control_plane_store_types.py` (Explicit portable snapshot-bearing and operation-only terminal commit modes)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/control_plane_durability.py` (Atomic commit-outcome cache publication, readback reconciliation, and poison-on-unknown behavior)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/control_plane_lifecycle.py` (Draining close, nested-call admission, and durability-poison boundary)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/control_plane_store_lease.py` (Secure single-process local runtime ownership)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/control_plane_store_snapshots.py` (Compatibility-preserving portable snapshot serialization split)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/control_plane_store_local.py` (Required WAL admission, pinned database identity, durable legacy backup copies, and atomic transactions)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/control_plane_store_records.py` (Strict lossless decoding of persisted operation and audit provenance)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/control_plane_store_legacy.py` (Complexity-bounded legacy JSON import readers)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/control_plane_store_paths.py` (Descriptor-verified private directories, fail-closed durability synchronization, and metadata-only SQLite path validation)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/control_plane_store_compatibility.py` (Fail-closed admission for complete atomic store capabilities)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/control_plane_store_revision.py` (Provider-neutral logical revision state, validation, and conflict signal)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/control_plane_store_history.py` (Participant-history concurrency guards for snapshot-bearing commits)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/control_plane_store_local_codec.py` (SQLite transaction and durable payload integrity primitives)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/control_plane_store_local_snapshot.py` (SQLite paired snapshot reads and transactional compare-and-swap writes)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/control_plane.py` (Unified mutation admission, authoritative revision-bound reads, and cache rebuild coordination)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/participant_control.py` (Repeatable decision-surface binding across the shared participant mutation authority)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/participant_decision_surface_control_v2.py` (Exact-cut v2 decision-surface admission across the shared mutation authority)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/control_plane_api/_operation_routes.py` (Revision-identifying snapshot and operational-summary reads)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/control_plane_api_participant_retrieval.py` (Revision-identifying participant view reads)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/participant_retrieval_context.py` (Runtime-owned participant context revision-path policy)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/participant_crossing_projection.py` (Stable participant projection subjects across provider revisions)
- DOCUMENTS → DOCUMENTATION `docs/decisions/issue-1092-local-control-plane-durability-preflight.md` (Crash recovery and supported process topology)
- DOCUMENTS → DOCUMENTATION `docs/decisions/issue-1180-snapshot-revision-cas-preflight.md` (Snapshot CAS architecture guardrails and compatibility boundaries)
- TESTS → TEST `implementations/python/tests/test_issue_1092_control_plane_crash_consistency.py` (Atomic terminal rollback, WAL admission, durable path handling, uncertain-commit preservation, multiprocess stress, retry, and runtime-owner tests)
- TESTS → TEST `implementations/python/tests/test_issue_1180_snapshot_revision_cas.py` (Interleaved stale writers, cache rebuild, provider metadata isolation, and SQLite revision migration)
- IMPLEMENTS → DOCUMENTATION `docs/decisions/issue-1181-unified-control-plane-mutations-preflight.md` (CP-2 mutation authority, write-ahead claim, atomic terminal cut, and compatibility boundaries)
- TESTS → TEST `implementations/python/tests/test_issue_1181_unified_control_plane_mutations.py` (CP-2 authority, claim ordering, validation gate, atomicity, audit provenance, capability, recovery, and facade-boundary acceptance tests)
