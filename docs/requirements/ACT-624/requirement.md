---
id: ACT-624
title: "Participant Interaction Budgets And Quotas"
status: ACTIVE
type: FUNCTIONAL
priority: MUST
created_at: 2026-04-05T01:39:33.331612Z
updated_at: 2026-10-09T00:00:00Z
---

# ACT-624 — Participant Interaction Budgets And Quotas

## Statement

The ecosystem shall support participant interaction budgets and quotas, including action, turn, time, token, tool-use, and comparable bounded-resource limits.

## Rationale

Primary-source refresh shows that participant-supporting ecosystems commonly impose explicit budgets and quotas that materially shape behavior and evaluation.

## Traceability

- DOCUMENTS → SPEC `specs/formal/participant-episode-model/README.md` (Participant episode + budget model formal design (issue #122))
- IMPLEMENTS → GITHUB_ISSUE `310`
- DOCUMENTS → SPEC `specs/formal/participant-semantics/autonomous-execution.md` (ACT-624 aggregate interaction budget member, backend declaration, and conformance)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/participant_resource_budgets.py` (Aggregate interaction budget model, clock basis, and governed-action scope)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/participant_behavior_specification.py` (First-class resource_budget member of the behavior aggregate)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/validator/_participant_resource_budget_owners.py` (Owner scope of aggregate budgets over the compiler's participant selection, and one governing budget per participant)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/validator/_participant_resource_budget_scopes.py` (Aggregate tool scope and clock resolution)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/validator/_content_objectives.py` (Owner and scope validation hooks)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/composition/_behavior.py` (Namespaced aggregate budget refs)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/manifest_authority.py` (Evidence-required interaction_budgets behavior feature)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/manifests.py` (Manifest declaration rules for interaction budgets)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_backend_protocols/participant_capabilities.py` (Backend capability declaration rules)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_backend_protocols/participant_resource_admission.py` (Planner admission of aggregate budgets and shared pools)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/models/participant_resources.py` (Compiled interaction budget IR)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/models/behavior_resources.py` (Compiled aggregate member)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/models/__init__.py` (Model export)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/compiler/participant_resource_budget_projection.py` (Shared budget projection and aggregate budget compilation)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/compiler/participant_autonomous_execution.py` (v3 budget projection through the shared path)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/compiler/participant_resource_scopes.py` (Governed tool scope)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/compiler/participant_behaviors.py` (Aggregate member compilation)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/planner/core.py` (Planner diagnostics for aggregate budgets)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/participant_submission_options.py` (Manual submissions cannot bypass an unrealized aggregate budget)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_conformance/conformance/participant_interaction_budgets.py` (Conformance of recorded budget evidence)
- TESTS → TEST `implementations/python/tests/test_issue_310_act_624_participant_interaction_budgets.py` (Aggregate member, owners, clocks, backend declaration, admission, and conformance)
