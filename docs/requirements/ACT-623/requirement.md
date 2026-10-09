---
id: ACT-623
title: "Participant Episode Structure"
status: DRAFT
type: FUNCTIONAL
priority: MUST
created_at: 2026-04-05T01:39:33.224963Z
updated_at: 2026-04-05T01:39:33.224963Z
---

# ACT-623 — Participant Episode Structure

## Statement

The ecosystem shall support participant episode structure, including initialization, turn or interaction ordering, resettable starts, and end conditions, as a first-class participant concern.

## Rationale

Primary-source refresh shows that participant behavior is often organized as bounded episodes or turns rather than as an unstructured stream of actions.

## Traceability

- DOCUMENTS → SPEC `specs/formal/participant-episode-model/README.md` (Participant episode + budget model formal design (issue #122))
- IMPLEMENTS → GITHUB_ISSUE `309` (ACT-623 — Participant Episode Structure)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/participant_behavior_specification.py` (ACT-623 episode policy as a behavior specification aggregate member)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/participant_episode_policy.py` (DSL-120 authored episode structure that the ACT-623 member aggregates)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/models/behavior_resources.py` (ACT-623 compiled aggregate episode_policy_address)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/compiler/participant_behaviors.py` (ACT-623 compiled aggregate episode_policy_address)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_conformance/conformance/participant_episode_structure.py` (ACT-623 recorded episode history conformance against the compiled structure)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_conformance/conformance/diagnostics.py` (ACT-623 episode-structure conformance diagnostic code)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_conformance/conformance/__init__.py` (ACT-623 episode-structure conformance facade export)
- IMPLEMENTS → SPEC `specs/sdl/sections.md` (ACT-623 first-class episode structure and conformance contract)
- DOCUMENTS → DOCUMENTATION `docs/explain/sdl/sections.md` (ACT-623 first-class episode structure guide)
- TESTS → TEST `implementations/python/tests/test_issue_309_act_623_participant_episode_structure.py` (ACT-623 cross-kind attachment, aggregate membership, per-participant uniqueness, and recorded-history conformance tests)
- TESTS → TEST `implementations/python/tests/test_conformance_facade_parity.py` (ACT-623 conformance facade export parity)
