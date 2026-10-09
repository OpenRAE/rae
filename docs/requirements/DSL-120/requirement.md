---
id: DSL-120
title: "Participant Episode Structure And Termination Surface"
status: DRAFT
type: FUNCTIONAL
priority: MUST
created_at: 2026-04-05T01:39:32.895216Z
updated_at: 2026-04-05T01:39:32.895216Z
---

# DSL-120 — Participant Episode Structure And Termination Surface

## Statement

The language shall support authored participant episode structure, including initialization, turn or interaction structure, termination conditions, truncation conditions, and reset-related declarations where tasks or experiments require them.

## Rationale

Primary-source refresh shows that participant-supporting ecosystems frequently treat episodes, turns, reset behavior, and termination structure as first-class authored concerns rather than backend-local conventions.

## Traceability

- DOCUMENTS → SPEC `specs/formal/participant-episode-model/README.md` (Participant episode + budget model formal design (issue #122))
- IMPLEMENTS → GITHUB_ISSUE `307` (DSL-120 — Participant Episode Structure And Termination Surface)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/participant_episode_policy.py` (DSL-120 authored participant episode policy model; rejects realized episode state)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/participant_behavior_specification.py` (DSL-120 behavior specification episode_policy member)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/validator/_participant_episode_policies.py` (DSL-120 fail-closed episode policy reference and role validation)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/composition/_behavior.py` (DSL-120 module-composition episode policy reference rewriting)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/compiler/participant_episode_policies.py` (DSL-120 participant.episode-policy compiled records)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/models/participant_episode_resources.py` (DSL-120 compiled episode policy and condition records)
- IMPLEMENTS → SPEC `specs/sdl/sections.md` (DSL-120 normative participant episode structure contract)
- IMPLEMENTS → SPEC `specs/sdl/references.md` (DSL-120 episode policy reference semantics)
- IMPLEMENTS → SPEC `contracts/schemas/sdl/sdl-authoring-input-v1.json` (DSL-120 governed authoring schema)
- IMPLEMENTS → SPEC `contracts/schemas/sdl/instantiated-scenario-v1.json` (DSL-120 governed instantiated scenario schema)
- DOCUMENTS → DOCUMENTATION `docs/explain/sdl/sections.md` (DSL-120 episode policy authoring guide)
- TESTS → TEST `implementations/python/tests/test_issue_307_dsl_120_participant_episode_policy.py` (DSL-120 authoring, validation, composition, compilation, and schema tests; no episode execution)
