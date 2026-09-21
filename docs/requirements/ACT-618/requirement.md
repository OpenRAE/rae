---
id: ACT-618
title: "Participant Outcome Model Support"
status: ACTIVE
type: FUNCTIONAL
priority: SHOULD
wave: 2
created_at: 2026-04-03T06:15:08.649778Z
updated_at: 2026-09-21T00:00:00Z
---

# ACT-618 — Participant Outcome Model Support

## Statement

The ecosystem shall support explicit participant-local outcome models, including role-neutral outcome categories and outcome state, independent of scenario-wide evaluation.

## Rationale

Requirement inventory expansion. Participant behavior needs explicit local outcome meaning rather than only scenario-wide success or failure.

## Clause verification

- Explicit participant-local models: the versioned SEM-215 local definition and
  v2 outcome-report contract bind category, criterion/evidence basis, participant,
  episode, immutable rule revision and observation cut.
- Role-neutral categories: the same task-completion category is exercised through
  the production control plane for red, blue and ordinary-service green roles.
- Evolving outcome state: the runtime producer, append-only snapshot history and
  replay validators cover revision checks, partial/unknown/conflicting evidence,
  corrections, freshness, retries, reset, persistence and failed commits.
- Independent of scenario evaluation: real effects with admitted evidence drive
  local attainment; action success alone supplies none. No evaluator, objective
  or reward result is created. Participant views do not expose local reports.
- Historical compatibility: v1 schemas/readers remain unchanged; explicit version
  dispatch preserves old records and rejects unsupported versions. Old snapshots
  acquire an empty history, never synthetic observations or attainment.

## Traceability

- IMPLEMENTS → GITHUB_ISSUE `218` (Complete participant-local outcome categories and state)
- IMPLEMENTS → CODE `implementations/python/packages/raes/participant_local_outcome.py`
- IMPLEMENTS → CODE `implementations/python/packages/raes/participant_outcome_semantics.py`
- IMPLEMENTS → CODE `implementations/python/packages/raes/semantics/participant_outcome.py`
- IMPLEMENTS → CODE `implementations/python/packages/raes_contracts/contracts/participant_outcomes.py`
- IMPLEMENTS → CODE `implementations/python/packages/raes_contracts/participant_outcome_history.py`
- IMPLEMENTS → CODE `implementations/python/packages/raes_runtime/participant_outcome_state.py`
- IMPLEMENTS → CODE `implementations/python/packages/raes_runtime/participant_outcome_control.py`
- IMPLEMENTS → SPEC `contracts/schemas/participant-runtime/participant-outcome-report-v2.json`
- IMPLEMENTS → SPEC `specs/formal/participant-semantics/local-outcomes.md`
- DOCUMENTS → DOCUMENTATION `docs/explain/reference/participant-local-outcomes.md`
- TESTS → TEST `implementations/python/tests/test_act_618_outcome_definition.py`
- TESTS → TEST `implementations/python/tests/test_act_618_outcome_state.py`
- TESTS → TEST `implementations/python/tests/test_act_618_outcome_control.py`
- TESTS → TEST `implementations/python/tests/test_participant_concurrent_batch_reservations.py`
- TESTS → TEST `implementations/python/tests/test_specification_coverage.py`
- TESTS → TEST `implementations/python/tests/test_formal_semantic_validation.py`
- TESTS → TEST `implementations/python/tests/test_issue_989_versioned_evidence.py`
- DOCUMENTS → DOCUMENTATION `docs/research/specification-coverage/analysis-v41.json`
- DOCUMENTS → DOCUMENTATION `docs/research/formal-semantic-validation/analysis-v41.json`
