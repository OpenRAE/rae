---
id: ACT-606
title: "First-Class Participant Behavior Specifications"
status: ACTIVE
type: FUNCTIONAL
priority: SHOULD
wave: 2
created_at: 2026-04-03T06:14:52.717714Z
updated_at: 2026-06-24T00:50:07.627651Z
---

# ACT-606 — First-Class Participant Behavior Specifications

## Statement

The ecosystem shall support first-class participant behavior specifications alongside declarative participant framing.

## Rationale

Requirement inventory expansion. Participant behavior must be expressible as a first-class concern rather than inferred from metadata or backend conventions.

## Traceability

- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/semantics/participant_behavior/_behavior_spec.py` (Behavior reference validation, including deferred parameterized role binding)
- TESTS → TEST `implementations/python/tests/test_act_612_relationship_integration.py` (Role-based refinement revalidation after instantiation)
- IMPLEMENTS → ADR `docs/decisions/adrs/adr-067-participant-behavior-model.md` (ADR-067 Participant Behavior Model)
- IMPLEMENTS → SPEC `specs/formal/participant-behavior-model/README.md` (Formal participant behavior model specification)
- IMPLEMENTS → GITHUB_ISSUE `77` (Issue #77 - Participant behavior model)
- IMPLEMENTS → GITHUB_ISSUE `206` (First-Class Participant Behavior Specifications (ACT-606))
- IMPLEMENTS → SPEC `contracts/schemas/sdl/sdl-authoring-input-v1.json` (SDL authoring schema behavior specifications)
- IMPLEMENTS → SPEC `contracts/schemas/sdl/instantiated-scenario-v1.json` (Instantiated scenario schema behavior specifications)
- TESTS → TEST `implementations/python/tests/test_sem_208_participant_behavior.py` (Participant behavior specification semantic tests)
- TESTS → TEST `implementations/python/tests/test_instantiated_scenario_schema.py` (Behavior specification instantiated-schema tests)
