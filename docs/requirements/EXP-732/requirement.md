---
id: EXP-732
title: "Realized Evidence Sources And Augmentation Provenance"
status: ACTIVE
type: FUNCTIONAL
priority: MUST
created_at: 2026-04-05T01:59:50.853423Z
updated_at: 2026-09-15T00:00:00Z
---

# EXP-732 — Realized Evidence Sources And Augmentation Provenance

## Statement

The ecosystem shall preserve, as part of run and apparatus provenance, the authored evidence requirements, the realized evidence sources used to satisfy them, and any processor or backend augmentation added for capture, evaluation, or operation.

## Rationale

Honest experiment interpretation requires preserving not only what data were captured, but also how the capture requirement was satisfied and what augmentation was added along the way.

## Traceability

- DOCUMENTS → GITHUB_ISSUE `347` (Issue #347 — Multi-Organizational Authority And Governance Contracts)
- IMPLEMENTS → GITHUB_ISSUE `128` (Issue #128 - Observability evidence conformance implementation)
- DOCUMENTS → DOCUMENTATION `docs/research/experiment-core/issue-342-exp-732-evidence-source-augmentation-provenance-preflight-guardrails.md` (Evidence source augmentation provenance preflight guardrails)
- DOCUMENTS → DOCUMENTATION `docs/research/experiment-core/issue-342-exp-732-evidence-provenance-2026-09-15.md` (Current provenance implementation guardrails)
- IMPLEMENTS → GITHUB_ISSUE `342` (Evidence source and augmentation provenance joins)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/evidence_requirements.py` (Authored evidence intent and explicit capture bindings)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/experiment_evidence.py` (Capture requirement, source and evidence traceability carriers)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/experiment_run.py` (Archival run, apparatus and exact disclosure evidence references)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/experiment_disclosure.py` (Processor/backend augmentation provenance)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/evidence_satisfaction.py` (Content-backed requirement, record, source and apparatus validation)
- IMPLEMENTS → DOCUMENTATION `specs/formal/experiment-core/README.md` (Evidence provenance chain and verification limits)
- IMPLEMENTS → CONFIG `tools/policy/requirement_order.yaml` (Scoped evidence-provenance ownership)
- TESTS → TEST `implementations/python/tests/test_exp_732_evidence_provenance.py` (Provenance round trip and contradictory identity rejection)
- TESTS → TEST `implementations/python/tests/test_requirement_governance.py` (Evidence-provenance policy ownership enforcement)
- TESTS → TEST `implementations/python/tests/test_issue_1112_capture_admission.py` (Authored capture admission and content-backed satisfaction)
- TESTS → TEST `implementations/python/tests/test_dsl_124_authored_evidence_requirements.py` (Preserved authored evidence dimensions and references)
- TESTS → TEST `implementations/python/tests/test_sem_225_augmentation_semantics.py` (Augmentation classifications and exact evidence traceability)
- TESTS → TEST `implementations/python/tests/test_specification_coverage.py` (Current and historical specification capture integrity)
- TESTS → TEST `implementations/python/tests/test_formal_semantic_validation.py` (Current formal replay and immutable release integrity)
- TESTS → TEST `implementations/python/tests/test_issue_989_versioned_evidence.py` (Versioned capture source and drift enforcement)
- TESTS → TEST `implementations/python/tests/test_observability_evidence_conformance.py` (Tests verify augmentation provenance diagnostics for evidence and carriers)
- TESTS → TEST `contracts/fixtures/experiment-core/experiment-run-v1/invalid/augmentation-without-affected-refs.json` (Semantic-invalid fixture for missing augmentation affected_refs)
