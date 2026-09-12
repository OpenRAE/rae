# Issue 1205: SEM-218 acquisition boundary supplement

Recorded 2026-09-12 against `c8996122`. Requirement: **SEM-218**, as explicitly
supplied in this review's requirement payload and issue context. Non-normative
architecture guidance; no implementation plan, syntax, schema or runtime change.

Read with the [software outcomes preflight](issue-1205-software-outcomes-preflight.md),
which appeared in the shared workspace during this inspection. This supplement
records additional boundary details without duplicating its repository inventory.
SEM-218 anchors this work. The orchestrator verified that native blocker #1204
is closed. The maintainer's repository-boundary correction governs this note:
RAE owns generic semantics, contracts and conformance; acquisition execution,
scenario-specific readiness and live qualification belong to downstream owners.
Host execution details below are consumer obligations, not implementation scope.

## Owner and extensibility constraints

[ADR-034](adrs/adr-034-runtime-software-component-inventory.md) and
[ADR-105](adrs/adr-105-recursive-partial-description-semantics.md) already select
`runtime.software_components` for software presence and version refinement.
Retain `runtime.packages` as exact package-coordinate shorthand normalized into
the same requirement semantics. Package identity and component identity are
different; any correspondence must be explicit, potentially many-to-many, and
conjunctive rather than inferred from names. No new inventory or ADR is needed.

The extension parameter is the existing typed domain-profile binding: exact
authority/namespace, revision, definition digest, host/lifecycle use and installed
semantic-contract identity, with caller-supplied support context and work limits.
Version ordering belongs to that semantic contract, not a generic numeric range
or lexical/SemVer/PEP 440 comparison. Application and package versions need an
explicit relation when compared. Unrestricted version needs no comparator.
Private profiles must not require core registration or executable handler data.

The current [plan profile host](../../specs/sdl/plan-realization-profiles.md) is
public programmatic carriage, not SDL attachment syntax or a credential channel.
An authoring refinement must connect the software owner to that admitted carriage
and its schemas. APT-only `RuntimePackageRepository` cannot become a universal
private-profile mechanism merely by extending its union. The #847 child retains
its exact **final** repository/trust-state meaning and pinned key; ordinary
source absence, opaque `source` and identity-only `purl` retain their old meaning.
Do not silently convert old final state into temporary acquisition.

## Additional cross-cutting gates

Package paths below are under `implementations/python/packages/`. These are
implementation obligations, not claims that a general acquisition service exists.

| Boundary | Canonical incumbent and required treatment |
| --- | --- |
| Ingress/configuration | `raes._yaml_loader`, `_source_validation`, `_mapping_key_analyzer`, `SDLParserLimits`, `SDLModel`, `ContractModel` and `raes_contracts.json_ingress` retain bounded parsing, duplicate rejection and closed shapes. `instantiate`, `phase_contracts`, `runtime_values` and semantic validation preserve authored presence and revalidate bound values. Parsing must not fetch, probe packages or resolve secrets. |
| Profile schemas | `domain_profiles`, `_domain_profile_validation`, `_domain_profile_schema_registry` and `_domain_profile_admission` enforce pinned offline definitions, allowed owners, bounded local references and installed operation support. The allowed schema vocabulary does not include `pattern`/`format`; copying the legacy APT schema into a profile therefore needs deliberate adaptation or governed extension. Opaque preservation never authorizes execution. |
| Backend inputs | `raes_runtime.backend_input_contracts.backend_input_violation` bounds portable arguments and realization authority before hashing/isolation while excluding injected services. Acquisition clients and secret resolvers are services, not dataclass payloads to traverse, copy or publish. Reuse this distinction rather than hiding clients or credential caches inside portable config. |
| Caller and selection authority | `control_plane_api._auth`, `control_plane_security`, `control_plane_api_guards`, `control_plane_plan_authorization`, manifests and `backend_preparation` bind role, target, plan, selected configuration and predecessor. Extend existing codecs/commitments; manager and direct submission must receive the same checks. Read-only preparation selects a joint witness, never performs acquisition or ambient secret lookup; ordinary backend validation must admit the selection before apply. Legacy universal subsumption retains its meaning. |
| Secret/env binding | `secret_references.SecretReferenceId`, `experiment_bindings` and `participant_configuration` supply reference/exclusivity disciplines, not a general repository credential resolver. `RuntimeEnvironmentVariable` rejects raw operator secrets and contradictory literal/`value_from` shapes; generated artifacts have distinct delivery authority. A private route may use backend operator-controlled credentials without placing them in SDL. Any authored credential selector needs an explicit owning consumer/admission contract using the existing primitives. |
| Credential egress | `backend_account_credentials.plan_has_account_credentials` only recognizes account-placement bindings; its sanitizer does not automatically protect new acquisition secrets. `realization_typed_runtime_projection` recognizes specific sensitive field/classification pairs, not arbitrary profile secrets. Audit every new authority, definition, snapshot, provenance and diagnostic carrier. Keep private credentials out before serialization; a final-response scrub is insufficient. |
| Network/artifact policy | `uri_safety.validate_safe_absolute_uri`, artifact/associated-artifact trust contracts and OCI `ImageTrustPolicy` retain their respective gates. Syntax, digest identity and a private namespace do not authorize fetches. A real route must supply destination/redirect and rebinding controls, byte/time limits and artifact/key verification; offline/cache routes also need identity and path confinement. No such generic package fetcher was established by this inspection; unsupported routes must refuse honestly. |
| Host/OS execution | Reference `drivers.oci` supplies an injected fixed-argv/timeout/coarse-error precedent, not a package installer. Use fixed executables, manager-specific token/option validation, controlled environment/cwd, bounded I/O and protected credential delivery. No shell fragments, credential argv/URLs/inherited env, authored privileged filenames or raw output logging. Seed media, image layers, staging files and guest logs also see acquisition data and need protection/cleanup. |
| Result/error envelopes | `backend_calls`, `backend_call_contracts`, `backend_apply_results._finalize_backend_apply`, `backend_entry_transitions`, `backend_effect_transitions` and `backend_result_diagnostics` own result shape, authorized effects, exact selected delivery, sanitization and predecessor preservation. Reuse `raes._errors`, `_model_diagnostics`, `Diagnostic` and API redacted 422/500 handlers. Native stderr, validation input and exception strings must not become diagnostics, audit or provenance. No new exception tree/logger. |
| Reporting/persistence | `observation_demand*`, `observation_admission`, `observation_execution`, `RuntimeSnapshot`, `RealizationProvenanceEntry`, `ControlPlaneStore` and its snapshot/local codecs retain demand-selected depth/basis, transient reports and atomic revision/history checks. Retain only admitted safe state. Backend selection is not guest evidence; acquisition does not imply collection, retention or export. No sidecar inventory, acquisition store or install workflow. |

## Compatibility and lifecycle traps

- `RuntimeConfiguration` identifies package duplicates by manager/name/architecture;
  the realization registry uses manager/name. Preserve both multi-architecture
  rows and existing delegated architecture selection: simply making architecture
  a mandatory identity key breaks sparse input. Software `component_id` must stay
  stable through composition, matching, reporting and reload; version/list index
  is not identity. Reuse the shared recursive normalization and compatibility
  relation rather than independent parser/planner/backend matching.
- Omitted component version currently becomes `""`; defaults also introduce
  `unknown` and empty collections. Preserve authored absence, explicit literal,
  null, unknown knowledge and closed empty inventory separately. Open parents
  delegate unspecified descendants without weakening exact siblings; optional
  present values still satisfy their constraints. Reject lossy legacy projection.
- Shared repository instance and trust identities are distinct from profile
  definition identity and URI location. Reject conflicting definitions/dangling
  references, serialize native manager transactions, and remove only owned files
  no longer required by another consumer. Transient acquisition must not delete
  explicitly retained trust. Failed portable acceptance does not roll back
  external effects or authorize automatic replay.
- `realization_operational_verification` currently assigns configuration-level
  guest observation to package/software concerns. Trace that floor through
  compiler, support and corroboration; do not make sparse outcomes inherit an
  unjustified inventory scan. Preserve applicable legacy/behavior obligations.
  Required/prohibited input conflicts need admission failure. Existing mandatory
  observation-plus-mutation and unsupported-export gates cannot be bypassed.
- Enrollment/readiness/behavior retain forwarding-agent, service/relationship,
  proposition and evidence owners. Package installation or a plan echo is not
  an enrolled, functioning endpoint. A deliberately insecure described target
  remains valid without granting unsafe acquisition or host trust; select a
  permitted route or reject execution, never silently harden an exact target.

Qualification must cover unrestricted/exact/older/newer/range versions, the Kali
required/optional refinement ladder, APT, DNF/RPM, private typed and private APT
routes, offline/cache and prebuilt images, plus separately selected reporting.
Use generic fixtures to prove that separately declared behavior and observation
obligations survive software refinement. Live endpoint qualification and
scenario-specific telemetry remain downstream; no downstream dependency or
product-specific rule is introduced here.

Reuse existing #847/#1200/#1202/#1203/#1204/#1078/#1043/#1212 boundary suites,
schema fixtures and control-plane round-trip/admission tests. Published changes
must keep Node-bearing and affected plan/profile/manifest schemas, `schema_bundle`,
schema-publication entries/ledger and fixtures aligned under ADR-009/061.
`.ground-control.yaml`, `.gc/plan-rules.md`, canonical nox lanes and existing
policy/schema scripts remain the workflow owners; no parallel verifier or
release-please-owned changelog/version edit.

Non-goals are implementation itself, a universal package/dependency solver,
arbitrary scripts, a new secret store/controller/schema registry, compulsory
capture, participant policy redesign, or changes to #1204 preparation,
#1212/#1112 observation ownership and #1210 global migration. Native acquisition
adapters and downstream live qualification are outside this RAE implementation.
