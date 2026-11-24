---
id: SEM-231
title: "Participant-Relative Predicate Opacity And Supervisor Observation Semantics"
status: ACTIVE
type: FUNCTIONAL
priority: MUST
wave: 4
created_at: 2026-07-29T04:33:26.550312Z
updated_at: 2026-07-29T15:37:00.506490Z
---

# SEM-231 — Participant-Relative Predicate Opacity And Supervisor Observation Semantics

## Statement

The ecosystem shall define revisioned participant-relative predicate-opacity semantics over a declared possible-point carrier, with explicit observer or coalition, secret predicate, initial information, accumulated observation including supervisor decisions and observable omissions, memory and horizon, supervisor and policy visibility, passive or active strategy quantifiers, declassification, time and order, nondeterminism, concurrency, probability scope, and independent definition, bounded-checking, model-checking, proof, runtime-enforcement, backend-declaration, backend-realization, and conformance states, without conflating opacity with policy noninterference, projected-history equality, epistemic indistinguishability, trace relations, simulation, refinement, or bisimulation.

## Rationale

SEM-230 governs participant-policy noninterference, but it intentionally delegates selected-secret opacity and supervisor-visibility semantics. Without a separate predicate-opacity authority, equal projected histories, hidden supervisor implementations, finite probes, randomization, or declassification could be misreported as opacity. This requirement supplies the missing one-sided epistemic relation while preserving the incumbent participant carriers and independent assurance axes.

## Traceability

- IMPLEMENTS → SPEC `contracts/profiles/behavioral-relation/participant-opacity-runtime-reference-v1.json` (Revisioned participant-opacity runtime profile)
- TESTS → TEST `implementations/python/tests/test_issue_965_participant_opacity_backend.py` (Backend participant-opacity assurance tests)
- IMPLEMENTS → GITHUB_ISSUE `965` (Declare and validate backend participant-opacity realization)
- DOCUMENTS → GITHUB_ISSUE `OpenRAE/rae#961` (Implement bounded participant-opacity profiles and falsification)
- DOCUMENTS → GITHUB_ISSUE `OpenRAE/rae#962` (Model-check finite participant-opacity profiles)
- DOCUMENTS → GITHUB_ISSUE `OpenRAE/rae#965` (Declare and validate backend participant-opacity realization)
- IMPLEMENTS → SPEC `specs/formal/participant-semantics/participant-predicate-opacity.md` (Participant-relative predicate opacity formal specification)
- IMPLEMENTS → CONFIG `contracts/concept-authority/behavioral-relations-v1.json` (Behavioral relation concept authority catalog)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/base.py` (Behavioral claim binding contract model)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/behavioral_claims.py` (Behavioral claim binding contract model)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/behavioral_relations.py` (Behavioral relation catalog and assurance validators)
- IMPLEMENTS → ADR `docs/decisions/adrs/adr-099-participant-relative-predicate-opacity.md` (ADR-099: Participant-relative predicate opacity)
- TESTS → TEST `implementations/python/tests/test_sem_231_participant_predicate_opacity.py` (SEM-231 participant predicate opacity contract tests)
- TESTS → TEST `implementations/python/tests/test_issue_810_participant_opacity_design.py` (Issue 810 participant opacity design tests)
- IMPLEMENTS → GITHUB_ISSUE `810` (Define participant-relative predicate-opacity semantics and implementation path)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/participant_opacity.py` (Participant-opacity bounded analysis contracts)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/participant_opacity/_service.py` (Deterministic bounded participant-opacity checker and replay)
- TESTS → TEST `implementations/python/tests/test_issue_961_participant_opacity.py` (Bounded participant-opacity analysis tests)
- IMPLEMENTS → GITHUB_ISSUE `961` (Implement bounded participant-opacity profiles and falsification)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/_participant_opacity_model_check.py` (Finite participant-opacity model-check contracts)
- TESTS → TEST `implementations/python/tests/test_issue_962_participant_opacity_model_check.py` (Finite participant-opacity model-check tests)
- IMPLEMENTS → GITHUB_ISSUE `962` (Issue #962 finite participant-opacity model checking)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/participant_opacity/_model_check.py` (Explicit-state participant-opacity model checker)
- IMPLEMENTS → GITHUB_ISSUE `963` (Prove participant-opacity relation theorems under declared assumptions)
- IMPLEMENTS → PROOF `specs/formal/participant-semantics/isabelle/Participant_Opacity.thy` (Kernel-checked participant-opacity theorem)
- TESTS → TEST `implementations/python/tests/test_issue_963_participant_opacity_proof.py` (Issue 963 participant-opacity proof integration tests)
- VERIFIES → PROOF `specs/formal/participant-semantics/participant-opacity-proof-evidence.json` (Participant-opacity proof evidence record)
- IMPLEMENTS → CONFIG `contracts/profiles/behavioral-relation/participant-opacity-runtime-reference-v1.json` (Bounded participant-opacity runtime reference profile)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/participant_opacity.py` (Participant-opacity runtime binding and support contracts)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/participant_opacity_runtime.py` (Bounded participant-opacity runtime admission validator)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/participant_opacity_enforcement.py` (Secret-independent participant-opacity enforcement normalizer)
- TESTS → TEST `implementations/python/tests/test_issue_964_participant_opacity_runtime.py` (Issue 964 bounded participant-opacity runtime boundary tests)
- IMPLEMENTS → GITHUB_ISSUE `964` (Enforce declared participant-opacity profiles in the reference runtime)
