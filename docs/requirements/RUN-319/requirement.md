---
id: RUN-319
title: "Participant Information-Flow Policy Enforcement"
status: ACTIVE
type: FUNCTIONAL
priority: MUST
wave: 3
created_at: 2026-07-15T05:45:06.979194Z
updated_at: 2026-07-28T03:49:46.735438Z
---

# RUN-319 — Participant Information-Flow Policy Enforcement

## Statement

The runtime shall enforce and record participant-relative crossing policies for input admission, output projection, intervention and handoff, participant-directed inject delivery, and governed transformations, failing closed when required semantics or backend capabilities are unavailable and preserving append-only decision and realization evidence.

## Rationale

Current admission, retrieval, lifecycle, and persistence surfaces do not yet form a complete portable enforcement path across participant ingress and egress.

## Traceability

- IMPLEMENTS → GITHUB_ISSUE `OpenRAE/rae#1016` (Coordinate mixed participant runtimes behind the incumbent crossing decision)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/participant_action_validation.py` (Protect runtime-owned composition state from provider mutation)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/participant_control.py` (Admit mixed participant actions without a logical provider fallback)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/participant_crossing_boundary.py` (Commit exact provider decision before mixed-runtime effect)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/participant_crossing_policy.py` (Resolve capability gates against the selected admitted allocation contract)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/participant_submission_options.py` (Require mixed dispatch resolution before invoking an effect sink)
- TESTS → TEST `implementations/python/tests/test_issue_1016_mixed_runtime_coordination.py` (Zero-call rejection and pre-effect policy-cut witnesses)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/participant_flow_sink.py` (RUN-319 SEM-233 final-sink flow-control enforcement guard)
- TESTS → TEST `implementations/python/tests/test_issue_1003_final_sink_flow_enforcement.py` (RUN-319 final-sink flow-control boundary enforcement tests)
- TESTS → TEST `implementations/python/tests/sem233_flow_sink_fixtures.py` (RUN-319 live-bound SEM-233 final-sink test fixtures)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/control_plane.py` (RUN-319 fail-closed final-sink enforcement configuration)
- DOCUMENTS → DOCUMENTATION `docs/decisions/issue-1003-sem-233-final-runtime-sinks-preflight.md` (Issue #1003 RUN-319 final-sink enforcement architecture preflight)
- IMPLEMENTS → GITHUB_ISSUE `1003` (Issue #1003 enforce participant flow policy at final runtime sinks)
- DOCUMENTS → GITHUB_ISSUE `803` (Document participant I/O control authoring, operations, and claim boundaries)
- DOCUMENTS → GITHUB_ISSUE `794` (Assess and design formal participant I/O control with information-flow and bisimulation semantics)
- DOCUMENTS → DOCUMENTATION `docs/research/participant-io-control/requirement-disposition.md` (Issue #794 participant information-flow/control requirement disposition)
- IMPLEMENTS → GITHUB_ISSUE `799` (RUN-319 — Participant Information-Flow Policy Enforcement)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/participant_crossing_history.py` (RUN-319 append-only participant crossing history contract)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/participant_crossing_action.py` (RUN-319 governed participant action ingress)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/participant_crossing_boundary.py` (RUN-319 operation-bound participant crossing boundary)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/participant_crossing_egress.py` (RUN-319 governed participant egress projection)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/participant_crossing_mediation.py` (RUN-319 participant crossing policy mediation)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/participant_crossing_policy.py` (RUN-319 fail-closed participant crossing policy resolution)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/participant_crossing_records.py` (RUN-319 durable crossing decision and governed-result records)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/participant_control.py` (RUN-319 participant intervention and handoff enforcement)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/participant_retrieval.py` (RUN-319 participant-relative governed retrieval)
- TESTS → TEST `implementations/python/tests/test_run_319_participant_flow_policy.py` (RUN-319 participant information-flow policy tests)
- TESTS → TEST `implementations/python/tests/test_api_423_participant_crossing_contracts.py` (RUN-319 exact-cut participant crossing contract tests)
- IMPLEMENTS → DOCUMENTATION `docs/migration/participant-information-flow-control.md` (Participant information-flow control migration guide)
- TESTS → TEST `implementations/python/tests/test_issue_802_participant_control_migration.py` (Issue #802 participant-control compatibility and migration tests)
- DOCUMENTS → DOCUMENTATION `docs/decisions/issue-802-api-423-participant-control-migration-preflight.md` (Issue #802 participant-control migration architecture preflight)
- IMPLEMENTS → GITHUB_ISSUE `802` (Migrate participant I/O control semantics and existing carriers)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/control_plane_api_participant_retrieval.py` (RUN-319 authenticated participant retrieval enforcement)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/control_plane_store.py` (RUN-319 participant crossing-history source classification)
- DOCUMENTS → DOCUMENTATION `docs/public/participant-control.md` (Participant input and output control guide)
- TESTS → TEST `implementations/python/tests/test_public_docs_policy.py` (Executable participant-control public guide claim example)
- IMPLEMENTS → GITHUB_ISSUE `OpenRAE/rae#964` (Enforce declared participant-opacity profiles in the reference runtime)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/participant_crossing_state_cut.py` (Atomic participant crossing state-cut binding)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/participant_opacity_enforcement.py` (RUN-319 participant-opacity crossing enforcement)
- TESTS → TEST `implementations/python/tests/test_issue_964_participant_opacity_runtime.py` (Issue 964 RUN-319 opacity mediation boundary tests)
- IMPLEMENTS → GITHUB_ISSUE `964` (Enforce declared participant-opacity profiles in the reference runtime)
