---
id: EXP-707
title: "Experiment Evidence Capture Specification"
status: ACTIVE
type: FUNCTIONAL
priority: MUST
wave: 2
created_at: 2026-04-03T06:39:28.526954Z
updated_at: 2026-06-21T23:48:51.450274Z
---

# EXP-707 — Experiment Evidence Capture Specification

## Statement

The ecosystem shall support declarative specification of what evidence, observations, traces, telemetry, artifacts, and comparable experiment data must be captured, over what scope or window, distinct from scenario-internal logging or monitoring configuration.

## Rationale

Requirement inventory expansion. Experiment data capture requirements are distinct from in-scenario operational logging or monitoring setup.

## Traceability

- DOCUMENTS → ADR `docs/decisions/adrs/adr-064-experiment-evidence-and-measure-contract-boundary.md` (ADR-064 Experiment Evidence and Measure Contract Boundary)
- DOCUMENTS → SPEC `specs/formal/experiment-core/README.md` (Experiment Core Formal Specification)
- TESTS → TEST `implementations/python/tests/test_runtime_contracts.py` (Experiment capture spec conformance and rejection tests)
- IMPLEMENTS → GITHUB_ISSUE `88` (Experiment evidence & measures (EXP-707, EXP-708, EXP-709, EXP-715))
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/experiment_capture.py` (Field- and output-contract-qualified capture requirements)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/trial_compiler/inputs.py` (Digest-bound capture specification admission)
- TESTS → TEST `implementations/python/tests/test_sce_002_trial_compiler.py` (Capture specification identity and backend admission tests)
