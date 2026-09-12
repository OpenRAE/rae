# Issue 1201: Recursive Description Semantics Preflight

Date: 2026-09-05. Inspected revision: `164dd140`.

Contract: SEM-218, #1201, and the supplied 2026-09-05 governing intent. This
note is architecture guidance for the design review, not an implementation
plan, accepted semantic revision, or evidence
that the acceptance examples execute today. No runtime or schema changes are
authorized by this note.

Inspection covers the current repository's formal contracts, authoring and
composition, compilation/admission, backend return paths, API/store codecs,
evidence owners, and policy tooling. Findings below come from source inspection;
this preflight does not rerun the supplied audit's behavioral probes or claim
independent backend conformance.

## Governing boundaries

The author constrains what matters; the backend resolves permitted remaining
choices; requested reports describe those choices with an honest basis.
Inherited delegation, complete abstract models, and independent observation
demand are requirements of the new design. Extending a catalog alone cannot
satisfy them.

Keep presence, value restriction, knowledge, default selection, delegation,
record/collection membership, and lifecycle authority independent. In
particular, distinguish schema key closure, external vocabulary closure,
scenario membership closure, and observation coverage. `extra="forbid"`
continues to reject unknown syntax; it cannot mean that a machine contains no
unmentioned software or files. Unknown/redacted facts grant no discretion.
Optional presence permits absence but preserves constraints when present.
Undefined makes no local statement; it is not a new spelling for every current
`None`, empty string, sentinel, or default.

Known absence is a fact; forbidden presence is a constraint. An observed empty
collection is not an unobserved collection or a prohibition on future members.
Define not-applicable separately from unknown and withheld information. Retain
contradictory observations with their scope/time/basis. Promoting selected
observations creates a new authored artifact; it must not overwrite intent or
freeze incidental backend defaults merely because a capture contained them.

An inherited open scope must cover unspecified descendants without per-field
waivers. Explicit children remain binding without closing siblings. Closure
must name its domain and treatment of incidental dependencies. Model detail
does not select evidence strength. A backend may internally use a private
acquisition route without author registration or study provenance; an authored
private route or final repository constraint remains binding.

## Current owners and contract hazards

All package paths below are relative to `implementations/python/packages/`.
These are incumbents to extend deliberately, not proof that they already
implement recursive partial descriptions.

| Concern | Canonical incumbents | Design obligation |
| --- | --- | --- |
| Description and lifecycle | `raes/_base.py`, `raes/validator/`, variable/instantiation and composition machinery, ADR-033, `raes/explicitness.py`, `raes/realization_designation.py` | Preserve authored/defaulted/derived origin through parse, composition, instantiation, compile, and serialization. Current `unspecified` ignores local entries beneath concrete inherited posture and otherwise uses apparatus/closed fallback; changing this needs an explicit compatibility decision. |
| Recursive realization | `raes_processor/compiler/realization_requirements.py`, `realization_concern_explicitness.py`, `raes_processor/semantics/realization_concerns.py`, `realization_runtime_concern_profiles.py`, `realization_runtime_evaluation.py` | Preserve child constraints and container closure through existing concern ownership. `semantic_explicitness_record()` takes the weakest leaf; the runtime open branch bypasses exact comparison. An aggregate flag cannot be the authority for mixed descendants. Do not register every possible leaf as a separate concern. |
| Relations and admission | `raes_contracts/bounded_domains.py`, `raes_contracts/realization_envelope.py`, `raes/realization_envelope.py`, processor `semantics/realization.py`, ADR-070 | Reuse the bounded relation substrate. `realization_envelope_diagnostics()` currently constructs open demand and calls `subsumes()`. Review the quantifier at this boundary explicitly; do not change the meaning of the shared relation. |
| Validation strength | `raes_contracts/validation_profiles.py`, `raes_contracts/contracts/validation_disclosure.py::ValidationBasisDisclosureModel`, `contracts/profiles/validation/validation-profile-catalog-v1.json` (repo-root catalog) | Reuse the shipped ASR-511/515 profile selection, gate outcomes, strength caps, and limitation checks. Structural acceptance, semantic understanding, operational admission, and corroborated conformance need distinct bases; no parallel validity flag or evidence-strength taxonomy. |
| Software | `raes/runtime_software.py`, `raes/runtime_packages.py`, `raes/runtime_configuration.py`, existing artifact, service/readiness, and proposition contracts | Evaluate `runtime.software_components` as the minimal software owner's first candidate: it already has `component_id`, `name`, and an optional version string. Its sentinel/default/comparison semantics still need review. `runtime.packages` is the existing exact package-coordinate surface. Resolve their relationship without a third competing inventory. |
| Typed extensions | `raes/_source.py::ArtifactMechanismProfile`, `raes_contracts/artifact_requirements.py`, processor `semantics/artifact_realization.py`, governed concepts and external bindings | Reuse profile identity/version/digest and support negotiation, artifact distribution, ADR-012/062, and `contracts/concept-authority/`. A mechanism profile is not already a general recursive schema/comparison contract; specify the missing semantics at this seam. External classification bindings do not grant execution authority. |
| Evidence and observation | `raes/evidence_requirements.py`, `raes/validator/_evidence_requirements.py`, `raes/observability_plane_semantics.py`, `raes_contracts/contracts/experiment_capture.py`, `experiment_evidence.py`, ADR-064/066 | Keep authored demand, capture facts, derived analysis, scenario-native observability, and apparatus operations in their existing planes. #1212 owns corrective scoped demand; #341 owns task/run/study refinement, #340 augmentation conformance, #342 source provenance. |
| Abstract behavior, topology, and data | `raes/participant_behavior_specification.py`, `raes/participant_action_semantics.py`, `raes_processor/models/behavior_resources.py`, domain-topology and stateful-resource contracts | SEM-219 separates tool identity, availability, visibility, and invocation admission. Declaring three actions cannot imply OS packages, grant extra actions, or weaken preconditions. Connections need declared interaction semantics, not automatic packet networks. Data/files/mounts retain their own identity, placement, and dependency owners when explicitly requested. |

There is a normative migration hazard beyond these code paths:
`specs/formal/realization/explicitness-and-realization.md` currently restricts
openness to registered concerns, associates the closed default with
`extra="forbid"`, and calls lifecycle enforcement complete. That text does not
ratify inherited arbitrary-depth delegation or demonstrate the new acceptance
anchors. The reviewed semantic revision must reconcile those clauses and
`specs/sdl/runtime-inventory.md`'s sentinel/completeness rules explicitly.
Neither the existing `active` status nor this preflight settles that revision.

The software compatibility boundary is substantive: today's APT v1 repository
means required final node state with HTTPS and an exact public-key digest;
`source` is inert provenance text, not a recipe. The older #847 preflight
describes that shipped contract, not the target abstraction for all software.
Do not silently reinterpret existing APT declarations or globally relax their
security guards. Software presence, version relation, acquisition restrictions,
and final repository state need separately reviewed meanings. Application and
package versions are not interchangeable; older/newer/range constraints need a
named comparison relation, including incomparable values and endpoint rules,
not lexicographic ordering or a universal SemVer assumption.

## Cross-cutting gates the intended design must pass

These are obligations for later design/implementation review, not claims of
completed security validation. This preflight adds no auth or execution path.

| Layer and incumbent | Required treatment |
| --- | --- |
| Source parsing: `raes/_yaml_loader.py`, `_source_validation.py`, `_mapping_key_analyzer.py`, `_source_profile.py::SDLParserLimits` | Retain safe YAML construction, duplicate/alias/key diagnostics, source locations, and byte/depth/node/alias/import/composition limits. SDL variables remain explicit bindings, not ambient environment lookup or variable-generated identity keys. Apply equivalent bounds to JSON/direct model inputs; YAML-only limits do not protect all consumers. |
| Model/configuration and semantic gates: `SDLModel`, `ContractModel`, `SemanticValidator`, instantiation validation, `raes_contracts/participant_configuration.py`, `raes_contracts/contracts/experiment_bindings.py::BindingValue` | Keep core and selected extension keys checked. Separate truthful description validity from selected completeness/execution profiles without removing reference, authority, or security invariants. Preserve the discriminated literal/secret-reference shapes and owner-normalized configuration constraints; an extension cannot bypass configuration-target entitlement. Defaults must not fabricate captured facts or become exact authored values during normalization. |
| Secret and environment shapes: `raes/runtime_values.py::enforce_observed_value_redaction`, `runtime_environment.py`, `raes_contracts/secret_references.py`, generated-artifact reference validators, ADR-056/057 | Preserve raw-value redaction, environment-name uniqueness, literal/`value_from` exclusivity, producer-output entitlement, and value-free observation/commitment projections. Generated secrets are not operator secrets. Partial/open descriptions cannot bypass these rules. Do not introduce secret resolution while parsing a profile or use a field-name heuristic as the sole classifier. |
| URI, schema, and acquisition trust: `raes_contracts/uri_safety.py::validate_safe_absolute_uri`, `raes/module_registry/`, artifact admission, ADR-071 | Identity URIs remain inert and credential-free. Parsing/comparison performs no network fetch, credential lookup, or executable plugin loading. Explicit resolution uses pinned local/offline inputs or existing verified distribution and trust policy, including cache/extraction integrity. A digest establishes identity/integrity, not trusted semantics. Retrieval needs scheme/destination/redirect and size limits; URI shape validation alone is not SSRF protection. Unresolved required meaning must block semantic admission before mutation. |
| Planner and alternate submission: `compile_runtime_model()`, `plan()`, `CompiledRealizationRequirement`, `CompiledRealizationAuthority`, `realization_authority_diagnostics()`, `raes_runtime/control_plane_submission.py` | Keep authored authority and effective policy distinct. Planner and directly submitted operations must consume shared admission helpers, including account credentials, generated artifacts, service materialization, and domain topology. Carry envelope/profile and material-configuration identity through plans and snapshots; a witness selected against stale configuration is not admission for a changed backend. Preserve ordering, refresh, reconciliation, and cleanup checks. |
| API authentication and authorization: `RuntimeControlPlane`, `ControlPlaneSecurityConfig`, `control_plane_api/_auth.py::_ControlPlaneApiAuth`, `control_plane_api_guards.py::RequestSizeLimitMiddleware`, operation routes | Reuse identity/role, target and participant-subject checks, trusted-proxy/bearer policy, request limits, idempotency fingerprints, planner authorization, bounded audit execution, and published response DTOs. Reportability does not authorize every caller to inspect private profiles or observed data. An extension must not introduce a bypass route. |
| Runtime and observation boundary: `realization_concern_observations.py::validate_typed_runtime_observation`, `realization_snapshot_sanitization.py`, runtime evaluator, `RuntimeSnapshot`, `RealizationProvenanceEntry` | Current typed observations pass through SDL adapters; defaults and specimen guards therefore affect capture too. Preserve partial coverage, identity, time, contradictions, and claim basis rather than completing a specimen. Compiler descriptor-derived `required_observation_strength` and runtime corroboration gates are explicit migration review points: enforce requested strength, but do not derive unconditional collection from precise scenario detail. |
| Error and operational observability: `SDLError` subclasses, `raes/_model_diagnostics.py`, `raes_contracts/diagnostics.py::Diagnostic`, `OperationReceipt`/`OperationStatus`, API `_install_request_guards()`, libvirt `_observability.py::record_suppressed_failure` | Reuse bounded structured diagnostics and redacted 422/500 envelopes. Distinguish invalid description, conflict, unsupported semantics/capture, limit exhaustion, and unverified evidence. Never serialize Pydantic inputs, raw exceptions, native output, or tracebacks. Existing message bounding does not redact values interpolated by a validator: new validator messages must be value-free. Operator failure classification must not become experimental capture. |
| Persistence, retention, and export: `ControlPlaneStore`, `LocalControlPlaneStore`, store payload/record/observation codecs, experiment evidence contracts | Preserve atomic snapshot/operation writes and existing audit ownership. Define enforcement before collection, queues, temporary buffers, snapshot serialization, caches, storage, and export; filtering a response cannot implement a prohibition. Operational cleanup state is a separate purpose, not an automatic research dataset. Retention and internal use do not authorize export. Do not create a parallel inventory/evidence database. |
| Host/OS and participant exposure: `raes_backend_protocols`, `raes_reference_backend/drivers/`, `raes_backend_libvirt/drivers/`, process resource-limit policy, generated-artifact handling, participant views and flow-policy gates | Delegation does not grant host privilege. No secret-bearing argv, shell interpolation, environment dumps, public temporary files, or native paths/IDs in public diagnostics. If a reference-model tool needs a subprocess, use bounded inert inputs, a fixed argument vector, restricted environment, and timeout/output limits. Detailed reports and exhaustive traces still obey participant visibility, marking, and redaction. Instrumentation effects require existing augmentation/comparability disclosure. |

No experimental data, operational-only, inherited/no-preference, selected
observations, and exhaustive capture within a named supported scope must remain
distinct. An explicit prohibition conflicting with mandatory operational
policy or execution/termination/analysis inputs needs an admission diagnostic.
Neither hidden collection nor silently discarding required inputs resolves the
conflict. Scope overlap and inheritance must yield one explainable effective
policy; omission must not become capture-everything. No-data mode cannot claim
independently verified conformance without the required basis.

## Extensibility and review criteria

The seam is a versioned shared semantic representation and pure relation
operations over existing typed domains, with selected profile identity/revision,
collection identity/matching policy, explicit scope, and bounded evaluation
limits. Core and private profiles must use the same composition rules. Keep
neutral DTOs in `raes_contracts`, SDL syntax/semantics in `raes`, compiler/planner
consumers in `raes_processor`, backend capability carriage in
`raes_backend_protocols`, runtime gates in `raes_runtime`, and conformance in
`raes_conformance`. Respect the import DAG in `tools/policy/adr_policy.yaml`.
Do not introduce a registry, solver service, or backend-specific relation.
Reuse `raes/canonical.py` for SDL identity and
`raes_contracts/_canonical.py`'s JCS helpers for contract identity. Define the
versioned semantic projection before hashing; digest equality is neither
refinement nor permission to expose a low-entropy secret commitment.

The design review must settle the following without treating this note as the
answer or selecting public syntax prematurely:

- Composition/refinement means conjunction/intersection on the owned scope,
  with deterministic conflicts and exact-sibling preservation. Evaluate
  commutativity, associativity, idempotence, refinement transitivity, and
  normalization/round-trip preservation in the requested compact executable
  model. A CUE-backed check is optional; no language migration is implied.
  Separate default precedence from conjunction; conflicting exact
  constraints must not be resolved by merge order. An inconsistent request's
  empty set cannot count as successful operational admission through vacuous
  subsumption. Preserve type distinctions such as boolean versus integer and
  domain-owned units/version relations; host-language equality is not the
  semantic relation.
- Define stable identities, duplicates, aliases, ambiguous matching, cardinality,
  and ordered sequences versus set-like collections. Reordering a set-like
  package inventory must not retarget a nested constraint. Existing namespace
  and RFC 6901 address/provenance mechanisms remain relevant; an index alone is
  not a stable semantic identity.
- Distinguish recursive schemas, recursively nested finite values, and graph
  references. Name cycle policy and limits on expansion, references, matching,
  validation work, and diagnostics. Existing parser limits and planner
  `dependency_cycles()` are reusable protections, not a complete budget for
  recursive schema evaluation. Exhausting a budget means unsupported/limited,
  not unsatisfiable or successfully validated. No arbitrary predicates,
  unbounded regex evaluation, automatic remote `$ref`, or profile-supplied
  executable validators.
- Preserve opaque, bounded unknown extensions only for exchange/inspection,
  with explicit validation limitations. Name required versus annotation-only
  semantics, namespace authority/collision/normalization rules, and offline
  schema/profile resolution. Private backend-internal choices require none of
  this authoring machinery unless constrained or exchanged.
- Keep `subsumes(B, R)` universal: every member of R is supported by B. Delegated
  execution instead requires choosing and delivering a witness in R intersect B
  under execution policy. Membership of one witness proves neither universal
  support nor successful execution. Review planner admission, direct submission,
  configuration-bound envelope carriage, and conformance/negative probes with
  their quantifiers named. SCE-002 factor selection/randomization remains an
  independent authority; realization choice cannot replace it.

The review evidence must include the issue's five Linux boxes under one open
scope; Kali alone, Kali with exact nmap, and the release/tools/optional-package/
configuration refinement; sparse software presence and defined version
relations; a deep private profile and a separate unmentioned private acquisition
route; partial capture; and a non-cyber model. Also require the complete abstract
two-computer/three-action case, detailed filesystems with no experimental
telemetry, abstract exhaustive action traces, and mixed link/component demand
with retention/export choices. Counterexamples must include a wrong exact child,
an optional member present with a wrong value, unsupported requested capture,
and one supported allowed completion that succeeds. Do not substitute a concrete
VM fixture for the abstract model or prose for the requested executable check.

Reuse `test_sem_218_realization_designation.py`, `test_sem_218_explicitness.py`,
`test_sem_218_runtime_realization.py`, `test_issue_985_realization_projection.py`,
`test_realization_envelope_relation.py`, `test_realization_honesty_conformance.py`,
`test_dsl_124_authored_evidence_requirements.py`, the observation/evidence
conformance suite, and existing contract fixtures. These are anchors for later
review, not tests added or run by this preflight. Include normalization/default
and mixed-sibling mutations across compiler, admission, returned snapshots, and
serialized contracts; a local algebra check alone cannot establish integration.

## Compatibility, workflow, and non-goals

Record reviewed language decisions and any change to omission, closure,
quantifiers, completeness, or evidence obligations at an explicit versioned
boundary. Follow ADR-059 for accepted ADR amendments, including ADR-070; follow
ADR-061/075 for published contracts and migration. Do not merely edit Python
defaults and call existing scenario meaning compatible.

Published schemas under `contracts/schemas/` remain authoritative. Reuse
`raes_contracts/contracts/bundle.py::schema_bundle()`, invariant annotations,
schema-publication entries/manifest, fixtures, `check_generated_schemas.py`,
`check_schema_publication.py`, and concept-authority governance. Schema-only
consumers need the same published shapes and disclosed semantic limitations;
generator parity does not itself prove semantic validity.

Use `.ground-control.yaml`, `.gc/plan-rules.md`, `noxfile.py`,
`tools/nox_support/`, `.pre-commit-config.yaml`, and existing CI/policy commands.
Set `RAES_REQUIREMENT_UID=SEM-218` because the working branch names #1201 without
the UID. Reuse `tools/check_repo_policy.py`,
`tools/check_requirement_governance.py`, and `tools/verify_all.py`; unavailable
Ground Control governance must be reported as unevaluated, not passed or
requirement-free. Keep release-please-owned versions/changelog untouched. No
workflow replacement or new policy exception is needed for this guidance.

This preflight does not implement #1201, build its reference model, ratify public
syntax, amend an ADR, migrate runtime families, or implement #1204/#1212. It
adds no solver dependency, schema, controller, service, persistence store,
backend recipe, capture system, or deployment. Avoid blanket optional fields,
enum-to-string conversions, untyped settings bags, wrappers around every scalar,
new exception hierarchies, duplicate validation engines, compulsory hidden
machine models, and capture-everything/report-less behavior. Targeted correctness
fixes remain separately reviewable; this design issue is not permission to
weaken existing contracts while a replacement remains unreviewed.
