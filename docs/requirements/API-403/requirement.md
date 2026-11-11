---
id: API-403
title: "Per-Target Control Plane Contract"
status: ACTIVE
type: FUNCTIONAL
priority: MUST
wave: 1
created_at: 2026-04-03T05:40:05.140230Z
updated_at: 2026-04-05T03:06:54.145226Z
---

# API-403 — Per-Target Control Plane Contract

## Statement

The ecosystem shall define a per-target control-plane contract for mutating operations, lifecycle observation, and status retrieval.

## Rationale

Current state: implemented. A per-target control-plane contract is required so runtime operations can be driven and observed through a portable external interface.

## Traceability

- DOCUMENTS → DOCUMENTATION `contracts/README.md` (Contracts Overview)
- DOCUMENTS → DOCUMENTATION `docs/explain/sdl/runtime-architecture.md` (SDL Runtime Architecture)
- CONSTRAINS → ADR `ADR-008` (Processor Layer And Execution Artifact Boundaries)
- CONSTRAINS → SPEC `contracts/schemas/control-plane/operation-receipt-v1.json` (Operation Receipt Schema)
- CONSTRAINS → SPEC `contracts/schemas/control-plane/operation-status-v1.json` (Operation Status Schema)
- CONSTRAINS → SPEC `contracts/schemas/control-plane/workflow-cancellation-request-v1.json` (Workflow Cancellation Request Schema)
- TESTS → TEST `implementations/python/tests/test_runtime_control_plane.py` (Runtime Control Plane Tests)
- TESTS → TEST `implementations/python/tests/test_runtime_control_plane_api.py` (Runtime Control Plane API Tests)
- IMPLEMENTS → SPEC `contracts/schemas/control-plane/workflow-cancellation-request-v1.json` (workflow-cancellation-request-v1 published schema)
