---
id: ACT-601
title: "Declarative Participant Framing"
status: ACTIVE
type: FUNCTIONAL
priority: SHOULD
wave: 1
created_at: 2026-04-03T05:40:05.746489Z
updated_at: 2026-05-18T00:27:11.473469Z
---

# ACT-601 — Declarative Participant Framing

## Statement

The language shall support declarative participant framing covering identity, role, starting conditions, authority anchors, and operating scope.

## Rationale

Requirement inventory expansion. Participant framing must describe who acts, under what initial conditions, and within what declared scope.

## Traceability

- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/agents.py` (Declaration identity, optional affiliation, and effective role)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/semantics/participant_behavior/_affiliations.py` (Normalized affiliation validation)
- IMPLEMENTS → SPEC `specs/sdl/participant-identity.md` (Participant identity and role boundary)
- TESTS → TEST `implementations/python/tests/test_issue_1338_participant_identity.py`
- TESTS → TEST `implementations/python/tests/test_issue_1338_identity_stages.py`
- TESTS → TEST `implementations/python/tests/test_issue_1338_identity_authority.py`
- TESTS → TEST `implementations/python/tests/test_issue_1338_identity_evidence.py`

- IMPLEMENTS → ADR `docs/decisions/adrs/adr-020-declarative-participant-framing-boundaries.md` (ADR-020 Declarative Participant Framing Boundaries)
- TESTS → TEST `implementations/python/tests/test_sdl_models.py` (Structural tests for Agent participant-framing fields)
- TESTS → TEST `implementations/python/tests/test_sdl_validator.py` (Semantic-validator tests for the three new framing fields (TestAgentParticipantFraming))
- TESTS → TEST `implementations/python/tests/test_sdl_parser.py` (Module-composition import tests covering both bare and qualified framing refs)
- IMPLEMENTS → GITHUB_ISSUE `70` (Declarative participant framing (ACT-601))
