---
id: RUN-303
title: "Planning Semantics"
status: ACTIVE
type: FUNCTIONAL
priority: MUST
wave: 1
created_at: 2026-04-03T05:39:40.776232Z
updated_at: 2026-04-05T03:20:37.242630Z
---

# RUN-303 — Planning Semantics

## Statement

The runtime shall define planning semantics for ordering, dependency management, refresh behavior, and execution applicability.

## Rationale

Current state: implemented. Planning needs normative semantics so lifecycle decisions do not drift across validators, compilers, and runtimes.

## Traceability

- CONSTRAINS → SPEC `specs/formal/planner/README.md` (Planner Graph Semantics)
- DOCUMENTS → DOCUMENTATION `docs/explain/sdl/runtime-architecture.md` (SDL Runtime Architecture)
- CONSTRAINS → SPEC `specs/formal/planner/dependency-ordering.md` (Planner Dependency Ordering)
- CONSTRAINS → SPEC `contracts/schemas/plans/provisioning-plan-v1.json` (Provisioning Plan Schema)
- CONSTRAINS → SPEC `contracts/schemas/plans/orchestration-plan-v1.json` (Orchestration Plan Schema)
- CONSTRAINS → SPEC `contracts/schemas/plans/evaluation-plan-v1.json` (Evaluation Plan Schema)
- TESTS → TEST `implementations/python/tests/test_semantics_planner.py` (Planner Semantic Tests)
- TESTS → TEST `implementations/python/tests/test_runtime_planner.py` (Runtime Planner Tests)
- TESTS → TEST `implementations/python/tests/test_fm2_semantics.py` (FM2 Semantic Tests)
- DOCUMENTS → GITHUB_ISSUE `1103` (Bounded dependency-cycle detection)
- DOCUMENTS → DOCUMENTATION `docs/decisions/issue-1103-bounded-dependency-cycle-detection-preflight.md` (Iterative graph-traversal decision and compatibility boundary)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/semantics/planner.py` (Iterative strongly-connected dependency analysis)
- TESTS → TEST `implementations/python/tests/test_semantics_planner.py` (Cycle-oracle, long-chain, and deterministic-order regressions)
- IMPLEMENTS → SPEC `contracts/schemas/plans/evaluation-plan-v1.json` (evaluation-plan-v1 published schema)
- IMPLEMENTS → SPEC `contracts/schemas/plans/orchestration-plan-v1.json` (orchestration-plan-v1 published schema)
- IMPLEMENTS → SPEC `contracts/schemas/plans/provisioning-plan-v1.json` (provisioning-plan-v1 published schema)
