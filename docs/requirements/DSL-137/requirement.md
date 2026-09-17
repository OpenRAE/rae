---
id: DSL-137
title: "Orchestration Authority Runtime Inventory"
status: ACTIVE
type: FUNCTIONAL
priority: MUST
wave: 1
created_at: 2026-05-30T06:21:14.941474Z
updated_at: 2026-09-13T00:00:00Z
---

# DSL-137 — Orchestration Authority Runtime Inventory

## Statement

The language shall represent container-orchestration control-authority state as a typed node-scoped runtime inventory primitive, including a reference to the observed control interface, engine identity and API version, organizational and environment scope, spawn templates, lifecycle policy, realized child workloads, and privilege classification, allowing partial privileged-interface knowledge while resolving supplied concrete interface references on the same node and requiring independently authorized supported access for selected privileged execution, without overloading the anonymous control-interface mount shell, transport services, or prose-only relationships.

## Rationale

APTL SCN-010 shuffle-orborus (#355) and cortex (#357) hold the Docker socket and spawn ephemeral worker/analyzer containers; RuntimeControlInterface types the socket as a present read-write mount shell but carries no field for what the holder is authorized to do (spawn image X into scope Y under policy Z) and has no id to reference. This host-root-equivalent spawn authority is the defining and most security-relevant logical state of these nodes.

## Traceability

- TESTS → TEST `implementations/python/tests/test_runtime_orchestration.py` (test_runtime_orchestration.py)
- DOCUMENTS → ADR `docs/decisions/adrs/adr-051-orchestration-authority-runtime-inventory.md` (ADR-051 Orchestration Authority Runtime Inventory)

- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/runtime_orchestration.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/validator/_runtime_orchestration.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/runtime_inventory.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/semantics/realization_runtime_concern_profiles.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/semantics/realization_specialized_projection.py`
- IMPLEMENTS → SPEC `specs/sdl/runtime-inventory.md` (Partial description and selected-operation boundary)
- IMPLEMENTS → GITHUB_ISSUE `1207` (Correct specimen-shaped completeness guards)
- TESTS → TEST `implementations/python/tests/test_issue_1207_partial_descriptions.py`
- TESTS → TEST `implementations/python/tests/test_issue_1207_profile_admission.py`
- TESTS → TEST `implementations/python/tests/test_issue_1207_recursive_inventory.py`
