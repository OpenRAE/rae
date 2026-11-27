---
id: ACT-619
title: "Participant Tool And Affordance Profiles"
status: ACTIVE
type: FUNCTIONAL
priority: MUST
created_at: 2026-04-05T01:24:06.900333Z
updated_at: 2026-10-26T03:30:54.561688+00:00
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
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/_behavior_authoring.py` (Source-anchored private-reference checks for participant, tool-binding, and inject-delivery references, including post-substitution validation)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/composition/_behavior.py` (Namespaced rewriting of explicit binding selectors)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/composition/_tool_affordance.py` (Preserve tool identity and namespace explicit binding selectors during module composition)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/compiler/participant_behaviors.py` (Compiled selector refs, resolved participant addresses and compiler diagnostics)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/compiler/participant_access.py` (Preserve separately authored participant access while compiling tool profiles)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/models/decision_surface.py` (Participant filter for bindings and the v1 refusal of scoped bindings)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/models/decision_surface_v2.py` (Participant-filtered v2 projection)
- IMPLEMENTS → SPEC `contracts/schemas/sdl/sdl-authoring-input-v1.json` (Published authoring schema for binding selectors)
- DOCUMENTS → SPEC `specs/formal/participant-behavior-model/README.md` (ACT-619 tool-profile rules TP-1 to TP-9 and conflict classes K1 to K5)
- DOCUMENTS → DOCUMENTATION `docs/decisions/issue-301-participant-tool-profiles.md` (Profile design, alternatives, reconciliation and unsupported cases)
- DOCUMENTS → DOCUMENTATION `docs/migration/participant-tool-profiles.md` (Folding per-role specifications into one profile)
- DOCUMENTS → DOCUMENTATION `docs/explain/sdl/sections.md` (Tool-profile authoring reference)
- TESTS → TEST `implementations/python/tests/test_issue_301_participant_tool_profiles.py` (Two roles on one profile through compilation, v2 projection, admission and evidence)
- TESTS → TEST `implementations/python/tests/test_issue_301_participant_tool_profile_conflicts.py` (Conflict classes, unresolved refs and no inferred availability)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/validator/_content_objectives.py` (Participant-scoped binding reference validation)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/compiler/alias_index.py` (Qualified tool-binding aliases in the canonical runtime address index)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/models/behavior_resources.py` (Typed compiled binding selectors, resolved participant addresses, and boundary reference aliases)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/compiler/participant_contracts.py` (Canonical observation lists, rules, transitions, and timelines)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/compiler/view_relations.py` (Visibility alias resolution and conflict rejection)
- IMPLEMENTS → CODE_FILE `tools/sdl_catalog_parity/_expectations_2.py` (Reference-catalog parity for binding participant selectors)
- TESTS → TEST `implementations/python/tests/test_issue_301_private_references.py` (Private module-reference rejection, exact generated-reference retention, and parameter-substitution checks)
- TESTS → TEST `implementations/python/tests/test_issue_301_projection_boundaries.py` (Participant-local action and boundary checks and binding boundary filtering in v1 and v2)
- TESTS → TEST `implementations/python/tests/test_issue_301_visibility_references.py` (Authored-only projection, visibility transitions, canonical aliases, and conflict rejection)
- TESTS → TEST `implementations/python/tests/test_issue_298_tool_authoring.py` (Imported tool identity and canonical visibility preserve independent invocation admission)
- TESTS → TEST `implementations/python/tests/test_sem_208_participant_behavior.py` (Published tool-affordance shape)
- TESTS → TEST `implementations/python/tests/test_sem_215_participant_outcome_interpretation.py` (Outcome evidence uses the compiled visibility reference space)
- TESTS → TEST `implementations/python/tests/test_sem_220_participant_decision_surface.py` (Declared participant scope in the shared decision-surface fixture)
- TESTS → TEST `implementations/python/tests/tool_profile_support.py` (Compiled profile, delivery, admission, and evidence harness)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/models/behavior_ref_checks.py` (Alias-aware visibility and evidence checks for history details, action results, and attribution)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/models/behavior_grounding_checks.py` (Alias-aware outcome evidence and provenance checks)
- TESTS → TEST `implementations/python/tests/test_issue_301_selector_schema_parity.py` (Published selector rejection of blank and duplicate items in all five contracts)
- TESTS → TEST `implementations/python/tests/test_issue_301_history_alias_visibility.py` (Hidden and ambiguous aliases rejected across history channels, with full-history effect, support, and provenance regressions)
