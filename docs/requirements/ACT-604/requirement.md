---
id: ACT-604
title: "Dynamic Knowledge And Environment-State Semantics"
status: ACTIVE
type: FUNCTIONAL
priority: SHOULD
wave: 2
created_at: 2026-04-03T05:40:06.095885Z
updated_at: 2026-08-01T15:54:15.556668Z
---

# ACT-604 — Dynamic Knowledge And Environment-State Semantics

## Statement

The ecosystem shall define dynamic participant knowledge and environment-state semantics, including evolving operational holdings, discovered context, and shared state.

## Rationale

Requirement inventory expansion. Rich participant behavior requires portable semantics for what actors know, hold, discover, and affect over time.

## Traceability

- IMPLEMENTS → SPEC `contracts/schemas/participant-runtime/participant-information-state-record-v1.json` (ACT-604 portable participant information-state record schema)
- IMPLEMENTS → SPEC `contracts/schemas/profiles/participant-information-reconstruction-profile-v1.json` (ACT-604 governed information-state reconstruction profile schema)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/participant_information_state.py` (ACT-604 participant information-state contract and contextual validation)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/participant_information_reconstruction_profiles.py` (ACT-604 participant information-state contract and contextual validation)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/participant_information_state_sources.py` (ACT-604 typed source-coordinate validation)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/participant_information_state_validation.py` (ACT-604 runtime information-state validation boundary)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/runtime_state.py` (ACT-604 append-only runtime information-state carriage)
- TESTS → TEST `implementations/python/tests/test_act_604_dynamic_information_state.py` (ACT-604 dynamic information-state regression and isolation tests)
- IMPLEMENTS → GITHUB_ISSUE `212` (Dynamic Knowledge And Environment-State Semantics (ACT-604))
