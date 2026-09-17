---
id: ACT-612
title: "Multi-Participant Coordination And Delegation"
status: ACTIVE
type: FUNCTIONAL
priority: SHOULD
wave: 2
created_at: 2026-04-03T06:14:53.343616Z
updated_at: 2026-09-16T00:00:00Z
---

# ACT-612 — Multi-Participant Coordination And Delegation

## Statement

The ecosystem shall support explicit coordination, delegation, cooperation, competition, and supervision relationships among participants.

## Rationale

Requirement inventory expansion. Real exercises and agentic experiments require participant relationships beyond isolated single-actor behavior.

## Traceability

- IMPLEMENTS → GITHUB_ISSUE `214`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/participant_relationships.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/relationships.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/validator/_participant_relationships.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/composition/_sections.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/composition/_behavior.py`
- IMPLEMENTS → SPEC `specs/sdl/participant-relationships.md`
- TESTS → TEST `implementations/python/tests/test_act_612_participant_relationships.py`
- TESTS → TEST `implementations/python/tests/test_act_612_relationship_integration.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/_language_metadata.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/semantics/participant_behavior/_behavior_spec.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/validator/__init__.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/validator/_content_objectives.py`
- IMPLEMENTS → SPEC `contracts/schemas/sdl/sdl-authoring-input-v1.json`
- IMPLEMENTS → SPEC `contracts/schemas/sdl/instantiated-scenario-v1.json`
- IMPLEMENTS → SPEC `contracts/schemas/sdl/instantiated-scenario-snapshot-v1.json`
- IMPLEMENTS → SPEC `contracts/schemas/sdl/materialized-scenario-v1.json`
- IMPLEMENTS → SPEC `contracts/schemas/satisfiability/scenario-satisfiability-evidence-v1.json`
- TESTS → TEST `implementations/python/tests/test_requirement_governance.py` (Participant ownership of local requirement records and publication shards)
- TESTS → TEST `implementations/python/tests/test_specification_coverage.py` (Current and historical evidence integrity after source changes)
- TESTS → TEST `implementations/python/tests/test_formal_semantic_validation.py` (Current and historical evidence integrity after source changes)
- TESTS → TEST `implementations/python/tests/test_issue_989_versioned_evidence.py` (Current and historical evidence integrity after source changes)
- IMPLEMENTS → SPEC `specs/sdl/references.md` (Participant reference domains, phases, and rejection rules)
- TESTS → TEST `implementations/python/tests/test_sdl_catalog_parity.py` (Reference catalog agreement with live relationship fields)
