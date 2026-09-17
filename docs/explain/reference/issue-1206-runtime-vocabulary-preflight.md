# GOV-922 / issue 1206: Identity-preserving runtime vocabularies

Architecture preflight, 2026-09-12; inspected revision `c8996122`.
The supplied GOV-922 requirement and corrective issue #1206 define the scope.
This note provides guardrails, not an implementation plan, new SDL syntax, an ADR amendment, or
evidence that the migration has shipped. Implementation remains subject to
the issue's native #1204 blocker; code present locally does not establish its
GitHub closure or ADR-105 ratification.

The governing [design intent](../../research/language-extensibility/design-intent.md),
[scope inventory](../../research/language-extensibility/scope-inventory.md), and
[ADR follow-ups](../../research/language-extensibility/adr-follow-ups.md) already
cover the rationale. This note locks down migration-specific integration risks.

## Findings that change the design

- The existing `audit.py census` scans 925 package files at this revision and
  still finds 144 authoring enums containing `other` or `unknown`. It is a
  candidate inventory, not a defect count or complete semantic inspection.
- `raes/_base.py::parse_enum_or_var()` rejects private tokens despite `Enum | str`;
  `runtime_values.parse_runtime_enum_or_var()` delegates to it. Its shared
  normalizer lowercases and changes hyphens to underscores. Globally loosening
  this parser would also loosen operational and security enums.
- `raes/architectures.py`, `operating_systems.py`, accounts and realization
  designation provide governed-extension precedents. Their vocabulary-specific
  lowercase/alias rules are not universal rules for external identifiers.
- `DnsResourceRecordSet.explicitness_exact_fields()` already preserves exactness
  of `record_type: other` when `type_code` is an integer. Preserve and verify this
  correction; do not report the baseline DNS explicitness finding as unchanged.
  Legacy sentinel handling still exists in `explicitness.py` and compiler
  `realization_recursive_constraints.py` and needs field-aware disposition.
  In particular, `_open_taxonomy_domain()` requires an Enum and enumerates its
  known core members. Accepting a private string in the model alone cannot make
  this compiler path represent delegated private choices; reuse the recursive
  scope/domain contract instead of expanding another finite product list.
- #1202's offline domain-profile contracts, #1203's recursive normal form,
  #1204's negotiated plan carrier and #1212's observation demand are present.
  The [plan host](../../../specs/sdl/plan-realization-profiles.md) supports public
  provisioning constraints only, with fixed owners and separately admitted
  target support. It is neither general SDL attachment syntax nor a secret,
  classification, observation or arbitrary runtime-extension channel.
- `specs/sdl/runtime-inventory.md` §3.2/3.4 still prescribe sentinel tails and
  discriminator-required profiles. Reconcile those statements with the owning
  family contracts when their behavior changes. Do not silently override
  normative prose with a permissive Python annotation. Historical ADRs remain
  governed by ADR-059 and their pins; the existing follow-up notes identify
  corrections without rewriting accepted history.
- `controlled_vocabularies.py` includes rejected values in `ValueError` messages;
  `_model_diagnostics.py` bounds/escapes validator prose but does not remove values
  already embedded in it. Reusing validation must not propagate that prose into
  API conflicts, receipts or logs when admitting private or protected data.

## Decisions and extension seam

Keep four concepts separate: exact identity, knowledge, realization authority,
and supported operations. A known private product stays exact and comparable
by its identity contract; `unknown` cannot erase known children or authorize
substitution. A namespace-qualified vocabulary token is inert identity, not
proof of namespace ownership, product compatibility, or executable semantics.
Typed domain meaning uses the existing `raes_contracts.domain_profiles`
definition/binding/resolution/support contract. Classification uses existing
concept bindings under #989. These are distinct established roles, not competing
ways to encode the same executable extension.

Normalize only aliases authorized by the owning vocabulary. Preserve external
case, punctuation and numeric identity wherever its contract distinguishes
them. Never reinterpret an exact native/provider identifier as a portable local
declaration id. Keep `${var}` recognition and post-instantiation validation:
placeholder acceptance must not become unrestricted string acceptance. An
extension must not shadow a core operator or gain semantics through spelling.
Retain canonical Enum members for built-in values while consumers depend on
member identity or enum-keyed maps; for example, environment source exclusions
use `is OPERATOR_SECRET`. A raw string that compares equal is not automatically
an equivalent input to every validator. Sensitivity labels that control value
egress require defined protection semantics, not a permissive taxonomy fallback.

The extension seam is the owning vocabulary scope or typed binding context,
plus the explicit `DomainProfileResolutionContextModel` and required semantic
operation. Reuse `validate_controlled_vocabulary_value()` / scope validation
for governed tokens and `admit_domain_profile_bindings()` for typed meaning.
Any reusable field adapter belongs beside these existing owners and selects a
declared policy; do not clone parsers, regexes or product maps across families.
Private definitions use the same pinned coordinates and bounded offline
admission as standard ones. Another product must not require a core term,
registry file or schema-publication entry merely to name it.

The catalog loader is cached and corpus-backed (`raes_contracts.corpus`), not a
mutable tenant registry. Its `contracts/vocabulary_sources.py` models already
enforce known governed scopes, unique scope ownership and extension policy.
Adding a field scope needs coordinated contract governance; adding a product
within an existing extension space does not. Keep catalog regexes reviewed core
data: accepting a regex as syntactically valid is not a work bound. Do not turn
this loader into a source of untrusted regexes or allow profile schemas to bypass
the inert keyword allowlist. Check Python and published-schema agreement on
aliases, placeholders, length limits and trailing/control characters.

A governed lowercase token is not a lossless encoding of every external native
identifier. Where the native contract distinguishes case or punctuation, preserve
that identifier in its owned typed field; do not squeeze it into the token grammar
by slugging, case-folding or inventing an alternative extension syntax.

An SDL attachment, if needed by a disposition, must be explicitly governed at
its owning surface and lower into the shared contracts. The programmatic plan
host is not evidence that this syntax or all host contexts already exist.
Unsupported semantic operations remain unsupported even when exact identifiers
can be compared. Schema validity, equal definition digests and advertised
support alone do not prove value equivalence or successful realization.

Use `raes_contracts.realization_structure` for inherited scope, local closure,
conditional presence, knowledge and source origins. Conjoin profile and core
constraints, including exact descendants of open parents. No binding is needed
for irrelevant unmentioned implementation identity in an open scope. Abstract
models can be complete without concrete infrastructure. Reporting an actual
choice is separate from observing it, and from retention or export. Do not
change ADR-070 universal subsumption into existential selection; use the
negotiated preparation contract for one supported completion.

## Disposition coverage and ownership

Extend the existing scope inventory with field-level dispositions and evidence;
do not create a second census or runtime-family registry. Every candidate must
name its external vocabulary/semantic owner, core host, disposition (retain,
governed identity, typed profile, classification migration, or already corrected),
normalization/legacy policy and affected consumers. Retaining a finite set needs
a semantic justification. Every disposition must also check inherited delegation,
exact descendants, abstraction-level completeness and independently requested
observations. The table below identifies architectural owners and exceptions;
it is not the completed field-level acceptance inventory.

Family keys, child identities and references remain owned by
`raes/_runtime_service_family_registry.py` and the runtime index. Package paths
below are relative to `implementations/python/packages/`.

| Runtime family | Existing owner and migration boundary |
| --- | --- |
| `service_listeners` | ADR-043 / `runtime_listeners.py`: protocol/provenance/scope identities; retain address, socket and port shapes. Unknown capture does not delegate binding or publish host ports. |
| `applications` | ADR-026 / `runtime_application.py`: protocol and parameter locations; retain precise HTTP/HTTPS upstream semantics until another typed profile supplies meaning. |
| `database_services` | ADR-029 / `runtime_database*.py`: engine, protocol, provenance and role identity; keep `ENGINE_TO_PROTOCOLS` compatibility within its owned profiles, with no unsupported-product fallthrough. |
| `dns_services` | ADR-039 / `runtime_dns*.py`: implementation/role/transport; preserve `other` + uint16 `type_code` + `rdata`, typed SOA/MX/SRV validation and the existing explicitness correction. Distinct codes remain distinct. |
| `identity_authorities` | ADR-032 / `runtime_directory_identity.py`: protocol/subject/policy classes; local ids, provider ids and policy authority remain separate. Attributes are not executable extension semantics. |
| `file_services` | ADR-037 / `runtime_file_service.py`: protocol/principal/action meaning; retain configured grants versus `access_observations`, explicit denial and sensitivity rules. |
| `mail_services` | ADR-038 / `runtime_mail*.py`: protocol/auth/store identity and knowledge states; retain partial message/queue knowledge and excluded-count boundaries. |
| `network_sensors` | ADR-042 / `runtime_network_sensor.py`: implementation/capture modes; preserve monitoring posture, references and demand. Inventory presence is not traffic capture. |
| `network_detection_engines` | ADR-044 / `runtime_network_detection.py`: engine/protocol/rule source and format/output identity; retain typed control capabilities and exact configuration. |
| `security_monitoring_managers` | ADR-040/045 / `runtime_security_monitoring/`, definitions: product/content/rule-language profiles; keep service references, status and identity separate. |
| `ssh_servers` | ADR-031 / `runtime_ssh_server.py`: retain SSH-specific structure and defined command classes; review nested partial policy without generalizing to all remote access. |
| `app_authorizations` | ADR-046 / `runtime_app_authorization.py`: resource/principal shapes need owned meaning; retain `allow`/`deny`, credential classification and reference checks. |
| `scheduled_jobs` | ADR-047 / `runtime_scheduled_job.py`: retain interval/cron/calendar grammar; last-result knowledge does not alter scheduling permission. |
| `datastore_services` | ADR-048/058 / `runtime_datastore*.py`: engine/role/eviction/replication profiles; #1207 owns specimen-guard correction. Retain explicit state and endpoint constraints. |
| `platform_applications` | ADR-049 / `runtime_platform_application*.py`: kind/content/markings; preserve #956's correction. Legacy `attributes` carriage does not establish comparison support. |
| `forwarding_agents` | ADR-050 / `runtime_forwarding_agent*.py`: product/format/transform/protocol; retain ownership, enrolled identity and service targets; #1207 owns compulsory profile detail. |
| `orchestration_authorities` | ADR-051 / `runtime_orchestration.py`: engine identity; #1207 owns partial-interface guards. Execution still requires admitted authority and real prerequisites. |

Adjacent surfaces are mandatory dispositions, including retained/delegated ones:

| Surfaces | Existing owner / boundary |
| --- | --- |
| Packages, service units, software, image provenance | `runtime_packages.py`, `runtime_service_units.py`, `runtime_software.py`, `image_provenance.py`; #1205 owns acquisition versus final state. Preserve precise systemd profiles; purls/hashes/coordinates are data, not acquisition authority. |
| Filesystem, mounts, local identity, network, environment | Respective `runtime_*` models and ADR-024/037/056/057; preserve absence, redaction, native mount/endpoint identity and generated-value references. |
| Containers, processes, capabilities, resource limits | Runtime configuration and platform profiles; retain security posture and Linux-specific operations within their declared scope. External resource classifications do not change enforcement. |
| Node OS, architecture, substrate | `nodes.py`, `architectures.py`, `operating_systems.py`, `realization_designation.py`; reconcile OS-family authoring/capability mismatch. Keep `compute`/`switch` structural and existing governed-extension regressions. |
| Generated artifacts and materialization | `stateful_resources.py`, `content.py`, contract vocabulary; #1208 owns generation/materialization extension work. Retain output type, sensitivity, ownership and delivery invariants. |
| Accounts, enterprise domains/facades/access | `accounts.py`, `identity_domains.py`, `enterprise_identity.py`, `agents.py`; retain governed authentication extensions, exact existing profiles, credential-source and authorization semantics; coordinate #1208's adjacent profiles. |
| Roles, vulnerabilities, participant classifications | #989 / `classification_migration.py`, external concept bindings; #959 remains the audit owner. Do not invent a parallel classification system or reopen #956. |
| Participant resources, relationships, references | Existing budget/contract and relation owners; #1208 owns resource-profile extension. Preserve units, ownership, enforcement, evidence, direction and endpoints. Retain accounting/reset operators; operational extensions need typed semantics, classifications use bindings. |
| Workflow, truth/comparison outcomes, lifecycle, contract/version/crypto discriminators, bounded mathematics | Retain finite operational meanings. Backend driver modes and CLI formats describe implementation capability, not universal language vocabularies; backend extraction remains #967. |

## Cross-cutting gates the migration must pass

These are required integration obligations, not claims that every current
consumer already accepts the proposed identities.

| Layer and canonical incumbents | Required treatment |
| --- | --- |
| Source/config ingress: `raes/_yaml_loader.py`, `_source_validation.py`, `_mapping_key_analyzer.py`, `_source_profile.py`, `SDLModel`; `raes_contracts/json_ingress.py`, `ContractModel` | Preserve safe YAML/JSON, duplicate-key rejection, source locations, bounded input, strict core keys, variables and family cross-field validators. Apply equivalent constraints to direct model/JSON ingestion. Widen only the disposed field's identity grammar. |
| Schema/profile admission: `domain_profiles.py`, `_domain_profile_validation.py`, `_domain_profile_schema_registry.py`, `_domain_profile_schema_identity.py` | Reuse pinned coordinates, namespace admission, local acyclic references, inert keyword/dialect rules and all work/diagnostic budgets. No remote retrieval, ambient filesystem/env discovery, imports or profile-selected handlers. An opaque-exchange allowance cannot satisfy a constraint or required comparison. |
| Identity and references: `_identifiers.py`, `_runtime_service_families.py`, runtime registry, `raes_contracts/addressing.py` | Preserve unique local and child ids, reference resolution and owner addresses. Product identity is a field, not a replacement collection key. Keep keyed collections distinct from ordered sequences and bounded semantic-address traversal. |
| Secrets/env/URI: `runtime_values.enforce_observed_value_redaction`, `runtime_environment.py`, `runtime_generated_value.py`, `raes_contracts/secret_references.py`, `uri_safety.py` | Keep raw-value exclusion for explicit protected classifications, generated-output ownership and `value`/`value_from` exclusions. Name heuristics stay advisory; do not strip scenario fixtures by name. A private sensitivity label cannot bypass protection. Reuse observation commitments; opaque nested values are not automatically sanitized. Credential-free URI shape is not network authorization. |
| Compilation/comparison: `explicitness.py`, compiler `realization_recursive_constraints.py`, `realization_structure`, semantics `realization_runtime_concern_profiles.py`, `realization_typed_runtime_projection.py`, `realization_concern_observations.py`, `semantic_comparison*` | Preserve source/default/variable origins, missing versus empty/null/unknown, exact siblings and numeric identities. TypeAdapter revalidation, defaults, excluded-field projections and sequence sorting can reject or erase extensions downstream. Reuse the shared relation/status/limits; unsupported or exhausted is not equal, unconstrained or unsatisfiable. |
| Planner, target config and authorization: planner `realization_profiles.py`, `raes_contracts.realization_profiles`, backend manifests, runtime `backend_profiles.py`, `backend_preparation.py`, `control_plane_submission.py` | Keep authenticated source-bound authority separate from target-owned trust/support. Revalidate configured context digest at registration and apply, whole core/profile conjunction and operation scope before effects. Direct submission gets the same checks. Support must never grant resources, privileges or observations. The current reference profile means portable labels only, not guest configuration. |
| Backend results and durable state: `backend_snapshot_contracts.py`, `backend_entry_transitions.py`, `backend_effect_transitions.py`, `realization_snapshot_sanitization.py`, `ControlPlaneStore`, `control_plane_store_snapshots.py`, local codecs/migrations | Validate the actual admitted completion before publication or storage. Retain exact coordinates and trusted predecessor on rejected results, including reload. Use existing revisions, atomic writes, idempotency and reconciliation; no profile database, sidecar or hidden cache. Value-free diagnostics and sanitized publication must cover history as well as immediate output. |
| API/auth/error envelopes: `ControlPlaneSecurityConfig`, API `_auth.py`, `control_plane_api_guards.py`, `_operation_routes.py`, `_responses.py`; `raes/_errors.py`, `_model_diagnostics.py`, `Diagnostic`, `portable_diagnostic_payload()` | Preserve authentication, target/audience entitlements, request limits, bounded mutation/audit queues and closed receipts. Reuse stable support/validation diagnostics; no new exception hierarchy. Routes expose `str(ValueError)` in 409 responses: no input values, private schemas/locators, native output or secrets in errors. Portable diagnostic shape validation alone is not redaction. |
| Observability, demand and disclosure: `observation_demand*`, compiler `observation_demands.py`, realization observation admission, backend result diagnostics, ADR-064/066 | Reuse operational audit/status and existing capture admission; do not log raw profiles or Pydantic inputs. Author, backend-selected and observed provenance remain distinct. #1212/#1112 own requested demand/capability gates; #1209 owns capture/report integration. No implicit collection, retention/export or new telemetry requirement. |
| Host/OS execution: reference `drivers/oci.py`, libvirt `cloudinit.py`, `drivers/seed.py`, and generated-artifact delivery | Identity parsing/resolution performs no subprocess or host-env lookup. A product token never selects an executable, shell fragment, import, path or privileged configuration. Actual authorized realization uses existing fixed argv/config interfaces, bounded subprocess calls and secret delivery; keep credentials out of argv, shell strings, logs and native-error envelopes. New backend semantics require installed support and admission, not string acceptance. |
| Publication/workflow: `contracts/schemas/`, `contracts/bundle.py::schema_bundle()`, schema generators/checkers, publication manifest and `contracts/schema-publication/entries/` | Model, schema, dataclass/DTO adapters, normalizers, examples, diagnostics and conversions change coherently. Follow the current v2 manifest's per-entry ledger, generator parity and ADR-061/075 negotiation rules. Do not publish private definitions in the core bundle or leave an unrestricted string branch in JSON Schema. |

Package boundaries and source-size rules remain in `tools/policy/adr_policy.yaml`;
do not put processor/runtime handlers into neutral DTOs or reverse dependency
direction to reuse them. `raes/canonical.py`, `composition/`, the existing
instantiation entry point, `classification_migration.py`, processor
`semantic_comparison*`, and runtime store codecs retain ownership of their
transformations. Use `raes_contracts.canonical.canonical_json_digest()` and
`canonical_domain_profile_definition_digest()` for their specified projections,
not a new canonicalizer or raw dictionary equality as profile semantics.
A legacy `other` without a
recoverable identity cannot be losslessly upgraded to a known private product;
retain its uncertainty. Downgrades that lose identity or authority must explicitly
refuse or disclose loss through existing compatibility outcomes, never silently
collapse to sentinels. Historical digests must not be reinterpreted in place.

## Review evidence and boundaries

Build on GOV-922's `test_controlled_vocabularies.py`, `test_backend_manifest.py`,
`test_runtime_contracts.py` and `test_runtime_planner.py`, plus
`test_issue_1202_domain_profiles.py`, the #1203 normal-form suite,
#1204 profile/offline/recursive/result/durability suites, #1212 policy tests,
`test_issue_985_runtime_realization_concerns.py`, architecture/governed-vocabulary
tests and schema/canonicalization/example conformance. The decisive probes are
two distinct private identities surviving parse, instantiate, compose, project,
compare and durable round trips; legacy aliases without private-token rewriting;
DNS distinct numeric codes; an open parent preserving exact children; and an
abstract model omitting irrelevant identity without acquiring data demand.

Include negative controls for retained operators/grant effects, known profile
incompatibility, unsupported semantic operations, malformed bindings, nested
reference/budget abuse, private sensitivity bypass, secret/error leakage,
unauthorized direct submission, altered selected results and lossy conversion.
Test schema-only consumers as well as Python validators. These probes establish
specific boundaries; a census count or successful parser test cannot establish
all-family conformance or backend support.

Workflow remains `.ground-control.yaml`, `.gc/plan-rules.md`, `noxfile.py`,
`tools/nox_support/`, `Makefile` and `.pre-commit-config.yaml`. Set
`RAES_REQUIREMENT_UID=GOV-922`; do not skip requirement governance for this work.
The current `tools/policy/requirement_order.yaml` selects repository-backed
requirements through `RepositoryRequirementClient`, including phase ownership
and traceability checks. This note resides under that phase's approved
`docs/explain/reference/` root. Runtime migration crosses additional ownership
roots: reconcile those explicit mappings with the issue's authorized scope before
implementation, rather than suppressing the gate or borrowing another UID.
Implementation must run `tools/check_repo_policy.py`,
`tools/check_requirement_governance.py` and `tools/verify_all.py` through the
prescribed environment, plus the selected nox verification/completion checks.
Reuse `tools/check_concept_authority_governance.py`,
`tools/check_generated_schemas.py` and `tools/check_schema_publication.py` when
their surfaces change. Preserve schema ledgers and ADR pins, align traceability,
and leave release-owned versions/changelog to release tooling despite the old
payload's changelog traceability link.

Non-goals: implementing this issue during preflight; a second extension system,
generic extension bag, compulsory core/profile catalog, executable plugin loader,
new controller/store/workflow, universal backend support, or global migration
owned by #1210. Do not pre-implement #1205/#1207/#1208/#1209 or duplicate #989/#959;
record their ownership and integration obligations. Neither a catalog migration
nor a profile definition can waive existing execution, security or genuinely
requested evidence requirements.

## Acceptance mapping

- [x] GOV-922, stable comparison and governed extension space:
  `raes/runtime_values.py:225`, `raes/runtime_vocabulary.py:22`, and the shared
  `controlled-vocabularies-v1.json` catalog preserve core terms and exact private
  identities through one declared vocabulary policy.
- [x] Issue, disposition and owner for every candidate:
  `docs/research/language-extensibility/scope-inventory.md:141` records the full
  runtime census, retained sets, adjacent surfaces, and semantic ownership.
- [x] Issue, exact identity versus knowledge and DNS numeric identity:
  `raes_processor/compiler/realization_recursive_constraints.py:267` and
  `test_issue_1206_runtime_vocabularies.py:95`,
  `test_issue_1206_vocabulary_consumers.py:38` exercise binding descendants and
  unresolved knowledge through compiled recursive conformance.
- [x] Issue, shared vocabulary/profile contract:
  `raes/runtime_vocabulary.py:22` uses the existing catalog validator. Existing
  domain-profile admission remains the owner of executable semantic support.
- [x] Issue, schema, normalization, projection, examples, diagnostics, legacy:
  `test_issue_1206_vocabulary_schema.py:52`,
  `test_issue_1206_vocabulary_roundtrips.py:36`,
  `test_issue_1206_runtime_vocabularies.py:120`, and
  `specs/sdl/runtime-inventory.md:185` cover the consumer-facing boundaries.
- [x] Issue, retained operators/security states and classification ownership:
  `test_issue_1206_vocabulary_schema.py:73` rejects private operations in Python
  and JSON Schema. The disposition inventory identifies #989 and #959 ownership.
- [x] Issue, no compulsory replacement catalog or implicit capture:
  `test_issue_1206_vocabulary_roundtrips.py:89` compiles an abstract model with
  no implementation identities or observation demands.
- [x] Issue, inherited delegation, exact descendants, abstraction, observations:
  the inventory applies all four checks to every disposition; compiled tests
  exercise their shared semantics across the family projections.
- [x] User clarification, Hub #3 domain boundary:
  `specs/sdl/runtime-inventory.md:185` describes identity as a portable constraint;
  no scenario recipe, asset pack, or backend implementation is introduced.

Python paths above are relative to `implementations/python/packages/`; test
paths are relative to `implementations/python/tests/`.

## Review correction evidence

The first code review identified two reports of the same OS-domain consumer
class, a finite image-schema class, and a replication-presence check. The OS
sweep also reproduced enum-only architecture filtering in satisfiability and a
binding-versus-normalized-alias mismatch during instantiation.

`test_issue_1206_review_regressions.py` now exercises both planner domain paths,
planning before and after instantiation, unsupported private OS families,
private OS and architecture satisfiability, architecture aliases, exact binding
substitution rejection, replication identity versus knowledge, and all three
published finite image fields. These regressions failed before their repairs.
The shared field normalizer preserves the recorded binding while comparing its
validated field value; it does not turn a private identity into semantic support.

The post-fix targeted run passed 475 tests. Current research evidence is replayed
at the corrected source digest; retained protocol outcomes and claim limits are
unchanged.

Test-quality review added direct positive alias-binding round trips for `AMD64`
to `x86_64` and `LINUX` to `linux`, including retained authored provenance and
model/JSON revalidation. Both pass with the real normalizer and fail during
instantiation when it is replaced in memory with a no-op, proving the tests
detect missing reconciliation without modifying production files.
