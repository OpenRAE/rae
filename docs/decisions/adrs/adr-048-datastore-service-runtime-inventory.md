# ADR-048: Datastore Service Runtime Inventory

## Status

accepted

## Date

2026-05-30

## Context

SCN-010 (DSL-132) identifies an SDL expressivity gap for the
participant-observable logical state of a node's *non-relational* datastore.
The existing `runtime.database_services` surface is irreducibly relational
(databases, schemas, tables, engine GRANTs) and cannot shape the OpenSearch /
Elasticsearch search cluster, the Cassandra wide-column store, or the Redis
key-value store that recur across the corpus. Those nodes already fit adjacent
ACES surfaces for package identity, processes, filesystem evidence, network
attachment, and transport listeners, but no surface carries the datastore facts
that matter to participants and downstream inventory consumers: search
cluster identity, per-index identity, document cardinality, deleted-document
cardinality, store size in bytes, creation timestamp, open/closed status,
shard/replica geometry, wide-column replication strategy/factor, and key-value
persistence posture.

Adjacent surfaces each own narrower meaning:

- `runtime.database_services` records relational logical state and engine
  GRANTs, not non-relational data models or their replication/persistence
  geometry.
- `runtime.app_authorizations` records application-internal RBAC, referenced
  here only by a string `authorization_ref`.
- `runtime.software_components` records installed component identity, not
  datastore logical state.
- `Node.services` and `runtime.network` record transport and host exposure.

The design risk is to force non-relational datastore semantics into the
relational surface, a config checksum, a fake listener, or free-form
relationship properties — silently shallow-encoding a defining fact such as a
search cluster with no shard geometry.

## Decision

### 1. Add a single discriminated datastore spine under runtime

Add `Node.runtime.datastore_services`. Each entry is a single
`RuntimeDatastoreService` spine with a stable `datastore_service_id`, an optional
same-node `service` ref, an open `engine` fact, and an OPEN `data_model`
discriminator (`search_index` / `wide_column` / `key_value` / `relational` /
`unknown` / `other`). The owning node is implicit; transport exposure stays in
`Node.services` and `runtime.network`; raw files remain evidence.

### 2. Describe partial state without a deployment recipe

The `data_model` identifies described state, not a mandatory complete profile.
Search services may have no configured indexes, mappings, or known shard
geometry; wide-column replication may be unknown; key-value persistence may be
omitted or explicitly disabled. Exact supplied counts and choices remain binding.
The structural contradiction between `key_value` and `keyspace`/`column_family`
partitions remains invalid. Selected operations may require persistence,
replication, or geometry through an installed profile's admission contract,
not through universal parser completeness.

### 3. Preserve typed child inventories

The service owns single nested postures (`cluster`, `persistence`,
`transport_security`) and id-bearing child collections (`nodes`, `partitions`,
`templates`, `mappings`, and `settings`). `templates` and `mappings` are bounded
manifests rather than raw engine payloads: templates carry index patterns,
selected settings, optional mapping refs, digests, and evidence refs; mappings
carry partition refs, field-count/type census, dynamic policy, dynamic-template
count, date-detection posture, schema digests, and evidence refs. `aliases`,
`lifecycle_policies`, `ingest_pipelines`, `pubsub_channels`, `queues_streams`,
`engine_plugins`, and `backup_targets` remain bare reference-name lists.
Secret-bearing settings omit their raw value and classify `redacted` /
`operator_secret`.

`cluster` records the service-local ACES `cluster_id` plus optional native
cluster `uuid`, observed `node_count`, aggregate `doc_count`,
`store_size_bytes`, `shard_total`, and `shard_primaries`. `partitions` record
the service-local ACES `partition_id` plus optional native partition/index
`uuid`, `doc_count`, `doc_count_deleted`, `store_size_bytes`,
`creation_timestamp`, and `open_closed_status`. These are participant-observed
facts, not reference identities; ACES refs continue to target the stable
`cluster_id` / `partition_id` values.

### 4. Keep datastore inventory targetable but not executable

Services and id-bearing children may be referenced from relationships using
qualified refs:

- `nodes.<node>.runtime.datastore_services.<datastore_service_id>`
- `nodes.<node>.runtime.datastore_services.<datastore_service_id>.nodes.<node_id>`
- `nodes.<node>.runtime.datastore_services.<datastore_service_id>.partitions.<partition_id>`
- `nodes.<node>.runtime.datastore_services.<datastore_service_id>.templates.<template_id>`
- `nodes.<node>.runtime.datastore_services.<datastore_service_id>.mappings.<mapping_id>`
- `nodes.<node>.runtime.datastore_services.<datastore_service_id>.settings.<setting_id>`

These refs are inventory targets. They do not imply query execution, indexing,
replication, or persistence behavior.

## Security and Validation Gates

- Parser/model gate: stable service and child ids are concrete symbols. Enum
  fields are normalized through the single runtime enum-parse helper. Duplicate
  service ids and duplicate service-local child ids fail early. Count and byte
  fields accept only non-negative integers or `${var}` placeholders.
- Selected-operation gate: base descriptions impose no universal completeness
  threshold. Installed profiles enforce prerequisites on the selected completion
  before apply, without weakening exact declarations or configured trust/support.
- Semantic validation gate: the owning `service` ref resolves to a same-node
  binding; a non-empty, non-variable `authorization_ref` resolves to a same-node
  `app_authorization`.
- Relationship/reference gate: service and child qualified refs resolve in
  generic relationships and survive module import namespacing.
- Secret/payload gate: raw key material, credentials, secret-bearing setting
  values, and raw `_mapping` / `_template` response bodies stay out of SDL model
  data; bounded manifests retain digests and evidence refs instead.
- Contract/schema gate: published schemas are hand-governed normative authority
  (ADR-009); the reference schema bundle must match their reviewed contract
  changes and publication ledger.

## Guardrails

- Do not model non-relational datastores as relational `database_services`, fake
  HTTP applications, fake transport services, generic software components, raw
  config blobs, or prose-only relationships.
- Do not embed principals, roles, or grants here; internal RBAC is delegated to
  `runtime.app_authorizations` via `authorization_ref`.
- Do not use `datatype_census` as a search-index document-count field; it
  remains a key-value datatype census.
- Do not preserve native store-size prose such as `92.4mb`; normalize observed
  store sizes to bytes before authoring SDL.
- Do not make OpenSearch, Cassandra, or Redis the schema authority. They
  motivate the surface; the SDL model remains product-neutral.

## Non-Goals

- Implementing query execution, indexing, replication, persistence, or backend
  provisioning behavior.
- Replacing the relational `runtime.database_services` surface.
- Redesigning `runtime.app_authorizations`, `Node.services`, or
  `runtime.filesystem_inventory`.

## Consequences

### Positive

- Non-relational datastore facts become typed, targetable, and
  validation-backed without corrupting the relational surface.
- Unknown configuration remains expressible without fabricating persistence,
  replication, or mapping facts.

### Negative

- Node runtime gains another optional inventory surface.
- Consumers needing raw engine internals must retain separate evidence.

### Risks

- Over-expanding the model into a query/replication engine would recreate the
  original ambiguity under a new name.
- Description presence does not prove deployment capability or successful
  persistence. Execution admission and independent observation remain separate.

## References

- [Database Logical-State Runtime Surface](adr-029-database-logical-state-runtime-surface.md)
- [App-Authorization Runtime Inventory](adr-046-app-authorization-runtime-inventory.md)
- [Runtime Software Component Inventory](adr-034-runtime-software-component-inventory.md)
- [Scenario/Delivery Boundary for Runtime Node State](adr-033-scenario-delivery-boundary-for-runtime-node-state.md)
- [Lineage and Prior Work](../../explain/sdl/lineage.md) and
  [Design Precedents](../../explain/sdl/precedents.md)

## Amendments

| Date | Commit/PR | Summary |
|------|-----------|---------|
| 2026-06-07 | e782722 | Added structured datastore mapping manifests. |
| 2026-06-07 | adf63e5 | Added datastore cardinality fields. |
| 2026-09-13 | #1207 | Separated partial inventory descriptions from selected-operation admission; retained structural and security invariants. |
