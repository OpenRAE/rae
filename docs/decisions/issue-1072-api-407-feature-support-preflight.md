# Issue #1072 — API-407 feature-support architecture preflight

Date: 2026-09-20. Inspection baseline: `3fa51877`.
Scope: participant feature declarations within API-424 contract publication;
no implementation or implementation sequencing.

## Authority and boundary

[ADR-060](adrs/adr-060-participant-backend-facing-contract-surface.md),
[ADR-108](adrs/adr-108-modular-participant-control-and-governed-effects.md),
[PC-01–PC-15](../research/modular-participant-control/composition.md) accepted
at `ebb70a34b8e7d1cc8964c443841ae57e12ed1014`, and
[SEM-235 revision 1](../../specs/formal/participant-semantics/modular-participant-control.md)
settle the architecture. SEM-235 is present through `65ca8e41`; local presence
does not establish a released or installed artifact. No new ADR is needed.
The [API-424 preflight](issue-1072-api-424-provider-contracts-preflight.md)
covers the complete provider/result/effect boundary; this note closes the
API-407 declaration-to-effective-support gap. The older
[#801 preflight](issue-801-api-407-participant-policy-capability-preflight.md)
describes historical gaps, several of which are now implemented.

API-407 already owns `backend-manifest-v2`'s
`capabilities.participant_runtime.feature_support`. Reuse it and its
`unsupported < disclosed_weak < bounded < exact` vocabulary. Constraint refs
name bounds; limitation refs name exclusions/nonclaims; disclosure refs name
audience obligations; evidence refs name supporting records. None substitutes
for another. SEM-218 `realization_support` and realization-envelope membership
remain independent cross-domain gates. General realization support cannot
establish a participant feature, and a participant declaration cannot waive a
realization envelope.

API-424's exact mechanism/profile capability records must bind back to the
backend's API-407 declaration, not create a competing manifest support block.
One backend feature entry cannot express every mechanism instance, profile,
configuration, effect target and state cut. Those coordinates belong in the
closed API-424 bindings and trusted contextual joins. Do not encode tuples in
feature names, manufacture one feature per installed instance, or put them in
the existing open `ParticipantRuntimeCapabilities.constraints` map.

## Admission guardrails exposed by current code

Package paths here are relative to `implementations/python/packages/`.

- `raes_contracts/manifest_authority.py` owns the contract allowlist,
  term-to-required-contract map and evidence-required feature set.
  `contracts/feature_support.py` and `contracts/participant_manifests.py`
  under `raes_contracts` enforce the published model; internal dataclasses in
  `raes_backend_protocols/participant_capabilities.py` and adapters in
  `manifest.py` preserve the same declaration. Extend these existing owners
  together, with round-trip and JSON-Schema/Python parity; add no third DTO
  or independent rule table. Model/dataclass validation already overlaps:
  new rules must remain consistent, without adding another validator in each
  consumer or broadening this issue into a global refactor.
- `raes_backend_protocols/participant_feature_admission.py::resolve_participant_feature_support`
  is the incumbent comparison. It can return `None` for a supported legacy
  feature outside `PARTICIPANT_RUNTIME_EVIDENCE_REQUIRED_FEATURES`; that is
  **not an explicit strength result**. New modular claims require explicit
  declarations. Preserve legacy acceptance outside that new claimed scope;
  do not globally require every historical manifest to enumerate all features.
- A governed `x-<owner>:<term>` spelling is not evidence semantics. An unknown
  extension currently gets an empty required-contract set. New modular terms
  need governed vocabulary/scope, evidence criteria and authorized contract
  IDs before admission can accept them. A mapping omission must not confer
  vacuous exact support. Evidence-required terms currently use the behavior
  map in `BackendManifestV2Model._validate_participant_policy_contracts`:
  merely inserting an interaction term into that set would break validation.
  Keep the intended terms in their owning scope, or extend the canonical
  scope-aware lookup deliberately rather than creating a parallel map.
- Evidence-required features demand evidence for positive support,
  limitations/disclosure below exact, constraints when bounded, and agreement
  with API-405 presence lists. Do not add declaration-only terms to
  `PARTICIPANT_RUNTIME_POLICY_FEATURES`: that set also participates in runtime
  policy behavior and reference-backend declarations. Schema publication must
  not cause a backend to advertise mechanisms it has not installed.
- The comparison checks presence of downgrade policy/provenance refs; it
  does **not** authenticate their authority or resolve evidence, bounds or
  limitations. Its return is the declaration, not an installed-provider or
  exact-cut attestation. Trusted context must establish those relationships,
  required strength and applicable constraints before publishing effective
  support. Nonempty evidence, matching digests and an allowed contract ID
  prove neither trust nor realization. Unsupported is never an authorized
  weaker execution mode.
- Reuse the dependency-inverted pattern in
  `raes_contracts/contracts/mixed_composition_resolution.py`: trusted
  component-local resolution and exact `MixedCompositionFeatureDowngradeAuthorization`
  membership. Its SEM-234 backend-component identity is not an API-424
  mechanism identity; bind their relationship explicitly. Reuse
  `raes_processor/trial_compiler/apparatus.py` and `realization_admission.py`
  for manifest, envelope, apparatus and allowlist joins. Never pool support
  across providers or let one profile authorize another profile's weakening.
- MPC-01/03/13 require requested and effective bindings to remain distinct,
  preserving every contributor and blocking reason. Missing, unknown,
  unsupported, abstain, deny, conflict, stale, failed, weakened and applied
  belong to their respective resolution/decision/composition/realization
  coordinates, not an expanded API-407 strength enum. A scalar minimum rank
  is insufficient for composed support: different bounds may be incompatible
  and mandatory slots may be unresolved. A weaker alternative needs a new
  admitted binding/cut, authority, disclosure and fresh validation; it cannot
  retain the stronger requested claim or silently drop obligations.

## Cross-cutting gates and canonical incumbents

| Layer | Required reuse and satisfaction |
| --- | --- |
| Bytes and parser | New portable ingestion uses `raes_contracts/json_ingress.py::parse_bounded_json_object` with byte/depth limits and bounded reads, rejecting duplicate keys and invalid roots. The current CLI `raes_cli/processor.py::_load_backend_manifest` uses a size stat followed by `read_text`/`json.loads`; this is not duplicate-safe or a race-free read bound. Do not copy it into new ingress. The shared parser rejects literal NaN/Infinity but numeric overflow still needs finite-value checks. |
| Shape and semantic validation | Reuse `ContractModel`, scalar constraints, discriminated variants, controlled vocabularies and owning manifest validators. `extra="forbid"` does not imply strict types or deep immutability; `NonEmptyString` does not reject whitespace. Test wire/model/dataclass parity, direct Python inputs, bounded collections, duplicate identities and mutable aliasing. Use `x-raes-invariants`/`contracts/schema_invariants.py` and conformance's validator registry for trusted-context obligations that JSON Schema cannot establish. |
| Configuration and identity | Reuse `participant_configuration.py`, `contracts/experiment_bindings.py` owner/type/normalization checks and canonical digest utilities in `raes_contracts/_canonical.py` and `satisfiability.py`. Pin exact profile, mechanism, implementation, protocol, configuration and evidence identities; order set-valued arrays canonically before hashing. Follow `participant_flow_policy_profiles.py` and packaged `corpus.py` for safe identifiers and exact revision/digest resolution. No latest fallback, caller-selected lookup roots, imports, URLs, commands or environment expressions as executable selectors. |
| Authentication and authorization | Contract publication adds no endpoint. Later consumers retain `ControlPlaneSecurityConfig.strict_defaults()`, `control_plane_api/_auth.py`, roles/target binding and `RequestSizeLimitMiddleware`. Authenticated identity, resolved downgrade authority, controller/action authority, crossing projection and final-sink permission remain independent conjuncts. Existing `participant_crossing_policy.py`, `participant_flow_sink.py`, ingress and egress gates must not be bypassed by a successful capability comparison. |
| Secrets and environment | Only safe bounded references cross the portable boundary: no prompts, credentials, private model state, raw rejected payloads, native handles or external-apparatus details. Reference strings/digests are not automatic redaction. No new environment bag is needed. If later installation consumes environment bindings, retain `raes/runtime_environment.py::RuntimeEnvironmentVariable` name/source/exclusivity checks and `runtime_values.py::enforce_observed_value_redaction`. |
| Host and process | No executable loading or host access belongs to #1072. Provider installation remains operator/backend-owned. Never transport secrets or provider payloads via argv, shell interpolation, environment dumps, filenames or stdout/stderr; portable paths are not installation authority. Contract validity makes no host-isolation or monitor-independence claim. |
| Errors and observability | Reuse `raes_contracts/diagnostics.py`, existing planner/conformance gaps, runtime `backend_result_diagnostics.py`, coarse `control_plane_api/_responses.py` and `_operation_routes.py` envelopes and rejection auditing. Incumbent manifest validators interpolate rejected terms, and CLI error locations can contain unknown keys: do not forward those strings to new public surfaces. `portable_diagnostic_payload` validates shape, not redaction. Sanitize messages and addresses before serialization. Conformance's sanitizer stays within its package; no reverse import from contracts/runtime. Apply SEM-224 plane classification and SEM-220/226/230 audience projection to reasons, evidence, existence and timing. |
| Persistence and concurrency | Reference existing apparatus/evidence/claim bindings, `RuntimeSnapshot`, operation receipts, `AuditEvent`, and `ControlPlaneStore`/`AtomicControlPlaneStore` expected-head commits. No support cache, snapshot metadata or audit details becomes semantic authority. Later RUN-320 integration owns both memory/local stores, dispatch fencing and recovery; schema-valid support cannot prove freshness, atomic effects, crash durability or exactly-once execution. |
| Package and publication | Portable models/shared validation remain in `raes_contracts`, protocols/admission in `raes_backend_protocols`, orchestration in runtime/processor and probes in conformance, per `tools/policy/adr_policy.yaml`. Normative schemas remain under `contracts/schemas`; match `schema_bundle`, explicit generator routing, exports and installed corpus packaging in `implementations/python/pyproject.toml`. Follow `contracts/README.md`/ADR-009/061, the current v2 publication index and per-contract `schema-publication/entries` hashes/ledger, plus tombstones for removals. Older prose describing code generation as authority or inline v1 ledger entries is not current publication procedure. |

## Extensibility, evidence and exclusions

The seam is a typed provider protocol over exact immutable context/results,
bound by trusted operator construction, with out-of-band contextual resolution.
Reuse the existing feature comparison parameterized by feature, required level
and authorized downgrade; add exact profile/mechanism/configuration/cut and
evidence bindings in API-424 rather than backend-name branches in that helper.
A second implementation of the same semantic profile should need new admitted
bindings/evidence, not edits to the profile's meaning. New domains or effect
meanings require governed closed revisions/variants, not an open metadata map.

Reuse `test_backend_manifest.py`, `test_backend_profiles.py`, vocabulary parity,
issue #1004 declaration tests, #1014/#1015 provider-local resolution tests and
API-409/API-423/SEM-233 fixture/conformance patterns. Necessary acceptance cases
include honest unsupported declarations; missing legacy strength; unknown
extension criteria; forged downgrade/evidence refs; wrong provider, profile,
configuration or cut; incompatible bounds despite equal ranks; partial support
misreported as exact; schema/model round trips; secret-bearing errors; and
unchanged legacy acceptance. Distinguish schema-invalid data from valid shapes
rejected by contextual resolution. Fixtures establish bounded contract behavior,
not installed provider realization or ASR-538 conformance.

Workflow remains `.ground-control.yaml`, `.gc/plan-rules.md`, `noxfile.py`,
`tools/nox_support/` and existing policy/schema/concept/authority/lineage gates.
Set `RAES_REQUIREMENT_UID=API-407` for this requirement-specific preflight;
#1072 implementation belongs to API-424's `modular-control-contracts` phase in
`tools/policy/requirement_order.yaml`. API-407's earlier mixed-composition phase
must not bypass #1070/#1072 dependencies. Keep traceability aligned without
claiming that document publication delivers runtime support.

Non-goals: no new ADR, support scale, manifest block, semantic profile registry,
validation framework, exception hierarchy, logger, store or workflow runner;
no provider discovery, executable installation, concrete engine, HTTP route,
runtime composition/effect execution, persistence migration or backend parity
claim. API-409/API-423, inject, lifecycle, evidence and audit remain the owners
of their operations. #1069 owns orchestration; #1071 owns reusable assurance.
