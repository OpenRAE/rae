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

- IMPLEMENTS → GITHUB_ISSUE `OpenRAE/rae#1013` (Publish sem-234/rev1 semantic definition; no runtime realization claim)
- IMPLEMENTS → SPEC `specs/formal/participant-semantics/cross-backend-participant-control.md` (Revisioned composition, admission and phase semantics)
- IMPLEMENTS → DOCUMENTATION `docs/explain/reference/mixed-participant-composition.md` (Worked cases, clause matrix and bounded assurance)
- TESTS → TEST `implementations/python/tests/sem234_mixed_composition_model.py` (Finite trusted-context composition oracle, not production enforcement)
- TESTS → TEST `implementations/python/tests/test_sem_234_mixed_composition.py` (Admission, projection, phase and progressive-specification witnesses)
- TESTS → TEST `implementations/python/tests/test_sem_234_governance.py` (Exact semantic publication ownership)
- TESTS → TEST `implementations/python/tests/test_nox_shard_wiring.py` (Supporting delivery hygiene and CI verification wiring; not composition semantics evidence)
- DOCUMENTS → DOCUMENTATION `docs/decisions/issue-1013-sem-234-mixed-participant-control-preflight.md` (Composition authority and current-carrier compatibility)
- DOCUMENTS → GITHUB_ISSUE `OpenRAE/rae#1014` (Publish portable mixed-composition contracts)
- DOCUMENTS → GITHUB_ISSUE `OpenRAE/rae#1015` (Admit mixed and staged participant trial realizations)
- DOCUMENTS → GITHUB_ISSUE `OpenRAE/rae#1016` (Coordinate mixed participant runtimes fail-closed)
- DOCUMENTS → GITHUB_ISSUE `OpenRAE/rae#1017` (Conform mixed-composition backend capabilities)
- DOCUMENTS → GITHUB_ISSUE `OpenRAE/rae#1018` (Demonstrate mixed cross-backend participant control)
- DOCUMENTS → GITHUB_ISSUE `OpenRAE/rae#1019` (Reconcile mixed participant-control claims)
- DOCUMENTS → ADR `docs/decisions/adrs/adr-102-mixed-cross-backend-participant-control.md` (ADR-102: Mixed Cross-Backend Participant Control)
- DOCUMENTS → DOCUMENTATION `docs/research/cross-backend-participant-control/composition-architecture.md` (Mixed cross-backend participant-control composition architecture)
- TESTS → TEST `implementations/python/tests/test_issue_813_cross_backend_participant_control_design.py` (Issue 813 structural acceptance gate)
- DOCUMENTS → GITHUB_ISSUE `OpenRAE/rae#813` (Design cross-backend participant control against simulation and cyber-range precedents)
