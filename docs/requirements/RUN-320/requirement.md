---
id: RUN-320
title: "Modular Participant-Control Orchestration and Governed Trigger Execution"
status: ACTIVE
type: FUNCTIONAL
priority: MUST
wave: 4
created_at: 2026-09-06T00:00:00Z
updated_at: 2026-09-20T00:00:00Z
---

# RUN-320 — Modular Participant-Control Orchestration and Governed Trigger Execution

## Statement

The RAES runtime shall invoke admitted participant-control providers through
the public protocol, compose their exact-cut results under SEM-235, and admit
and commit every effective decision and typed effect intent through existing
crossing/control and operation-store authority before backend effect or
participant disclosure. It shall preserve append-only contribution, provider
state, causal and realization evidence; fresh derived identities; stable
logical effect keys; finite root/depth/firing/retry budgets; predecessor and
subsequent effect distinctions; and ordinary downstream admission. Missing
mandatory support, unaccepted weakening, stale state, conflict, exhausted
required triggers and failed commit shall cause no prohibited dispatch.
Recovery shall distinguish intent, dispatch, observed application and external
uncertainty without blind duplicate execution or unsupported exactly-once
claims. Runtime orchestration shall not select or load scenario-designated
code, implement backend-specific mechanism branches, or take ownership of
out-of-world provider integrity.

## Rationale

RUN-319 and RUN-310 supply crossing/control enforcement and ADR-104 supplies
operation durability. The new owner adds mechanism-neutral composition and
bounded triggered execution while retaining those boundaries.

## Fulfillment boundary

DRAFT through #1068. #1069 delivers the reference-runtime orchestration against
the published API-424 contracts: the implicit SEM-233 resolver hook is replaced
by an explicitly selected adapter, providers are invoked only through
`participant-control-provider/v1`, and the composed evaluation commits to the
ADR-104 store before any backend effect or participant disclosure. ACTIVE is
proposed in this delivery diff and becomes authoritative on merge. Synthetic
providers are runtime evidence only; downstream providers own real
instrumentation, and this delivery claims no production mechanism, external
exactly-once effect, or backend equivalence.

## Traceability

- DOCUMENTS → GITHUB_ISSUE `https://github.com/OpenRAE/rae/issues/1068` (Architecture)
- DOCUMENTS → GITHUB_ISSUE `https://github.com/OpenRAE/rae/issues/1069` (Runtime orchestration)
- DOCUMENTS → ADR `docs/decisions/adrs/adr-108-modular-participant-control-and-governed-effects.md` (ADR-108)
- DOCUMENTS → DOCUMENTATION `docs/research/modular-participant-control/composition.md` (PC-05 through PC-12 and PC-15)
- TESTS → TEST `docs/research/modular-participant-control/check_design.py` (Bounded abstract transition counterexamples only)
- IMPLEMENTS → GITHUB_ISSUE `1069` (Runtime orchestration of participant-control mechanisms and triggered effects)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/participant_control_binding.py` (Admitted selection bound to exact operator-created providers)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/participant_control_orchestration.py` (Exact-cut resolution, protocol invocation, composition and commit before effect)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/participant_control_effects.py` (Governed dispatch of admitted effects through their incumbent owners)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/participant_control_evaluation_history.py` (Append-only composition and realization history invariants)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/control_plane_composition.py` (Explicitly negotiated modular-control and legacy SEM-233 selection)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/participant_flow_sink.py` (Declared final-sink resolver protocol replacing method-presence discovery)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/participant_crossing_boundary.py` (Modular control at the ingress action and control sinks)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/participant_crossing_egress.py` (Modular control before governed egress serialization)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/participant_control.py` (Runtime entry point for separately admitted effect dispatch)
- TESTS → TEST `implementations/python/tests/test_issue_1069_participant_control_orchestration.py` (Real-sink composition, zero-dispatch refusal and permuted provider order)
- TESTS → TEST `implementations/python/tests/test_issue_1069_participant_control_effects.py` (IFC-triggered inject and handoff, idempotent replay and unsupported owners)
- TESTS → TEST `implementations/python/tests/test_issue_1069_participant_control_binding.py` (Exact provider binding and revalidated selections)
- TESTS → TEST `implementations/python/tests/test_issue_1069_participant_control_durability.py` (Both stores, restart replay and concurrent stale writers)
- TESTS → TEST `implementations/python/tests/test_issue_1069_control_evaluation_carrier.py` (Append-only evaluation carrier and expected-head binding)
- DOCUMENTS → DOCUMENTATION `docs/decisions/issue-1069-run-320-runtime-orchestration-preflight.md` (Issue #1069 runtime orchestration architecture preflight)
- DOCUMENTS → DOCUMENTATION `docs/explain/reference/modular-participant-control-contracts.md` (Runtime orchestration reference and verification map)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/_snapshot_updates.py` (Participant-control evaluation history in the snapshot update surface)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/realization_plans.py` (Participant-control evaluation history in the published snapshot envelope)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/runtime_state.py` (First-class append-only participant-control evaluation carrier)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/backend_snapshot_contracts.py` (Runtime ownership of the participant-control evaluation carrier)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/control_plane.py` (Modular participant-control binding and explicit final-sink selection)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/control_plane_api_models.py` (Participant-control evaluation history in the control-plane projection)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/control_plane_audit.py` (Bounded participant-control audit references and realization action)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/control_plane_configuration.py` (Typed participant-control binding configuration)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/control_plane_store_history.py` (Participant-control evaluation history head resolution)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/control_plane_store_snapshots.py` (Durable persistence and absent-carrier classification)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/participant_action_validation.py` (Runtime-owned evaluation carrier protected from backend rewrite)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/participant_crossing_state_cut.py` (Shared state-cut head rendering for both final-sink owners)
- TESTS → TEST `implementations/python/tests/participant_crossing_fixtures.py` (Crossing fixtures binding a modular participant-control configuration)
- TESTS → TEST `implementations/python/tests/sem233_flow_sink_fixtures.py` (Explicit legacy SEM-233 final-sink selection in fixtures)
- TESTS → TEST `implementations/python/tests/test_issue_1003_final_sink_flow_enforcement.py` (Legacy SEM-233 enforcement under explicit selection)
- TESTS → TEST `implementations/python/tests/test_participant_concurrent_batch_reservations.py` (Exhaustive snapshot ownership including the evaluation carrier)
- TESTS → TEST `implementations/python/tests/test_issue_989_versioned_evidence.py` (Re-cut evidence releases pinned to the current source state)
- TESTS → TEST `implementations/python/tests/test_specification_coverage.py` (Re-cut coverage capture bound to the current implementation surfaces)
- DOCUMENTS → DOCUMENTATION `docs/research/specification-coverage/index.md` (Release 40.0.0 coverage capture for this source state)
- DOCUMENTS → DOCUMENTATION `docs/research/formal-semantic-validation/index.md` (Release 41.0.0 formal retest for this source state)
- TESTS → TEST `implementations/python/tests/participant_control_runtime_fixtures.py` (Synthetic providers and trusted resolvers bound to the live cut)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/participant_result_contracts.py` (Backend results preserve the runtime-owned evaluation history)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/participant_control_causal_state.py` (Durable causal consumption folded from committed history)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/participant_control_records.py` (Append-only realization transitions for dispatched effects)
- TESTS → TEST `implementations/python/tests/test_issue_1069_control_evaluation_authority.py` (A backend result can neither erase a committed evaluation nor forge a realization)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/participant_control_receipts.py` (Each effect acts for, and is claimed under, the operation that admitted it)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/control_plane_store_record_migration.py` (Schema 6 records the evaluation carrier; older builds refuse the store)
- TESTS → TEST `implementations/python/tests/test_issue_1092_control_plane_crash_consistency.py` (Migration reaches the current schema)
- TESTS → TEST `implementations/python/tests/test_issue_1180_snapshot_revision_cas.py` (Migration reaches the current schema)
- TESTS → TEST `implementations/python/tests/test_issue_1184_atomic_idempotency_claims.py` (Migration reaches the current schema)
- TESTS → TEST `implementations/python/tests/test_issue_1186_control_plane_recovery_operations.py` (Migration reaches the current schema)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/participant_control_cut.py` (Exact-cut binding to the committed crossing and retained consumption)
