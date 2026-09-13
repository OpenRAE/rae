---
id: DSL-132
title: "Datastore Service Runtime Inventory"
status: ACTIVE
type: FUNCTIONAL
priority: MUST
wave: 1
created_at: 2026-05-30T06:20:47.447494Z
updated_at: 2026-09-13T00:00:00Z
---

# DSL-132 — Datastore Service Runtime Inventory

## Statement

The language shall represent relational and non-relational datastore service logical runtime state as typed node-scoped runtime inventory under a single data-model-discriminated surface — covering search/index clusters, wide-column stores, and key-value/cache/broker stores — including cluster and node-role topology, index/keyspace/logical-database partitions with shard, replica, and replication-factor geometry, templates and aliases, bounded mapping manifests, lifecycle and ingest policies, persistence and eviction posture, pub/sub channels and queues/streams, engine plugins, transport security, backup targets, and bounded provenance settings with a referenced application-authorization surface, without overloading the relational-only database object tree, transport services, filesystem evidence, software-component identity, or prose-only relationships. Data-model identity permits partial knowledge and legitimate empty configured inventories. Supplied identities, bounds, references and structurally compatible partition kinds remain validated; completeness needed by a selected operation is enforced by its admitted execution contract, not by universal base-description guards.

## Rationale

APTL TechVault SCN-010 capture of wazuh.indexer (#341), thehive-es (#352), shuffle-opensearch (#356, OpenSearch), misp-redis (#348, Redis), and thehive-cassandra (#351, Cassandra) cannot be inventoried to wazuh.manager parity depth: runtime.database_services is irreducibly relational (closed database|schema|table object tree, no shard/replica/replication-factor/keyspace/numbered-logical-db), so non-relational stores can only be shallow-encoded, which the SCN-010 observable-parity gate forbids.

## Traceability

- TESTS → TEST `implementations/python/tests/test_issue_1206_review_regressions.py` (Unknown replication does not impose base-description completeness)

- TESTS → TEST `implementations/python/tests/test_runtime_datastore.py` (test_runtime_datastore.py)
- DOCUMENTS → ADR `docs/decisions/adrs/adr-048-datastore-service-runtime-inventory.md` (ADR-048 Datastore Service Runtime Inventory)

- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/runtime_datastore.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/runtime_inventory.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/semantics/realization_runtime_concern_profiles.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/semantics/realization_specialized_projection.py`
- IMPLEMENTS → SPEC `specs/sdl/runtime-inventory.md` (Partial description and selected-operation boundary)
- IMPLEMENTS → GITHUB_ISSUE `1207` (Correct specimen-shaped completeness guards)
- TESTS → TEST `implementations/python/tests/test_issue_1207_partial_descriptions.py`
- TESTS → TEST `implementations/python/tests/test_issue_1207_profile_admission.py`
- TESTS → TEST `implementations/python/tests/test_issue_1207_recursive_inventory.py`
