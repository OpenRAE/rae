---
id: RUN-301
title: "Instantiated Scenario Model"
status: ACTIVE
type: FUNCTIONAL
priority: MUST
wave: 1
created_at: 2026-04-03T05:39:40.530002Z
updated_at: 2026-04-05T03:19:47.798914Z
---

# RUN-301 — Instantiated Scenario Model

## Statement

The runtime shall define an instantiated scenario model that resolves parameters into a concrete scenario prior to runtime compilation.

## Rationale

Current state: implemented. A concrete instantiated scenario is needed so later stages operate on resolved values rather than backend-defined substitution behavior.

## Traceability

- DOCUMENTS → DOCUMENTATION `docs/explain/sdl/runtime-architecture.md` (SDL Runtime Architecture)
- CONSTRAINS → SPEC `contracts/schemas/sdl/scenario-instantiation-request-v1.json` (Scenario Instantiation Request Schema)
- CONSTRAINS → SPEC `contracts/schemas/sdl/instantiated-scenario-v1.json` (Instantiated Scenario Schema)
- TESTS → TEST `implementations/python/tests/test_runtime_planner.py` (Runtime Planner Tests)
- IMPLEMENTS → SPEC `contracts/schemas/sdl/scenario-instantiation-request-v1.json` (scenario-instantiation-request-v1 published schema)
