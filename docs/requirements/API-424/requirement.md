---
id: API-424
title: "Participant-Control Provider, Composition and Effect Contracts"
status: ACTIVE
type: INTERFACE
priority: MUST
wave: 4
created_at: 2026-09-06T00:00:00Z
updated_at: 2026-09-20T00:00:00Z
---

# API-424 — Participant-Control Provider, Composition and Effect Contracts

## Statement

RAES shall publish closed, versioned portable contracts and a public
participant-control provider protocol for exact profile/mechanism selection,
resolved facts, deterministic decisions, advisory results, composition and
typed effect requests. The contracts shall bind apparatus, implementation,
configuration, authority, provenance, limitations, participant/episode,
crossing/sink, state cut, expected history, provider state and causal identities;
preserve every contributing result and explicit unsupported, abstain, conflict,
stale, failed, weakened and realization dispositions; and reuse existing action,
crossing, inject, intervention, lifecycle and evidence carriers. Executable code
selection, open label/effect/metadata maps and backend-private state shall not
be portable request authority. Backend declarations and effective support shall
remain distinct from installed providers and realized effects.

## Rationale

API-409/423 own incumbent operations and API-407/420 own capability/manifests.
They need closed composition and provider bindings, including typed review,
delay and lifecycle effect targets, before the runtime replaces its implicit
SEM-233 resolver hook. This is a protocol boundary, not a plugin host.

## Fulfillment boundary

#1072 publishes the closed selection, evaluation and teaching-profile schemas,
publication records, structural provider protocol, valid/invalid and contextual
fixtures, and trusted-context validators against #1070's sem-235/rev1.
ACTIVE is proposed in this delivery diff and becomes authoritative on merge.
Contract validity does not install a provider or execute an effect.

## Traceability
- DOCUMENTS → DOCUMENTATION `docs/research/formal-semantic-validation/index.md` (Retained evidence replay bound to participant-control contract source; no runtime claims)
- DOCUMENTS → DOCUMENTATION `docs/research/specification-coverage/index.md` (Retained evidence replay bound to participant-control contract source; no runtime claims)
- TESTS → TEST `implementations/python/tests/test_formal_semantic_validation.py` (Retained evidence replay bound to participant-control contract source; no runtime claims)
- TESTS → TEST `implementations/python/tests/test_specification_coverage.py` (Retained evidence replay bound to participant-control contract source; no runtime claims)
- IMPLEMENTS → CODE_FILE `tools/check_specification_coverage.py` (Retained evidence replay bound to participant-control contract source; no runtime claims)
- IMPLEMENTS → CODE_FILE `tools/formal_semantic_validation/_baseline.py` (Retained evidence replay bound to participant-control contract source; no runtime claims)
- IMPLEMENTS → CODE_FILE `tools/formal_semantic_validation/_loading.py` (Retained evidence replay bound to participant-control contract source; no runtime claims)
- IMPLEMENTS → CODE_FILE `tools/formal_semantic_validation/_releases.py` (Retained evidence replay bound to participant-control contract source; no runtime claims)
- IMPLEMENTS → CODE_FILE `tools/formal_semantic_validation/_retest.py` (Retained evidence replay bound to participant-control contract source; no runtime claims)
- DOCUMENTS → DOCUMENTATION `docs/research/formal-semantic-validation/analysis-v36.json` (Retained evidence replay bound to participant-control contract source; no runtime claims)
- DOCUMENTS → DOCUMENTATION `docs/research/formal-semantic-validation/bundles/retest-v36.json` (Retained evidence replay bound to participant-control contract source; no runtime claims)
- DOCUMENTS → DOCUMENTATION `docs/research/formal-semantic-validation/execution-snapshot-v36.json` (Retained evidence replay bound to participant-control contract source; no runtime claims)
- DOCUMENTS → DOCUMENTATION `docs/research/specification-coverage/analysis-v36.json` (Retained evidence replay bound to participant-control contract source; no runtime claims)
- DOCUMENTS → DOCUMENTATION `docs/research/specification-coverage/bundles/raes-standardized-specification-coverage-issue-1072-v36.json` (Retained evidence replay bound to participant-control contract source; no runtime claims)
- DOCUMENTS → DOCUMENTATION `docs/research/specification-coverage/execution-snapshot-v36.json` (Retained evidence replay bound to participant-control contract source; no runtime claims)

- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/participant_control_effect_composition.py` (Order-independent compatibility and prior logical-claim accounting)
- TESTS → TEST `implementations/python/tests/test_api_424_review_regressions.py` (Lifecycle ordering, exhausted-budget replay and duplicate-identity permutations)

- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/participant_flow_policy_profiles.py` (Bounded file reads for the consumed incumbent profile)

- IMPLEMENTS → CONFIG `contracts/schema-publication/entries/backend-manifest-v2.json`
- IMPLEMENTS → CONFIG `contracts/schema-publication/entries/backend-profile-v1.json`
- IMPLEMENTS → CONFIG `contracts/schema-publication/entries/participant-control-evaluation-v1.json`
- IMPLEMENTS → CONFIG `contracts/schema-publication/entries/participant-control-selection-v1.json`
- IMPLEMENTS → CONFIG `contracts/schema-publication/entries/participant-control-teaching-profile-v1.json`
- IMPLEMENTS → SPEC `contracts/schemas/backend-manifest/backend-manifest-v2.json`
- IMPLEMENTS → SPEC `contracts/schemas/participant-runtime/participant-control-evaluation-v1.json`
- IMPLEMENTS → SPEC `contracts/schemas/participant-runtime/participant-control-selection-v1.json`
- IMPLEMENTS → SPEC `contracts/schemas/participant-runtime/participant-control-teaching-profile-v1.json`
- IMPLEMENTS → SPEC `contracts/schemas/profiles/backend-profile-v1.json`
- DOCUMENTS → DOCUMENTATION `docs/decisions/issue-1072-api-407-feature-support-preflight.md`
- DOCUMENTS → DOCUMENTATION `docs/decisions/issue-1072-api-409-control-effect-bindings-preflight.md`
- DOCUMENTS → DOCUMENTATION `docs/decisions/issue-1072-api-424-provider-contracts-preflight.md`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/observability_plane_semantics.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_backend_protocols/participant_control_admission.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_backend_protocols/protocols.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_conformance/conformance/validators.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/__init__.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/_exports.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/_participant_control_exports.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/bundle_runtime.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/participant_control_composition.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/participant_control_coordinates.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/participant_control_effects.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/participant_control_profiles.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/participant_control_resolution.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/participant_control_results.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/participant_control_selection.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/json_ingress.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/manifest_authority.py`
- TESTS → TEST `implementations/python/tests/participant_control_contract_fixtures.py`
- TESTS → TEST `implementations/python/tests/test_api_424_capability_admission.py`
- TESTS → TEST `implementations/python/tests/test_api_424_composition_boundaries.py`
- TESTS → TEST `implementations/python/tests/test_api_424_control_effects.py`
- TESTS → TEST `implementations/python/tests/test_api_424_control_resolution.py`
- TESTS → TEST `implementations/python/tests/test_api_424_governance.py`
- TESTS → TEST `implementations/python/tests/test_api_424_participant_control_contracts.py`
- TESTS → TEST `implementations/python/tests/test_api_424_publication.py`
- TESTS → TEST `implementations/python/tests/test_api_424_security_profile.py`
- TESTS → TEST `implementations/python/tests/test_corpus_packaging.py`
- TESTS → TEST `implementations/python/tests/test_json_ingress.py`
- IMPLEMENTS → CODE_FILE `tools/generate_contract_schemas.py`
- IMPLEMENTS → CONFIG `tools/policy/requirement_order.yaml`
- IMPLEMENTS → CONFIG `docs/governance/requirement-scopes/1072.json`
- IMPLEMENTS → CONFIG `contracts/concept-authority/controlled-vocabularies-v1.json`
- IMPLEMENTS → DOCUMENTATION `docs/explain/reference/modular-participant-control-contracts.md`
- DOCUMENTS → DOCUMENTATION `docs/public/participant-control.md`

- DOCUMENTS → GITHUB_ISSUE `https://github.com/OpenRAE/rae/issues/1068` (Architecture)
- DOCUMENTS → GITHUB_ISSUE `https://github.com/OpenRAE/rae/issues/1072` (Contract publication)
- DOCUMENTS → ADR `docs/decisions/adrs/adr-108-modular-participant-control-and-governed-effects.md` (ADR-108)
- DOCUMENTS → DOCUMENTATION `docs/research/modular-participant-control/composition.md` (PC-01 through PC-03 and PC-07 through PC-15)
