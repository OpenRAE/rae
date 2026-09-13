# Issue 1205: software outcomes, acquisition and final repository state

Recorded 2026-09-12 against `c8996122`. Requirement: SEM-218; issue #1205 and its
supplied corrective intent are the delivery contract. This is non-normative
architecture guidance, not an implementation plan, public syntax, or evidence
of backend support. No runtime or schema changes accompany it.

## Repository boundary correction

The maintainer confirmed that this work owns generic semantics, contracts and
conformance only. Downstream scenarios motivate requirements; they are not
dependencies, product-specific rules, endpoint inventories or live qualification
obligations in RAE. Backend products own acquisition, realization and operational
readiness. Their implementation obligations discussed below describe consumer
contracts, not instructions to add installers or backend workflows here.

Read with the [governing design intent](../research/language-extensibility/design-intent.md),
[ADR-105](adrs/adr-105-recursive-partial-description-semantics.md),
[recursive constraints](../../specs/sdl/recursive-realization-constraints.md),
[backend preparation](../../specs/sdl/backend-realization-preparation.md), and
[plan profile carriage](../../specs/sdl/plan-realization-profiles.md).
ADR-105 already selects the software owner; another ADR is unnecessary here.
Its inspected acceptance text makes ratification effective on the #1204 merge.
Local dependency code is not proof that GitHub blockers cleared: dependent
implementation still requires #1205's native #1204 blocker to clear.

## Ownership and compatibility decisions

**Use `runtime.software_components` for software presence and version
refinement.** Retain `runtime.packages` as the existing exact package-coordinate
shorthand and compatibility input, lowering it into the same owning software
requirement semantics. Do not create `software`, `installations`, or a parallel
backend requirements inventory. Package rows and component identities remain
different facts: migration must not assert that a package is an application,
invent a component identity from its name, or require authors to duplicate rows.
When both surfaces constrain a related installation, conjoin their constraints;
neither takes precedence. Make the correspondence explicit and unambiguous.

Preserve the old meaning of every accepted package shorthand: exact manager,
name, version and selected architecture; opaque `source`; identity-only `purl`;
and the optional `apt`/`1` repository as **final** source/trust configuration.
Absent legacy `repository` retains ordinary target-configured-source semantics.
Do not reinterpret that absence as the new unconstrained acquisition model or
turn an existing repository into a disposable bootstrap hint. Preserve legacy
parsing compatibility without making its permissive strings executable.
ADR-034's distinction between package rows and component inventory remains;
any changed normative language must follow ADR-059's recorded amendment rules.

The minimal outcome needs neither a version nor a manager/repository/digest.
Use inherited recursive freedom, `model_fields_set`, explicitness/provenance,
and the normal form to distinguish omitted, defaulted, unknown, redacted and
authored values. Existing empty-string and `unknown` defaults are not automatic
exact constraints on a new partial description; nor may migration erase an
explicit legacy value. Required, optional-if-present and forbidden tools keep
their distinct presence relations. One exact child must not close siblings or
the inventory. Keep abstract descriptions valid at their chosen level; ability
to execute them is a separate backend admission question.

Enrollment, readiness and behavior stay with their existing owners:
`runtime_forwarding_agent` and forwarding relationships, service-manager units,
service/listener contracts, and propositions/evaluation. Link the software
identity to those requirements rather than copying their schemas into a software
row. `RuntimeListenerReadiness` is optional observation data, not an execution
barrier; scheduler participant readiness is another concept. Package installation,
a running process, or an open port alone cannot establish enrolled, ready,
correctly forwarding Wazuh behavior. Software presence grants no participant
affordance or access authority.

## Independent refinements and the extension seam

| Semantic role | Boundary |
| --- | --- |
| Software outcome | Required component/behavior, optional application-version restriction, and explicit package-coordinate restrictions. One owning requirement relation. |
| Acquisition constraint | An optional restriction on acceptable routes/artifacts. Unselected private routes remain backend configuration, with no authored profile, package digest or experimental provenance obligation. |
| Acquisition authorization | Trusted execution policy and scoped credential bindings. Authoring a route, insecure target or trust description never grants network, host, signing, or secret authority. |
| Final repository/trust state | Explicit, referenceable node-state requirements, including required presence or required absence after installation. A transient route neither creates nor satisfies them implicitly. |
| Shared identity | Distinguish profile definition coordinate, repository instance identity, and trust-binding identity. Share admitted definitions; reconcile effective configuration per target. A URI is a locator, not any of these identities. |
| Reporting/evidence | Actual selected choices at requested depth and honest basis. Operational verification, experimental collection, retention and export are separately selected obligations. |

Use the existing `raes_contracts.domain_profiles` definition/binding/resolution/
support contracts for standard and private typed semantics. A private APT
instance is data under APT semantics; a private profile supplies independently
identified typed constraints and may reuse an installed semantic contract.
Neither needs a public registry entry. Keep APT suite/components and
RPM-family semantics in their profiles, not a universal `url/options` bag or a
growing union of every manager. A definition's pinned digest is distinct from a
software/package digest; requiring exact identity for an exchanged profile does
not require the author to expose an internal route.

Final-state repository/trust records need stable identities and references so
several package refinements can bind the same effective state without copying
conflicting definitions. Use existing scoped reference, duplicate and dependency
rules. Detect same-identity/different-definition conflicts and dangling refs;
do not merge by URL, silently alias trust roots, or use last-write-wins. Removal
must respect other users of shared state. This is a typed node-state boundary,
not a new controller, database, workflow or general repository catalog. Extend
the canonical runtime ownership inventory deliberately if a new state carrier
is necessary; do not register every profile leaf as a concern.

**Version ordering is a real missing semantic operation.** `bounded_domains`
supplies exact/enumerated values and numeric intervals, not Debian/RPM/application
version ordering. Define version predicates under an exact semantic-contract
coordinate: unrestricted, exact, older/newer, or bounded range, with explicit
inclusive/exclusive endpoints and defined comparison behavior. Permit a one-sided
constraint without an invented opposite endpoint or exact selected version.
Preserve Debian epoch/revision and RPM epoch/version/release distinctions under
their own semantics; application-to-package version correspondence must be a
defined profile-owned relation, possibly non-bijective. No relation means no
inferred equality. `purl`, CPE, package name and arbitrary source labels cannot
supply an unstated mapping.

The seam belongs at the existing domain-profile/recursive relation boundary:
explicit semantic coordinate, bounded predicate data, installed pure comparison
support and caller-supplied limits/context. Extend that shared relation where
needed, so compilation, comparison, preparation and delivery use the same
meaning. Do not implement independent comparators in parser, planner and backend,
coerce versions to numbers, borrow module-registry `packaging.version` ordering,
enumerate every possible release, or execute `dpkg`/`rpm` during validation.
An unsupported comparator is diagnosed as unsupported, not unconstrained or
nonconformant. The current evaluator and `profile_selection_violation` do not
gain version semantics merely because profile support rows say “comparison”.

The current profile host is programmatic and publication-safe; it is not yet an
SDL attachment syntax or a secret carrier. An authored attachment must lower
through that owner and preserve its contract, not hide in metadata. Standard and
private profiles must pass the same schema vocabulary/namespace/owner/use gates.
`SAFE_DOMAIN_PROFILE_SCHEMA_KEYWORDS` currently excludes `pattern` and `format`:
do not copy the legacy APT JSON Schema into a profile and assume admission works.
Use supported structural vocabulary plus installed semantic validation, or make
an explicitly governed, bounded vocabulary extension. Never relax the validator
with unrestricted JSON Schema evaluation or network `$ref` retrieval.

## Cross-cutting layers implementation must pass

Package paths below are relative to `implementations/python/packages/`.

| Layer and canonical incumbents | Required treatment |
| --- | --- |
| Source ingress: `raes._yaml_loader`, `SDLParserLimits`, parser, `_base.SDLModel`, `raes_contracts.json_ingress` | Preserve safe bounded YAML/JSON, duplicate-key/alias/depth rejection, closed models and published literal-or-variable shapes. Parsing/resolution is inert: no network, package probing, secret lookup or handler import. Bound profile values before copying, hashing and evaluation. |
| Binding and semantic validation: `instantiate_scenario`, `SemanticValidator`, `runtime_values`, `runtime_configuration`, `architectures`, compiler `realization_recursive_constraints` | Revalidate concrete values after whole-field variable binding, including manager/profile agreement, tokens, references, architecture and joint constraints. Keep local invariants on models, cross-object invariants in existing semantic passes. Retain authored-address rewriting and defaults provenance; never reconstruct intent from an unrestricted `model_dump()`. |
| Profile/config shapes: `domain_profiles`, `realization_profiles`, `registry._validate_runtime_target_shape`, backend manifests and planner `manifest_validation` | Admit exact locally supplied coordinates, namespace authority, owner/lifecycle/use, supported vocabulary and operation-specific installed semantics. No opaque execution fallback. Keep target trust/support separate from plan-supplied definitions and bind the configured context digest. Reference `profile_preparation` supports public resource labels, not arbitrary repository semantics. |
| Recursive/plan authority: `realization_structure`, compiler `realization_requirements`, `CompiledRealizationRequirement`, `ResolvedRealizationAuthority`, `plan_projection`, planner `realization_preparation` and `prepared_node_*` | Preserve one bounded constraint relation, identities, optional presence, closure universes and plan digests through forward/reverse codecs. Use `backend-realization-preparation-v1` for one joint supported selection before mutation. Keep universal envelope subsumption unchanged for legacy targets. Prepared data must pass the normal node/config/semantic/capability gates, not just profile validation. |
| Caller authorization: `RuntimePlanAuthorizationMixin`, `control_plane_submission`, `ControlPlaneSecurityConfig.strict_defaults`, API `_auth`, request-size middleware | Keep authenticated target/role/audience, runtime ownership, idempotency and request commitments on manager and direct HTTP paths. Bind original constraints, selected manifest/context and predecessor; a digest or profile document alone grants nothing. CLI/MCP remain adapters. |
| URI and acquisition trust: `uri_safety.validate_safe_absolute_uri`, `artifact_requirements`, associated-artifact admission, module-registry trust, OCI `ImageTrustPolicy` | Reuse inert credential-free locator checks and existing artifact/image admission where those owners apply. URI safety is not SSRF/egress authorization. The route's backend must enforce allowed destinations and redirects, bounded bytes/time, integrity and local-artifact confinement before use. No generic authenticated package-fetch service was established by this inspection; unsupported routes must fail admission rather than bypass policy. |
| Secrets/env shapes: `secret_references.SecretReferenceId`, `contracts.experiment_bindings.BindingValue`, `participant_configuration`, account-credential admission, `RuntimeEnvironmentVariable`, generated-value/file validators | Reuse logical references and literal/reference exclusivity in their proper owners; a reference still needs an authorized acquisition consumer, not the account-credential subsystem repurposed as a repository resolver. Keep operator secrets outside portable values, hashes, source labels and profile data. Runtime env forbids nonempty redacted/operator-secret values and incompatible `value_from` combinations. A generated artifact is not operator-secret storage. Existing forwarding enrollment classifications never carry raw enrollment keys. |
| Host/guest execution: reference `drivers.oci`, libvirt `drivers.seed`, backend driver/config seams | Reuse injected runners, fixed executables/argv, controlled environment/cwd, timeouts and redacted native failures. No shell fragments, credential-bearing argv/URLs, ambient host credentials, authored root filenames or world-readable staging. Native package tooling also needs option-injection prevention, owned/symlink-safe files, manager locking, bounded output and idempotent shared-state reconciliation. Apply least-scoped acquisition trust; no global `apt-key` trust shortcut. Persistent seed media, image layers and guest logs are disclosure surfaces too. |
| Result acceptance: `backend_calls._call_backend_apply`, `backend_preparation`, `backend_realization_authority`, credential sanitization, concern observation validators and `realization_snapshot_sanitization` | Validate full result shape, exact admitted selection, canonical identities, authorized transitions and history before publication. Reject wrong versions, dropped constraints or changed shared trust with the immediate trusted predecessor preserved. Validate before lossy sanitization; do not repair forbidden state by dropping it. Failure handling does not roll back infrastructure or authorize retry. |
| Errors/logging: SDL exception family, `Diagnostic`/`Severity`, `portable_diagnostic_payload`, `runtime.backend-contract-invalid`, API redacted 422/500 handlers, `AuditEvent` | Reuse addressed bounded codes and existing terminal/audit envelopes. No new exception hierarchy/logger. Never expose `ValidationError` input, raw exception text, backend stderr, commands, downloads, enrollment data or private acquisition locators through logs, diagnostics, API responses or provenance. Sanitization applies on rejection as well as success. |
| Reporting and persistence: `observation_demand`, `observation_reporting`, `observation_execution`, `backend_observation_calls`, `RuntimeSnapshot`, snapshot envelopes/codecs, `RuntimeDurabilityMixin`, `ControlPlaneStore` | Select depth, basis and lifecycle before collection. Backend-selected reporting needs no fabricated observation or automatic package digest; observed/verified claims need their actual evidence basis. Retain only authorized protected data using existing revision/CAS, terminal-operation/audit and observation transactions; no repository side table/cache or log-only evidence. Rejected choices must not reappear on durable reload. |

An insecure final target must remain describable/capturable without loosening
legacy `apt`/`1` HTTPS/pinned-key semantics or granting unsafe acquisition. A
separately typed description can bind insecure effective state while execution
policy still rejects using that state to fetch/install. A permitted safe route
(for example an admitted offline artifact or image) may produce such a target;
if the selected backend cannot safely deliver it, refuse execution while
preserving the valid description. Never silently “secure” an exact insecure
target, nor turn its modeled trust posture into host trust or TLS bypass.

## Repository-wide gotchas and qualification boundary

- **Identity drift:** `RuntimeConfiguration` rejects duplicate packages by
  `(manager, name, architecture)`, while `RUNTIME_CONCERN_PROFILES` currently
  names `(manager, name)` for packages and no explicit collection key for
  software components. The latter have `component_id` uniqueness in the model.
  Align source, recursive matching, projection, composition and reporting
  identities; multiarch rows and reordered inventories must not merge or become
  positional. Version and repository location are not stable component IDs.
- **Automatic verification floor:** `realization_operational_verification`
  currently assigns guest-observed configuration verification to both package
  and software-component concerns, and daemon-observed verification to
  forwarding agents. Trace compiler, support admission and runtime corroboration
  together. Preserve obligations justified by legacy contracts or declared
  behavior, but do not let the new presence-only owner inherit compulsory
  acquisition/repository observation by registry membership. Renaming a scan
  “operational” does not authorize it. Conflicting required/prohibited input
  needs explicit admission failure, not silent collection or false conformance.
- **Limited backend support:** the reference manifest does not claim general
  package/software realization; libvirt capabilities derive from selected
  governed envelopes. Profile parsing, label-profile preparation, VM creation
  or an OCI driver are not proof of APT/DNF/software support. Qualify each
  selected backend configuration and route honestly; never widen a manifest
  merely to make fixtures pass.
- **Lifecycle limits:** current observation admission rejects mandatory
  observation combined with mutation and rejects export without its delivery
  owner. Required endpoint evidence must respect those gates and use the
  established capture lifecycle; a carrier alone does not deliver telemetry.
  Bind any later verification to the actual delivered endpoint/generation.
  Nonretained descriptions are immediate results, not recoverable API history.

Acceptance must span authoring, instantiation, both plan codecs, manager/direct
submission, preparation, delivery rejection and durable reload. Reuse #847
package-repository tests/fixtures, #1201/#1203 recursive suites, #1204 preparation,
profile, credential, result and collection suites, #1212 demand/policy suites,
forwarding-agent/service-unit tests and the existing conformance probes. At
minimum, distinguish these independent cases:

- Presence without version/manager/repository; exact, older, newer and ranges
  with endpoint inclusion/exclusion, contradictory constraints, unsupported
  orderings and distinct application/package versions. Preserve old #847 input
  meaning through round-trip and execution admission, not parsing alone.
- One open Kali; Kali plus exact nmap; pinned Kali plus required/optional tools
  and configurations. Check inherited freedom, forbidden presence, optional
  constraints when present, unchanged exact siblings and joint OS compatibility.
- APT, DNF/RPM, private typed profile, private APT instance, cache/offline
  artifacts and prebuilt image. Separate software-only internal acquisition
  from explicitly bound route, package digest, final repository and trust state;
  include shared-state conflicts and final repository absence after acquisition.
- No requested repository/install telemetry (assert no collector invocation),
  separately requested software/OS choice detail, stronger evidence explicitly
  selected, and independently forbidden retention/export. Include negative
  leakage checks across authority, snapshots, recovery, diagnostics and drivers.
- Generic composition tests must distinguish software presence from separately
  declared behavior and observation obligations. Conformance fixtures establish
  contract enforcement, not live product support. Scenario-specific topology,
  telemetry checks and deployment qualification belong to downstream owners.

Keep publication authority in `specs/`, `contracts/`, `docs/`, and
`implementations/`. Reuse #847's four Node-bearing schemas:
`sdl-authoring-input-v1`, `instantiated-scenario-v1`,
`instantiated-scenario-snapshot-v1`, and `scenario-satisfiability-evidence-v1`.
Keep all affected plan/profile/snapshot carriers, `schema_bundle()`, publication
entries/manifest and their change ledger, generated-schema/fixture parity, and
`docs/explain/sdl/sections.md`. A model-only change is not a published contract.
Preserve ADR-015/036 package dependencies and size limits: neutral relations/DTOs
in contracts, language validation in `raes`, compilation/planning in processor,
execution acceptance in runtime, native effects in backends. Backends must not
import SDL or processor internals.

`.ground-control.yaml`, `.gc/plan-rules.md`, `noxfile.py`,
`tools/nox_support/policy_lanes.py`, `tools/check_repo_policy.py`,
`tools/check_requirement_governance.py`, `tools/verify_all.py`, pre-commit and
`.github/workflows/canonical-verification.yml` remain the verification owners.
SEM-218 anchors the software realization enforcement changes and is present in
the issue's Requirements section. Keep its traceability aligned. No release
version, changelog, alternate verifier or workflow bypass belongs in this change.

## Non-goals

This preflight implements no issue behavior and selects no public field syntax.
#1205 is not a universal package resolver, SBOM importer, repository browser,
secret manager, plugin loader, new service-readiness engine, participant tool
catalog or experimental telemetry system. Do not turn backend recipes into
mandatory author data, infer source-label semantics, close an inventory because
one version is exact, make package hashes universal, or duplicate validators,
schemas, exception trees and execution workflows. Program-wide migration and
general reporting/capture/export delivery retain #1210/#1209/#1112 ownership;
RAE verifies its generic contracts; downstream repositories qualify concrete
scenarios and backend behavior.
