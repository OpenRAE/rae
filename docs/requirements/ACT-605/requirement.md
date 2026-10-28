---
id: ACT-605
title: "Declarative Baseline Behavior Profiles"
status: ACTIVE
type: FUNCTIONAL
priority: SHOULD
wave: 2
created_at: 2026-04-03T06:02:32.681038Z
updated_at: 2026-08-01T18:41:07.253514Z
---

# ACT-605 — Declarative Baseline Behavior Profiles

## Statement

The ecosystem shall support declarative baseline and background behavior profiles for non-adversarial participants, including user activity patterns and other ambient scenario activity.

## Rationale

Requirement inventory expansion. Realistic scenarios require first-class specification of background participant behavior, not only adversarial and defensive activity.

## Traceability

- DOCUMENTS → SPEC `specs/formal/participant-semantics/autonomous-execution.md` (Autonomous participant execution formal specification)
- DOCUMENTS → DOCUMENTATION `docs/decisions/issue-213-act-605-baseline-behavior-profiles-preflight.md` (ACT-605 reconciliation preflight)
- DOCUMENTS → ADR `docs/decisions/adrs/adr-092-autonomous-benign-participants-under-shared-time.md` (ADR-092 autonomous participant authority)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/participant_behavior_specification.py` (Participant behavior specification autonomous policy ingress)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/participant_execution.py` (Versioned autonomous participant execution policies)
- TESTS → TEST `implementations/python/tests/test_issue_898_participant_execution_control.py` (Autonomous participant control and lifecycle coverage)
- TESTS → TEST `implementations/python/tests/test_issue_899_participant_resource_budgets.py` (Autonomous participant v3 resource-budget coverage)
- TESTS → TEST `implementations/python/tests/test_dsl_437_benign_participant_execution.py` (Autonomous participant behavior execution coverage)
- IMPLEMENTS → GITHUB_ISSUE `213` (Issue #213)
- TESTS → TEST `implementations/python/tests/test_dsl_437_evaluation_authority.py` (Autonomous participant evaluation-authority coverage)
- TESTS → TEST `implementations/python/tests/test_dsl_437_snapshot_durability_conformance.py` (Autonomous participant durability and conformance coverage)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/compiler/participant_autonomous_execution.py` (Autonomous participant runtime compilation)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/semantics/participant_behavior/__init__.py` (Autonomous participant semantic validation)
- IMPLEMENTS → SPEC `contracts/schemas/participant-runtime/participant-execution-control-v1.json` (participant-execution-control-v1 published schema)
- IMPLEMENTS → SPEC `contracts/schemas/participant-runtime/participant-execution-service-state-v1.json` (participant-execution-service-state-v1 published schema)
