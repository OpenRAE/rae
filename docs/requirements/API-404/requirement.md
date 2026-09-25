---
id: API-404
title: "Secure, Durable, And Idempotent Control-Plane Semantics"
status: ACTIVE
type: FUNCTIONAL
priority: MUST
wave: 1
created_at: 2026-04-03T05:55:58.825305Z
updated_at: 2026-09-23T00:00:00.000000Z
---

# API-404 — Secure, Durable, And Idempotent Control-Plane Semantics

## Statement

The runtime control plane shall expose only explicitly selected operating
profiles and shall satisfy the applicable stable clauses below. A profile makes
no guarantee outside its matrix row.

## Contract clauses

### API-404-C1 — Common in-process control

P0, P1, and P2 shall preserve typed actor provenance, authorize every mutation
and disclosure, isolate one target and run, scope idempotency to the actor and
operation context, validate admitted state, compare revisions before snapshot
writes, route mutations through one authority, and commit terminal operation
state with its operational audit atomically. The corresponding runtime
guarantee identifiers are `in-process-safety`, `actor-scoped-idempotency`,
`target-run-isolation`, `revision-cas`, and `atomic-audit`.

P0 receives its actor identity from the trusted embedder. P0 process loss
discards operation state, idempotency records, and audit evidence held by the
composition. P0 does not provide durability, restart recovery, or retained
deduplication across process loss.

For P0/P1 SDK use, the host application owns participant-facing caller
authentication, entitlement and result release. Direct Python methods have no
P2 transport authentication: `get_snapshot()` returns the full snapshot
without a caller identity, and participant retrieval accepts optional identity
context. The host keeps the control-plane object and store private, binds a
participant request to its target/run, participant, exact episode, audience
and operation, and releases only a permitted governed projection after a
configured API-423/RUN-319 crossing. The current legacy no-resolver retrieval
path can return a view without that crossing; the host must reject it for
participant-facing use. Local hosts need no organizational account model.

### API-404-C2 — Durable local control

P1 and P2 shall add crash-consistent authoritative state, retained idempotency
claims, exclusive owner-lease admission, strict persisted carriers, and startup
classification without automatic effect replay. The corresponding runtime
guarantee identifiers are `durable-state`, `retained-idempotency`,
`lease-admission`, and `startup-reconciliation`.

Durability and a retained idempotency claim shall not authorize another
invocation, continuation, termination or new trial. Such choices remain governed
by admitted authored requirements and the existing workflow, time and trial
authorities; an unsupported or refused required guarantee shall not be weakened.

### API-404-C3 — Served transport control

P2 shall add bounded authenticated HTTP admission, actor-bound disclosure,
owner-serialized mutation, and revision-bearing reads over an explicitly
selected P1 core. The corresponding runtime guarantee identifiers are
`authenticated-transport`, `actor-bound-disclosure`,
`owner-serialized-mutation`, and `revision-carrying-reads`. Only P2
authenticates transport callers; P0 and P1 rely on their trusted embedders.

P2 identities are deployment-configured bearer tokens or verified proxy
identities, not RAES-issued participant credentials. A host may use one as a
service identity. Read-role admission to an API-408 participant projection
also permits full snapshot and operational reads; the participant/audience
binding used for governed projection is not a route-wide read restriction.
The host keeps its P2 identity private, binds its participant-facing caller to
target/run, participant, exact episode, audience and permitted operation, and
checks the returned view before release. P2 checks the configured identity's
target and role and, with a resolver, the governed crossing; it does not
authorize the host's end user or reject the legacy no-resolver path solely
because the result will be participant-facing. The host must not release raw
snapshot, operation, history, event, error or cached control-plane outputs as
participant views. Organizational identity and policy remain with an
organizational host such as BigRAE. This interpretation adds no P2 profile
guarantee or SDL participant role.

### API-404-C4 — Excluded stronger claims

P0, P1, and P2 shall not imply high availability, multitenancy, multi-owner
coordination, exactly-once backend effects, TLS or proxy deployment correctness,
or universal recovery proof. P3 is unavailable and satisfies no API-404 clause;
coordination, fencing, scheduling, cache coherence, partition behavior, and
tenant isolation require a future ADR and formal model.

## Profile-to-clause matrix

| Profile | Required clauses | Guarantee identifiers | Explicit boundaries |
| --- | --- | --- | --- |
| P0 | `API-404-C1` | `in-process-safety`, `actor-scoped-idempotency`, `target-run-isolation`, `revision-cas`, `atomic-audit` | Process-lifetime state only; no durability, restart recovery, retained deduplication after loss, or authenticated transport. |
| P1 | `API-404-C1`, `API-404-C2` | `in-process-safety`, `actor-scoped-idempotency`, `target-run-isolation`, `revision-cas`, `atomic-audit`, `durable-state`, `retained-idempotency`, `lease-admission`, `startup-reconciliation` | Trusted-embedder identity; no authenticated transport, multi-owner operation, or exactly-once backend effects. |
| P2 | `API-404-C1`, `API-404-C2`, `API-404-C3` | `in-process-safety`, `actor-scoped-idempotency`, `target-run-isolation`, `revision-cas`, `atomic-audit`, `durable-state`, `retained-idempotency`, `lease-admission`, `startup-reconciliation`, `authenticated-transport`, `actor-bound-disclosure`, `owner-serialized-mutation`, `revision-carrying-reads` | One P1 owner and one target/run scope; TLS, proxy correctness, high availability, and multitenancy remain deployment or future-profile duties. |
| P3 | none | none | Unavailable; no guarantee or implementation claim. |

## Rationale

The control-plane implementations deliberately provide cumulative operating
profiles rather than one universal durability and transport contract. Stable
clause identifiers keep requirement traceability aligned with the runtime-owned
profile catalog while preserving the distinction between trusted-embedder
identity, crash-persistent local control, and authenticated served admission.
ADR-104 and the FM3 model define the architecture; landed code and automated
tests provide implementation evidence.

## Supervision interpretation and fulfillment boundary

The [ADR-104 supervision supplement](../../../specs/formal/runtime-control-plane/supervision.md)
defines the design interpretation adopted by issue #1348. C1's single authority
serializes state mutation; it does not require holding the supervision permit
through external execution. Cancellation request, backend acceptance/refusal,
established cessation, terminal operation outcome and independent cleanup are
distinct. Atomic state publication and local CAS do not prove external fencing.
C2's startup classification never supplies implicit replay or resumption.
C3's bounded authenticated admission also constrains the designed supervisory
path. C4's nonclaims remain applicable, including unavailable P3.

The existing profile matrix is unchanged. API-404 remains ACTIVE for those
implemented clauses; the supplement and its finite model establish design
semantics only. They do not certify that current runtime calls or shutdown are
bounded, that backend effects can be interrupted, or that a general continuation
carrier exists. The [decision](../../decisions/issue-1348-operation-lifecycle.md)
identifies those implementation gaps and the retained canonical requirements.

## Traceability

- DOCUMENTS → GITHUB_ISSUE `1356` (Control-plane and participant-access trust boundary)
- DOCUMENTS → DOCUMENTATION `docs/decisions/issue-1356-control-plane-participant-access-preflight.md` (Accepted exposure model, route authority matrix, deployment and crossing guardrails)

- DOCUMENTS → GITHUB_ISSUE `1350` (Execution architecture selection; no new executable profile claim)
- DOCUMENTS → ADR `docs/decisions/adrs/adr-113-reusable-execution-machinery.md` (Reusable machinery, retained RAE authority and deployment boundaries)
- DOCUMENTS → DOCUMENTATION `docs/research/execution-architecture/execution-protocol.md` (Ledger/engine reconciliation, scoped worker authorization and conservative ownership recovery design)
- DOCUMENTS → DOCUMENTATION `docs/research/execution-architecture/authored-retry-policy.md` (Contextual author failure/retry policy, scoped defaults and fresh-trial distinctions; public support requires implementation)
- DOCUMENTS → DOCUMENTATION `docs/research/execution-architecture/experiment-report.md` (Bounded mechanism observations, not distributed conformance evidence)
- TESTS → TEST `implementations/python/tests/test_issue_1350_fixture_secret_scan.py` (Design-evidence publication checks: retained experiment source hashes match their record, and the exact synthetic fixture exception preserves detection of other values, paths and rules through the real-scanner integration lane; no runtime conformance claim)

- DOCUMENTS → GITHUB_ISSUE `1348` (Operation supervision decision; no new executable profile claim)
- DOCUMENTS → DOCUMENTATION `docs/decisions/issue-1348-operation-lifecycle-preflight.md` (Supervision architecture guardrails)
- DOCUMENTS → DOCUMENTATION `docs/decisions/issue-1348-operation-lifecycle.md` (Decision, requirement dispositions and implementation boundaries)
- IMPLEMENTS → SPEC `specs/formal/runtime-control-plane/supervision.md` (Design interpretation of operation supervision and authored recovery choices)
- TESTS → TEST `implementations/python/tests/operation_supervision_model.py` (Finite abstract model; no runtime conformance claim)
- TESTS → TEST `implementations/python/tests/test_issue_1348_operation_supervision.py` (Bounded supervision and recovery counterexamples)

- DOCUMENTS → GITHUB_ISSUE `8` (API-404: Secure, Durable, And Idempotent Control-Plane Semantics)
- DOCUMENTS → GITHUB_ISSUE `1151` (design(runtime): define the runtime control-plane architecture)
- DOCUMENTS → ADR `docs/decisions/adrs/adr-104-runtime-control-plane-architecture.md` (ADR-104: Runtime Control-Plane Architecture)
- DOCUMENTS → DOCUMENTATION `docs/research/runtime-control-plane/index.md` (Runtime control-plane architecture design set)
- DOCUMENTS → SPEC `specs/formal/runtime-control-plane/README.md` (ADR-104 FM3 abstract operation model and invariants)
- TESTS → TEST `implementations/python/tests/test_issue_1151_runtime_control_plane_design.py` (Structural acceptance gate for the design set)
- DOCUMENTS → GITHUB_ISSUE `1182` (CP-1: Operation lifecycle contract)
- DOCUMENTS → GITHUB_ISSUE `1181` (CP-2: Unified control-plane mutation commits)
- DOCUMENTS → GITHUB_ISSUE `1179` (CP-3: Startup reconciliation)
- DOCUMENTS → DOCUMENTATION `docs/decisions/issue-1179-startup-reconciliation-preflight.md` (CP-3 startup reconciliation classification, observation, authorization, and recovery boundaries)
- IMPLEMENTS → SPEC `contracts/schemas/backend-manifest/backend-manifest-v2.json` (Optional backend-neutral recovery-observation capability and supported operation kinds)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_backend_protocols/recovery_observation.py` (Closed value-free recovery classification request/result protocol)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_backend_protocols/backend_manifest.py` (Recovery-observation capability access on composed backend manifests)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_backend_protocols/capabilities.py` (Strict recovery-observation capability declaration)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_backend_protocols/manifest.py` (Recovery-observation manifest serialization and parsing)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/__init__.py` (Public recovery capability contract export)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/_exports.py` (Governed recovery capability export inventory)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/manifests.py` (Strict recovery-observation manifest contract model)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/runtime_state.py` (Public changed-address validation reused by recovery observations)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/registry.py` (Exact recovery manifest/component presence and signature validation)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/registry_target_validation.py` (Focused optional-component and recovery-observer target validation)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/manager.py` (Recovery-observer composition through registered runtime targets)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/control_plane_recovery.py` (Runtime-owned startup classification, atomic terminalization, quarantine, and linked resolution)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/control_plane_api/_auth.py` (Operator-only HTTP resolution authorization)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/control_plane_api/_operation_routes.py` (Redacted linked-resolution HTTP endpoint)
- TESTS → TEST `implementations/python/tests/test_issue_1179_startup_reconciliation.py` (Classification, no-replay, observer validation, manifest separation, quarantine, linkage, idempotency, authorization, and redaction tests)
- TESTS → TEST `implementations/python/tests/test_issue_989_versioned_evidence.py` (Current versioned evidence selection after recovery contract changes)
- TESTS → TEST `implementations/python/tests/test_specification_coverage.py` (Current specification-coverage bundle integrity after contract changes)
- TESTS → TEST `implementations/python/tests/test_formal_semantic_validation.py` (Current formal-semantic retest bundle integrity after runtime changes)
- IMPLEMENTS → CODE_FILE `tools/formal_semantic_validation/_baseline.py` (Versioned formal-evidence baseline selection)
- IMPLEMENTS → CODE_FILE `tools/formal_semantic_validation/_loading.py` (Complete formal-evidence release loading and current selection)
- IMPLEMENTS → CODE_FILE `tools/formal_semantic_validation/_releases.py` (Historical and current formal-evidence release validation)
- IMPLEMENTS → CODE_FILE `tools/formal_semantic_validation/_retest.py` (Current retained-corpus replay validation)
- IMPLEMENTS → CODE_FILE `tools/check_specification_coverage.py` (Complete specification-coverage release loading and current selection)
- DOCUMENTS → GITHUB_ISSUE `1180` (CP-4: Snapshot revision compare-and-swap)
- DOCUMENTS → GITHUB_ISSUE `1183` (CP-5: Store lease admission)
- DOCUMENTS → DOCUMENTATION `docs/decisions/issue-1183-store-ownership-lease-preflight.md` (CP-5 immutable scope, exclusive ownership, startup, and shutdown boundaries)
- DOCUMENTS → GITHUB_ISSUE `1092` (CP-6: Transactional local store)
- DOCUMENTS → GITHUB_ISSUE `1184` (CP-7: Atomic idempotency claims and cache demotion)
- DOCUMENTS → GITHUB_ISSUE `1188` (CP-8: Served profile alignment)
- DOCUMENTS → GITHUB_ISSUE `1187` (CP-9: Crash and profile conformance suite)
- DOCUMENTS → DOCUMENTATION `docs/decisions/issue-1187-control-plane-conformance-preflight.md` (CP-9 profile, fault-evidence, and security boundaries)
- DOCUMENTS → DOCUMENTATION `docs/research/runtime-control-plane/conformance.md` (Unified suite invocation, finite evidence map, and explicit profile nonclaims)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/backend_result_diagnostics.py` (Value-free backend failure diagnostics without provider type names)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/observation_execution.py` (Observation-adapter failure diagnostics without provider exception names or text)
- TESTS → TEST `implementations/python/tests/test_issue_1212_observation_demand.py` (Observation failures preserve terminal state and redact exception details from operation carriers)
- TESTS → TEST `implementations/python/tests/test_issue_1187_control_plane_profiles.py` (Shared P0/P1/P2 retry, isolation, concurrency, coherence, ownership, and restore checks)
- TESTS → TEST `implementations/python/tests/test_issue_1187_control_plane_process_loss.py` (Supervised abrupt loss across claim, invocation, terminal commit and recovery, with independent effect witnesses)
- TESTS → TEST `implementations/python/tests/test_issue_1187_control_plane_lifecycle_properties.py` (Independent lifecycle matrix, generated sequences, operation-kind audit coverage and enforcement mutation detection)
- TESTS → TEST `implementations/python/tests/test_issue_1187_control_plane_durable_carriers.py` (Fail-closed durable-carrier mutation and corruption checks on reopen)
- TESTS → TEST `implementations/python/tests/test_issue_1187_control_plane_security_conformance.py` (Configuration admission, provider error redaction, and denial response preservation)
- TESTS → TEST `implementations/python/tests/control_plane_conformance_fixtures.py` (Shared reference compositions and independent backend-effect witness)
- TESTS → TEST `implementations/python/tests/control_plane_crash_fixtures.py` (Supervised process termination at acknowledged real transaction boundaries)
- DOCUMENTS → DOCUMENTATION `docs/research/formal-semantic-validation/bundles/retest-v34.json` (Fresh retained formal and participant replay bound to CP-9 source without new claim classes)
- DOCUMENTS → DOCUMENTATION `docs/research/specification-coverage/bundles/raes-standardized-specification-coverage-issue-1187-v34.json` (Fresh retained language coverage replay bound to CP-9 source without crash-conformance claims)
- TESTS → TEST `implementations/python/tests/test_run_319_participant_flow_policy.py` (Operation-bound participant authorization, atomic crossing history, and idempotent replay in the conformance suite)
- DOCUMENTS → GITHUB_ISSUE `1189` (CP-10: Profile declaration and capability discovery)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/control_plane_profiles.py` (Canonical typed P0-P3 declarations and layer-qualified capability admission)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/__init__.py` (Public profile and capability declaration exports)
- DOCUMENTS → DOCUMENTATION `docs/explain/sdl/runtime-architecture.md` (Profile guarantees, nonclaims, selection, and deployment responsibilities)
- DOCUMENTS → DOCUMENTATION `docs/decisions/issue-1189-control-plane-profile-declaration-preflight.md` (CP-10 composition and capability boundary)
- TESTS → TEST `implementations/python/tests/test_issue_1189_control_plane_profile_declarations.py` (Profile matrix, fail-closed construction, cross-surface identity, and documentation drift tests)
- DOCUMENTS → DOCUMENTATION `docs/research/formal-semantic-validation/bundles/retest-v35.json` (Current retained formal and participant replay bound to CP-10 source without new profile claims)
- DOCUMENTS → DOCUMENTATION `docs/research/specification-coverage/bundles/raes-standardized-specification-coverage-issue-1189-v35.json` (Current retained language coverage replay bound to CP-10 source without profile-composition claims)
- DOCUMENTS → GITHUB_ISSUE `1185` (CP-11: API-404 requirement update)
- DOCUMENTS → DOCUMENTATION `docs/decisions/issue-1185-api-404-profile-alignment-preflight.md` (CP-11 profile and evidence boundaries)
- TESTS → TEST `implementations/python/tests/test_issue_1185_api_404_profile_alignment.py` (Clause matrix, profile catalog, nonclaims, public documentation, and local-evidence drift checks)
- DOCUMENTS → GITHUB_ISSUE `1186` (CP-12: Recovery runbook and operator tooling)
- DOCUMENTS → DOCUMENTATION `docs/decisions/issue-1186-control-plane-recovery-operations-preflight.md` (CP-12 recovery, maintenance, health, and disclosure boundaries)
- DOCUMENTS → DOCUMENTATION `docs/explain/sdl/control-plane-operations.md` (Operator recovery, health, shutdown, backup, restore, and upgrade runbook)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_cli/runtime.py` (Stable value-free local-store maintenance CLI)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/control_plane_api/_health_routes.py` (Public value-free liveness and readiness probes)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/control_plane_audit.py` (Bounded audit-carrier validation)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/control_plane_health.py` (Closed lifecycle, lease, poison, and recovery readiness projection)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/control_plane_store_maintenance.py` (Lease-admitted local integrity check, SQLite backup, migration, and restore operations)
- TESTS → TEST `implementations/python/tests/test_issue_1186_control_plane_recovery_operations.py` (CP-12 health, maintenance, migration, recovery, redaction, and failure-path acceptance tests)
- DOCUMENTS → GITHUB_ISSUE `1090` (Fail-closed bearer-token authentication and target binding)
- DOCUMENTS → GITHUB_ISSUE `1091` (Bounded pre-routing HTTP request admission)
- DOCUMENTS → GITHUB_ISSUE `1093` (In-process HTTP offload and rejection-audit slice)
- IMPLEMENTS → SPEC `contracts/schemas/control-plane/operation-receipt-v1.json` (Operation receipt JSON Schema — submission acknowledgment contract)
- IMPLEMENTS → SPEC `contracts/schemas/control-plane/operation-status-v1.json` (Operation status JSON Schema — durable operation state contract)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/operation_lifecycle.py` (Closed operation states, transitions, stable terminal diagnostics, and immutable admission context)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/operation_carriers.py` (Closed transport carriers and canonical terminal-diagnostic constraints)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/control_plane_operation_context.py` (Value-free canonical request commitment and authenticated actor binding)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/control_plane_configuration.py` (Trusted immutable run-scope composition)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/control_plane_plan_authorization.py` (Observed base-snapshot admission and planner artifact authorization)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/control_plane_admission.py` (Central actor-bound denial auditing and exact idempotency ownership checks)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/control_plane_store_record_migration.py` (Versioned legacy operation-record migration and denial-only disposition)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/control_plane_api/_auth.py` (Fail-closed bearer and verified-proxy authentication)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/control_plane_api/_offload.py` (Bounded worker offload and mutation admission)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/control_plane_api/__init__.py` (Single-worker admission and lifespan-owned runtime shutdown)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/control_plane_api_guards.py` (Bounded fail-closed request-size admission and rejection-audit offload)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/control_plane_security.py` (HTTP admission and pending-work limits)
- DOCUMENTS → DOCUMENTATION `docs/decisions/issue-1093-control-plane-offload-preflight.md` (In-process ASGI offload and rejection semantics)
- TESTS → TEST `implementations/python/tests/test_runtime_control_plane.py` (Core control-plane unit tests)
- TESTS → TEST `implementations/python/tests/test_runtime_control_plane_api.py` (HTTP/JSON control-plane API tests — auth, idempotency, durability, audit)
- TESTS → TEST `implementations/python/tests/test_issue_1182_operation_lifecycle_contract.py` (Closed transition matrix, malformed carriers, immutability, denial, semantic idempotency, and schema governance)
- TESTS → TEST `implementations/python/tests/test_issue_1093_request_rejection_offload.py` (Non-blocking, saturation-bounded, fail-closed request rejection audit tests)
- DOCUMENTS → GITHUB_ISSUE `1092` (Make the local control plane crash-consistent and explicitly single-process)
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
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/control_plane_store_local_records.py` (SQLite atomic idempotency claims and operation-record persistence)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/control_plane_store_local_scope.py` (Immutable target/run binding and admitted legacy-store migration)
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
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/control_plane_api/_participant_routes.py` (Participant mutation routing with bounded synchronous receipt-audit submission)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/control_plane_api/_responses.py` (Receipt response conversion and bounded synchronous denial-audit submission)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/control_plane_api/_workflow_routes.py` (Workflow mutation routing with bounded synchronous receipt-audit submission)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/control_plane_api_participant_retrieval.py` (Revision-identifying participant view reads)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/participant_retrieval_context.py` (Runtime-owned participant context revision-path policy)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/participant_crossing_projection.py` (Stable participant projection subjects across provider revisions)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/participant_control_mediation.py` (Control-plane-owned fixed run scope for participant control operations)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/participant_crossing_mediation.py` (Control-plane-owned fixed run scope for crossing operations)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/participant_crossing_records.py` (Control-plane-owned fixed run scope for crossing record operations)
- DOCUMENTS → DOCUMENTATION `docs/decisions/issue-1092-local-control-plane-durability-preflight.md` (Crash recovery and supported process topology)
- DOCUMENTS → DOCUMENTATION `docs/decisions/issue-1180-snapshot-revision-cas-preflight.md` (Snapshot CAS architecture guardrails and compatibility boundaries)
- TESTS → TEST `implementations/python/tests/test_issue_1092_control_plane_crash_consistency.py` (Atomic terminal rollback, WAL admission, durable path handling, uncertain-commit preservation, multiprocess stress, retry, and runtime-owner tests)
- TESTS → TEST `implementations/python/tests/test_issue_1180_snapshot_revision_cas.py` (Interleaved stale writers, cache rebuild, provider metadata isolation, and SQLite revision migration)
- DOCUMENTS → DOCUMENTATION `docs/decisions/issue-1181-unified-control-plane-mutations-preflight.md` (CP-2 mutation authority, write-ahead claim, atomic terminal cut, and compatibility boundaries)
- TESTS → TEST `implementations/python/tests/test_issue_1181_unified_control_plane_mutations.py` (CP-2 authority, claim ordering, validation gate, atomicity, audit provenance, capability, recovery, and facade-boundary acceptance tests)
- TESTS → TEST `implementations/python/tests/test_issue_1183_store_ownership_leases.py` (CP-5 admission, scope binding, process ownership, shutdown ordering, and worker-posture acceptance tests)
- DOCUMENTS → DOCUMENTATION `docs/decisions/issue-1184-atomic-idempotency-claims-preflight.md` (CP-7 atomic claim, replay authorization, migration, and cache-authority boundaries)
- DOCUMENTS → DOCUMENTATION `docs/decisions/issue-1188-served-control-plane-profile-preflight.md` (CP-8 P2 identity, authorization, audit, read, error-redaction, and single-owner boundaries)
- TESTS → TEST `implementations/python/tests/test_issue_1184_atomic_idempotency_claims.py` (CP-7 atomic scoped claims, replay conflicts, migration, authorization, and authoritative-read regressions)
- TESTS → TEST `implementations/python/tests/test_dsl_437_snapshot_durability_conformance.py` (Snapshot durability conformance under explicit local-store admission)
- TESTS → TEST `implementations/python/tests/test_realization_envelope_contract.py` (Realization envelope persistence under explicit local-store admission)
- TESTS → TEST `implementations/python/tests/test_run_310_supervisory_lifecycle.py` (Supervisory lifecycle persistence under explicit local-store admission)
- TESTS → TEST `implementations/python/tests/test_sem_211_participant_action_semantics.py` (Participant action persistence under explicit local-store admission)
- TESTS → TEST `implementations/python/tests/test_libvirt_backend_techvault_honesty.py` (Backend admission preserves the explicitly admitted durable predecessor)
- TESTS → TEST `implementations/python/tests/test_issue_1204_reference_profiles.py` (API lifespan ownership preserves durable profile-validation predecessors)
- TESTS → TEST `implementations/python/tests/test_issue_1212_runtime_boundaries.py` (API lifespan ownership preserves rejected-evaluation predecessors)
- TESTS → TEST `implementations/python/tests/test_issue_802_participant_control_migration.py` (Legacy snapshot migration under explicit local-store admission)
- TESTS → TEST `implementations/python/tests/test_issue_899_participant_resource_budgets.py` (Participant resource-budget persistence under explicit local-store admission)
- TESTS → TEST `implementations/python/tests/test_issue_1241_materialization_durability.py` (Run-scoped materialization durability and restart behavior)
- TESTS → TEST `implementations/python/tests/test_issue_1242_scope_durability.py` (Run-scoped augmentation durability and retry behavior)
- DOCUMENTS → GITHUB_ISSUE `1069` (Composed control state committed through the ADR-104 store authority)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/participant_control_evaluation_history.py` (Append-only evaluation-history invariants in the runtime snapshot)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/control_plane_store_snapshots.py` (Durable persistence and absent-carrier classification)
- TESTS → TEST `implementations/python/tests/test_issue_1069_participant_control_durability.py` (P0 process-loss nonclaims and P1 restart replay)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/_snapshot_updates.py` (Participant-control evaluation history in the snapshot update surface)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/realization_plans.py` (Participant-control evaluation history in the published snapshot envelope)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/backend_snapshot_contracts.py` (Runtime ownership of the participant-control evaluation carrier)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/control_plane_api_models.py` (Participant-control evaluation history in the control-plane projection)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/participant_action_validation.py` (Runtime-owned evaluation carrier protected from backend rewrite)
