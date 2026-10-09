---
id: API-410
title: "Shared Operational State And Derived Context Contracts"
status: ACTIVE
type: INTERFACE
priority: SHOULD
wave: 3
created_at: 2026-04-03T06:16:04.699562Z
updated_at: 2026-10-09T00:00:00Z
---

# API-410 — Shared Operational State And Derived Context Contracts

## Statement

The ecosystem shall define plain-data contracts for shared operational state and derived participant-relevant context views.

## Rationale

Requirement inventory expansion. Shared state and derived context must be portable if they are visible outside a backend.

## Clause verification

- Shared operational state: `participant-shared-state-record-v1` (RUN-307)
  carries address, scope, kind, revision or digest, predecessor revisions,
  conflict policy, visibility basis, provenance, evidence, and read/write
  accesses whose revision markers the model and published schema both enforce.
  `runtime-snapshot-v1` holds current records and append-only history. Snapshot
  conformance and backend apply reject unresolved or mismatched shared state,
  and backend apply also rejects rewritten history. Joint-action records bind
  conflict classes and policies to overlapping reads and writes.
- Derived context: `participant-context-view-v1` (API-408, SEM-214) carries
  participant-local scope, audience, observation point, source layers with a
  freshness basis, transformation, evidence and provenance, comparability with
  backend disclosures, semantic limitations, visibility projection, and
  redaction policy.
- Composition: a view cites the snapshot that holds a shared-state revision. An
  ACT-604 information-state record joins a shared-state source and a
  context-view source only when identity, relation, participant, episode,
  visibility projection, and redaction policy agree, and the shared-state
  record falls inside the sequence cut.
- Retrieval: the runtime context view names the snapshot revision it came from.
  An unknown or mismatched participant or episode gets no view, a governed view
  needs exactly one audience binding, and unsupported projection options fail.
- Limits: no validator resolves a view's references against recorded
  shared-state revisions, and contract presence does not show that a backend
  can compute a given view. The composition reference note lists each limit.

## Traceability

- IMPLEMENTS → GITHUB_ISSUE `253` (Reconcile shared-state and derived-context contracts)
- IMPLEMENTS → SPEC `contracts/schemas/participant-runtime/participant-shared-state-record-v1.json` (Shared-state record with revision, predecessor, conflict, visibility, and access fields)
- IMPLEMENTS → SPEC `contracts/schemas/snapshots/runtime-snapshot-v1.json` (Current shared-state records and append-only shared-state history)
- IMPLEMENTS → SPEC `contracts/schemas/control-plane/participant-context-view-v1.json` (Derived context view with source, freshness, comparability, evidence, and limitation fields)
- IMPLEMENTS → SPEC `contracts/schemas/participant-runtime/participant-information-state-record-v1.json` (Typed shared-state and context-view information-state sources)
- IMPLEMENTS → SPEC `contracts/fixtures/participant-runtime/participant-shared-state-record-v1/valid/serialized-service-state-commit.json` (Published shared-state revision used by the composition example)
- IMPLEMENTS → SPEC `contracts/fixtures/control-plane/participant-context-view-v1/valid/network-posture-context.json` (Published positive context-view fixture)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/participant_envelopes.py` (Shared-state record and access revision-marker validation)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/participant_context.py` (Context-view source binding, freshness, comparability, and audience-boundary validation)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/participant_shared_state.py` (Snapshot shared-state semantics and append-only history)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/participant_concurrency.py` (Joint-action state references and read/write conflict checks in snapshots)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_conformance/conformance/snapshot_semantics.py` (Snapshot conformance for shared-state and joint-action records)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/participant_information_state_sources.py` (Shared-state and context-view source joins at one information-state cut)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/participant_result_contracts.py` (Backend-apply shared-state snapshot and history checks)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/participant_retrieval.py` (Context-view projection bound to a snapshot revision)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/participant_retrieval_context.py` (Context-view projection options)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/control_plane_api_participant_retrieval.py` (Context-view HTTP retrieval and audience binding)
- DOCUMENTS → SPEC `specs/formal/runtime-contracts/participant-backend-contracts.md` (API-406 carrier and API-408 retrieval design)
- DOCUMENTS → SPEC `specs/formal/participant-semantics/README.md` (SEM-214 and SEM-216 view semantics)
- DOCUMENTS → DOCUMENTATION `docs/explain/reference/shared-state-context-composition.md` (Composition example, binding map, and limits)
- TESTS → TEST `implementations/python/tests/test_issue_253_api_410_contracts.py` (Composition example, information-state join, access markers, view sources, and retrieval)
- TESTS → TEST `implementations/python/tests/test_run_307_shared_operational_state.py` (Snapshot shared-state semantics and append-only history)
- TESTS → TEST `implementations/python/tests/test_run_308_concurrent_participant_execution.py` (Joint-action conflict classes and policies over shared-state reads and writes)
- TESTS → TEST `implementations/python/tests/test_participant_backend_contracts.py` (Carrier and view schemas and fixtures)
- TESTS → TEST `implementations/python/tests/test_sem_216_boundary_semantics.py` (Participant-visible view boundary)
- TESTS → TEST `implementations/python/tests/test_act_604_dynamic_information_state.py` (Information-state source resolution)
- TESTS → TEST `implementations/python/tests/test_runtime_control_plane_api.py` (HTTP context-view route)
