# Issue 1653: cloud ownership, workload identity and secret services

Architecture preflight against `f7e5f49a`, 2026-10-27. The supplied issue #1653
is the delivery contract; there is no formal requirement UID. This is
non-normative guidance, not public syntax, an implementation plan, captured
cloud evidence or a claim of backend support. No implementation accompanies it.

## Architecture direction

Extend the smallest owning contracts to connect cloud scope, identity use,
policy attachment and service-owned secret state. Reuse existing identity,
application, content and profile mechanisms. Do not introduce a general cloud
resource graph, IAM evaluator, credential store or deployment workflow.
Field names and schema placement remain implementation design choices.

ADR-032/033/046/049, as amended, already establish adjacent owners;
ADR-057 governs explicit withholding, ADR-066 observation and disclosure,
ADR-105 partial description, and ADR-115 external backend ownership. A new
ADR is unnecessary for these guardrails. A design that changes their ownership
or meaning needs an explicit governed decision rather than a silent exception.

| Existing owner | Coverage and remaining gap |
| --- | --- |
| `runtime.applications`, `platform_applications`, `Node.services` | API, application identity/capabilities and transport bindings. None establishes cloud ownership, resource policy or version state. A managed API needs no invented OS, image or VM. |
| `runtime.identity_authorities` | `cloud_iam`, service-account subjects, policy facts and authority-local relationships. Local refs do not provide cross-project ownership or a workload's right to use an identity. |
| `runtime.app_authorizations` | Roles, allow/deny action/resource grants and mappings. These describe an application's internal store; they are not a complete cloud policy attachment, inheritance or effective-access contract. |
| Top-level `content`, `service_materialization`, generated artifacts | Initial payloads, service establishment and generated outputs with lifecycle and consumer controls. They do not yet join secret/version identity, lifecycle and selection. |
| Typed domain profiles | Pinned schemas, semantic contracts, independent support, preparation and result carriage. Existing hosts are bounded; there is no universal authored runtime profile bag. |
| External concept bindings | Exact, revision-bound assertions about native subjects. They neither supply missing native semantics nor make permissions executable. |

## Minimum supported meaning

The motivating description needs project A, project B, an identity owned by A,
a workload using that identity, a service endpoint, a secret owned by B, its
versions and a consumer's selection. It needs independent facts for identity
use, resource permissions, version state, reachability and access results.
This is a minimum semantic witness, not compulsory detail for every application.

**Scope and identity.** Preserve provider identity and scope kind. A GCP project,
AWS account, Azure subscription and identity tenant are not aliases for one
generic tenant. Cloud resource ownership, policy attachment, identity issuer,
service hosting, deployment isolation and reset ownership are separate facts.
Do not overload top-level node accounts, exercise `entities`, application-local
tenants or ADR-087 deployment tenants/cells. A globally served endpoint need
not belong to the same project as every resource served through it.

Use stable portable declaration IDs and qualified references. Retain provider
names/IDs as native data with their actual case and scope rules; a display
name, email, URL prefix or graph edge cannot establish equality or authority.
Repeated names across projects and module instances must remain distinct.
Where native incarnation matters, re-creation under a previous name must not
inherit the old identity's bindings automatically.

Supplied refs must resolve to the correct kind and owner; reject ambiguity,
wrong-provider joins, duplicate portable IDs and scope cycles. An external or
unknown target must be explicitly represented as such, never treated as a
successfully resolved local reference. Do not require an entire organization
inventory to describe two projects. Missing ancestry limits inheritance claims.
Node containment remains an SDL address/hosting context, not proof of cloud
ownership. Preserve existing same-node endpoint rules rather than globally
loosening them to admit cross-project resource references.

**Identity and policy.** Distinguish attachment/use, impersonation or token
creation, and permissions exercised by the resulting principal. A service
account can be both a principal and a policy target without duplicating its
identity. A credentialless workload identity is valid; do not require a key.
Keep listing metadata, retrieving a value and changing policy distinct actions
with explicit targets. Separate policy attachment scope from resource ownership
and from the resource a request targets. Preserve direct/inherited origin and
the source policy/scope, relevant conditions, denials and known policy coverage.
Do not flatten inheritance into a fabricated direct grant or assume one
provider's allow/deny combination rules apply to every provider.

An uninterpreted condition or unsupported policy construct remains describable
with explicit limits; an operation needing its meaning must refuse unsupported
semantics. Do not execute policy expressions, fetch provider role catalogs,
expand role names by guesswork or infer denial from an incomplete grant list.
A policy claim, a test expectation, and an observed allowed/denied result are
different claims. Bind observed access to principal, action, exact resource or
version, context and observation basis. Unknown, untested, unsupported and
denied must remain distinguishable. Connectivity alone proves none of them.

**Secrets.** Separate service, secret metadata, immutable version identity,
payload and version lifecycle. Preserve enabled, disabled and destroyed state;
destroyed is not an absent row, empty payload or implicitly reusable version.
Consumer selection must distinguish an exact version from a provider selector
or mutable alias. Preserve selection intent separately from any resolved
version and its observation basis. Do not silently select another enabled
version when the requested one is disabled or destroyed.

Scenario payload establishment belongs to `content`/service materialization or
the existing generated-output owner, not identity attributes or public profile
values. Link payload to its version instead of creating another blob store.
ADR-057 permits intentional synthetic scenario values; explicit `redacted` or
`operator_secret` still requires raw-value omission. Posture-only principal
models remain value-free. Operator credentials, scenario secret values and
participant disclosure are separate authorities; declaring a consumer or grant
does not disclose bytes to a participant or authorize an operator-secret lookup.

Location/global-versus-regional scope, replication, encryption-key dependencies,
service limits and reset/deletion responsibility need typed constraints when
they affect the scenario. Keep them optional otherwise. Exact provider
restrictions remain binding, including restrictions on policy attachment to
versions. An unsupported encryption dependency or reset requirement cannot be
silently discarded. Cloud ownership alone never authorizes deleting a shared
project, key or secret. Existing shared-service/reset contracts still govern
exercise isolation; cross-project access is not automatically cross-tenant access.

## Representation and extension seam

Use native fields for portable identity, ownership, references, state and claim
distinctions that core must validate, compose, compare or target. Extend an
existing owner where it owns that meaning; introduce bounded missing meaning
only where no incumbent does. Do not copy the same principal, grant or payload
into several inventories as independent authorities.

Provider-specific refinements belong at the existing `DomainProfileBindingModel`
seam when an appropriate host exists or is deliberately extended. Pin namespace,
definition/revision/digest, owner, context and installed semantic contract.
Parameterize provider scope kinds, supported policy/action semantics and version
selectors there rather than branching on product names throughout core.
An external concept binding can annotate the exact subject using an inert
provider concept locator; it cannot substitute for that contract.

Two inspected limits matter:

- `raes/composition/_profiles.py` rewrites known binding hosts/owners and the
  governed mailbox join, not arbitrary private strings. Cross-project refs
  need a declared reference owner and composition rule. Never recursively
  rewrite strings that merely look like refs, native names or policy text.
- `plan-realization-profiles-v1` carries bounded **public** execution data;
  profiles cannot add resource membership, dependencies or participant powers.
  Existing built-in service profiles require their own readback/evidence and
  disclosure bindings. Do not select those profiles as generic secret loaders
  and then weaken their prerequisites, or promise secret payload carriage
  through a public profile. New service semantics must use the established
  owner and protected value boundary deliberately.

## Cross-cutting gates and canonical incumbents

Package paths below are relative to `implementations/python/packages/`.
These are obligations for the intended implementation, not claims of completed
validation. Reuse the existing gate in each layer; no parallel validators,
exception hierarchy, logger, persistence service or workflow engine is needed.

| Layer | Incumbents and required behavior |
| --- | --- |
| Ingress and models | `raes/parser.py`, `_yaml_loader.py`, `_base.SDLModel`, `runtime_values` helpers; `raes_contracts/json_ingress.py`, `runtime_value_limits.py`. Retain closed shapes, duplicate/mapping-key checks, portable IDs, variable handling and bounded bytes/depth/collections before copying or hashing policy data. Provider expressions remain inert data. |
| Semantic references | `raes/validator/_runtime_identity_data.py`, `_runtime_services.py`, `_service_materialization.py`; `_declarations.py`, `_reference_targetability.py`, `_runtime_service_family_registry.py`, `runtime_inventory.py`. Resolve supplied refs by kind/scope and reuse collection identity metadata. File-service `directory_subject_ref` is a precedent for referring to one canonical identity authority subject. Do not conflate generic targetability with permission. |
| Composition and instantiation | `raes/composition/_references.py`, `_sections.py`, `_profiles.py`, `instantiate.py`. Qualify owners and governed cross-resource refs across repeated imports; preserve native identifiers, explicitness and selected-profile coordinates. Revalidate substitutions; pre-instantiation validity alone is insufficient. |
| Compilation and partiality | `raes_processor/compiler/realization_requirements.py`, `materialization_origins.py`, `placement.py`; `semantics/realization_runtime_concern_profiles.py` and the shared recursive relation. Preserve stable collection keys, exact leaves, open/closed scopes, dependencies and concern origins. Omitted does not mean empty, denied or absent. Constraints conjoin; neither core nor profile overwrites the other. |
| Support and configuration | `raes_contracts/domain_profiles.py`, `manifest_authority.py`; `raes_backend_protocols/provisioner_manifest.py`, `service_materialization.py`; processor `planner/realization_profiles.py` and runtime `backend_profiles.py`. Require exact installed structural/semantic/comparison/execution support in independently configured context. Resolve pinned definitions offline with no remote schema retrieval, ambient credential discovery or executable handlers in data. Advertised labels and valid schemas prove no execution support. Repeat admission for direct submissions before effects. |
| Caller authority | `raes_runtime/control_plane_security.py`, `control_plane_plan_authorization.py`, `control_plane_submission.py`, `control_plane_api/_auth.py` and API guards. Scenario IAM is data, never control-plane authentication. Retain caller role/audience/target/run scope, sealed configuration, plan commitments, idempotency and request bounds. No cloud credential parameter or alternate public secret-read endpoint is implied. |
| Secrets and env/config shapes | `raes/runtime_values.enforce_observed_value_redaction`, `runtime_environment.py`, `runtime_generated_value.py`; `raes_contracts/secret_references.py`, `account_credentials.py`; runtime `backend_account_credentials.py`. Preserve explicit withholding and fixture/reference separation. Current `value_from` supports generated artifacts only, with literal exclusion, producer-private checks and redacted generated-secret consumers; it is not a secret-service resolver. Any deliberate extension must pass model, schema, compiler and consumer gates together. Account-specific egress protection does not automatically protect a new service payload. |
| Results and materialized descriptions | Runtime `backend_input_contracts.py`, `backend_snapshot_contracts.py`, result acceptance; processor `planner/materialization_admission.py`, `semantics/realization_snapshot_sanitization.py`. Check raw shape, admitted scope/selection, safe values and provenance before publication. Keep declared, selected and observed state distinct; reject fabricated access success or weakened constraints. An invalid success retains the trusted predecessor; sanitization must not turn forbidden state into accepted state. |
| Observation and disclosure | `realization_operational_verification.py`, runtime `observation_admission.py` and the ADR-066 demand/reporting owners. Registering a runtime concern can add configuration verification automatically. Define the legitimate metadata/configuration verification boundary explicitly; it must not become value retrieval, an access probe or experimental capture. Separately requested observation must pass collection, retention, export and participant-view policy before collection, not after filtering. |
| Persistence and DTOs | Shared plan/snapshot carriers and codecs, runtime `control_plane_api_models.py`, `control_plane_store_*`, `control_plane_durability.py`, revision/CAS and `RunMaterializationArchive`. Preserve scope, refs, version selectors/state and claim basis through both plan directions, snapshots and reload. Reuse carrier classification and runtime-write guards; keep protected values out of generic labels/details/history. No cloud database, policy cache or evidence side table. |
| Host/OS boundary | ADR-115 injected `RuntimeTarget`, backend manifests and protocols. RAES parsing/admission must not contact cloud APIs, read host credentials, resolve secret locators or spawn cloud tools. Downstream backends own bounded native calls, destination trust, protected staging, controlled env, timeouts and cleanup. Tokens and secret bytes must not enter argv, shell history, URLs, debug env dumps or world-readable files. URI validity is not network authorization. |
| Errors, audit and logs | `raes/_errors.py`, `_model_diagnostics.py`; `raes_contracts/diagnostics.py`; runtime `diagnostics.py`, `control_plane_api/_responses.py`, `_operation_routes.py`, `control_plane_audit.py`. Use bounded addressed codes and existing redacted HTTP/error/audit envelopes. Never echo Pydantic input, policy bodies, fixture bytes, operator references, backend exceptions or SDK stderr. Rejection and durable recovery need the same protection as success. No secret or guessable-secret digest as a diagnostic identifier. |

## Contract publication and acceptance guardrails

Published schemas under `contracts/schemas/` remain authoritative (ADR-009/061).
Keep `schema_bundle()`/generated parity, shared factoring, semantic invariant
annotations and affected `contracts/schema-publication/entries/` change records
aligned. The SDL carriers include `sdl-authoring-input-v1`,
`instantiated-scenario-v1`, `instantiated-scenario-snapshot-v1` and
`scenario-satisfiability-evidence-v1`; trace any affected plan, profile,
materialization and public DTO carriers as well. Model-only success is insufficient.
Update native references/runtime index and user documentation with the chosen
contract; do not publish speculative syntax from this note.

Acceptance examples must preserve cross-project joins, repeated native names,
identity use versus granted rights, metadata access versus denied value access,
policy changes, direct/inherited conditional or denied policy, disabled and
destroyed versions, exact versus mutable selection, and unknown/unsupported
outcomes. Include repeated module imports, substitution, compile/codec round
trips, independently unsupported execution, result rejection and durable reload.
Keep expected denial separate from a failed test invocation. Assert that no
unrequested secret retrieval, telemetry or disclosure occurs; use synthetic
sentinels to check success and failure leakage paths.

Reuse `test_runtime_app_authorization.py`, `test_issue_1338_identity_authority.py`,
`test_external_concept_bindings.py`, #1202/#1204 profile admission/offline tests,
#1208 composition/boundary tests, #1241 materialization tests, #1212 observation
tests, #673 credential and #1074 generated-environment cases. Contract stubs
prove contract behavior, not live provider support.

`.ground-control.yaml`, `.gc/plan-rules.md`, `noxfile.py`,
`tools/nox_support/policy_lanes.py`, repo-policy/schema-publication tooling and
the canonical CI workflow retain workflow authority. Use targeted local checks;
CI owns full suites. Do not fabricate a requirement UID for this issue-only run.
Retain the requirement-free workflow's explicit classification when publishing.
Release-please owns versions/changelog; preserve ADR pins and research history.

## Non-goals and anti-patterns

No concrete backend, cloud SDK, deployment recipe, billing administration,
complete cloud catalog, general policy evaluator, automatic discovery,
credential broker or new persistence/workflow system belongs in #1653.
RAES owns language, portable contracts and conformance; downstream backends own
native execution and live qualification under ADR-115.

Avoid vendor JSON as semantic authority, generic relationship bags as grants,
fake OS/node placement requirements, provider tenants collapsed into deployment
cells, duplicate principal schemas, name-based permission inference, blanket
secret-name bans, public-profile secret transport, and access inferred from
reachability, role labels, policy presence or a backend acknowledgement.
Do not add compulsory regional/encryption/replication detail to ordinary cloud
applications, silently repair exact disabled-version requests, or turn a valid
partial description into a complete-policy or effective-access claim.

## Provider grounding

The design inference is to preserve provider-specific scope and policy semantics
behind the existing portable boundaries. The primary sources support that
distinction; they do not prescribe SDL layout:

- [GCP resource hierarchy](https://docs.cloud.google.com/resource-manager/docs/cloud-platform-resource-hierarchy): resource parents and policy inheritance.
- [GCP service accounts](https://docs.cloud.google.com/iam/docs/service-account-overview): principal/resource duality, identity use, project ownership and native identity replacement.
- [Secret Manager concepts](https://docs.cloud.google.com/secret-manager/docs/overview) and [versions](https://docs.cloud.google.com/secret-manager/docs/add-secret-version): metadata versus version payload, immutability and policy attachment restrictions.
- [AWS policies](https://docs.aws.amazon.com/IAM/latest/UserGuide/access_policies.html): distinct identity/resource policies and limiting policy types.
- [Azure scope](https://learn.microsoft.com/en-us/azure/role-based-access-control/scope-overview): management-group/subscription/resource-group/resource scopes and inheritance.
