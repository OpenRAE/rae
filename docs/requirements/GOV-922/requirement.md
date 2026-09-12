---
id: GOV-922
title: "Controlled Vocabularies And Enumerations"
status: ACTIVE
type: FUNCTIONAL
priority: MUST
wave: 2
created_at: 2026-04-05T15:37:12.514093Z
updated_at: 2026-04-11T02:26:15.170014Z
---

# GOV-922 — Controlled Vocabularies And Enumerations

## Statement

The ecosystem shall define controlled vocabularies and enumerations for portable declared concepts where stable cross-artifact comparison is required, while permitting governed extension space for concepts that are RAES-native, experimental, or still evolving.

## Rationale

A mature interoperability surface needs stable portable terms where comparison matters, but it also needs governed extension space so evolving concepts do not force premature standardization or uncontrolled drift.

## Traceability

- DOCUMENTS → SPEC `specs/concept-authority/concept-authority.md` (Concept authority specification)
- TESTS → TEST `implementations/python/tests/test_controlled_vocabularies.py` (Controlled vocabulary catalog tests)
- TESTS → TEST `implementations/python/tests/test_backend_manifest.py` (Backend manifest vocabulary enforcement tests)
- TESTS → TEST `implementations/python/tests/test_runtime_contracts.py` (Controlled vocabulary schema publication tests)
- TESTS → TEST `implementations/python/tests/test_runtime_planner.py` (Planner tests for SDL OS validation with governed backend vocabularies)
- DOCUMENTS → SPEC `specs/concept-authority/controlled-vocabularies.md` (Controlled vocabularies and enumerations spec)
- DOCUMENTS → SPEC `contracts/concept-authority/controlled-vocabularies-v1.json` (Authoritative controlled vocabulary catalog)
- DOCUMENTS → DOCUMENTATION `docs/explain/reference/shared-concept-model.md` (Shared concept model design note)
- IMPLEMENTS → CODE_FILE `tools/generate_contract_schemas.py` (Schema generation routing for controlled vocabularies)
- DOCUMENTS → DOCUMENTATION `contracts/schemas/README.md` (Schema publication README)
- DOCUMENTS → DOCUMENTATION `CHANGELOG.md` (Project changelog)
- IMPLEMENTS → SCHEMA `contracts/schemas/artifact-requirements/artifact-requirement-v1.json` (Published vocabulary validation)
- IMPLEMENTS → SCHEMA `contracts/schemas/satisfiability/scenario-satisfiability-evidence-v1.json` (Published vocabulary validation)
- IMPLEMENTS → SCHEMA `contracts/schemas/sdl/instantiated-scenario-snapshot-v1.json` (Published vocabulary validation)
- IMPLEMENTS → SCHEMA `contracts/schemas/sdl/instantiated-scenario-v1.json` (Published vocabulary validation)
- IMPLEMENTS → SCHEMA `contracts/schemas/sdl/sdl-authoring-input-v1.json` (Published vocabulary validation)
- DOCUMENTS → DOCUMENTATION `docs/explain/reference/issue-1206-runtime-vocabulary-preflight.md` (Runtime vocabulary scope and semantics)
- DOCUMENTS → DOCUMENTATION `docs/explain/sdl/validation.md` (Runtime vocabulary scope and semantics)
- DOCUMENTS → DOCUMENTATION `docs/research/language-extensibility/scope-inventory.md` (Runtime vocabulary scope and semantics)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/evidence_requirements.py` (Shared governed runtime vocabulary semantics)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/image_provenance.py` (Shared governed runtime vocabulary semantics)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/nodes.py` (Shared governed runtime vocabulary semantics)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/runtime_app_authorization.py` (Shared governed runtime vocabulary semantics)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/runtime_application.py` (Shared governed runtime vocabulary semantics)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/runtime_capabilities.py` (Shared governed runtime vocabulary semantics)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/runtime_configuration.py` (Shared governed runtime vocabulary semantics)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/runtime_database.py` (Shared governed runtime vocabulary semantics)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/runtime_datastore.py` (Shared governed runtime vocabulary semantics)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/runtime_datastore_nodes.py` (Shared governed runtime vocabulary semantics)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/runtime_datastore_partitions.py` (Shared governed runtime vocabulary semantics)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/runtime_directory_identity.py` (Shared governed runtime vocabulary semantics)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/runtime_dns.py` (Shared governed runtime vocabulary semantics)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/runtime_dns_records.py` (Shared governed runtime vocabulary semantics)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/runtime_environment.py` (Shared governed runtime vocabulary semantics)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/runtime_file_service.py` (Shared governed runtime vocabulary semantics)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/runtime_filesystem.py` (Shared governed runtime vocabulary semantics)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/runtime_forwarding_agent.py` (Shared governed runtime vocabulary semantics)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/runtime_identity.py` (Shared governed runtime vocabulary semantics)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/runtime_listeners.py` (Shared governed runtime vocabulary semantics)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/runtime_mail_service/_elements.py` (Shared governed runtime vocabulary semantics)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/runtime_mail_service/_service.py` (Shared governed runtime vocabulary semantics)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/runtime_mounts.py` (Shared governed runtime vocabulary semantics)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/runtime_network.py` (Shared governed runtime vocabulary semantics)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/runtime_network_detection.py` (Shared governed runtime vocabulary semantics)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/runtime_network_sensor.py` (Shared governed runtime vocabulary semantics)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/runtime_orchestration.py` (Shared governed runtime vocabulary semantics)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/runtime_platform_application.py` (Shared governed runtime vocabulary semantics)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/runtime_platform_application_content.py` (Shared governed runtime vocabulary semantics)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/runtime_scheduled_job.py` (Shared governed runtime vocabulary semantics)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/runtime_security_monitoring/_models.py` (Shared governed runtime vocabulary semantics)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/runtime_security_monitoring_definitions.py` (Shared governed runtime vocabulary semantics)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/runtime_service_units.py` (Shared governed runtime vocabulary semantics)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/runtime_software.py` (Shared governed runtime vocabulary semantics)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/runtime_ssh_server.py` (Shared governed runtime vocabulary semantics)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/runtime_values.py` (Shared governed runtime vocabulary semantics)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/runtime_vocabulary.py` (Shared governed runtime vocabulary semantics)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/validator/_relationships.py` (Shared governed runtime vocabulary semantics)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/base.py` (Shared governed runtime vocabulary semantics)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/controlled_vocabularies.py` (Shared governed runtime vocabulary semantics)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/runtime_vocabulary_scopes.py` (Shared governed runtime vocabulary semantics)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/compiler/realization_recursive_constraints.py` (Shared governed runtime vocabulary semantics)
- TESTS → TEST `implementations/python/tests/test_issue_1206_runtime_vocabularies.py` (Runtime vocabulary identity conformance)
- TESTS → TEST `implementations/python/tests/test_issue_1206_vocabulary_consumers.py` (Runtime vocabulary identity conformance)
- TESTS → TEST `implementations/python/tests/test_issue_1206_vocabulary_families.py` (Runtime vocabulary identity conformance)
- TESTS → TEST `implementations/python/tests/test_issue_1206_vocabulary_governance.py` (Runtime vocabulary identity conformance)
- TESTS → TEST `implementations/python/tests/test_issue_1206_vocabulary_roundtrips.py` (Runtime vocabulary identity conformance)
- TESTS → TEST `implementations/python/tests/test_issue_1206_vocabulary_schema.py` (Runtime vocabulary identity conformance)
- IMPLEMENTS → SPEC `specs/sdl/runtime-inventory.md` (Runtime identity extension and ownership contract)
- IMPLEMENTS → GITHUB_ISSUE `1206` (Governed runtime vocabulary identities)
- TESTS → TEST `implementations/python/tests/test_issue_1200_mixed_runtime_constraints.py` (Delegation, taxonomy knowledge and exact membership through runtime admission)
- DOCUMENTS → DOCUMENTATION `docs/research/formal-semantic-validation/bundles/retest-v8.json` (Replayed evidence for the current vocabulary implementation)
- DOCUMENTS → DOCUMENTATION `docs/research/formal-semantic-validation/execution-snapshot-v8.json` (Replayed evidence for the current vocabulary implementation)
- DOCUMENTS → DOCUMENTATION `docs/research/specification-coverage/analysis-v7.json` (Replayed evidence for the current vocabulary implementation)
- DOCUMENTS → DOCUMENTATION `docs/research/specification-coverage/bundles/raes-standardized-specification-coverage-issue-1204-v7.json` (Replayed evidence for the current vocabulary implementation)
- DOCUMENTS → DOCUMENTATION `docs/research/specification-coverage/execution-snapshot-v7.json` (Replayed evidence for the current vocabulary implementation)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/runtime_forwarding_buffer.py` (Typed runtime vocabulary boundary)
- TESTS → TEST `implementations/python/tests/test_issue_1204_backend_preparation.py` (Governed vocabulary and conformance regression)
- TESTS → TEST `implementations/python/tests/test_issue_1204_recursive_carriage.py` (Governed vocabulary and conformance regression)
- TESTS → TEST `implementations/python/tests/test_requirement_governance.py` (Governed vocabulary and conformance regression)
- TESTS → TEST `implementations/python/tests/test_runtime_app_authorization.py` (Governed vocabulary and conformance regression)
- TESTS → TEST `implementations/python/tests/test_runtime_datastore.py` (Governed vocabulary and conformance regression)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/_capability_binding_normalization.py` (Governed identity propagation and owning field normalization)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/scenario.py` (Governed identity propagation and owning field normalization)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/planner/capability_domains.py` (Governed identity propagation and owning field normalization)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/planner/operating_system_capability_domains.py` (Governed identity propagation and owning field normalization)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/satisfiability/_translation.py` (Governed identity propagation and owning field normalization)
- TESTS → TEST `implementations/python/tests/test_issue_1206_review_regressions.py` (Private identity, alias, and finite semantic consumer regressions)
