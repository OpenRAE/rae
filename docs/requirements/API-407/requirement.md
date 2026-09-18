---
id: API-407
title: "Participant Feature Support And Constraint Declaration"
status: ACTIVE
type: INTERFACE
priority: SHOULD
wave: 2
created_at: 2026-04-03T06:16:04.357369Z
updated_at: 2026-06-21T02:21:42.017233Z
---

# API-407 — Participant Feature Support And Constraint Declaration

## Statement

Backend manifests shall declare unsupported, constrained, or partially supported participant features without ambiguity, distinct from general realization-support and disclosure declarations that apply across concern domains.

## Rationale

Requirement inventory expansion. Participant-feature boundaries need to be explicit in their own right, while broader realization-handling rules are covered separately.

## Traceability

- IMPLEMENTS → GITHUB_ISSUE `OpenRAE/rae#1014` (Resolve mixed-composition feature strength per provider)
- IMPLEMENTS → SPEC `contracts/schemas/plans/mixed-participant-composition-profile-v1.json` (Closed per-allocation feature requirement and downgrade authority carrier)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/mixed_composition.py` (Per-provider feature-support resolution without capability union)
- TESTS → TEST `implementations/python/tests/test_issue_1014_mixed_composition_contracts.py` (Exact, unsupported, and authorized-downgrade resolution tests)
- TESTS → TEST `implementations/python/tests/test_issue_965_participant_opacity_backend.py` (Backend participant-opacity assurance tests)
- IMPLEMENTS → GITHUB_ISSUE `965` (Declare and validate backend participant-opacity realization)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_backend_protocols/participant_capabilities.py` (Participant feature-support declaration validation)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/participant_flow_sink.py` (API-407 backend participant capability enforced at the final sink)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/participant_crossing_egress.py` (API-407 capability gate enforced at the egress serialization sink)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/participant_crossing_boundary.py` (API-407 capability gate enforced at the ingress admission sink)
- TESTS → TEST `implementations/python/tests/test_issue_1003_final_sink_flow_enforcement.py` (API-407 capability-non-permit final-sink denial tests)
- TESTS → TEST `implementations/python/tests/sem233_flow_sink_fixtures.py` (API-407 capability-resolution fixtures for final-sink tests)
- DOCUMENTS → ADR `docs/decisions/adrs/adr-060-participant-backend-facing-contract-surface.md` (ADR-060 participant backend-facing contract surface)
- DOCUMENTS → SPEC `specs/formal/runtime-contracts/participant-backend-contracts.md` (Participant backend-facing contracts formal design (API-407 feature support))
- DOCUMENTS → SPEC `contracts/schemas/backend-manifest/backend-manifest-v2.json` (Generated backend manifest v2 schema with API-407 feature_support)
- DOCUMENTS → CONFIG `contracts/concept-authority/controlled-vocabularies-v1.json` (API-407 governed feature-support-level vocabulary)
- TESTS → TEST `implementations/python/tests/test_backend_manifest.py` (API-407 feature_support validator tests)
- TESTS → TEST `implementations/python/tests/test_controlled_vocabularies.py` (Feature-support-level vocabulary parity tests)
- IMPLEMENTS → GITHUB_ISSUE `201` (Participant Feature Support And Constraint Declaration (API-407))
- IMPLEMENTS → GITHUB_ISSUE `1003` (Issue #1003 enforce participant flow policy at final runtime sinks)
- TESTS → TEST `implementations/python/tests/test_issue_1004_apparatus_backend_capabilities.py` (API-407 adversarial-control apparatus/backend feature-support declaration tests)
- DOCUMENTS → GITHUB_ISSUE `794` (Assess and design formal participant I/O control with information-flow and bisimulation semantics)
- DOCUMENTS → DOCUMENTATION `docs/research/participant-io-control/requirement-disposition.md` (Issue #794 participant information-flow/control requirement disposition)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/manifest_authority.py` (API-407 authoritative participant feature-support validation)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/feature_support.py` (API-407 participant feature-support contract model)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_backend_protocols/capability_admission.py` (API-407 participant capability admission policy)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/planner/core.py` (API-407 fail-closed planner capability preflight)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_conformance/conformance/target.py` (API-407 conformance target capability preflight)
- TESTS → TEST `implementations/python/tests/test_backend_profiles.py` (API-407 backend profile feature-support tests)
- TESTS → TEST `implementations/python/tests/test_dsl_437_benign_participant_execution.py` (API-407 planner admission and downgrade-provenance tests)
- TESTS → TEST `implementations/python/tests/test_runtime_conformance.py` (API-407 runtime conformance capability-preflight tests)
- IMPLEMENTS → GITHUB_ISSUE `801` (Declare participant I/O policy capability and realization support (API-407))
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_backend_protocols/participant_feature_admission.py` (API-407 participant feature support admission)
- IMPLEMENTS → GITHUB_ISSUE `OpenRAE/rae#965` (Declare and validate backend participant-opacity realization)
