# Issue #1831: cloud audit log configuration preflight

Inspected at `927cfb7935740f76f0dc13d60a054239cfa4de7c`, 2026-11-01.
The supplied GitHub issue is the delivery contract; no requirement UID applies.
This is non-normative architecture guidance, not public syntax, an implementation
plan, acceptance evidence or a claim of cloud interoperability.

## Responsibility correction

The user's responsibility clarification supersedes capability-based acceptance wording in this preflight.
[Hub issue 3](https://github.com/OpenRAE/hub/issues/3) and ADR-115 assign RAES semantics, contracts, conformance, and portable runtime enforcement.
RAES sets the contract; concrete backend distributions depend on and implement it.
References below to support or refusal describe protocol conformance, not downstream delivery requirements.
Provider documentation explains domain concepts; it is not a backend architecture to copy into RAES.
The current issue and design define acceptance at RAES-owned boundaries.
Native execution methods and live integration qualification remain outside this work.

## Direction and semantic boundaries

Extend `RuntimeIdentityResourceScope` with optional, closed, typed audit logging
configuration owned by that scope. Each declaration must identify a native cloud
service and a native audit log type whose recording is required. Preserve the
scope's exact provider identity and the native strings' case. A native service
name is not an SDL `Node.services` reference or the identity authority's endpoint.
Do not require a fake endpoint, VM, application or account to describe it.
`RuntimeIdentityPolicy.settings` remains inert: recognizing special attribute
names there would create a second, hidden language.

Use bounded records that can represent several services and several log types
per service. Give records stable scope-local identity and reject duplicate or
conflicting declarations of the same service/log-type pair, even under different
record IDs. Optional principal exemptions belong to the applicable log-type
record, not to an authority-wide permission binding. If included, use exact
references to existing `RuntimeIdentitySubject` declarations; do not duplicate
principals, resolve native emails by spelling, or require their ownership scope
to equal the logging scope. Provider-specific eligibility remains backend work.
Do not quietly omit exemptions when admitting or realizing a declaration.

Omission contributes no audit setting. An empty collection must not accidentally
become a provider request to disable all logging. Preserve the existing
explicitness/closure contract (ADR-105), including explicit empty/closed scopes;
do not introduce separate absence/default/closure rules for this feature.
A positive statement does not assert a complete organization policy, deny other
log types, prove an emitted event, or establish effective inherited coverage.
Do not compute inheritance by copying IAM binding logic. Native defaults,
wildcards, inheritance and exemptions require their actual provider semantics.

Audit configuration, IAM access policy, access observations, control-plane audit
records, operational logs and experiment evidence remain different concepts.
Enabling provider recording is the requested configuration effect. It grants no
RAES permission to retrieve, retain, export or disclose those records. A
detection exercise must still declare its separate collection/evidence needs.
Existing ADR-032/033, ADR-066, ADR-105, ADR-115 and ADR-121 cover these owners;
no new ADR or amendment to an accepted ADR is needed for this direction.

## Canonical owners and cross-cutting gates

Paths below are relative to `implementations/python/packages/` unless stated.
Reuse these owners rather than introducing parallel DTOs or validation engines.

| Layer | Incumbent and required boundary |
| --- | --- |
| Source ingress and shape | `raes.parser`, `_yaml_loader`, `_source_profile` and `raes_contracts.sdl_model.SDLModel` provide bounded parsing and closed records. Build on `raes.runtime_identity_resources`, `PortableIdentifier`, `NativeIdentity`, `require_non_empty` and `reject_duplicates`. Bound new strings/collections; reject unknown fields and malformed/blank values. Keep expressible structural restrictions in published JSON Schema too; register genuinely semantic restrictions through the existing invariant mechanism. Pydantic validators raise `ValueError`, not a new domain exception. |
| Reference identity and composition | `raes.validator._cloud_resources`, the declaration index, `_runtime_service_family_registry`, and public `raes.runtime_inventory.runtime_inventory_collection_identity` own exact kinds and collection identity. Scope-local audit IDs must not collide or gain authority-wide short aliases. Register identity/targetability deliberately through the existing child metadata; a stable ID alone does not grant mutation authority. Extend `raes.composition._cloud` only for explicit principal references, preserving native service/log-type strings. Repeated imports and variable binding must retain distinct scope identities and revalidate references, duplicates and values after substitution. Keep existing same-node endpoint checks intact. |
| Configuration projection | `raes_processor.semantics.realization_concerns`, `realization_runtime_concern_profiles` and `realization_typed_runtime_projection` already own `runtime-identity-authorities`. Audit settings must survive exact and recursive projections as configuration. Do not add them to observation-only exclusions alongside `access_observations`. Reuse registered collection identities for recursive matching; positional order must not silently become the identity of audit rules. Verify exemption collection ordering against the existing sequence/set contract rather than inventing another comparator. |
| Planning and execution admission | `raes_processor.semantics.realization_support`, `raes_processor.planner.realization_authority_diagnostics`, runtime `control_plane_submission`, and the existing backend preparation/validation call path own admission before apply. Preserve generic **and concern-specific** exact support, required configuration corroboration and recomputation from submitted operations. Apply the same rules to direct/deserialized plans and prepared selections, not only compiler-produced plans. An open ancestor cannot weaken an explicit audit requirement. |
| Caller authentication and authorization | `raes_runtime.control_plane_security`, `control_plane_plan_authorization`, `control_plane_api._auth` and existing API guards retain role, audience, target/run scope, sealed configuration and plan commitments. SDL resource ownership, principal exemptions and scenario IAM never authenticate the caller or authorize native administration. No new route, token parameter or authorization bypass is needed. |
| Secrets, environment and host configuration | This term carries metadata and subject references, never credentials, log payloads or operator secret locators. Keep ADR-057, `raes_contracts.runtime_values.enforce_observed_value_redaction`, `secret_references`, `account_credentials`, `raes.runtime_environment`, and runtime `backend_account_credentials` intact. Do not put audit settings in environment variables, generated-secret bindings or generic settings bags. Existing `value_from` shapes remain unchanged; there is no new credential resolver or environment/config map. A service name containing “secret” is not itself a secret value. |
| Returned shapes and evidence | Runtime `backend_input_contracts`, `backend_snapshot_contracts`, processor `realization_concern_observations`, `realization_snapshot_sanitization`, `planner.materialization_admission` and existing backend result acceptance must retain their bounds, typed readback, provenance and predecessor protection. Reject missing/weakened settings, altered exemptions and unknown fields before accepting a successful result. Sanitization must not erase a mismatch into apparent success. `realization_operational_verification` requires configuration readback, not generated traffic, an access probe, log retrieval or experiment capture. |
| Persistence and transport | Reuse node specifications, `ProvisioningPlan`, `plan_projection` codecs/digests, `RuntimeSnapshot.entries`, `control_plane_api_models`, `control_plane_store_*`, revision/CAS, `control_plane_durability` and `raes_operations.run_artifacts.RunMaterializationArchive`. Preserve settings through wire round trips, materialized SDL and durable reload. No new database, audit table, repository service, controller or snapshot carrier is needed. Do not hide authoritative configuration in labels, diagnostics or snapshot metadata. |
| Errors and observability | Reuse `raes._errors`, `_model_diagnostics`, `raes_contracts.diagnostics.Diagnostic`, the shared `raes_contracts.errors` categories and `operational_logging` (ADR-116). Expected unsupported configuration is a bounded addressed diagnostic, not a new exception hierarchy. Translate operational/foreign failures once at the owning boundary; preserve cancellation. Keep `control_plane_api._responses` fixed redacted envelopes, portable diagnostics and `control_plane_audit` records. Never echo Pydantic input, full policy/configuration, provider exceptions, SDK output, credentials or environment maps. Library logging uses `get_logger(__name__)`; no second logging setup. |
| OS and native effects | ADR-115's injected `RuntimeTarget`, backend manifest/protocols and conformance facade are the execution seam. Parsing, compilation and admission in RAES must not discover credentials, spawn cloud CLIs, contact cloud APIs or fetch catalogs. Downstream native execution owns protected credentials, fixed argv, controlled environment, destination trust, timeouts and cleanup. Credentials must not enter argv, URLs, command dumps or public files. Scope containment is not permission to replace a shared cloud policy or disable pre-existing logging during teardown. |

## Admission limits and provider variation

The current manifest check operates at the `runtime-identity-authorities`
concern level; it is not a provider/service/log-type capability matrix. A broad
identity-support declaration cannot justify silently ignoring newly authored
audit settings. Require either complete applicable support or refusal through
the existing backend validation/preparation path before **any** apply effects.
When preparation is negotiated, validate the admitted concrete selection.
Do not treat a provider's later API rejection, or post-effect readback failure,
as satisfaction of the issue's pre-effect refusal requirement. Static admission
does not guarantee against native races or operational failures.

Keep provider mapping behind that seam. GCP's [AuditConfig contract](https://docs.cloud.google.com/resource-manager/reference/rest/Shared.Types/AuditConfig)
combines service-specific and `allServices` configurations; its
[configuration guide](https://docs.cloud.google.com/logging/docs/audit/configure-data-access)
also defines inherited settings and exemptions. AWS's
[CloudTrail event selectors](https://docs.aws.amazon.com/awscloudtrail/latest/APIReference/API_EventSelector.html)
distinguish management/data events and read/write selection. Azure's
[diagnostic settings](https://learn.microsoft.com/en-us/azure/azure-monitor/data-collection/diagnostic-settings)
use resource categories and destinations. These are distinct contracts, not
three spellings of GCP's three log types. The design inference is to parameterize
native service and log-type identity within the existing provider-qualified
scope, rather than publish a universal three-value enum or provider switch.

A provider that needs an undeclared destination, selector or unsupported
exemption must refuse rather than approximate or create implicit infrastructure.
Later native refinements can use the existing governed, admitted profile seam
when its host and operations apply; this feature does not create a universal
runtime profile bag. Native wildcards remain inert unless their exact semantics
are supported. Core must not expand a wildcard by querying a service catalog.

GCP stores audit settings alongside IAM bindings. This is domain context only.
RAES does not prescribe a provider mutation API, concurrency mechanism, or policy replacement strategy.
Its contract preserves authored scope, logging, and access-policy distinctions.
Scope ownership and reset responsibility do not grant blanket mutation authority.
Concrete backend owners choose and qualify their implementation of those obligations.

## Publication, verification boundaries and non-goals

The normative semantic owner remains `specs/sdl/cloud-resource-access.md`.
Reconcile `specs/sdl/runtime-inventory.md`, `specs/sdl/references.md` and
`tools/sdl_catalog_parity/_expectations_cloud.py` with any new reference fields.
Published schemas under `contracts/schemas/` remain authority (ADR-009/061).
Keep owner contributions (`raes.schema_contributions`, and processor evidence)
and `raes_schemas.schema_bundle()` identical to the governed publication.
Affected embedded definitions include authoring input, instantiated scenario,
instantiated snapshot, materialized scenario and satisfiability evidence.
Trace the actual bundle rather than updating just the authoring schema.
Maintain `contracts/schema-publication/entries/` content hashes and `last_change`
records through the existing publication tooling/manifest convention, plus
semantic-invariant and catalog parity checks. Do not copy the SDL model into
`raes_contracts`; ADR-121 keeps it below SDL and runtime reaches SDL checks
through public processor interfaces.

Reuse the existing `identities` and `runtime-inventory` concept families in
`contracts/concept-authority/concept-families-v1.json` and the controlled
vocabulary governance (ADR-012/062). Native service/log-type strings are not a
new portable enum or a new concept family. Keep authority-boundary,
concept-governance, generated-schema and schema-publication checks intact.

Acceptance evidence should extend the #1653 cloud model/reference/lifecycle
tests and fixtures. It must cover a positive service/log-type statement;
multiple types/services; omission and explicit closure; duplicate/blank/unknown
shape refusal; exemptions and wrong-kind/dangling references when supported;
repeated imports and post-binding collisions; all affected published schemas;
compile/projection/codec/durable round trips; and materialized-result mismatch.
Exercise RAES admission with declared support and protocol rejection fixtures.
Assert zero effectful calls when RAES rejects admission, including direct submitted plans.
No concrete backend implementation or native logging behavior is required.
An accepting fixture must preserve settings and use the existing configuration
corroboration contract; echoing a plan is not proof of native realization.
Synthetic sentinel tests should cover diagnostic/log/HTTP failure leakage.
Fixture conformance cannot claim live GCP/AWS/Azure support.

`.ground-control.yaml`, `.gc/plan-rules.md`, repo-policy tooling, `noxfile.py`,
`tools/verification_plan.py`, pre-commit and canonical CI retain workflow
authority. Use targeted local tests/checks; full, integration, fuzz and completion
suites remain CI-only. Do not fabricate a requirement UID for this issue-only
run. Release-please owns versions and changelog: the eventual consumer-visible
change needs a release-producing Conventional Commit/PR classification under
the repository rules. A documentation-only preflight does not ship the feature.

Non-goals are concrete cloud backends/SDKs, a complete cross-cloud logging model,
automatic discovery, effective IAM/audit inheritance evaluation, credential
transport, sink provisioning, retention/export controls, log retrieval, SIEM
connectors, detection rules, new workflow/persistence machinery and live-provider
qualification. Avoid vendor JSON as semantic authority, audit meaning hidden in
settings, permission bindings reused as logging rules, fabricated evidence,
optimistic capability claims and duplicate validators outside the owning layers.
Final field names and schema layout remain implementation design choices within
these boundaries. No source, schema or normative contract changes accompany
this preflight.
