# Issue 1207: Partial descriptions and executable completeness

Date: 2026-09-13. Inspected revision: `d36608e8`, branch
`1207-partial-profile-descriptions`. Focus: DSL-137 and the SEM-218 boundary
shared with DSL-132, DSL-136 and DSL-134. This is architecture guidance, not an
implementation plan or a claim that the correction has shipped. Inspection is confined to this
repository; the supplied SCN-010/issue context is not independent capture
evidence. Native implementation blockers must be checked by the implementation
workflow; this preliminary review does not certify their clearance.

The baseline findings below describe the inspected revision. The SEM-218
addendum separately considers the in-progress working tree on 2026-09-13;
its existing implementation and tests are not changes made by this preflight.

## Decision and compatibility boundary

Keep `RuntimeOrchestrationAuthority` and its existing node placement, stable
identity, engine/API identity, scope, templates, lifecycle policy and observed
children. `RuntimeControlInterface` already has a required stable id: the
requirement's anonymous-shell rationale describes the original gap, not today's
schema. No new inventory family, shell DTO or relationship encoding is needed.

Separate description validity from selected execution completeness. A truthful
partial record can assert `host_root_equivalent` without knowing its interface;
this asserts observed privilege, not permission for RAE to exercise it. A
complete abstract model can omit backend detail under inherited open scope.
Neither case needs invented interfaces, templates, persistence or evidence.
Unknown/redacted information grants no choice; delegated detail is different.
Explicit constraints remain binding, including under an open parent.

Retain the requirement's resolvable read-write interface obligation when
admitting execution that actually exercises or materializes host-root-equivalent
authority. The backend may select a missing prerequisite only within admitted
delegation and operator authority. Before mutation, the complete selection must
resolve the same-node interface, establish supported engine/API semantics and
effective access, and satisfy scope, template and lifecycle constraints selected
by the operation. Unresolved privilege/access or `${var}` cannot establish
permission. Do not globally require every descriptive field for execution:
the selected semantic contract determines necessary completeness and verification.

The current base model rejects missing/variable refs and the semantic validator
requires `read_write`, `unix_socket` and a path ending in `docker.sock`. Move the
completeness obligation to its proper admission owner; do not merely delete it.
Retain validation of concrete references, stable identities, supported shapes
and explicit contradictions. An omitted ref is not a dangling concrete ref;
incomplete evidence must not be encoded as a fabricated reference. Independent
observations of conflicting state belong in the existing scoped description
carriers, not a silent rewrite of an authored constraint.

A filename is neither necessary nor sufficient proof of authority. Alternative
local endpoints must be judged by supported semantics; Docker-specific endpoint
rules belong to an explicitly selected Docker contract. Existing Windows named
pipe shape rules remain binding. The local, non-network interface shell must
not become a URI/credential bag to accommodate a future remote engine.
[Docker's daemon security guidance](https://docs.docker.com/engine/security/#docker-daemon-attack-surface)
distinguishes privileged daemon control from rootless operation;
[Kubernetes authorization](https://kubernetes.io/docs/reference/access-authn-authz/authorization/)
evaluates requested actions against authorization policy. These precedents
support separating engine identity, transport shape and effective authority;
they do not justify inferring any of them from a socket name.

The governing correction is already recorded in
[ADR follow-ups](../research/language-extensibility/adr-follow-ups.md#adr-051).
ADR-051's historical section 4 and its validation-gate text, ADR-048/050's
specimen guards, ADR-046's vocabulary/grant obligation, and
`specs/sdl/runtime-inventory.md` §3.4 must be reconciled when semantics change.
Do not leave normative prose asserting the old universal guard or present this
note as a published schema migration. Follow ADR-059's amendment and pin rules
when updating accepted ADRs. ADR-033/036 own scenario/delivery and package
boundaries; ADR-049's #956 capability correction remains intact.

## Canonical owners and extensibility seam

Package paths below are relative to `implementations/python/packages/`.

| Concern | Incumbents and required reuse |
| --- | --- |
| Inventory and references | `raes/runtime_orchestration.py`, `runtime_mounts.py`, `runtime_configuration.py`, `validator/_runtime_orchestration.py`; `_runtime_service_family_registry.py`, `_runtime_service_families.py`, `_module_runtime_aliases.py` and `composition/` already own family addressing and imported aliases. Preserve same-node resolution and authority-local id uniqueness; do not fork a resolver. `scope.organization_ref` and image/evidence strings are not automatically resolved or authenticated by the interface resolver. |
| Partial values and constraints | `raes_processor/compiler/realization_recursive_constraints.py`, `realization_structure.py`, and `raes_contracts/realization_structure/` own recursive knowledge, delegation, closure and conjunction. Preserve source presence through composition, instantiation, canonicalization and replay. Defaults of `[]`, `""` and `None` cannot by themselves distinguish omitted, known empty, unknown and forbidden. Use the existing description/coverage contracts for observation knowledge, not new per-family completeness flags. |
| Realization and observation | `raes_processor/semantics/realization_runtime_concern_profiles.py` already registers `runtime-orchestration-authorities` and excludes `realized_children` from desired configuration. Reuse `realization_concern_observations.py` and `realization_snapshot_sanitization.py`. Templates describe authority/configuration; realized children/counts describe observations, not desired replica counts or new node membership. |
| Selection and admission | `raes_processor/planner/realization_preparation.py`, `prepared_node_admission.py`, `prepared_node_semantics.py`; `raes_runtime/backend_preparation.py`, `control_plane_submission.py`, `control_plane_plan_authorization.py` and `backend_realization_authority.py` own selected completion, authentic plan authority and pre-apply checks. Reuse one semantic decision across planner, prepared existing/new nodes and direct submission; a permissive description parser is not executable admission. |
| Profiles | `raes_contracts/domain_profiles.py`, `_domain_profile_admission.py`, `realization_profiles.py`; planner `realization_profiles.py`; backend manifests and installed `validate_profiles(selected_plan)` own exact definition, local trust/support and joint core/profile checks. Validation-strength profiles (`validation_profiles.py`, ADR-072) describe assurance claims; they are not engine execution profiles. |
| Reports and evidence | `raes_contracts/contracts/realization_descriptions.py`, `description_coverage.py`, `description_reporting.py`, `observation_demand.py`; processor `capture_admission.py` preserve requested detail, observer/basis, coverage and required-capture admission. #1209/#1212 reporting does not imply independent evidence, retention or export; #1112's selected required-capture checks remain binding. |

The extension parameter belongs at the existing selected-operation admission
boundary: exact semantic-profile coordinate plus independently configured,
immutable local resolution/support context, bound to the selected backend and
plan. A next engine or endpoint variant must not require editing a universal
Docker predicate or adding an ambient `strict`/`capture` switch to Pydantic.
Core description/reference rules stay in `raes`; neutral portable contracts in
`raes_contracts`; selection checks in processor; operational policy in runtime
and installed backend semantics. Respect `tools/policy/adr_policy.yaml` imports.

This seam has limits: `plan-realization-profiles-v1` currently hosts public
provisioning constraints, not SDL profile syntax, secrets, observations or
orchestration-domain operations. Its reference backend supports only
`portable-resource-labels`. Carrier availability, a support row or schema
validation does not implement engine authority semantics. Reuse its negotiation
and installed-validator boundary where applicable; unsupported required
semantics must refuse before mutation. Do not smuggle authority through labels
or enlarge the host implicitly. No author profile is compulsory for an
irrelevant choice the backend can already resolve under open scope.

## Cross-cutting gates

| Layer | Required treatment |
| --- | --- |
| Source/shape/configuration | Keep `raes/_yaml_loader.py`, `_source_validation.py`, `_mapping_key_analyzer.py`, `_source_profile.py::SDLParserLimits`, `SDLModel`, `ContractModel` and bounded JSON ingress authoritative. Preserve safe YAML, duplicate/key diagnostics, closed keys, explicit variables, finite quantities/counts and bounded work. Direct JSON/model calls and backend returns must not bypass shape checks. |
| Semantic and prepared-node validation | Preserve `SemanticValidator`'s concrete references and native shapes. `validate_prepared_node_semantics()` reconstructs a scenario and invokes `validate_node_realization()`; any moved guard must survive at the appropriate executable boundary without making this shared description validator universally strict again. Conjoin selected core/profile constraints; recheck same-node interface and effective permissions after backend completion. |
| Secrets and environment | Reuse `runtime_values.enforce_observed_value_redaction`, `runtime_environment.py`, `runtime_mounts.py`, `raes_contracts/secret_references.py` and generated-artifact admission. Keep literal/`value_from` exclusivity, producer/consumer entitlement, environment-name uniqueness, protected-value omission and named-pipe rules. Generated secrets are not operator secrets. Orchestration adds no raw credential surface; free text, image refs, scope or lifecycle strings cannot become secret channels. Name heuristics alone do not sanitize arbitrary text. |
| Profile/config trust | Use exact admitted definitions and operation support from `DomainProfileResolutionContextModel`, manifest/context digest binding, and installed semantic validation. Preserve local-only bounded schema resolution, no remote `$ref`, no credential lookup, imports or executable handlers during parsing. Profile identity and support grant no resource authority. |
| API authentication/authorization | Keep `ControlPlaneSecurityConfig`, `_ControlPlaneApiAuth`, target/audience checks, request-size middleware and authenticated plan registration. Observed application permissions and orchestration privilege never become caller/operator authorization. Direct APIs must receive the same admission decision as HTTP and planned operations. |
| Host/OS and backend boundary | Description processing opens no sockets, contacts no daemon, pulls no image and spawns no subprocess. Future admitted realization uses the existing backend execution owner, with actual OS/daemon policy checks; never pass tokens or arbitrary lifecycle text through shell strings/argv. A mount's declared access or path does not prove host permission or protocol authorization. Unchanged engine API strings remain inert data. |
| Error envelopes and observability | Reuse `raes/_errors.py`, `_model_diagnostics.py`, `raes_contracts/diagnostics.py::Diagnostic`, backend preparation's value-free failures, operation receipts and audit dispatch. Keep stable bounded reasons, generic 422/500 responses and no raw Pydantic input/native output. `_operation_routes.py` and `_workflow_routes.py` expose `str(ValueError)` in 409 responses: new refusal messages must be payload-free before reaching them. Escaping/truncation alone does not redact secrets. No new exception hierarchy or payload logging. |
| Persistence, returns and replay | Reuse `ControlPlaneStore`/`LocalControlPlaneStore`, snapshot/observation codecs, SQLite transaction and payload-integrity helpers in `control_plane_store_local_codec.py`, existing revision/idempotency/reconciliation controls and sanitized concern projections. Preserve the original constraint and distinct selected/observed bases; reject altered completion, stale support or forged evidence before publication. No new database, sidecar or profile cache. |
| Contract publication/workflow | `raes_contracts/contracts/bundle.py::schema_bundle()`, `tools/generate_contract_schemas.py`, `check_generated_schemas.py`, schema fixtures and publication ledger must agree if contracts change. Published schemas remain governed authority; Python generation alone does not authorize change. Use `.ground-control.yaml`, `.gc/plan-rules.md`, `noxfile.py`, `tools/nox_support/`, `Makefile` and `.pre-commit-config.yaml`, with `RAES_REQUIREMENT_UID=DSL-137` and issue-wide traceability where relevant. Do not edit release-owned versions/changelogs. |

## Adjacent-family disposition and review evidence

Apply #959's existing audit distinction: identity, capability, configured state,
binding, policy and evidence are different facts. Ask whether each guard enforces
an explicit contradiction/security boundary or demands a specimen's recipe.

| Surface inspected | Disposition |
| --- | --- |
| Datastore | Separate persistence/geometry/mapping/replication completeness from valid partial records. Nonpersistent key-value stores and empty search/keyspace configuration are legitimate. Keep numeric bounds, local mapping refs and true data-model contradictions; assess prohibitions individually instead of deleting entire guard methods. |
| Forwarding | API-pull + IOC conversion + reload is one pipeline. Buffering, destinations and enrollment are selected obligations, not universal facts of synchronization. Review negative recipe restrictions too. Retain endpoint ownership (`target_service_ref` needs its node), enrollment classification, redaction and measurement-apparatus ownership. |
| Application authorization | `_require_grants_for_resource_vocabulary()` rejects named vocabularies with zero grants: this blocks known empty configured state as well as partial knowledge. Retain closed grant effects, credential posture, references and duplicate checks. Vocabulary identity never grants an action. |
| Platform applications | #956 already removed category completeness and uses composable capabilities with optional configuration. Keep that correction and stable ids; do not reopen MISP sharing-group obligations. |
| Local interfaces, mounts, sensors, detection, scheduled jobs | Preserve path/named-pipe and sensitivity checks, bounded values, identity/duplicate checks and typed configuration. These adjacent owners do not justify wholesale removal of validators when removing completeness recipes. Services/listeners remain transport/observed binding, not spawn authority; identity/accounts, software, content and evidence retain their own owners. |

Read-only model probes at the inspected revision rejected all five inputs:
privileged authority without an interface, key-value description without
persistence, partial search description, content synchronizer without the IOC
recipe, and `redis_acl` authorization with an explicitly empty grant set.
These establish the current guards, not execution conformance or independent
SCN-010 observation. Existing test owners include `test_runtime_orchestration.py`,
the datastore/forwarding/app-authorization suites, `test_issue_1201_*`,
`test_issue_1204_*`, `test_issue_1209_*` and `test_issue_1112_capture_admission.py`.

Required review evidence must distinguish base acceptance from operational
refusal: missing/unknown/variable interface versus bad concrete reference;
known read-only versus unresolved access; a supported non-Docker local endpoint;
valid empty versus omitted collections; explicit children retained under open
scope; and installed semantic validation rejecting unsupported/unauthorized
completion before backend mutation. Cover preparation of existing and added
nodes, direct submission, snapshot replay, imported references and schema/model
round trips. Keep positive full legacy examples and negative security tests;
do not merely invert every old rejection. Verify no secret-bearing exception or
unrequested capture is introduced.

## SEM-218 cross-family guardrails

The existing [SEM-218 specification](../../specs/formal/realization/explicitness-and-realization.md),
[ADR-105](adrs/adr-105-recursive-partial-description-semantics.md), recursive
constraint contract and #1204/#1209 lifecycle owners already supply the design.
No additional ADR or alternate partial-description schema is needed. Apply the
cross-cutting gates above to all four families, with these additional constraints.

| Distinction | Required treatment and canonical owner |
| --- | --- |
| Knowledge versus permission | `raes/explicitness.py` historically classifies `unknown`/`other` as `OPEN`; `compiler/realization_recursive_constraints.py::_SourceMetadata.leaf()` deliberately lowers those to `RealizationKnowledgeValue`, not delegation. Reuse that translation. Never admit replacement from the classifier label or an aggregate support summary alone. Omission permits selection only through resolved scope authority; `unspecified` is not automatically open. |
| Author choice versus selected value | `instantiate.py`, `phase_contracts.py`, recursive normalization and source binding retain source presence, finite domains and origin. Substitution and Pydantic defaults do not become exact author declarations. An explicit false/zero/empty value is not missing knowledge. Collection membership depends on its own closure: an empty list under open membership does not imply a closed empty collection. |
| Identity versus order | `_runtime_service_family_registry.py` owns addressable family/child IDs; concern descriptors and `realization_specialized_projection.py` own comparison policy. An addressable child is not automatically an unordered collection. Adopt keyed identity only for the reviewed inventory paths, preserving ordered sequences and explicit nested closure. Reuse `_normalization_scopes.py` and `source_occurrences()` to carry source-index scopes to semantic identities; do not reconstruct authority from a reordered backend payload. |
| Description coverage versus author closure | `contracts/realization_descriptions.py`, `description_coverage.py`, `description_projection.py` and `description_promotion.py` own fact states, universe/window, comparison and explicit promotion. Complete coverage does not close an author collection; partial coverage does not conceal a known violation. Backend-selected values remain descriptive until an authorized promotion creates a new authored artifact. An observed basis retains its evidence-reference requirements even though independent observation is not universally demanded. |
| Operation support versus a profile-shaped payload | `backend_profiles.py::configured_profile_context()` binds independent trust/support to the selected manifest; `backend_preparation.py` checks the complete selection and invokes installed `validate_profiles()` and ordinary backend `validate()` before apply. Required operational/security checks belong to the actual operation even when no optional author profile was supplied. Parsing inventory or omitting a profile cannot bypass them. |

Paths in this table use the package-relative convention above; compiler files
are under `raes_processor/compiler/`, description/normalization contracts under
`raes_contracts/`, and backend admission under `raes_runtime/`.

**Observed package-boundary blocker.** The working tree imports
`raes._runtime_service_families.RUNTIME_SERVICE_FAMILIES` from processor
`realization_runtime_concern_profiles.py`. Running
`RAES_REQUIREMENT_UID=SEM-218 implementations/python/.venv/bin/python tools/check_repo_policy.py`
reports `module-boundary-private-import`. Reuse the registry through a narrow,
supported read-only SDL boundary if cross-package identity lookup is required;
keep its traversal inside the owning package. Do not copy the registry, export
its mutable module internals, add a policy exception, or move SDL imports into
the dependency-neutral `raes_contracts` package. The identity seam takes a
registered family and validated collection path and returns identity metadata;
comparison adoption remains explicitly scoped by the concern owner. Pointer
handling must account for nested records, indices and escaping, rather than
assuming every future collection path alternates field/index segments.

**Admission evidence has a bounded claim.** The existing working-tree
`test_issue_1207_profile_admission.py` installs a test-only semantic contract and
calls `_call_backend_apply` directly. It exercises the real preparation hook,
refusal and delivery checks; it does not establish HTTP/manager authorization,
durable replay, live host permissions or installed production inventory support.
`raes_reference_backend/profile_preparation.py` supports public resource labels
only and explicitly rejects other semantic contracts. Do not present its carrier
as a datastore/orchestrator executor, encode privileged behavior as labels, or
require every author to select a profile merely to obtain a backend default.

The extensibility parameter remains the exact semantic contract/definition,
resource owner and requested operation, joined with independently configured
target support and bounded local resolution. A nonpersistent cache, non-IOC
synchronizer or supported non-Docker interface must fit without a compulsory
product recipe. Shared native semantic validation remains appropriate for
supplied-reference integrity; `validate_prepared_node_semantics()` also calls
it, so restoring universal completeness there would recreate the original bug.
Operation-specific admission must nevertheless reject unresolved necessary
authority or unsupported exact constraints before effects. Legacy targets retain
universal-envelope admission; one supported prepared witness does not prove
universal subsumption. Backend choice remains a backend responsibility.

Reuse `backend_input_contracts.py` for aggregate work admission before copying
and hashing, and `backend_apply_results.py` plus the shared recursive relation
for result checks before and after sanitization. Keep admitted selection fidelity
as well as original-author conformance: another allowed result is not the
admitted completion. Rejected successful claims preserve the trusted predecessor;
this is portable-state protection, not infrastructure rollback. Existing store
transactions/codecs and revision checks own durable publication. No second
inventory repository, profile cache, exception hierarchy or logging pipeline is
warranted. Keep disclosure value-free, including 409 routes that expose
`str(ValueError)`; neither bounded messages nor value commitments sanitize raw
text interpolated into an error.

Required review evidence must connect base-model cases to recursive compilation,
prepared existing/added nodes, direct and authenticated submission, delivery and
durable reload. Include closed-empty versus omitted collections, nested keyed
reordering with exact-child violation, variables and imported references, partial
readback through the legacy typed observation adapter, denied host authority,
secret presence/commitment tampering, and #1112 required-capture refusal. The
legacy adapter revalidates through SDL models and serializes defaults; it cannot
by itself establish observation coverage. Preserve #956 and #1043 ownership
regressions and the #959 adjacent-family dispositions above. A labels fixture or
an echoed plan does not establish execution or independent observation evidence.

This review changes guidance only. Full-tree policy currently fails on the
private import identified above; it must not be reported as passed. The Ground
Control context tool required approval unavailable in this session; local
`.ground-control.yaml` and `.gc/plan-rules.md` supplied the workflow context.
Remote blocker/traceability status and implementation conformance remain
unevaluated. Later implementation uses `RAES_REQUIREMENT_UID=SEM-218` where
appropriate, retains the other affected requirement links, and follows the
existing schema-publication, ADR amendment/pin and verification tooling.

## Non-goals and anti-patterns

No container spawning, engine client, lifecycle reconciler, remote-interface
redesign, new service/API/store, new profile registry, alternate validation
framework or global semantic-version migration. No full child-node expansion,
inferred authorization from a mount, product name, process argv or observed
child. No mandatory backend recipe/catalog/evidence for every author. No
sentinel-as-permission shortcut, duplicate schemas/resolvers/exceptions, generic
metadata authority, global validation bypass or unvalidated execution fallback.
Public guidance should distinguish historical guards from target admission
semantics so later implementations do not recreate the same ambiguity.
