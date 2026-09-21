---
id: ACT-614
title: "Temporal Behavior Profiles"
status: ACTIVE
type: FUNCTIONAL
priority: SHOULD
wave: 2
created_at: 2026-04-03T06:15:08.208790Z
updated_at: 2026-09-21T00:00:00Z
---

# ACT-614 — Temporal Behavior Profiles

## Statement

The ecosystem shall support participant behavior profiles with schedules, cadence, dwell, timing constraints, and other temporal characteristics.

## Rationale

Requirement inventory expansion. Participant behavior over time is a first-class scenario concern rather than a backend-local pacing detail.

## Traceability

- IMPLEMENTS → GITHUB_ISSUE `216`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/participant_execution.py` (Versioned schedules and typed numeric parameters)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/composition/_behavior.py` (Namespaced profile references)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/participant_temporal_semantics.py` (Explicit deadline and dwell bindings)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/semantics/participant_temporal_bindings.py` (Backend-independent binding validity)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/compiler/participant_temporal.py` (Resolved temporal identity)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_backend_protocols/capability_admission.py` (Exact manifest sufficiency)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/participant_temporal.py` (Dispatch and outcome enforcement)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/participant_temporal.py` (Evidence assessment and durable consistency)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_conformance/conformance/participant_temporal_probes.py` (Scenario-specific conformance)
- IMPLEMENTS → SPEC `specs/formal/participant-semantics/autonomous-execution.md` (Schedules, cadence, dwell, deadlines and lifecycle)
- IMPLEMENTS → SPEC `contracts/schemas/sdl/sdl-authoring-input-v1.json` (Published authoring contract)
- IMPLEMENTS → SPEC `contracts/schemas/snapshots/runtime-snapshot-v1.json` (Published evidence and assessment carriers)
- DOCUMENTS → DOCUMENTATION `examples/scenarios/temporal-profiles/README.md` (User/automation mapping, capabilities and limits)
- TESTS → TEST `implementations/python/tests/test_act_614_temporal_profiles.py` (Imports, parameters, bindings and examples)
- TESTS → TEST `implementations/python/tests/test_act_614_temporal_admission.py` (Limited/rich manifests and conditional conformance)
- TESTS → TEST `implementations/python/tests/test_act_614_temporal_runtime.py` (Deadline, dwell, generation and retry enforcement)
- TESTS → TEST `implementations/python/tests/test_act_614_temporal_durability.py` (History, persistence and legacy identity)
- TESTS → TEST `implementations/python/tests/test_act_614_temporal_security.py` (Evidence authorization and backend mutation isolation)
- TESTS → TEST `implementations/python/tests/test_act_614_temporal_conformance.py` (Probe-owned clock driver shutdown on success and failure)
- TESTS → TEST `implementations/python/tests/test_dsl_437_benign_participant_execution.py` (Cadence, windows, intervals, dependencies, retries and cooldowns)
