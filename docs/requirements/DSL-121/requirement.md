---
id: DSL-121
title: "Participant Interaction Budget Surface"
status: ACTIVE
type: FUNCTIONAL
priority: MUST
created_at: 2026-04-05T01:39:33.007327Z
updated_at: 2026-10-09T00:00:00Z
---

# DSL-121 — Participant Interaction Budget Surface

## Statement

The language shall support authored participant interaction budgets and limits, including step, turn, time, token, tool-use, and comparable bounded-resource constraints where relevant.

## Rationale

Primary-source refresh shows that participant tasks and benchmarks often rely on explicit interaction budgets rather than leaving bounded-resource limits implicit.

## Traceability

- DOCUMENTS → SPEC `specs/formal/participant-episode-model/README.md` (Participant episode + budget model formal design (issue #122))
- IMPLEMENTS → GITHUB_ISSUE `308`
- DOCUMENTS → SPEC `specs/formal/participant-semantics/autonomous-execution.md` (DSL-121 interaction dimensions, tool-use scope, logical-time basis, and quota disclosure)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/participant_resource_budgets.py` (Authored interaction kinds, logical-time basis, and the shared tool-scope and disclosure rules)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/participant_behavior/_view_boundaries.py` (Sensitive resource_budget view-rule class)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/validator/_participant_resource_budget_scopes.py` (Tool-scope resolution and explicit quota disclosure validation, and the validator entry point that runs them after the owner checks)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/validator/_content_objectives.py` (Validator hook for the resource-budget owner, tool-scope and disclosure checks)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/composition/_behavior.py` (Namespaced resource-budget dimension refs)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/participant_resource_types.py` (Governed interaction catalog, units, accounting modes, and shared-time meter)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/participant_resource_budgets.py` (Published demand tool scope and the scenario-time meter rule on quantities, measurements, and events)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/participant_resource_validation.py` (Parent tool-scope containment)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/schema_factoring.py` (Shared property-name rules that keep the materialized-scenario schema within its publication budget)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/compiler/participant_autonomous_execution.py` (Projection into the canonical demand)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/compiler/participant_resource_scopes.py` (Tool-scope and disclosure projection)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/models/participant_resources.py` (Compiled tool scope and disclosure ref)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/participant_scheduler_resources.py` (Per-action tool-scoped reservation and measurement)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/participant_scheduler_binding.py` (Per-action measurement requirements)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/participant_resource_rejection.py` (Disclosed quota on rejected attempts)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/participant_resource_scenario_time.py` (RAES-metered elapsed logical time)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/participant_resource_reservation.py` (Deterministic budget event ids and zero-quantity admission)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/participant_scheduler_policy.py` (Policy identity that omits unset DSL-121 demand fields)
- TESTS → TEST `implementations/python/tests/test_issue_308_participant_interaction_budgets.py` (Projection, distinct dimensions, tool scope, disclosure, composition, and contract negatives)
- TESTS → TEST `implementations/python/tests/test_issue_1241_schema_publication_size.py` (Shared property-name rules stay lossless and the materialized-scenario schema fits its budget)
