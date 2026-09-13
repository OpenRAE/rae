# ADR-046: Application-Internal Authorization Runtime Inventory

## Status

accepted

## Date

2026-05-30

## Context

The SCN-010 expressivity gap analysis (issue #441) identifies
application-internal role-based access control as the highest-recurrence gap in
the corpus, observed at eight-plus sites: OpenSearch/Elasticsearch security,
Cassandra `system_auth`, Redis ACLs, the Kibana/OpenSearch dashboard, MISP,
TheHive, Cortex, and Shuffle. Each of these applications maintains an internal
authorization store — principals, roles, resource-scoped permissions, role
mappings, and tenants — that is the defining logical state of the node, yet no
existing runtime surface can carry it.

Adjacent surfaces each own narrower meaning:

- `runtime.identity_authorities` records wire-protocol directory state (LDAP,
  Kerberos, SAML, OIDC, SCIM, IAM) with subjects, policies, and trust edges. It
  has no resource-scoped permission grant and no notion of an application's
  private RBAC store that fronts no directory protocol.
- `runtime.database_services` records database engine GRANTs over relational
  databases/schemas/tables. It cannot express index-pattern, CQL-resource,
  Redis-ACL, or app-resource scoping, and its grant shape is engine-specific.
- `runtime.applications` records inbound HTTP routes, not the application's
  internal authorization model.
- `runtime.local_identity` records OS-local `/etc/passwd`/`/etc/group`/sudoers;
  application-internal principals are not OS accounts.

The design risk is to force application RBAC into a fake directory authority, a
database GRANT surface, OS-local identities, or free-form relationship
properties, and to leak raw bcrypt hashes, API keys, or passwords into SDL
fixtures.

## Decision

### 1. Add a node-scoped application-internal authorization surface

Add `Node.runtime.app_authorizations` as an observed runtime inventory surface.
Each entry is a `RuntimeAppAuthorization` with a stable `app_authorization_id`,
an open `resource_vocabulary` spine discriminator (`index_pattern`,
`cql_resource`, `redis_acl`, `app_resource`, `unknown`, `other`) naming the
resource space the store governs, and an `auth_enabled` flag. Tier placement
(storage RBAC for OpenSearch/Cassandra/Redis versus presentation RBAC for
dashboards, Cortex, Shuffle, and TheHive) is derived from which spine references
the authorization, never declared on the model.

### 2. Preserve typed child inventories

The authorization owns typed child collections for:

- `principals`: users, service accounts, API keys, or backend roles with
  `reserved`/`hidden` flags and a `credential_classification`.
- `roles`: named local roles.
- `permission_grants`: the defining resource-scoped grant — a role reference,
  bounded `actions`, `resource_patterns`, an `allow`/`deny` effect, and a
  `resource_kind`. The grant's `resource_kind` identifies that grant's resource space;
  the store's scalar vocabulary need not be covered by a partial grant inventory.
- `role_mappings`: bindings of backend roles, users, or hosts onto a local role.
- `tenants`: namespace/tenancy scopes within the store.

Stable ACES ids are the portable reference surface. Native security-config
stanzas, raw role definitions, and vendor API responses remain evidence unless
promoted into a bounded field above.

### 3. Never store raw credentials

A principal never carries a raw credential value. Its posture is recorded purely
via a `credential_classification` (`none`, `redacted`, `operator_secret`), and
the model has no field that can hold a raw bcrypt hash, API key, or password. Principal names are identities, not setting keys; name-based secret
classification does not apply to them (ADR-057).

### 4. Keep authorization inventory targetable but not executable

Authorizations and child records may be referenced from relationships using
qualified refs:

- `nodes.<node>.runtime.app_authorizations.<app_authorization_id>`
- `...app_authorizations.<app_authorization_id>.principals.<principal_id>`
- `...app_authorizations.<app_authorization_id>.roles.<role_id>`
- `...app_authorizations.<app_authorization_id>.permission_grants.<grant_id>`
- `...app_authorizations.<app_authorization_id>.role_mappings.<mapping_id>`
- `...app_authorizations.<app_authorization_id>.tenants.<tenant_id>`

These refs are inventory targets. They do not imply access-decision execution.

## Security and Validation Gates

- Parser/model gate: stable authorization and child ids are concrete symbols,
  not variables. Duplicate authorization ids and duplicate authorization-local
  child ids (across the authorization and its principal/role/grant/mapping/tenant
  collections) fail early.
- Semantic validation gate: supplied concrete `permission_grants` and
  `role_mappings` `role_ref` values resolve within the same authorization.
  A scalar vocabulary declaration does not require a matching grant: empty,
  omitted, deny-only, and partially captured inventories remain descriptions.
- Selected-operation gate: an operation that needs grant coverage or effective
  access must enforce its installed, independently admitted profile before
  execution; merely recording a matching grant does not authorize access.
- Relationship/reference gate: authorization and child qualified refs resolve in
  generic relationships and survive module import namespacing.
- Secret/credential gate: raw bcrypt hashes, API keys, and passwords stay out of
  SDL model data; only a `credential_classification` is recorded.
- Contract/schema gate: published schemas are hand-governed normative authority
  (ADR-009); the reference schema bundle must match their reviewed contract
  changes and publication ledger.

## Guardrails

- Do not model application-internal RBAC as a fake `identity_authorities`
  directory, a `database_services` GRANT surface, OS-local identities, or
  prose-only relationships.
- Do not store raw credentials of any kind; use the classification only.
- Do not fabricate a matching grant to make a partial inventory parse.
- Do not make OpenSearch, Cassandra, Redis, MISP, TheHive, Cortex, or any one
  product the schema authority. They motivate the surface; the model is
  product-neutral.

## Non-Goals

- Implementing access-decision evaluation, policy compilation, or backend RBAC
  provisioning behavior.
- Replacing ANSI INCITS 359, NIST SP 800-162, or any vendor security schema.
- Redesigning `runtime.identity_authorities`, `runtime.database_services`,
  `runtime.local_identity`, or `runtime.applications`.

## Consequences

### Positive

- Application-internal RBAC becomes typed, targetable, and validation-backed
  once, shared across storage-tier and presentation-tier applications, without
  corrupting adjacent runtime surfaces.
- The resource-scoped permission grant gives a single portable home for the most
  replicated gap in the corpus.

### Negative

- Node runtime gains another optional inventory surface.
- Consumers needing raw security-config semantics must retain separate evidence
  artifacts.

### Risks

- A vocabulary name or structurally valid grant is not an access-decision
  engine. Selected operations must disclose and enforce their actual supported
  semantics; unknown coverage is not permission.

## References

- [Directory, Domain, And Identity Runtime Surface](adr-032-directory-domain-identity-runtime-surface.md)
- [Database Logical State Runtime Surface](adr-029-database-logical-state-runtime-surface.md)
- [Scenario/Delivery Boundary for Runtime Node State](adr-033-scenario-delivery-boundary-for-runtime-node-state.md)
- [Lineage and Prior Work](../../explain/sdl/lineage.md) and
  [Design Precedents](../../explain/sdl/precedents.md)

## Amendments

| Date | Commit/PR | Summary |
|------|-----------|---------|
| 2026-09-13 | #1207 | Separated partial inventory descriptions from selected-operation admission; retained structural and security invariants. |
