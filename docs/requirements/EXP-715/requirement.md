---
id: EXP-715
title: "Observation Capability Declaration"
status: ACTIVE
type: INTERFACE
priority: MUST
wave: 2
created_at: 2026-04-03T06:39:29.450399Z
updated_at: 2026-06-22T15:43:18.790479Z
---

# EXP-715 — Observation Capability Declaration

## Statement

The ecosystem shall require backends to declare supported observation and evidence-collection capabilities separately from execution capabilities.

## Rationale

Requirement inventory expansion. Observation support must be declared explicitly so the runtime remains agnostic and experiment claims remain honest.

## Traceability

- DOCUMENTS → ADR `docs/decisions/adrs/adr-064-experiment-evidence-and-measure-contract-boundary.md` (ADR-064 Experiment Evidence and Measure Contract Boundary)
- DOCUMENTS → SPEC `specs/formal/experiment-core/README.md` (Experiment Core Formal Specification)
- TESTS → TEST `implementations/python/tests/test_backend_manifest.py` (EXP-715 backend manifest observation capability tests)
- IMPLEMENTS → GITHUB_ISSUE `236` (Observation Capability Declaration (EXP-715))
- IMPLEMENTS → GITHUB_ISSUE `88` (Experiment evidence & measures (EXP-707, EXP-708, EXP-709, EXP-715))
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_backend_protocols/capabilities.py` (Observation capability container and offer coherence validation)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_backend_protocols/observation_capture.py` (Atomic versioned backend capture-offer declarations)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_backend_protocols/observation_manifest.py` (Capture-offer manifest serialization and reconstruction)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/observation_capture.py` (Published capture-offer contract model)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_conformance/conformance/target_manifest_probe.py` (Fail-closed capture-offer manifest conformance validation)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/capture_admission.py` (Conjunctive required-capture capability admission)
- TESTS → TEST `implementations/python/tests/test_issue_1112_capture_admission.py` (Capture-offer manifest and admission failure coverage)
