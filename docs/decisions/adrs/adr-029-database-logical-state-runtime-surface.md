# ADR-029: Database Logical-State Runtime Surface

## Status

accepted

## Date

2026-05-22

## Context

Issue #388 requires ACES SDL to represent participant-observable database
logical state as structured facts. The motivating PostgreSQL inventory includes
database names, schemas, tables, roles, runtime settings, listener facts, and
application access such as "webapp connects to database techvault as role
techvault".

The repository already has adjacent surfaces, but none owns this meaning by
itself:

- `Node.services` declares transport-level service bindings such as
  `tcp/5432`.
- `Node.runtime.network.published_ports` records host/OS publication of
  container ports.
- `Node.runtime.applications` records participant-observable HTTP route/API/UI
  inventory.
- `Node.runtime.local_identity` records OS-local user/group/sudo facts.
- top-level `accounts` records scenario/provisioning account resources.
- top-level `relationships` records typed edges between scenario elements.
- `runtime.environment`, `runtime.processes`, and runtime filesystem inventory
  record surrounding runtime facts, not database object catalogs.

The design risk is to overload one of those surfaces and make transport
bindings, application routes, database catalogs, database roles, OS accounts,
environment secrets, and connectivity relationships mean the same thing.

## Decision

### 1. Model database logical state as node-scoped runtime inventory

Database logical-state observations belong under `Node.runtime`, as typed
observed facts attached to the node that hosts the database process or service.
The initial owning surface should be a `database_services` inventory under
`RuntimeConfiguration`.

The owning node is implicit from the enclosing node. The owning transport
service must be explicit by referencing a declared same-node
`Node.services[].name` or its qualified `nodes.<node>.services.<name>` form,
matching the `runtime.applications` ownership pattern. A database inventory
must not mutate `Node.services`, `infrastructure`,
`Source.build.config.exposed_ports`, or `runtime.network.published_ports`.

The initial surface must not add a new top-level `databases`, `schemas`,
`tables`, `roles`, or `database_relationships` section. A future authored
database intent/provisioning surface would need a distinct decision and must
not reuse this observed runtime inventory meaning accidentally.

### 2. Keep stable identities separate from database object names

Database object names are data. They may be case-sensitive, quoted,
engine-specific, or awkward as reference path segments. Do not use raw database,
schema, table, or role names as YAML mapping keys.

Prefer list records with explicit stable identifiers, such as
`database_service_id`, `database_id`, `schema_id`, `table_id`, and `role_id`,
alongside observed `name` fields. If an implementation intentionally lets an
observed name double as an identifier, the model must reject empty values,
variable placeholders, duplicates in the owning scope, and values that cannot
be referenced unambiguously.

Canonical reference forms should include the owning node and runtime boundary,
for example:

`nodes.<node>.runtime.database_services.<database_service_id>`

`nodes.<node>.runtime.database_services.<database_service_id>.databases.<database_id>`

`nodes.<node>.runtime.database_services.<database_service_id>.roles.<role_id>`

If these refs are published into the generic named-reference index, semantic
validation, module-composition namespacing, relationship validation, and docs
must be updated together so refs survive imports and ambiguity checks.

### 3. Separate engine, protocol, version, and listener facts

Database engine, protocol, and version are distinct facts:

- `engine` identifies the database engine, such as `postgresql`.
- `protocol` identifies the wire protocol, such as `postgresql`.
- `version` records the observed engine version string.
- listener facts record DB-process listener observations, not host exposure.

A known engine does not require an authored protocol merely to describe partial
state. Omitted protocol defaults to `unknown`, not an asserted `other` protocol,
and remains omitted in source-preserving serialization. This permits
instantiation and portable compilation without inventing a contradictory fact.
An explicitly supplied incompatible known protocol (including `other` for a
canonical engine) still fails validation. Selected connection operations enforce
their necessary concrete protocol and support at admission.

PostgreSQL must not be represented as `runtime.applications[].protocol: other`.
Likewise, a database listener must not replace `Node.services` or
`runtime.network.published_ports`; those surfaces remain the transport and
host-publication facts.

Listener validation needs a database-aware validator. PostgreSQL values such
as `*`, `localhost`, concrete IP addresses, hostnames, and Unix socket paths
should not be forced through filesystem-path or IP-only validators.

### 4. Model logical objects and database-local principals directly

The database surface should model databases, schemas, tables, and roles as
typed records. Database roles are database-local authorization principals. They
are not top-level `accounts`, OS-local users in `runtime.local_identity`, or
runtime environment variables.

If grants or privileges are included, they should be structured by grantee,
object reference, privilege, grant option/admin option, and scope. Raw
`GRANT`, catalog query, or `psql` output may be retained only as bounded
descriptive evidence with redaction controls; it must not be the primary
portable model.

Application-to-database access should reuse the existing top-level
`relationships` graph rather than creating a second relationship graph inside
runtime inventory. Relationship endpoints should resolve to runtime application
and database refs, and database-specific access details such as `role_ref` and
`auth_method` must be structurally validated. A flat prose description or
unvalidated `properties` convention alone is not sufficient for issue #388.

### 5. Settings are provenance-bearing facts, not raw config dumps

Relevant database runtime settings should be represented as typed fields when
portable, or as bounded setting records when engine-specific:

- `name`
- `value` or redacted value marker
- sensitivity/value classification
- provenance/source, such as introspection, configuration file, image default,
  operator override, runtime default, unknown, or other
- optional description

Reuse the existing runtime sensitivity vocabulary for redaction. Settings or
connection details that may contain credentials, hashes, private keys,
connection strings, replication secrets, or operator-only values must omit raw
values. This includes common PostgreSQL risk areas such as `primary_conninfo`,
password-related role attributes, authentication files, and TLS key material.

If a native key/value map is added for bounded backend-specific options, update
only the necessary parser hashmap preservation entries and keep values typed as
strings or a deliberately validated scalar set. Do not store raw backend
inspect payloads or unbounded catalog dumps.

### 6. Reuse existing SDL gates

The implementation must reuse the repository's existing gates:

- `SDLModel` closed-world Pydantic validation and field/model validators.
- parser key normalization, source-shorthand behavior, nested hashmap-key
  preservation, and variable-placeholder key rejection.
- shared parse helpers such as `parse_int_or_var()`,
  `parse_bool_or_var()`, `parse_runtime_enum_or_var()`,
  `absolute_path_or_var()` where a value is truly a filesystem path, and
  `coerce_string_list()`.
- `SemanticValidator` and `SDLValidationError` for same-node service refs,
  database object refs, role refs, application/database relationship refs, and
  any filesystem associations for config paths when inventories are present.
- `instantiate_scenario()` and `SDLInstantiationError` for substitution and
  concrete revalidation.
- `Relationship` as the owning relationship graph; extend that model or its
  validators narrowly if database access requires typed relationship metadata.
- Published normative schemas under `contracts/schemas/` and their reviewed
  publication ledger; `schema_bundle()` and `tools/check_generated_schemas.py`
  prove reference implementation parity with that authority (ADR-009).
- existing `aces_processor.models.Diagnostic` and published control-plane or
  runtime envelopes if database facts later flow into snapshots, reports, or
  backend diagnostics.

No new parser, schema registry, validation framework, exception hierarchy,
logging stack, persistence mechanism, backend-specific PostgreSQL dialect, or
second relationship framework is justified for this issue.

### 7. Keep the extensibility seam database-service scoped

The extension seam is the node-scoped runtime database service inventory,
parameterized by engine/protocol and owning transport service. It should not
be parameterized by `psql` output, PostgreSQL catalog table names, Docker
Compose service names, ORM framework names, or a specific scanner format.

The next likely variations are views, indexes, sequences, functions,
extensions, row-level security policy, richer grants, replication, clusters,
multiple database listeners, MySQL/MariaDB, SQLite file-backed databases, and
document stores. Those should extend typed database-service submodels or
bounded engine-specific setting/evidence fields without creating another
database schema elsewhere.

## Security and Validation Gates

- Parser gate: object identities must be concrete values, not `${var}`
  placeholders or mapping keys. If native maps are added for settings or engine
  options, update only the required `_NESTED_HASHMAP_FIELDS` entries. Avoid
  fields named `source` unless the existing runtime source-shorthand skip
  behavior remains correct for that scope.
- SDL model gate: reject malformed ports, duplicate database-service ids,
  duplicate database/schema/table/role ids in their owning scopes, empty
  object names, invalid engine/protocol/auth-method values, and raw values
  where sensitivity classification requires redaction.
- Semantic validation gate: owning service refs must resolve to the same node;
  application/database relationship endpoints must resolve; `role_ref` and
  database refs must resolve in the targeted database service; config-file
  paths should resolve to observed runtime filesystem inventory when that
  inventory is present.
- Instantiation gate: variable placeholders may stand in ordinary value fields,
  but not symbol-defining ids, relationship endpoint identities, or mapping
  keys. Concrete instantiated scenarios must revalidate.
- Contract/schema gate: reviewed normative schema changes carry publication
  ledger entries and identical reference implementation output (ADR-009).
- Host/OS exposure gate: host-published ports remain
  `runtime.network.published_ports`; DB listeners and settings must not hide
  externally reachable attack surface or duplicate host binding state.
- Secret-handling gate: database passwords, SCRAM/MD5 hashes, private keys,
  bearer tokens, connection strings, operator-only settings, and raw auth files
  must not enter examples, fixtures, diagnostics, generated schemas, logs,
  snapshots, audit details, or process command arguments.
- Runtime/control-plane gate: if database facts are reported through APIs or
  snapshots, use existing envelopes, authentication/authorization/audit
  behavior, request-size limits, idempotency patterns, persistence envelopes,
  and redacted error handling rather than raw backend payloads.

## Guardrails

- Do not add PostgreSQL facts to `runtime.applications[].description` or model
  PostgreSQL as application `protocol: other`.
- Do not add database names, schemas, tables, roles, grants, or settings to
  `Node.services`; that surface is transport binding.
- Do not place database catalogs in `infrastructure.properties`, `content`,
  `runtime.environment`, or runtime filesystem inventory merely because a
  database stores data or has config files on disk.
- Do not promote every database role into top-level `accounts` or every
  PostgreSQL role into `runtime.local_identity`.
- Do not equate DB listen settings with host reachability; container host
  publication remains a network runtime fact.
- Do not case-fold, normalize, or infer equivalence for database identifiers
  unless the engine-specific model explicitly owns that rule.
- Do not dump `pg_catalog`, `information_schema`, `pg_hba.conf`, SQL migration
  files, ORM metadata, scanner JSON, or backend inspect output as the portable
  SDL model.
- Do not make built-in databases, schemas, or roles look scenario-authored
  without an explicit built-in/system classification.
- Do not add implementation logic under `implementations/python/src/aces/`;
  that tree is compatibility-only wrappers.

## Non-Goals

- Implementing issue #388.
- Updating `examples/scenarios/techvault.sdl.yaml`.
- Building a PostgreSQL, SQL, ORM, catalog, migration, scanner, or discovery
  parser.
- Defining backend provisioning behavior for databases, schemas, tables, roles,
  grants, or credentials.
- Designing a complete cross-engine privilege algebra beyond the structure
  needed for first-class inventory and typed application access.
- Redesigning `Node.services`, `runtime.network`, `runtime.applications`,
  top-level `accounts`, `runtime.local_identity`, control-plane
  authentication, or runtime snapshot contracts.

## Consequences

### Positive

- Transport services, host publication, HTTP applications, database catalogs,
  database roles, OS-local identities, and scenario accounts stay
  distinguishable.
- Existing SDL parsing, validation, instantiation, schema generation, concept
  authority, relationship validation, diagnostics, and control-plane envelopes
  remain authoritative.
- TechVault parity can move PostgreSQL logical-state facts out of prose while
  keeping database settings and credentials redacted.

### Negative

- Database object refs are longer because they include node, runtime service,
  and object identity context.
- Some observed names may need explicit ids when their raw database spelling is
  not safe as a reference segment.

### Risks

- A top-level database section would make ownership and module namespacing
  easier to get wrong unless a distinct authored database-intent concept is
  justified later.
- A free-form database settings dictionary would bypass closed-world
  validation, provenance, redaction, and generated schema guarantees.
- Overfitting to PostgreSQL would make the ACES surface poor at representing
  other SQL engines, embedded databases, document stores, or scanner-observed
  database surfaces.

## Amendments

| Date | Commit/PR | Summary |
|------|-----------|---------|
| 2026-05-30 | d0b4332 | Corrected the runtime field reference `runtime.process` to `runtime.processes` during the DSL-139 family reconciliation. |
| 2026-09-13 | #1207 | Preserve omitted protocol knowledge through instantiation while retaining explicit engine/protocol contradiction checks. |
