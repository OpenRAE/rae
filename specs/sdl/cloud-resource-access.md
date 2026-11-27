# Cloud resource ownership and secret services

Status: **normative**. Issue: #1653.
The published SDL schemas govern serialized structure.
This contract extends identity authorities and platform applications.
The new fields are optional.
It does not define a cloud backend or an IAM policy evaluator.

## Resource ownership

`runtime.identity_authorities[].resource_scopes` lists cloud ownership scopes.
Each scope requires `scope_id`, `provider` and `scope_kind`.
The portable `scope_id` is the reference identity.
Provider identity and native scope kind retain their exact spelling.
GCP projects, AWS accounts and Azure subscriptions have distinct meanings.
They MUST NOT become aliases for one tenant type.

`name`, `native_id` and `incarnation_id` are optional native observations or authored constraints.
They do not create reference aliases or prove resource control.
An optional `parent_ref` MUST name an exact declared resource scope with the same provider.
Scope ancestry MUST be acyclic.
Omitted ancestry makes no statement about parents outside the description.
It MUST NOT imply a complete organization inventory.

Scopes belong to an authority's SDL address namespace.
Node containment MUST NOT imply cloud ownership, isolation, policy inheritance or deletion authority.
The service endpoint can serve resources from several scopes.

`runtime.identity_authorities[].subjects[].resource_scope_ref` names a subject's scope.
`runtime.platform_applications[].resource_scope_ref` names an application's scope.
Both fields are optional.

Subject, endpoint and secret ownership MUST NOT be inferred from each other.

## Identity use

`runtime.identity_authorities[].identity_uses` connects existing subjects to workloads.
Each record requires `use_id`, `workload_ref`, `principal_ref` and `mode`.
Modes are `attached`, `impersonated` or `federated`.
An optional `source_principal_ref` identifies the requesting identity.
Principal references MUST name identity-authority subjects.
Workload references MUST name compute nodes, named services or application records.

Identity use and permission to use that identity remain separate declarations.
An identity-use record MUST NOT imply permission, credential discovery or participant disclosure.
A service account needs no account-placement record, password or private key.
The subject remains the sole principal identity.
A policy can also target that subject as a resource.

## Resource policies

`runtime.identity_authorities[].policies[].resource_access` describes resource-policy attachment.
It requires an exact resource `attachment_ref`.
Optional `bindings` have policy-local `binding_id` identities.

Bindings require `principal_refs`, `resource_refs` and an explicit `effect`.
Both reference lists MUST be nonempty and contain no duplicates.
Effects are `allow` or `deny`.

Each binding requires explicit `actions`, a `role_ref`, or both.
Role references MUST name role subjects.
Role names MUST NOT cause automatic permission expansion.

An optional `condition` requires `language` and `expression`.
Condition text is inert provider data.
Core MUST NOT evaluate expressions, load handlers or fetch role catalogs from these fields.

A valid description does not prove that a provider accepts the policy.
A backend must support the provider's restrictions and policy rules before execution.
For example, GCP Secret Manager does not permit IAM role attachment to a version.

A generic reference to a version MUST NOT claim such native support.

An inherited policy view uses `inherited_from_ref` to name its source policy.
It MUST NOT copy the source bindings into a second authority.
Policy-source references MUST be acyclic.

An inherited view requires declared resource ancestry.
Scope policies can apply through declared descendant scopes to resources owned there.
A secret can be the structural parent of its versions.

Sharing one project does not make two secrets ancestors of each other.
These structural relations do not decide effective access.

Application-internal roles and grants retain their existing `runtime.app_authorizations` owner.
Resource policies do not replace that store.

## Access observations

`runtime.identity_authorities[].access_observations` records reported attempts.
Each record requires `observation_id`, `principal_ref`, `action`, `resource_ref` and `outcome`.
Outcomes are `allowed`, `denied`, `unknown` or `unsupported`.

An allowed or denied outcome MUST include nonempty `evidence_refs`.
Optional `context_refs` name exact described resources.
Evidence identifiers name evidence records.

They do not declare SDL resources or request data retrieval.

The record remains its producer's claim.
An evidence reference alone does not prove capture, freshness or a successful probe.
The existing evidence and truth-result contracts govern those claims.
Policy presence and network reachability MUST NOT synthesize an access observation.
An expected denial is distinct from an observed denial or an unsupported test.
Listing metadata, retrieving a value and changing policy remain different actions.

Access observations are descriptive state, not configuration requirements.
They MUST NOT create an access probe, secret retrieval or experimental capture duty.

## Secret resources

`runtime.platform_applications[].secrets` describes service-owned secret resources.
Each secret requires a portable `secret_id`.
Optional `resource_scope_ref` identifies its owning resource scope.
Optional `native_id` preserves the provider resource name without creating an alias.
The application record identifies the service.
It does not declare another secret container or cloud project.

`versions` contains stable `version_id` records.
Optional `native_id` preserves the native version identifier.
Portable `state` is `enabled`, `disabled`, `destroyed` or unspecified.
`native_state` can preserve another provider state without assigning it portable execution semantics.
Destroyed state is distinct from an absent version or an empty value.
A destroyed version MUST NOT declare a live `payload_content_ref`.

`payload_content_ref` MUST reference exact top-level `content`.
Copying a file onto a node does not establish the state of the secret service.
Payload establishment uses the existing content and service-materialization owners.
The version model has no raw payload, operator credential or secret locator field.
Synthetic scenario content remains valid under ADR-057.
Existing rules still control withheld values, protected execution and what participants can see.

## Consumer selection

`secrets[].consumers` contains stable `selection_id` records.
Each record requires an exact `consumer_ref` and one selection method:

- `version_ref` names a version of this secret.
- `selector` preserves a provider selector's `kind` and `value` as inert data.

Core MUST NOT resolve aliases, select a newer version or substitute an enabled version.
An exact selection of a disabled or destroyed version remains describable.
It can describe a scenario that expects access to fail.

Optional `resolved_version_ref` MUST name a version of the same secret.
It MUST agree with an exact `version_ref`, when supplied.
Resolution requires `resolution_basis`: `declared`, `backend-selected` or `observed`.
Observed resolution also requires nonempty `resolution_evidence_refs`.
A basis or resolution evidence without a resolved version is invalid.
Resolution reports MUST NOT replace the requested selection or become configuration requirements.

## Optional constraints and lifecycle responsibility

Secret metadata can declare `location`, `replica_locations` and `encryption_key_ref`.
These legacy fields do not declare a replication policy.
Declared encryption references MUST resolve to existing resources.
Optional `reset_owner_ref` and `deletion_owner_ref` also name existing resources.
These references describe responsibility; they grant no mutation or deletion authority.
Cloud ownership alone never authorizes deletion of a shared project, key or service.

`platform_applications[].cloud_limits` records optional scoped service limits.
Each limit requires `limit_id`, native `name`, nonnegative integer `maximum` and explicit `unit`.
An optional `resource_scope_ref` identifies its scope.
No unit conversion, quota enforcement or billing behavior is implied.
Other native refinements require an appropriate admitted profile and independent support.
Authors MUST NOT have to supply these details for every cloud application.

### Secret replication

`secrets[].replication` declares an optional typed policy. Omission or null means
unspecified; neither an absent nor an empty replica list implies automatic
replication. The policy identity combines the exact `provider` and `mode`.
The supported provider is `gcp-secret-manager`, with two modes:

- `automatic` requires unrestricted replication and MUST NOT declare replicas.
- `user-managed` requires replication only in the nonempty `replicas` list.
  Each replica requires a distinct, nonblank `location`.

Other providers and mode spellings MUST be rejected. Core does not equate these
policies with another provider's policies. A supplied `resource_scope_ref` MUST
resolve to a scope with provider `gcp`. The provider identity selects semantics;
it does not select or authorize a backend.

An automatic policy may declare a native `kms_key_name`. A user-managed policy
may declare that field on each replica, and MUST NOT declare a policy-level key.
Key names have shape `projects/P/locations/L/keyRings/R/cryptoKeys/K`.
The key location MUST be `global` for automatic replication and MUST match its
replica's location for user-managed replication. Omitted keys retain GCP's
provider-managed encryption meaning. Names are inert resource identifiers,
not key material or SDL references, and imports MUST preserve their spelling.

When `replication` is supplied, `location`, `replica_locations`, and
`encryption_key_ref` MUST be empty. No competing legacy declaration is allowed.
Mode, location and key names may use whole-field variables; instantiation MUST
repeat mode, uniqueness, key-location, and provider-scope checks after binding.
Published schemas enforce shape and mode alternatives. Their callable semantic
invariant also enforces location uniqueness and key-location agreement.

```yaml
secret_id: automatic-example
replication:
  provider: gcp-secret-manager
  mode: automatic
```

```yaml
secret_id: regional-example
replication:
  provider: gcp-secret-manager
  mode: user-managed
  replicas:
    - location: us-east1
      kms_key_name: projects/example/locations/us-east1/keyRings/example/cryptoKeys/example
    - location: europe-west1
```

Imports, compilation, plan transport, snapshots and materialized SDL MUST retain
the complete authored policy. Exact runtime configuration verification MUST
reject omitted policies, changed modes, missing replicas and missing or changed
keys. Unsupported execution MUST be refused before effects. A backend that
advertises the runtime concern MUST still reject any unsupported policy through
its validation interface. RAES adds no provider implementation or qualification.

GCP replication policy is immutable. A backend MUST qualify existing-resource
handling and MUST NOT silently replace a secret to satisfy changed intent.
Live location availability, key permissions, service restrictions and execution
remain backend responsibilities. See the
[REST v1 replication contract](https://docs.cloud.google.com/secret-manager/docs/reference/rest/v1/projects.secrets#Replication)
and [design](../../docs/decisions/issue-1848-secret-replication.md).

## Composition, admission and descriptions

Registered cloud records are resource reference targets.
These include scopes, identity uses, observations, secrets, versions, selections and limits.
Permission-binding IDs remain local to their policy record.
Supplied references MUST resolve exactly to the required declaration kind.
Native names, provider IDs and expression strings MUST NOT establish identity or permission by spelling.

Module imports rewrite explicit reference fields through the existing symbol maps.
They preserve native identifiers, conditions, selectors and evidence identifiers.
Normal SDL variable substitution remains explicit and is revalidated after instantiation.
Compilation and materialized descriptions retain these optional typed structures.
No new top-level SDL section, cloud SDK, credential resolver or storage service is introduced.

Configuration checks cover declared metadata, ownership, policy and version state.
It excludes access observations and selector-resolution reports.
Such verification MUST NOT become a value read or an access test.
Actual execution requires supported backend semantics at the existing admission boundary.
Unsupported execution MUST fail explicitly before effects.
Fixture conformance does not establish live GCP, AWS or Azure interoperability.

The design rationale, alternatives, data flow and security controls are in
[the issue design](../../docs/decisions/issue-1653-cloud-identity-secrets-design.md).

## Audit log configuration

`resource_scopes[].audit_logs` states required recording on the owning scope.
Each record requires a scope-local `audit_log_id`, native `service`, and native `log_type`.
The ID and the service/log-type pair MUST each be unique within the scope.

The collection contains at most 1024 records.
Native service and log-type strings contain 1 to 2048 characters and MUST NOT be blank.
Their case and provider meaning remain unchanged.

A service name is not a node service or endpoint reference.
Core MUST NOT expand native wildcards or calculate effective inherited coverage.

Optional `exempted_principal_refs` names exact declared identity subjects.
It contains at most 1024 distinct references.
Each reference contains 1 to 2048 characters and MUST NOT be blank.

Subject ownership need not equal the logging scope.
RAES MUST retain each exemption in the binding runtime requirement.
Runtime admission MUST honor protocol rejection before effectful invocation.

The reference does not create a principal or an access grant.

Omission or an empty collection contributes no recording requirement.
It MUST NOT become a command to disable existing logging.
Existing explicitness and closure rules still govern supplied constraints.
Positive declarations do not forbid other log types or claim complete organization coverage.
Audit record IDs are addressable below their scope; they create no authority-wide alias.

For example, a GCP project scope can declare:

```yaml
audit_logs:
  - audit_log_id: secret-reads
    service: secretmanager.googleapis.com
    log_type: DATA_READ
  - audit_log_id: secret-admin-reads
    service: secretmanager.googleapis.com
    log_type: ADMIN_READ
```

These records remain configuration in the `runtime-identity-authorities` concern.
RAES defines the support, refusal, and result obligations at the backend protocol boundary.
Runtime admission MUST reject unsupported exact requirements before effectful invocation.

A protocol validation rejection MUST also prevent that invocation.
A general identity support declaration MUST NOT remove or weaken an audit requirement.
RAES result validation MUST detect missing rules and changed exemptions.

Conforming results MUST preserve the binding configuration and its declared closure semantics.
No destination, selector, or additional infrastructure is implied by these fields.
Scope ownership alone grants no right to change a shared cloud policy.

Provider identity identifies the described cloud domain, not a concrete backend implementation.
Service names and log types MUST NOT select a backend, SDK, provider API, or credential source in core.
Concrete implementations depend on this contract and own their native mappings and qualification.
RAES acceptance does not depend on any concrete backend implementing this term.
[ADR-115](../../docs/decisions/adrs/adr-115-concrete-backends-owned-outside-raes.md) governs that dependency direction.

Recording configuration is separate from access policy, access observations, and experiment evidence.
It grants no authority to retrieve, retain, export, or disclose logs.
It does not prove that any event was recorded.
No live cloud backend support is claimed by the reference implementation.
The [audit design](../../docs/decisions/issue-1831-cloud-audit-log-configuration-design.md) records the rationale and security boundaries.
