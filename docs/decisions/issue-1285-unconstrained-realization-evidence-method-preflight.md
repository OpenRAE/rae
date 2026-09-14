# Issue 1285 unconstrained realization-evidence method preflight

Date: 2026-09-14. Inspected revision: `0f4205b6`.

Contract: GitHub issue #1285. This is implementation guidance, not an
implementation plan, schema release, or claim that the behavior is delivered.
It clarifies the operational-corroboration boundary left inconsistent after
#1212; ADR-021, ADR-064, ADR-066, ADR-070, ADR-105, and the formal realization
specifications remain authoritative.

## Architecture decision

Required corroboration has independent axes and must not be represented by a
single strength ladder:

- `RealizationVerificationScope` remains claim coverage (`presence` or
  `configuration`). It says what part of the authored claim was checked, not
  where or how it was checked.
- The existing `ObservationStrength` wire values describe the actual source
  provenance of an observation. The legacy type/field names remain for contract
  compatibility, but `driver-reported`, `daemon-observed`, and
  `guest-observed` are alternatives, not a total order.
- `required_observation_strength=None` means that the author did not constrain
  source or method. It does not remove the required verification scope, permit
  an undeclared source, or let planned/snapshot equality stand in for readback.
- When an explicit source constraint is present on the compatibility carrier,
  it is an exact source constraint. A guest observation does not satisfy a
  daemon-boundary requirement merely because the legacy enum ranked it higher.
- Claim sufficiency is decided by the concern-specific claim, required coverage,
  actual value/binding/freshness, selected manifest capability, and any explicit
  portable boundary or independence constraint. Source provenance alone never
  proves sufficiency.

`operational_verification_requirement()` remains the single concern-policy
entry point. It may require `presence` or `configuration` corroboration while
leaving the source unconstrained. A concern may retain a method/boundary
constraint only where the portable claim inherently requires it; effective
in-workload process resource limits are the existing example. Do not replace
the current blanket guest floor with a different blanket daemon floor or a
concern-family lookup duplicated elsewhere.

The canonical admission/evaluation seam is
`realization_observation_admission.has_required_observation_support()` together
with `realization_runtime_evaluation._observation_corroborates()` and
`realization_runtime_common.manifest_corroborates()`. Those paths must use one
claim-specific predicate. `observation_strength_satisfies()` must no longer
provide realization sufficiency or allow a capability for one source to attest
an observation from another source.

This does not merge operational verification into experimental observation.
The #1212 `ObservationDemandDocument` / `EffectiveObservationDemand` contract
continues to own whether data is collected for a purpose and whether it may be
retained or exported. A transient readback used to admit a realized claim is
operational input. It becomes experiment evidence or a reportable observed
basis only through the existing demand, evidence, protection, and lifecycle
owners.

## Closure, intrusion, and disclosure

Realization closure and observation method remain separate:

- A closed realization scope permits external/native readback that does not
  change the realized world, but permits no added in-world probe, sidecar,
  service, account, mount, package, listener, or forwarding path. If the claim
  cannot be proved without such an addition, reject before mutation.
- An open realization scope is not blanket instrumentation authority. A backend
  may add only a sufficient method with the least environment and participant
  effect among the methods it can honestly provide.
- Any added apparatus must pass the normal realization-authority/preparation
  gates and be reported through the existing realized-form and SEM-225
  augmentation disclosures. `environment_visible`, `participant_visible`, and
  `comparability_relevant` effects remain explicit. Hidden backend metadata,
  logs, or snapshot extras are not disclosure.

Do not define a global numeric "intrusion strength" that also ranks provenance.
For the current single-method capability shape, backend selection can remain
backend-local while the core verifies the declared method and returned source.
If a backend later exposes alternatives, the extension seam is a bounded set of
method candidates on the existing realization-observation capability, with
separate source, observation boundary, independence, and augmentation/effect
attributes. The pure admission helper receives the author constraints and
candidate set; it does not parse SDL or call a backend. Absence of a source
constraint must remain `None`, never an enum default.

Portable author constraints belong to the existing `EvidenceRequirement` and
`ObservationDemandRule` ownership. `EvidenceRequirement` owns source and
boundary references; the demand rule owns semantic selection, purpose, and
requested basis. `ObservationBasis.INDEPENDENTLY_VERIFIED` is not a shorthand
for guest or daemon vantage and is valid only with the existing trusted evidence
verifier. Do not add guest/libvirt/container/daemon terms to runtime-inventory
fields or realization posture. Where an operational demand is used to constrain
corroboration, only `purpose=operational` at the matching canonical semantic
scope may refine the operational check; experimental, realization-description,
retention, and export choices must not do so.

## Canonical incumbents and cross-cutting gates

| Layer | Incumbent and required treatment |
| --- | --- |
| SDL/source shape | `raes._yaml_loader`, `_mapping_key_analyzer`, `_source_validation`, `SDLParserLimits`, closed `SDLModel`, composition/instantiation revalidation, and `SemanticValidator`. Reuse these only if authoring carriage changes; no backend-local parser or free-form method string. |
| Claim and concern semantics | `realization_operational_verification.py`, the registered concern projections/observed validators, and the SEM-218 explicitness/constraint model. Preserve exact/open/constrained meaning and value-safe concern projection; observation method does not alter authored state. |
| Contract/config shape | `ContractModel`, `RealizationObservationCapability` plus its Pydantic model, `CompiledRealizationRequirement`, `CompiledRealizationAuthority`, `ResolvedRealizationAuthority`, and `RealizationObservationDisclosure`. Keep dataclass/model adapters and plan projections symmetric, closed, bounded, and enum-validated. Do not add a second verification DTO. |
| Planner and direct submission | `realization_support_diagnostics`, realization-authority materialization, `realization_authority_diagnostics`, `manager_plan_admission`, `control_plane_submission`, and exact runtime plan digests/authorization. Planner-created and HTTP-decoded plans must pass the same predicate; the method constraint is configuration-bound and digest-covered. |
| Backend result boundary | `backend_apply_results._finalize_backend_apply`, concern observation validators, snapshot sanitization, operation/envelope/configuration binding, and backend manifest corroboration. Planned payload equality, handles, success flags, or manifest claims alone are not evidence. Preserve baseline-on-contract-failure behavior. |
| Authentication/API | `ControlPlaneSecurityConfig.strict_defaults`, `_ControlPlaneApiAuth`, `RequestSizeLimitMiddleware`, target/role checks, bounded mutation/offload guards, and closed `ProvisioningPlanModel`. No new route or auth scheme; changing verification metadata must not let a caller forge planner authority or backend capability. |
| Secrets and environment | `RuntimeEnvironmentVariable`, `GeneratedArtifactValueSource`, `project_environment()`, `validate_environment_observation()`, value commitments, account-credential projection, and snapshot sanitizers. Compare protected values through the existing commitment-safe projection; never return or log environment values, secret references, credentials, native locators, or raw backend output. |
| Host/native IO | Existing libvirt native readback uses bounded `defusedxml` parsing and ownership/configuration binding; existing guest transport and OCI drivers own fixed argv, no-shell execution, restricted inputs, timeouts, and bounded output. #1285 must not add a subprocess or probe path merely to satisfy a historical floor. Any future collector reuses these controls and keeps secrets out of argv/environment/stdout/stderr. |
| Errors and observability | `Diagnostic`/`DiagnosticModel`, `portable_diagnostic_payload`, backend contract diagnostics, operation receipts/status, control-plane audit, redacted request-validation handling, and the generic HTTP 500 envelope. Reuse stable bounded codes and safe addresses; report the failed claim/constraint, never observed values or exception text. No new exception hierarchy or logging channel. |
| Persistence and lifecycle | `ApplyResult.operational_realization_observations`, `backend_apply_results` transient validation projection, `RuntimeSnapshot`, snapshot codecs, and memory/SQLite `ControlPlaneStore` implementations. Operational observations remain transient unless an independently admitted retention owner says otherwise; preserve atomic terminal commits, revisions/CAS, private store modes, link checks, canonical digests, and recovery behavior. Added in-world apparatus is realized state/provenance and cannot be hidden by stripping evidence. |
| Public schema/repository policy | Existing plan, snapshot, backend-manifest, and realization-envelope schemas; `schema_bundle()`, schema-publication entries/fixtures, concept authority, package dependency rules, Nox, pre-commit, and canonical verification. If a public shape changes, update the canonical model and generated/public mirrors together; do not hand-edit one schema or create backend-to-processor imports. Requirement-free verification uses the repository's existing policy lane, not an invented UID. |

## Compatibility and acceptance guardrails

- Omitted method constraints on runtime environment and published-port claims
  must retain configuration-scope corroboration and admit authoritative native
  control-plane readback from its honestly declared source.
- Actual source provenance must survive backend result validation. External
  projection or retention still requires its existing lifecycle authority.
- An explicit source/boundary constraint must not be weakened through the old
  ordering; a mismatched source fails before snapshot persistence.
- Claim-specific exceptions remain exceptions: effective in-workload, participant
  vantage, or independent-of-workload claims keep the boundary they need.
- Closed scope must fail before any in-world collector is installed. Open scope
  must disclose every added collector and its visibility/comparability effects.
- Compiler/planner, published-plan round trips, direct submission, and runtime
  evaluation must agree. A caller must not gain different semantics by omitting
  or modifying verification fields in JSON.
- Secret-bearing environment observations use commitments and redaction; native
  XML, guest output, backend object representations, and exception messages do
  not enter diagnostics, audits, snapshots, or reports.
- Update the contradictory prose when behavior changes:
  `specs/formal/observability-evidence-plane.md` currently says descriptors no
  longer derive strength, while
  `specs/formal/realization/explicitness-and-realization.md` and
  `docs/explain/reference/realization-envelopes.md` still describe the legacy
  ladder and fixed guest requirements. Tests must not preserve both readings.

Reuse the established regression owners: `test_issue_1043_realization_corroboration.py`
for capability/disclosure shape, `test_issue_1078_runtime_boundary_coverage.py`
for concern admission, `test_issue_1066_runtime_resource_limits.py` for the
effective-in-workload exception, the #1212 observation-demand/runtime-boundary
suites for lifecycle separation, the TechVault honesty/integration suites for
native readback, and `test_runtime_control_plane_api.py` for closed plan round
trips and authorization. The current #1078 and #1212 assertions that preserve a
derived guest floor are compatibility tests to correct, not architecture to
copy.

## Non-goals and anti-patterns

This issue does not remove corroboration, weaken SEM-218 non-approximation,
redefine realization closure, implement general live experiment capture,
authorize retention/export, create a universal probe scheduler, redesign
participant observation boundaries, or rename the released wire fields in
place. It does not make driver self-report authoritative for every claim or
assert that daemon readback always suffices.

Avoid: source ranking; `guest-observed` as a universal upgrade; method defaults
derived from concern family or open/exact posture; a parallel evidence schema;
backend-specific author syntax; hidden instrumentation; post-hoc filtering after
collection; capability availability treated as demand; plan/snapshot echo
treated as proof; placeholder evidence; duplicate validators, exception types,
stores, serializers, or workflow logic.
