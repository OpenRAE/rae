---
id: EXP-709
title: "Derived Measure And Evaluation Model"
status: ACTIVE
type: FUNCTIONAL
priority: MUST
wave: 2
created_at: 2026-04-03T06:39:28.747413Z
updated_at: 2026-06-22T15:12:00.516490Z
---

# EXP-709 — Derived Measure And Evaluation Model

## Statement

The ecosystem shall distinguish captured evidence from derived measures, evaluations, scores, summaries, and comparable analysis outputs computed from that evidence.

## Rationale

Requirement inventory expansion. Derived evaluations must stay distinct from the underlying evidence they interpret.

## Traceability

- DOCUMENTS → ADR `docs/decisions/adrs/adr-064-experiment-evidence-and-measure-contract-boundary.md` (ADR-064 Experiment Evidence and Measure Contract Boundary)
- DOCUMENTS → SPEC `specs/formal/experiment-core/README.md` (Experiment Core Formal Specification)
- TESTS → TEST `implementations/python/tests/test_runtime_contracts.py` (Experiment derived measure conformance and rejection tests)
- IMPLEMENTS → GITHUB_ISSUE `88` (Experiment evidence & measures (EXP-707, EXP-708, EXP-709, EXP-715))
- IMPLEMENTS → SPEC `contracts/schemas/experiment-core/experiment-derived-measure-v1.json` (experiment-derived-measure-v1 published schema)
