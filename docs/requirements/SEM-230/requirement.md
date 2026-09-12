---
id: SEM-230
title: "Participant Information-Flow And Control Semantics"
status: ACTIVE
type: FUNCTIONAL
priority: MUST
wave: 3
created_at: 2026-07-15T05:45:06.805688Z
updated_at: 2026-07-18T14:33:41.000394Z
---

# SEM-230 — Participant Information-Flow And Control Semantics

## Statement

The ecosystem shall define revisioned participant-relative information-flow and control semantics for input admission, output projection, disclosure and declassification, transformation, observable and hidden action labels, policy change over time, and the precise relation and assurance boundary of every noninterference or behavioral claim.

## Rationale

Existing participant action, observation, visibility, runtime, and behavioral-relation authorities are adjacent but do not define one coherent policy decision model or a governed noninterference claim surface.

## Traceability

- TESTS → TEST `implementations/python/tests/test_sem_233_flow_control_contracts.py` (SEM-230 portable information-flow contract tests)
- IMPLEMENTS → SPEC `contracts/schemas/participant-runtime/participant-flow-control-relation-v1.json` (SEM-230 portable participant flow-control relation schema)
- IMPLEMENTS → GITHUB_ISSUE `1002` (Issue #1002 portable flow-control contracts)
- DOCUMENTS → GITHUB_ISSUE `803` (Document participant I/O control authoring, operations, and claim boundaries)
- DOCUMENTS → GITHUB_ISSUE `794` (Assess and design formal participant I/O control with information-flow and bisimulation semantics)
- DOCUMENTS → DOCUMENTATION `docs/research/participant-io-control/requirement-disposition.md` (Issue #794 participant information-flow/control requirement disposition)
- IMPLEMENTS → SPEC `specs/formal/participant-semantics/information-flow-control.md` (SEM-230 participant information-flow and control semantics)
- IMPLEMENTS → SPEC `contracts/concept-authority/behavioral-relations-v1.json` (Behavioral relation catalog rev2 policy-noninterference authority)
- IMPLEMENTS → CODE_FILE `tools/check_behavioral_relation_claims.py` (Behavioral relation claim policy checker)
- IMPLEMENTS → ADR `docs/decisions/adrs/adr-085-participant-information-flow-and-control.md` (ADR-085 participant information-flow and control decision)
- IMPLEMENTS → DOCUMENTATION `docs/explain/sdl/lineage.md` (SDL formal lineage and prior-work mapping)
- IMPLEMENTS → CONFIG `contracts/provenance/sdl-lineage-ledger-v1.json` (Machine-readable SDL lineage ledger)
- IMPLEMENTS → CONFIG `specs/formal/assurance-fulfillment.yaml` (Formal assurance fulfillment mapping)
- IMPLEMENTS → DOCUMENTATION `docs/research/lineage/source-audit-2026-07-12.md` (Formal lineage source audit)
- TESTS → TEST `implementations/python/tests/sem230_information_flow_model.py` (SEM-230 bounded information-flow model)
- TESTS → TEST `implementations/python/tests/test_behavioral_relation_claims.py` (Behavioral relation claim policy tests)
- TESTS → TEST `implementations/python/tests/test_behavioral_relations.py` (Behavioral relation catalog and binding tests)
- TESTS → TEST `implementations/python/tests/test_sem_230_information_flow_control.py` (SEM-230 bounded information-flow control tests)
- IMPLEMENTS → GITHUB_ISSUE `796` (SEM-230 — Participant Information-Flow And Control Semantics)
- IMPLEMENTS → GITHUB_ISSUE `802` (Migrate participant I/O control semantics and existing carriers)
- IMPLEMENTS → DOCUMENTATION `docs/migration/participant-information-flow-control.md` (Participant information-flow control migration guide)
- DOCUMENTS → DOCUMENTATION `docs/decisions/issue-802-api-423-participant-control-migration-preflight.md` (Issue #802 participant-control migration architecture preflight)
- TESTS → TEST `implementations/python/tests/test_issue_802_participant_control_migration.py` (Issue #802 participant-control compatibility and migration tests)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/participant_retrieval.py` (Trusted participant-relative governed retrieval)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/control_plane_store_types.py` (Participant crossing-history source-presence classification)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/control_plane_api_participant_retrieval.py` (Audience-bound participant retrieval API adapter)
- TESTS → TEST `implementations/python/tests/test_public_docs_policy.py` (Executable participant-control public guide claim example)
- DOCUMENTS → DOCUMENTATION `docs/public/participant-control.md` (Participant input and output control guide)
