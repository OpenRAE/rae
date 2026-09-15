---
id: GOV-903
title: "Migration And Upgrade Paths"
status: ACTIVE
type: FUNCTIONAL
priority: MUST
wave: 2
created_at: 2026-04-03T07:16:00.908374Z
updated_at: 2026-07-11T01:46:42.049621Z
---

# GOV-903 — Migration And Upgrade Paths

## Statement

The ecosystem shall support migration and upgrade paths across language, processing, module, task, run, and study versions.

## Rationale

Requirement inventory expansion. Evolution requires explicit migration and upgrade paths across language, processing, module, task, run, and study artifacts.

## Traceability

- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/classification_migration.py` (Deterministic classification migration with atomic refusals and typed loss reports)
- TESTS → TEST `implementations/python/tests/test_classification_migration.py` (Legacy conversion, exact provenance, loss authorization and refusal tests)

- IMPLEMENTS → ADR `docs/decisions/adrs/adr-075-ecosystem-versioning-deprecation-and-migration-governance.md` (ADR-075 Ecosystem Versioning, Deprecation, and Migration Governance)
- IMPLEMENTS → SPEC `specs/evolution/versioning-deprecation-and-migration.md` (Versioning, Deprecation, and Migration Specification)
- IMPLEMENTS → GITHUB_ISSUE `90` (Issue #90: Versioning, deprecation & migration governance)

- IMPLEMENTS → GITHUB_ISSUE `1210` (Progressive semantic revision and migration boundary)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/semantic_revisions.py` (Explicit current revision selection and breaking adoption)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/semantic_migration.py` (Author-bound progressive adoption and binding transport)
- IMPLEMENTS → CODE_FILE `tools/formal_semantic_validation/_archival_shape.py` (Closed admission of retained research evidence without legacy semantic execution)
- IMPLEMENTS → CODE_FILE `tools/formal_semantic_validation/_archival_invariants.py` (Computed integrity joins for the finite retained evidence corpus)
- IMPLEMENTS → CODE_FILE `tools/formal_semantic_validation/_types.py` (Independent immutable archive manifest and evidence admission pins)
- TESTS → TEST `implementations/python/tests/test_semantic_comparison.py` (Current comparison profile integration)
- TESTS → TEST `implementations/python/tests/test_candidate_synthesis.py` (Current comparison profile in candidate synthesis)
- IMPLEMENTS → DOCUMENTATION `docs/research/lineage/source-audit-2026-09-14.md` (Immutable source revisions and digest-bound capture for the current lineage ledger)
- IMPLEMENTS → SPEC `specs/evolution/progressive-semantics.md` (Revision compatibility and identity contract)
- IMPLEMENTS → DOCUMENTATION `docs/migration/progressive-semantics.md` (Breaking semantic cutover and migration procedure)
- TESTS → TEST `implementations/python/tests/test_issue_1210_semantic_revisions.py` (Current revision rejection and import lifecycle)
- TESTS → TEST `implementations/python/tests/test_issue_1210_semantic_migration.py` (Adoption, sentinel decisions and classification sidecars)
- TESTS → TEST `implementations/python/tests/test_issue_1210_semantic_comparison.py` (Presence, private profile and observation projections)
- TESTS → TEST `implementations/python/tests/test_issue_1210_formatting.py` (Current formatting and safe inspection)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/_source_profile.py` (Progressive revision propagation and migration contract support)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/_legacy_classification_source.py` (Shared source parse options for classification and semantic migration)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/_yaml_loader.py` (Progressive revision propagation and migration contract support)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/composition/_expand.py` (Progressive revision propagation and migration contract support)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/formatting.py` (Progressive revision propagation and migration contract support)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/module_registry/_verified_sources.py` (Progressive revision propagation and migration contract support)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/module_registry/resolution.py` (Progressive revision propagation and migration contract support)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/parser.py` (Progressive revision propagation and migration contract support)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/scenario.py` (Progressive revision propagation and migration contract support)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_cli/_semantic_sdl.py` (Progressive revision propagation and migration contract support)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/bundle.py` (Progressive revision propagation and migration contract support)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/semantic_comparison.py` (Progressive revision propagation and migration contract support)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/semantic_comparison.py` (Progressive revision propagation and migration contract support)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/semantic_comparison_adapters.py` (Progressive revision propagation and migration contract support)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/semantic_comparison_projections.py` (Progressive revision propagation and migration contract support)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/_semantic_migration_decisions.py` (Progressive revision propagation and migration contract support)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/sdl_semantic_migration.py` (Progressive revision propagation and migration contract support)
- TESTS → TEST `implementations/python/tests/test_issue_1210_governance.py` (Progressive migration governance regression)
- TESTS → TEST `implementations/python/tests/test_sdl_catalog_parity.py` (Nullable revision metadata catalog parity)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/language_service.py` (Progressive revision metadata support)
- TESTS → TEST `implementations/python/tests/test_formal_semantic_validation.py` (Historical evidence preservation and current release selection)
- TESTS → TEST `implementations/python/tests/test_formal_semantic_validation_review.py` (Integration lane classification for current evidence replay)
- TESTS → TEST `implementations/python/tests/test_issue_989_versioned_evidence.py` (Historical evidence preservation and current release selection)
- TESTS → TEST `implementations/python/tests/test_sdl_lineage.py` (Historical evidence preservation and current release selection)
- TESTS → TEST `implementations/python/tests/test_specification_coverage.py` (Current capture selection retains historical evidence)

- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/__init__.py` (Current canonical identity and lineage cutover)

- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/canonical.py` (Current canonical identity and lineage cutover)

- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/phase_contracts.py` (Current canonical identity and lineage cutover)

- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/provenance.py` (Current canonical identity and lineage cutover)

- TESTS → TEST `implementations/python/tests/test_authored_domain_topology.py` (Canonical identity propagation and current corpus acceptance)

- TESTS → TEST `implementations/python/tests/test_corpus_packaging.py` (Canonical identity propagation and current corpus acceptance)

- TESTS → TEST `implementations/python/tests/test_enterprise_deployment_tenancy.py` (Canonical identity propagation and current corpus acceptance)

- TESTS → TEST `implementations/python/tests/test_instantiated_scenario_schema.py` (Canonical identity propagation and current corpus acceptance)

- TESTS → TEST `implementations/python/tests/test_sce_002_trial_realization.py` (Canonical identity propagation and current corpus acceptance)

- TESTS → TEST `implementations/python/tests/test_scenario_satisfiability.py` (Canonical identity propagation and current corpus acceptance)

- TESTS → TEST `implementations/python/tests/test_sdl_canonicalization.py` (Canonical identity propagation and current corpus acceptance)

- TESTS → TEST `implementations/python/tests/test_sdl_identifiers.py` (Canonical identity propagation and current corpus acceptance)

- TESTS → TEST `implementations/python/tests/test_sdl_phase_contracts.py` (Canonical identity propagation and current corpus acceptance)

- TESTS → TEST `implementations/python/tests/test_sdl_variation_points.py` (Canonical identity propagation and current corpus acceptance)

- TESTS → TEST `implementations/python/tests/test_semantic_cli.py` (Canonical identity propagation and current corpus acceptance)

- IMPLEMENTS → ADR `docs/decisions/adrs/adr-080-revision-pinned-sdl-lineage-and-provenance-ledger.md` (Amended current lineage authority for issue #1210)

- IMPLEMENTS → ADR `docs/decisions/adrs/adr-095-participant-decision-epoch-state-cut-and-delivery-semantics.md` (Amended current lineage authority for issue #1210)

- TESTS → TEST `implementations/python/tests/test_issue_1076_compute_realization.py` (Current snapshot identity and legacy VM spelling join integrity)
