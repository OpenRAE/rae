---
id: ACT-611
title: "Autonomous Service And Agent Behavior Vocabularies"
status: ACTIVE
type: FUNCTIONAL
priority: SHOULD
wave: 2
created_at: 2026-04-03T06:14:53.234945Z
updated_at: 2026-07-31T04:03:21.544823Z
---

# ACT-611 — Autonomous Service And Agent Behavior Vocabularies

## Statement

The ecosystem shall support behavior vocabularies for autonomous services and agents that act within scenarios as independent participants.

## Rationale

Requirement inventory expansion. Scenarios need to describe autonomous system behavior, not only human-team proxies.

## Traceability

- IMPLEMENTS → SPEC `specs/concept-authority/autonomous-behavior-vocabularies.md` (Autonomous behavior vocabularies specification)
- IMPLEMENTS → SPEC `contracts/concept-authority/fipa-communicative-acts-source-v1.json` (FIPA communicative-act source contract)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_conformance/conformance/validators.py` (Canonical structural conformance registration)
- TESTS → TEST `implementations/python/tests/test_autonomous_behavior_vocabularies.py` (Autonomous behavior vocabulary tests)
- IMPLEMENTS → SPEC `contracts/concept-authority/w3c-activitystreams-activity-types-source-v1.json` (W3C ActivityStreams Activity-type source contract)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/external_concept_bindings.py` (External concept binding source adapters)
- IMPLEMENTS → GITHUB_ISSUE `211` (Autonomous Service And Agent Behavior Vocabularies (ACT-611))
- TESTS → TEST `implementations/python/tests/test_external_concept_bindings.py` (External concept binding production-path tests)
- TESTS → TEST `tools/check_autonomous_behavior_vocabularies.py` (Autonomous behavior vocabulary source integrity checker)
- IMPLEMENTS → SPEC `contracts/schemas/concept-authority/fipa-communicative-acts-source-v1.json` (fipa-communicative-acts-source-v1 published schema)
- IMPLEMENTS → SPEC `contracts/schemas/concept-authority/w3c-activitystreams-activity-types-source-v1.json` (w3c-activitystreams-activity-types-source-v1 published schema)
