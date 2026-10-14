---
id: ACT-619
title: "Participant Tool And Affordance Profiles"
status: DRAFT
type: FUNCTIONAL
priority: MUST
created_at: 2026-04-05T01:24:06.900333Z
updated_at: 2026-04-05T01:24:06.900333Z
---

# ACT-619 — Participant Tool And Affordance Profiles

## Statement

The ecosystem shall support explicit participant tool and affordance profiles, including role-specific availability, visibility, and invocation constraints.

## Rationale

Primary-source refresh shows that participant behavior cannot be expressed or compared honestly unless the available tool and affordance surface is explicit.

## Traceability

- IMPLEMENTS → GITHUB_ISSUE `301` (Reusable participant tool profiles)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/participant_behavior_specification.py` (Optional participant selectors on tool-affordance bindings)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/semantics/participant_behavior/_tool_affordance.py` (Selector narrowing, unbound-selector and participant-local checks per binding)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/validator/_participant_tool_affordance_renderers.py` (Authoring diagnostics for binding selectors)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/_behavior_authoring.py` (Authored `__private` rejection for binding selector refs)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/composition/_behavior.py` (Namespaced rewriting of explicit binding selectors)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/compiler/participant_behaviors.py` (Compiled selector refs, resolved participant addresses and compiler diagnostics)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/models/decision_surface.py` (Participant filter for bindings and the v1 refusal of scoped bindings)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/models/decision_surface_v2.py` (Participant-filtered v2 projection)
- IMPLEMENTS → SPEC `contracts/schemas/sdl/sdl-authoring-input-v1.json` (Published authoring schema for binding selectors)
- DOCUMENTS → SPEC `specs/formal/participant-behavior-model/README.md` (ACT-619 tool-profile rules TP-1 to TP-9 and conflict classes K1 to K5)
- DOCUMENTS → DOCUMENTATION `docs/decisions/issue-301-participant-tool-profiles.md` (Profile design, alternatives, reconciliation and unsupported cases)
- DOCUMENTS → DOCUMENTATION `docs/migration/participant-tool-profiles.md` (Folding per-role specifications into one profile)
- DOCUMENTS → DOCUMENTATION `docs/explain/sdl/sections.md` (Tool-profile authoring reference)
- TESTS → TEST `implementations/python/tests/test_issue_301_participant_tool_profiles.py` (Two roles on one profile through compilation, v2 projection, admission and evidence)
- TESTS → TEST `implementations/python/tests/test_issue_301_participant_tool_profile_conflicts.py` (Conflict classes, unresolved refs and no inferred availability)
