---
id: DSL-125
title: "Participant Decision Exposure And Visibility Surface"
status: ACTIVE
type: FUNCTIONAL
priority: MUST
created_at: 2026-04-05T02:10:21.414865Z
updated_at: 2026-10-31T00:00:00Z
---

# DSL-125 — Participant Decision Exposure And Visibility Surface

## Statement

The language shall support declaration of participant-visible decision surfaces and exposure policies, including what observations, control-context artifacts, hidden assets, benchmark-only assets, and other context are exposed, withheld, or role-scoped for participant decision-making.

## Rationale

Current state: identified gap. The imported research consistently treats the participant-visible decision surface as a first-class authored concern distinct from abstract behavior semantics and from hidden evaluation assets.

## Traceability

- IMPLEMENTS → GITHUB_ISSUE `300` (Authored exposure to participant decision surfaces)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/models/authored_participant_exposure_v2.py` (Compiled selection, ACT-620 disclosure and delivery agreement)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/models/decision_surface_v2.py` (Authored exposure at the existing v2 projection boundary)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/compiler/participant_behaviors.py` (Existing pinned participant and reusable control-context selections)
- IMPLEMENTS → SPEC `specs/sdl/participant-control-context.md` (Authored decision exposure and live authority boundaries)
- TESTS → TEST `implementations/python/tests/test_dsl_125_authored_exposure.py` (Compiled-to-delivered trace and adversarial exposure cases)
- TESTS → TEST `implementations/python/tests/test_dsl_118_control_context.py` (Existing scope and pin enforcement)
- TESTS → TEST `implementations/python/tests/test_dsl_118_trial_control_context.py` (Existing admitted trial selection pins)
- TESTS → TEST `implementations/python/tests/test_act_620_control_context_assets.py` (Existing content, lifecycle and authority checks)
- DOCUMENTS → DOCUMENTATION `docs/explain/sdl/issue-300-clause-mapping.md` (Acceptance mapping)
- DOCUMENTS → DOCUMENTATION `docs/explain/reference/participant-decision-surface-v2-migration.md` (Compatibility and migration)
