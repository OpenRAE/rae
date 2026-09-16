---
id: EXP-731
title: "Evidence Requirement Refinement And Extension"
status: ACTIVE
type: FUNCTIONAL
priority: MUST
created_at: 2026-04-05T01:59:50.735706Z
updated_at: 2026-06-28T18:07:50.939641Z
---

# EXP-731 — Evidence Requirement Refinement And Extension

## Statement

The ecosystem shall support task-, run-, or study-level refinement and extension of authored data and evidence requirements without silently rewriting authored scenario meaning.

## Rationale

Different experiments may need to add or tighten evidence requirements without changing the base scenario contract, and that relationship needs to be explicit rather than implicit.

## Traceability

- IMPLEMENTS → GITHUB_ISSUE `128` (Issue #128 - Observability evidence conformance implementation)
- TESTS → TEST `implementations/python/tests/test_observability_evidence_conformance.py` (Tests verify capture-window and measurement-channel refinements preserve authored and evidence references)
- IMPLEMENTS → GITHUB_ISSUE `341` (Issue #341 - Evidence Requirement Refinement And Extension)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/__init__.py` (Public experiment-contract facade for evidence-requirement relations)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/_evidence_requirement_exports.py` (Evidence-requirement facade exports extracted to keep the public contract surface within static-analysis limits)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/_exports.py` (Governed public evidence-requirement relation exports)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/experiment_evidence_refinement.py` (Typed scoped relation, exact lineage resolution, and governed monotone refinement validation)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/experiment_evidence.py` (Evidence-contract public relation surface)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/experiment_apparatus.py` (Compatibility export for the extracted task relation carrier)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/experiment_task.py` (Task-scoped evidence-requirement relation carrier)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/experiment_spec.py` (Prospective run-plan evidence-requirement relation carrier)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/experiment_study_contract.py` (Study-scoped evidence-requirement relation carrier)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/experiment_run.py` (Archival run evidence-requirement relation carrier)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/experiment_run_evidence_validation.py` (Authoritative task/run relation resolution against supplied scenarios and capture specifications)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/experiment_analysis.py` (Authoritative study relation resolution against supplied scenarios and capture specifications)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/experiment_study_run_validation.py` (Study run/task membership delegates to authoritative relation-aware run evidence validation)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/trial_analysis.py` (Admitted-trial study validation passes archival relation artifacts through the authoritative study seam)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/capture_admission.py` (Conjunctive authored and scoped capture-demand compilation)
- IMPLEMENTS → CONFIG `contracts/profiles/semantic-comparison/reference-v2.json` (Current task, run, and study relation-aware comparison projections)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/semantic_comparison.py` (Versioned owner-projection policy for relation-bearing carriers)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/semantic_comparison_adapters.py` (Current relation-bearing carrier projection admission)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/semantic_comparison_projections.py` (Task, run, and study relation-aware structural and semantic projections)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/trial_compiler/compiler.py` (Authoritative pre-run relation validation and capture admission)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/trial_realization.py` (Digest-bound relation revalidation during processor planning)
- IMPLEMENTS → SPEC `specs/formal/experiment-core/README.md` (Experiment-core evidence refinement and extension semantics)
- TESTS → TEST `implementations/python/tests/test_exp_731_evidence_requirement_refinement.py` (Carrier, lineage, monotonicity, semantic comparison, trial admission, and open-scope regression coverage)
- TESTS → TEST `implementations/python/tests/test_exp_731_archival_validation.py` (Authoritative archival run and study cross-artifact relation validation)
- TESTS → TEST `implementations/python/tests/test_exp_731_trial_realization.py` (Digest-bound relation revalidation during trial realization)
- TESTS → TEST `implementations/python/tests/test_formal_semantic_validation.py` (Integrated formal evidence release selection, immutable baseline, and replay coverage)
- TESTS → TEST `implementations/python/tests/test_issue_989_versioned_evidence.py` (Current and historical research evidence release integrity coverage)
- TESTS → TEST `implementations/python/tests/test_issue_1210_semantic_comparison.py` (Owner-projection revision compatibility coverage)
- TESTS → TEST `implementations/python/tests/test_specification_coverage.py` (Integrated specification-coverage release selection and immutable bundle coverage)
