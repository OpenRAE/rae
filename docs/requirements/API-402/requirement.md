---
id: API-402
title: "Plain-Data Execution, Result, And History Contracts"
status: ACTIVE
type: FUNCTIONAL
priority: MUST
wave: 1
created_at: 2026-04-03T05:40:04.988670Z
updated_at: 2026-09-25T00:00:00.000000Z
---

# API-402 — Plain-Data Execution, Result, And History Contracts

## Statement

The ecosystem shall define plain-data contracts for submission, live execution state, results, and history that are independent of implementation language and distinct from archival run provenance artifacts.

## Rationale

Current state: implemented. Portable live-execution contracts are required so independent implementations can interoperate without sharing internal object models or conflating operational state with experiment records.

## Traceability

- CONSTRAINS → SPEC `specs/formal/runtime-contracts/README.md` (Runtime Contracts Overview)
- CONSTRAINS → SPEC `specs/formal/runtime-contracts/workflow-results.md` (Workflow Result Contracts)
- CONSTRAINS → SPEC `specs/formal/runtime-contracts/evaluator-results.md` (Evaluator Result Contracts)
- TESTS → TEST `implementations/python/tests/test_runtime_contracts.py` (Runtime Contract Tests)
- TESTS → TEST `implementations/python/tests/test_runtime_manager.py` (Runtime Manager Tests)
- TESTS → TEST `implementations/python/tests/test_runtime_control_plane_api.py` (Runtime Control Plane API Tests)
- DOCUMENTS → DOCUMENTATION `contracts/README.md` (Contracts Overview)
- DOCUMENTS → DOCUMENTATION `docs/explain/sdl/runtime-architecture.md` (SDL Runtime Architecture)
- CONSTRAINS → SPEC `contracts/schemas/control-plane/workflow-result-envelope-v1.json` (Workflow Result Envelope Schema)
- CONSTRAINS → SPEC `contracts/schemas/control-plane/evaluation-result-envelope-v1.json` (Evaluation Result Envelope Schema)
- CONSTRAINS → SPEC `contracts/schemas/control-plane/workflow-history-event-stream-v1.json` (Workflow History Event Stream Schema)
- CONSTRAINS → SPEC `contracts/schemas/control-plane/evaluation-history-event-stream-v1.json` (Evaluation History Event Stream Schema)
- CONSTRAINS → SPEC `contracts/schemas/snapshots/runtime-snapshot-v1.json` (Runtime Snapshot Schema)

- IMPLEMENTS → GITHUB_ISSUE `1360` (Optional backend operation and supervision contract publication)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_backend_protocols/__init__.py` (Portable operation carriers, contextual validation and publication boundary; no runtime supervision claim)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_backend_protocols/operation_supervision.py` (Portable operation carriers, contextual validation and publication boundary; no runtime supervision claim)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/__init__.py` (Portable operation carriers, contextual validation and publication boundary; no runtime supervision claim)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/_exports.py` (Portable operation carriers, contextual validation and publication boundary; no runtime supervision claim)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/_version_exports.py` (Portable operation carriers, contextual validation and publication boundary; no runtime supervision claim)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/backend_operation.py` (Portable operation carriers, contextual validation and publication boundary; no runtime supervision claim)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/backend_operation_response.py` (Portable operation carriers, contextual validation and publication boundary; no runtime supervision claim)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/backend_operation_schema.py` (Portable operation carriers, contextual validation and publication boundary; no runtime supervision claim)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/backend_operation_validation.py` (Portable operation carriers, contextual validation and publication boundary; no runtime supervision claim)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/bundle_runtime.py` (Portable operation carriers, contextual validation and publication boundary; no runtime supervision claim)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/manifest_authority.py` (Portable operation carriers, contextual validation and publication boundary; no runtime supervision claim)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/versions.py` (Portable operation carriers, contextual validation and publication boundary; no runtime supervision claim)
- TESTS → TEST `implementations/python/tests/test_issue_1360_backend_operations.py` (Portable operation carriers, contextual validation and publication boundary; no runtime supervision claim)
- TESTS → TEST `implementations/python/tests/test_issue_1360_operation_rejections.py` (Portable operation carriers, contextual validation and publication boundary; no runtime supervision claim)
- IMPLEMENTS → SPEC `specs/formal/runtime-contracts/backend-operation-supervision.md` (Normative carrier and cross-message semantics)
- DOCUMENTS → DOCUMENTATION `docs/explain/reference/backend-operation-supervision.md` (Provider duties, migration and evidence limits)
- DOCUMENTS → DOCUMENTATION `docs/decisions/issue-1360-backend-operation-contracts-preflight.md` (Contract publication guardrails)
- IMPLEMENTS → CONFIG `tools/policy/requirement_order.yaml` (Existing live-contract requirement admitted through control-plane governance)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/_backend_operation_exports.py` (Public operation contract facade exports)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_backend_stubs/manifest.py` (Keep operation supervision opt-in; legacy stub does not advertise an unimplemented provider)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_reference_backend/manifest.py` (Keep operation supervision opt-in for reference emulation)
