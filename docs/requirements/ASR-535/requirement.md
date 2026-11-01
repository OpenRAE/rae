---
id: ASR-535
title: "Participant Information-Flow And Relation Assurance"
status: ACTIVE
type: FUNCTIONAL
priority: MUST
wave: 3
created_at: 2026-07-15T05:45:07.036951Z
updated_at: 2026-07-28T17:25:13.606038Z
---

# ASR-535 — Participant Information-Flow And Relation Assurance

## Statement

The ecosystem shall provide executable assurance for participant information-flow and control claims, including negative leakage and declassification cases, relation-bound claim records, bounded model checks or proofs where explicitly claimed, backend conformance evidence, and explicit nonclaims that prevent finite evidence from being promoted to universal noninterference or bisimulation.

## Rationale

ADR-081 governs relation discipline and current tests provide bounded evidence, but participant information-flow policy needs its own falsification, assurance-progression, and backend-conformance obligations.

## Traceability

- TESTS → TEST `implementations/python/tests/test_issue_965_participant_opacity_backend.py` (Backend participant-opacity assurance tests)
- IMPLEMENTS → GITHUB_ISSUE `965` (Declare and validate backend participant-opacity realization)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_conformance/conformance/participant_opacity_probes.py` (Bounded backend participant-opacity conformance runner)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_conformance/conformance/participant_opacity_execution.py` (Runner-owned participant-opacity probe execution and measurement)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_conformance/conformance/participant_opacity_projection.py` (Participant-opacity transcript projection, normal form, and ownership derivation)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_conformance/conformance/participant_opacity_types.py` (Participant-opacity probe vocabulary and harness protocol)
- DOCUMENTS → GITHUB_ISSUE `800` (ASR-535 — Participant Information-Flow And Relation Assurance)
- DOCUMENTS → GITHUB_ISSUE `794` (Assess and design formal participant I/O control with information-flow and bisimulation semantics)
- DOCUMENTS → DOCUMENTATION `docs/research/participant-io-control/requirement-disposition.md` (Issue #794 participant information-flow/control requirement disposition)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_conformance/conformance/participant_policy_probes.py` (ASR-535 participant-policy probe judging and reporting)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_conformance/conformance/participant_policy_execution.py` (ASR-535 runner-owned probe execution and measurement)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_conformance/conformance/participant_policy_types.py` (ASR-535 participant-policy probe vocabulary and claim binding)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_conformance/conformance/report.py` (ASR-535 catalog-bound case claim records and report validation seam)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_conformance/conformance/diagnostics.py` (ASR-535 shared conformance diagnostic sanitization)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_conformance/conformance/target.py` (ASR-535 participant-policy harness seam on the target conformance runner)
- TESTS → TEST `implementations/python/tests/test_asr_535_participant_flow_assurance.py` (ASR-535 participant information-flow assurance tests)
- TESTS → TEST `implementations/python/tests/asr535_policy_probe_harness.py` (ASR-535 honest and adversarial participant-policy probe harnesses)
- IMPLEMENTS → DOCUMENTATION `docs/explain/reference/backend-conformance.md` (ASR-535 participant-policy probe seam, coverage rule, and nonclaims)
- IMPLEMENTS → GITHUB_ISSUE `800` (ASR-535 — Participant Information-Flow And Relation Assurance)
- DOCUMENTS → DOCUMENTATION `docs/explain/sdl/lineage.md` (ASR-535 adopted lineage, delivery status, evidence, and explicit nonclaims)
- IMPLEMENTS → GITHUB_ISSUE `OpenRAE/rae#961` (Implement bounded participant-opacity profiles and falsification)
- IMPLEMENTS → GITHUB_ISSUE `OpenRAE/rae#962` (Model-check finite participant-opacity profiles)
- IMPLEMENTS → GITHUB_ISSUE `OpenRAE/rae#965` (Declare and validate backend participant-opacity realization)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_conformance/conformance/validators.py` (Participant-opacity conformance validation integration)
- TESTS → TEST `implementations/python/tests/test_issue_961_participant_opacity.py` (Bounded participant-opacity assurance integration tests)
- IMPLEMENTS → GITHUB_ISSUE `961` (Implement bounded participant-opacity profiles and falsification)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/participant_opacity/_model_check.py` (Explicit-state participant-opacity model checker)
- IMPLEMENTS → SPEC `contracts/schemas/formal-analysis/participant-opacity-model-check-evidence-v1.json` (Participant-opacity model-check evidence contract)
- TESTS → TEST `implementations/python/tests/test_issue_962_participant_opacity_model_check.py` (Finite participant-opacity model-check tests)
- IMPLEMENTS → GITHUB_ISSUE `962` (Issue #962 finite participant-opacity model checking)
- IMPLEMENTS → GITHUB_ISSUE `963` (Prove participant-opacity relation theorems under declared assumptions)
- IMPLEMENTS → PROOF `specs/formal/participant-semantics/isabelle/Participant_Opacity.thy` (Kernel-checked participant-opacity theorem)
- TESTS → TEST `implementations/python/tests/test_issue_963_participant_opacity_proof.py` (Issue 963 participant-opacity proof integration tests)
- VERIFIES → PROOF `specs/formal/participant-semantics/participant-opacity-proof-evidence.json` (Participant-opacity proof evidence record)
- IMPLEMENTS → GITHUB_ISSUE `1109` (Make the offline Isabelle sandbox portable on Ubuntu)
- DOCUMENTS → DOCUMENTATION `docs/decisions/issue-1109-asr-535-isabelle-sandbox-portability.md` (Pinned proof-runtime allowlist decision)
- IMPLEMENTS → SPEC `contracts/schemas/formal-analysis/participant-opacity-analysis-evidence-v1.json` (participant-opacity-analysis-evidence-v1 published schema)
- IMPLEMENTS → SPEC `contracts/schemas/formal-analysis/participant-opacity-analysis-input-v1.json` (participant-opacity-analysis-input-v1 published schema)
- IMPLEMENTS → SPEC `contracts/schemas/formal-analysis/participant-opacity-model-check-input-v1.json` (participant-opacity-model-check-input-v1 published schema)
- IMPLEMENTS → SPEC `contracts/schemas/profiles/behavioral-relation-profile-v1.json` (behavioral-relation-profile-v1 published schema)

- IMPLEMENTS → GITHUB_ISSUE `OpenRAE/rae#973` (Bounded negative relation evidence with explicit nonclaims)
- IMPLEMENTS → CODE_FILE `implementations/formal/participant_crossing/counterexample_corpus.py` (Measured decisions and independent witness admission)
- IMPLEMENTS → CODE_FILE `implementations/formal/participant_crossing/counterexample_witnesses.py` (Measured decisions and independent witness admission)
- TESTS → TEST `implementations/python/tests/test_issue_973_crossing_corpus.py` (False witness, claim promotion, source and artifact drift rejection)
- TESTS → TEST `implementations/python/tests/test_issue_973_crossing_witnesses.py` (False witness, claim promotion, source and artifact drift rejection)

- IMPLEMENTS → CODE_FILE `implementations/formal/participant_crossing/machine_check.py` (Issue 974 exact finite model-check evidence; no runtime-realization claim)
- IMPLEMENTS → CODE_FILE `implementations/formal/participant_crossing/machine_check_evidence.py` (Complete carrier, model, projection, source and model-check claim joins)
- IMPLEMENTS → SPEC `specs/formal/participant-semantics/participant-crossing-machine-check.md` (Finite relation boundary, security and data flows)
- TESTS → TEST `implementations/python/tests/test_issue_974_machine_check.py` (Incomplete carriers, source drift, mutation false acceptance and claim promotion are refused)
- IMPLEMENTS → CODE_FILE `implementations/formal/participant_crossing/machine_check_publication.py` (Qualified hosted provenance and admitted artifact inventory)
- TESTS → TEST `implementations/python/tests/test_issue_974_machine_check_publication.py` (Offline verification and refusal of unadmitted publication)
- IMPLEMENTS → GITHUB_ISSUE `OpenRAE/rae#974` (Machine-check finite participant-crossing bisimulation)
- IMPLEMENTS → CODE_FILE `tools/check_participant_opacity_proof.py` (Exact shared tooling-validator and schema provenance for the existing proof axis)

- IMPLEMENTS → CODE_FILE `implementations/formal/participant_crossing/reproduction.py` (Issue 975 fresh measurement; independent acceptance requires a separate attributable review)
- IMPLEMENTS → CODE_FILE `implementations/formal/participant_crossing/reproduction_sandbox.py` (Issue 975 fresh measurement; independent acceptance requires a separate attributable review)
- IMPLEMENTS → SPEC `specs/formal/participant-semantics/participant-crossing-reproduction.md` (Isolation, exact subject and separate reviewer authority)
- TESTS → TEST `implementations/python/tests/test_issue_975_reproduction.py` (Exact comparison, isolated execution and refusal of self-approved measurement)
- TESTS → TEST `implementations/python/tests/test_issue_975_reproduction_sandbox.py` (Exact comparison, isolated execution and refusal of self-approved measurement)
- TESTS → TEST `implementations/python/tests/test_issue_975_reproduction_workflow.py` (Routine finite verification remains separate from explicit research publication)
- IMPLEMENTS → GITHUB_ISSUE `OpenRAE/rae#975` (Fresh bounded measurement and separate review authority)
- IMPLEMENTS → CODE_FILE `implementations/formal/participant_crossing/reproduction_checks.py` (Fixed independent comparison driver within the complete rootless worker boundary)
- TESTS → TEST `implementations/python/tests/test_issue_975_reproduction_checks.py` (Complete comparison inventory, exact original bytes and always-accept rejection)
- TESTS → TEST `implementations/python/tests/test_issue_975_reproduction_record.py` (Retained qualified evidence, exact artifact joins and attributable agent acceptance)
- IMPLEMENTS → DOCUMENTATION `specs/formal/participant-semantics/reproduction/pin.json` (Immutable qualified reproduction and separate acceptance record)

- IMPLEMENTS → GITHUB_ISSUE `OpenRAE/rae#976` (Reproduced finite model-check publication with explicit nonclaims)
- IMPLEMENTS → CODE_FILE `implementations/formal/participant_crossing/reproduction_record.py` (Separate attributable review admission for the retained reproduction)
- IMPLEMENTS → CODE_FILE `implementations/formal/participant_crossing/publication.py` (Bounded publication facts from admitted evidence only)
- IMPLEMENTS → DOCUMENTATION `specs/formal/assurance-fulfillment.yaml` (FM3 participant-semantics fulfillment with the finite model-check artifacts)
- IMPLEMENTS → SPEC `contracts/profiles/scientific-completeness/delivery-assessment-2026-10-31.json` (Assessment evidence without profile promotion)
- TESTS → TEST `implementations/python/tests/test_issue_976_reproduction_record.py` (Self-approved, detached, and stale reproduction records are refused)
- TESTS → TEST `implementations/python/tests/test_issue_976_crossing_publication.py` (Finite evidence is not promoted to proof, runtime, backend, noninterference, or opacity)
- TESTS → TEST `implementations/python/tests/test_issue_976_evidence_identity.py` (Retained evidence stays admissible across apparatus changes and refuses subject changes)
- IMPLEMENTS → CODE_FILE `implementations/formal/participant_crossing/reproduction_attestation.py` (Retain-time binding of review references to GitHub comment, run, job, artifact, and commit records)
