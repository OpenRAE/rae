---
id: SEM-234
title: "Mixed Cross-Backend Participant-Control Composition"
status: ACTIVE
type: FUNCTIONAL
priority: MUST
wave: 4
created_at: 2026-07-31T02:14:06.833733Z
updated_at: 2026-07-31T02:14:06.833733Z
---

# SEM-234 — Mixed Cross-Backend Participant-Control Composition

## Statement

RAES SHALL define a revisioned mixed cross-backend participant-control composition profile that: (1) supports both alternative realization of one authored scenario in simulation or emulation/operation and simultaneous composed realization across two or more admitted apparatus components; (2) allocates stable compiled participant, controlled-scope, action-family, observation-source, and crossing refs without adding backend choice to portable SDL meaning; (3) binds every composition edge to apparatus identities, authority, mapping, participant/audience policy, temporal coupling and governed order, mapping loss, failure behavior, and evidence; (4) keeps participant identity, acting controller, action admission, backend realization responsibility, HLA-style ownership, routing, and disclosure authority distinct; (5) represents linked inter-trial realization changes and only finite pre-admitted within-run membership/phase schedules without rewriting trial identity or history; (6) distinguishes open/closed control-loop posture, world assumption, and federation membership; and (7) rejects or explicitly weakens compositions with missing, stale, unsupported, contradictory, or unmapped authority, capability, policy, clock/order, or evidence.

## Rationale

Existing RAES authorities support backend-neutral participant semantics, one selected realization envelope, a single acting controller, crossings, time, capability, and evidence, but do not define simultaneous mixed simulation/emulation composition or staged cross-runtime realization. HLA, co-simulation, cyber-range, LVC, and digital-twin precedents show that routing, ownership, time, topology, and empirical transfer need separate, evidenced treatment.

## Traceability

- IMPLEMENTS → GITHUB_ISSUE `OpenRAE/rae#1016` (Coordinate mixed participant runtimes fail-closed)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/mixed_runtime.py` (Typed append-only runtime phase and coordination facts)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/mixed_runtime_history.py` (Runtime composition fold and append-only invariants)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/_snapshot_updates.py` (Composition state preservation through immutable snapshot updates)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/realization_plans.py` (Typed runtime-snapshot composition carriers)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/operation_lifecycle.py` (Runtime-owned composition-phase operation kind)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/runtime_state.py` (Validated live composition state and history)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/_mixed_composition_exports.py` (Public mixed-runtime contract exports)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/__init__.py` (Public mixed-runtime configuration surface)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/backend_snapshot_contracts.py` (Runtime ownership classification for composition state)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/control_plane.py` (Single mixed-runtime mutation authority)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/control_plane_configuration.py` (Run-matched fail-closed mixed-runtime configuration)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/control_plane_recovery.py` (Exact component recovery routing without logical-target fallback)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/control_plane_store_history.py` (Composition history-head CAS support)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/control_plane_store_snapshots.py` (Durable composition state and history codec)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/mixed_runtime.py` (Exact admitted component binding and pre-effect provider decision)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/mixed_runtime_dispatch.py` (Exact allocation, topology, policy, effect-result, and recovery routing)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/mixed_runtime_state.py` (Shared validated composition-state fold updates)
- TESTS → TEST `implementations/python/tests/test_issue_1016_mixed_runtime_coordination.py` (Pure, mixed, staged, replay, failure, recovery, and no-effect witnesses)
- TESTS → TEST `implementations/python/tests/test_participant_concurrent_batch_reservations.py` (Exhaustive runtime-snapshot ownership classification)
- IMPLEMENTS → SPEC `contracts/schemas/snapshots/runtime-snapshot-v1.json` (Published mixed-runtime snapshot facts)
- DOCUMENTS → DOCUMENTATION `docs/decisions/issue-1016-mixed-runtime-coordination-preflight.md` (Issue #1016 architecture and authority boundary)
- IMPLEMENTS → GITHUB_ISSUE `OpenRAE/rae#1014` (Publish portable mixed-composition contracts)
- IMPLEMENTS → SPEC `contracts/schemas/plans/mixed-participant-composition-profile-v1.json` (Closed portable composition profile schema)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/mixed_composition.py` (Sealed profile models and root-local validation)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/mixed_composition_validation.py` (Decomposed root-local phase, activity, and transition validation)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/mixed_composition_resolution.py` (Bounded trusted-context relationship resolution)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/json_ingress.py` (Shared pre-decode nesting bound for safe composition ingress)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/bundle.py` (Reference schema bundle registration)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/__init__.py` (Public contract facade registration)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/_exports.py` (Public contract export manifest)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/versions.py` (Published composition schema-version constant)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_conformance/conformance/validators.py` (Structural-context-required conformance registration)
- TESTS → TEST `implementations/python/tests/test_issue_1014_mixed_composition_contracts.py` (Profile modes, rejection, resolution, publication, and bounded-ingress tests)
- TESTS → TEST `implementations/python/tests/test_issue_1014_mixed_composition_governance.py` (Requirement-scope, order, and ownership governance tests)
- IMPLEMENTS → GITHUB_ISSUE `OpenRAE/rae#1013` (Publish sem-234/rev1 semantic definition; no runtime realization claim)
- IMPLEMENTS → SPEC `specs/formal/participant-semantics/cross-backend-participant-control.md` (Revisioned composition, admission and phase semantics)
- IMPLEMENTS → DOCUMENTATION `docs/explain/reference/mixed-participant-composition.md` (Worked cases, clause matrix and bounded assurance)
- TESTS → TEST `implementations/python/tests/sem234_mixed_composition_model.py` (Finite trusted-context composition oracle, not production enforcement)
- TESTS → TEST `implementations/python/tests/test_sem_234_mixed_composition.py` (Admission, projection, phase and progressive-specification witnesses)
- TESTS → TEST `implementations/python/tests/test_sem_234_governance.py` (Exact semantic publication ownership)
- TESTS → TEST `implementations/python/tests/test_nox_shard_wiring.py` (Supporting delivery hygiene and CI verification wiring; not composition semantics evidence)
- TESTS → TEST `implementations/python/tests/test_issue_1238_development_container.py` (Supporting development-container delivery setup; not composition semantics evidence)
- DOCUMENTS → DOCUMENTATION `docs/decisions/issue-1013-sem-234-mixed-participant-control-preflight.md` (Composition authority and current-carrier compatibility)
- IMPLEMENTS → GITHUB_ISSUE `OpenRAE/rae#1015` (Admit mixed and staged participant trial realizations)
- IMPLEMENTS → SPEC `contracts/schemas/plans/admitted-trial-plan-v1.json` (Mixed-composition binding, profile refs, and source lineage)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/admitted_trial_plan.py` (Plan-local mixed-profile and source-lineage joins)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/admitted_trial_plan_components.py` (Closed mixed realization binding and composition-aware profiles)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/mixed_composition_resolution.py` (Trial-admission effect, projection, and all-phase resource resolution)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/trial_compiler/compiler.py` (Atomic mixed and staged trial admission)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/trial_compiler/apparatus.py` (Exact per-component apparatus and capability admission)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/trial_compiler/inputs.py` (Exact profile input and total coordinate-assignment validation)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/trial_compiler/models.py` (Immutable mixed-composition compilation request inputs)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/trial_compiler/realization_admission.py` (Selected-scenario, source-lineage, context, resource, and apparatus admission)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/trial_compiler/__init__.py` (Public realization-assignment key export)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/trial_compilation.py` (Aggregate mixed-profile and contextual-work bounds)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/trial_compiler/profiles.py` (Composition-aware entry and run identities)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/trial_realization.py` (Fail-closed mixed-runtime nonclaim enforcement)
- VERIFIES → SPEC `contracts/fixtures/plans/trial-compiler-mixed-composition-v1/identity-vectors.json` (Mixed compiler identity conformance vectors)
- TESTS → TEST `implementations/python/tests/test_issue_1015_mixed_staged_trial_admission.py` (Alternative, simultaneous, staged, drift, bounds, identity, lineage, and runtime-rejection coverage)
- TESTS → TEST `implementations/python/tests/test_formal_semantic_validation.py` (Immutable formal-evidence release binding for the changed implementation)
- TESTS → TEST `implementations/python/tests/test_specification_coverage.py` (Immutable specification-coverage release binding for the changed implementation)
- TESTS → TEST `implementations/python/tests/test_issue_989_versioned_evidence.py` (Current-release strictness and immutable historical evidence regression coverage)
- IMPLEMENTS → CODE_FILE `tools/formal_semantic_validation/_loading.py` (Current formal-evidence release selection)
- IMPLEMENTS → CODE_FILE `tools/formal_semantic_validation/_baseline.py` (Immutable formal-evidence baseline admission)
- IMPLEMENTS → CODE_FILE `tools/formal_semantic_validation/_releases.py` (Versioned formal-evidence replay and lineage checks)
- IMPLEMENTS → CODE_FILE `tools/formal_semantic_validation/_retest.py` (Current source-bound formal snapshot validation)
- IMPLEMENTS → CODE_FILE `tools/check_specification_coverage.py` (Versioned specification-coverage release selection)
- VERIFIES → SPEC `docs/research/formal-semantic-validation/bundles/retest-v36.json` (Issue #1016 source-bound formal replay release)
- VERIFIES → SPEC `docs/research/specification-coverage/bundles/raes-standardized-specification-coverage-issue-1016-v36.json` (Issue #1016 source-bound specification-coverage release)
- DOCUMENTS → GITHUB_ISSUE `OpenRAE/rae#1016` (Coordinate mixed participant runtimes fail-closed)
- DOCUMENTS → GITHUB_ISSUE `OpenRAE/rae#1017` (Conform mixed-composition backend capabilities)
- DOCUMENTS → GITHUB_ISSUE `OpenRAE/rae#1018` (Demonstrate mixed cross-backend participant control)
- DOCUMENTS → GITHUB_ISSUE `OpenRAE/rae#1019` (Reconcile mixed participant-control claims)
- DOCUMENTS → ADR `docs/decisions/adrs/adr-102-mixed-cross-backend-participant-control.md` (ADR-102: Mixed Cross-Backend Participant Control)
- DOCUMENTS → DOCUMENTATION `docs/research/cross-backend-participant-control/composition-architecture.md` (Mixed cross-backend participant-control composition architecture)
- TESTS → TEST `implementations/python/tests/test_issue_813_cross_backend_participant_control_design.py` (Issue 813 structural acceptance gate)
- DOCUMENTS → GITHUB_ISSUE `OpenRAE/rae#813` (Design cross-backend participant control against simulation and cyber-range precedents)
