---
id: API-402
title: "Plain-Data Execution, Result, And History Contracts"
status: ACTIVE
type: FUNCTIONAL
priority: MUST
wave: 1
created_at: 2026-04-03T05:40:04.988670Z
updated_at: 2026-10-21T00:00:00Z
---

# API-402 — Plain-data execution, result, and history contracts

## Statement

The ecosystem shall define plain-data contracts for submission, live execution state, results, and history.
These contracts shall be independent of implementation language.
They shall be distinct from archival run provenance artifacts.

## Rationale

Current state: implemented.
Portable live-execution contracts let separate implementations work together.
They do not share internal object models.
They keep live state distinct from experiment records.

## Traceability

- IMPLEMENTS → SPEC `contracts/schemas/control-plane/workflow-step-dispatch-v1.json` (Runtime step command.)
- IMPLEMENTS → SPEC `contracts/schemas/control-plane/workflow-step-response-v1.json` (Bound terminal step response.)
- TESTS → TEST `implementations/python/tests/test_issue_2041_runtime_step_dispatch.py` (Dispatch permission, graph transitions, lifecycle and history.)
- TESTS → TEST `implementations/python/tests/test_issue_2041_workflow_contracts.py` (Carrier shape and provider transport.)
- TESTS → TEST `implementations/python/tests/test_issue_2041_workflow_recovery.py` (Durable checkpoint and effect recovery.)
- TESTS → TEST `implementations/python/tests/test_issue_2041_operation_failures.py` (Terminal child outcomes and uncertain setup.)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/workflow_dispatch.py` (Closed step carriers.)
- DOCUMENTS → DOCUMENTATION `docs/migration/runtime-workflow-step-dispatch.md` (Backend migration.)

- CONSTRAINS → SPEC `specs/formal/runtime-contracts/README.md` (Runtime Contracts Overview.)
- CONSTRAINS → SPEC `specs/formal/runtime-contracts/workflow-results.md` (Workflow Result Contracts.)
- CONSTRAINS → SPEC `specs/formal/runtime-contracts/evaluator-results.md` (Evaluator Result Contracts.)
- TESTS → TEST `implementations/python/tests/test_runtime_contracts.py` (Runtime Contract Tests.)
- TESTS → TEST `implementations/python/tests/test_runtime_manager.py` (Runtime Manager Tests.)
- TESTS → TEST `implementations/python/tests/test_runtime_control_plane_api.py` (Runtime Control Plane API Tests.)
- DOCUMENTS → DOCUMENTATION `contracts/README.md` (Contracts Overview.)
- DOCUMENTS → DOCUMENTATION `docs/explain/sdl/runtime-architecture.md` (SDL Runtime Architecture.)
- CONSTRAINS → SPEC `contracts/schemas/control-plane/workflow-result-envelope-v1.json` (Workflow Result Envelope Schema.)
- CONSTRAINS → SPEC `contracts/schemas/control-plane/evaluation-result-envelope-v1.json` (Evaluation Result Envelope Schema.)
- CONSTRAINS → SPEC `contracts/schemas/control-plane/workflow-history-event-stream-v1.json` (Workflow History Event Stream Schema.)
- CONSTRAINS → SPEC `contracts/schemas/control-plane/evaluation-history-event-stream-v1.json` (Evaluation History Event Stream Schema.)
- CONSTRAINS → SPEC `contracts/schemas/snapshots/runtime-snapshot-v1.json` (Runtime Snapshot Schema.)

- IMPLEMENTS → GITHUB_ISSUE `1360` (Optional backend operation and supervision contract publication.)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_backend_protocols/__init__.py` (These files define plain-data operation contracts. They check each call in its context. They set the scope of what gets published. They do not claim that the runtime supervises calls.)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_backend_protocols/operation_supervision.py` (These files define plain-data operation contracts. They check each call in its context. They set the scope of what gets published. They do not claim that the runtime supervises calls.)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/__init__.py` (These files define plain-data operation contracts. They check each call in its context. They set the scope of what gets published. They do not claim that the runtime supervises calls.)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/_exports.py` (These files define plain-data operation contracts. They check each call in its context. They set the scope of what gets published. They do not claim that the runtime supervises calls.)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/_version_exports.py` (These files define plain-data operation contracts. They check each call in its context. They set the scope of what gets published. They do not claim that the runtime supervises calls.)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/backend_operation.py` (These files define plain-data operation contracts. They check each call in its context. They set the scope of what gets published. They do not claim that the runtime supervises calls.)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/backend_operation_response.py` (These files define plain-data operation contracts. They check each call in its context. They set the scope of what gets published. They do not claim that the runtime supervises calls.)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/backend_operation_schema.py` (These files define plain-data operation contracts. They check each call in its context. They set the scope of what gets published. They do not claim that the runtime supervises calls.)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/backend_operation_validation.py` (These files define plain-data operation contracts. They check each call in its context. They set the scope of what gets published. They do not claim that the runtime supervises calls.)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/bundle_runtime.py` (These files define plain-data operation contracts. They check each call in its context. They set the scope of what gets published. They do not claim that the runtime supervises calls.)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/manifest_authority.py` (These files define plain-data operation contracts. They check each call in its context. They set the scope of what gets published. They do not claim that the runtime supervises calls.)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/versions.py` (These files define plain-data operation contracts. They check each call in its context. They set the scope of what gets published. They do not claim that the runtime supervises calls.)
- TESTS → TEST `implementations/python/tests/test_issue_1360_backend_operations.py` (These files define plain-data operation contracts. They check each call in its context. They set the scope of what gets published. They do not claim that the runtime supervises calls.)
- TESTS → TEST `implementations/python/tests/test_issue_1360_operation_rejections.py` (These files define plain-data operation contracts. They check each call in its context. They set the scope of what gets published. They do not claim that the runtime supervises calls.)
- IMPLEMENTS → SPEC `specs/formal/runtime-contracts/backend-operation-supervision.md` (Normative carrier and cross-message semantics.)
- DOCUMENTS → DOCUMENTATION `docs/explain/reference/backend-operation-supervision.md` (Provider duties, migration and evidence limits.)
- DOCUMENTS → DOCUMENTATION `docs/decisions/issue-1360-backend-operation-contracts-preflight.md` (Contract publication guardrails.)
- IMPLEMENTS → CONFIG `tools/policy/requirement_order.yaml` (Existing live-contract requirement admitted through control-plane governance.)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/_backend_operation_exports.py` (Public operation contract facade exports.)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_backend_stubs/manifest.py` (Keep operation supervision opt-in; legacy stub does not advertise an unimplemented provider.)
- IMPLEMENTS → SPEC `contracts/schemas/control-plane/backend-operation-capabilities-v1.json` (backend-operation-capabilities-v1 published schema.)
- IMPLEMENTS → SPEC `contracts/schemas/control-plane/backend-operation-control-v1.json` (backend-operation-control-v1 published schema.)
- IMPLEMENTS → SPEC `contracts/schemas/control-plane/backend-operation-request-v1.json` (backend-operation-request-v1 published schema.)
- IMPLEMENTS → SPEC `contracts/schemas/control-plane/backend-operation-response-v1.json` (backend-operation-response-v1 published schema.)
- IMPLEMENTS → SPEC `contracts/schemas/control-plane/evaluation-history-event-stream-v1.json` (evaluation-history-event-stream-v1 published schema.)
- IMPLEMENTS → SPEC `contracts/schemas/control-plane/evaluation-result-envelope-v1.json` (evaluation-result-envelope-v1 published schema.)
- IMPLEMENTS → SPEC `contracts/schemas/control-plane/workflow-history-event-stream-v1.json` (workflow-history-event-stream-v1 published schema.)
- IMPLEMENTS → SPEC `contracts/schemas/control-plane/workflow-result-envelope-v1.json` (workflow-result-envelope-v1 published schema.)
