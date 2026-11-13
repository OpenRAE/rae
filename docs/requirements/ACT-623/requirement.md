---
id: ACT-623
title: "Participant Episode Structure"
status: DRAFT
type: FUNCTIONAL
priority: MUST
created_at: 2026-04-05T01:39:33.224963Z
updated_at: 2026-04-05T01:39:33.224963Z
---

# `ACT-623` participant episode structure

## Statement

The ecosystem shall support participant episode structure, including initialization, turn or interaction ordering, resettable starts, and end conditions, as a first-class participant concern.

## Rationale

Primary-source refresh shows that participant behavior is often organized as bounded episodes or turns rather than as an unstructured stream of actions.

## Traceability

- DOCUMENTS → SPEC `specs/formal/participant-episode-model/README.md` (Participant episode + budget model formal design (issue #122))
- IMPLEMENTS → GITHUB_ISSUE `309` (ACT-623 — Participant Episode Structure)
- IMPLEMENTS → SPEC `specs/sdl/sections.md` (ACT-623 first-class episode structure, runtime binding, and conformance contract)
- IMPLEMENTS → SPEC `specs/formal/participant-behavior-model/README.md` (ACT-623 first-class aggregate member for every behavior mode)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/compiler/addresses.py` (ACT-623 shared participant.episode-policy address)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/compiler/participant_behaviors.py` (ACT-623 compiled aggregate episode_policy_address)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/compiler/participant_episode_policies.py` (ACT-623 compiled policy address shared with the aggregate)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/models/behavior_resources.py` (ACT-623 compiled aggregate episode_policy_address)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/models/participant_episode_validation.py` (ACT-623 shared recorded-history policy check)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/participant_episode_binding.py` (ACT-623 runtime binding of policies to implementation selections)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/control_plane_configuration.py` (ACT-623 installed binding option and configuration checks)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/control_plane_plan_authorization.py` (ACT-623 planner authorization under the exact installed binding)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/manager_plan_admission.py` (ACT-623 plan admission under the exact installed binding)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/interaction.py` (ACT-623 apply admission passes the installed binding)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/runtime_experiment_admission.py` (ACT-623 trial admission passes the installed binding)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/participant_control_episode_admission.py` (ACT-623 request and result bounds on ordinary dispatch)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/mixed_runtime_lifecycle.py` (ACT-623 request and result bounds on mixed-control lifecycle dispatch)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/time_control.py` (ACT-623 clock resets stay within the authored reset bounds)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/interaction_results.py` (ACT-623 composed time and scheduler results stay within the policy)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/runtime_run_context.py` (ACT-623 installed binding, target check, and restored history check)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_conformance/conformance/participant_episode_structure.py` (ACT-623 recorded episode history conformance against the compiled structure)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_conformance/conformance/participant_episode_case.py` (ACT-623 target conformance case)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_conformance/conformance/target.py` (ACT-623 target runner episode case and probe model reuse)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_conformance/conformance/target_probes.py` (ACT-623 probe runtime binding and compiled probe model)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_conformance/conformance/report.py` (ACT-623 not-applicable conformance case rules)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_conformance/conformance/diagnostics.py` (ACT-623 episode-structure diagnostic code and public diagnostic interface)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_conformance/conformance/__init__.py` (ACT-623 episode-structure conformance export)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_conformance/__init__.py` (ACT-623 episode-structure conformance facade export)
- IMPLEMENTS → CODE_FILE `tools/policy/adr_policy.yaml` (ACT-623 public runtime binding interface for conformance)
- IMPLEMENTS → CODE_FILE `tools/formal_semantic_validation/_replay.py` (ACT-623 absent aggregate policy addresses do not change retained fingerprints)
- DOCUMENTS → DOCUMENTATION `docs/explain/sdl/participant-episode-runtime-binding.md` (ACT-623 attachment, runtime binding, and conformance guide)
- DOCUMENTS → DOCUMENTATION `docs/decisions/issue-309-participant-episode-runtime-binding.md` (ACT-623 runtime binding design)
- TESTS → TEST `implementations/python/tests/test_issue_309_act_623_participant_episode_structure.py` (ACT-623 cross-kind attachment, aggregate membership, schema placement, and history conformance)
- TESTS → TEST `implementations/python/tests/test_issue_309_episode_runtime_binding.py` (ACT-623 implementation kinds, binding refusals, and lifecycle bounds)
- TESTS → TEST `implementations/python/tests/test_issue_309_episode_runtime_admission.py` (ACT-623 plan admission and clock-reset bounds)
- TESTS → TEST `implementations/python/tests/test_issue_309_episode_target_conformance.py` (ACT-623 target runner outcomes and probe model reuse)
- TESTS → TEST `implementations/python/tests/test_issue_309_policy_ownership.py` (ACT-623 requirement-governance route and ownership bounds)
- TESTS → TEST `implementations/python/tests/test_conformance_facade_parity.py` (ACT-623 conformance facade export parity)
- TESTS → TEST `implementations/python/tests/test_runtime_conformance.py` (ACT-623 not-applicable episode cases keep the existing target failures)
- TESTS → TEST `implementations/python/tests/test_issue_989_versioned_evidence.py` (ACT-623 absent aggregate policy addresses keep the full capture dimension)
