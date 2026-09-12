# Issue 1200: mixed runtime constraints architecture preflight

Recorded 2026-09-05. Guidance for #1200, not an implementation plan or a claim
of corrected runtime behavior. The issue and the
[corrective design intent](../research/language-extensibility/design-intent.md)
govern. Existing ADRs remain pinned; no new ADR or parallel semantic authority
is needed.

## Findings and binding decisions

The current compiler reproduces both loss points: `database_service_id: db`
with `engine: other` produces open database authority; an inherited open scope
with an exact nmap package produces exact authority for the whole package list.
`explicitness._weakest_class` and `semantic_explicitness_record` discard leaf
distinctions. `_compiled_registered_realization` chooses an aggregate authored
record instead of combining its constraints with inherited designation.
`_evaluate_open_realization` validates observed shape/corroboration without
comparing authored leaves. Generic constrained evaluation also lacks the
process-limit evaluator's exact-sibling checks. A different aggregate label
alone cannot correct these boundaries.

Preserve three independent facts through execution: authored leaf constraints,
the permitted membership/additions of the owning collection, and effective
delegation for unspecified descendants. Exact children do not close siblings;
open children do not erase exact identities or required members. Closure names
the modeled inventory universe, not the entire guest. Missing, explicitly
empty, optional presence, unknown knowledge, and delegated choice are distinct.
Do not infer authored constraints from defaults inserted by Pydantic or from
backend-selected values. Preserve `model_fields_set`, variable domains and
instantiation provenance until their semantic demand has been lowered.

Use the existing concern registry and portable plan authority. The
`RealizationConcernDescriptor`/`RUNTIME_CONCERN_PROFILES` seam must own any
needed collection identity, membership/comparison policy and context-sensitive
sentinel interpretation alongside its projector and exclusions. Reuse owning
model identities and domain validators; do not treat the projector's heuristic
sort key as a universal identity contract. Keyed inventories must survive
reordering while rejecting missing, duplicate or substituted required members.
Ordered sequences keep their owning semantics. An identity selector must not
depend on the very mutable leaf it is intended to constrain without also
checking required membership. Authored list indices are not stable observed
identities, especially after canonical sorting.

`unknown` is not proof of a known actual value or permission to change an exact
sibling. Interpret legacy enum sentinels at their owning typed surface, not by
globally matching strings or making every unknown exact. DNS
`DnsResourceRecordSet` already requires `type_code` for `record_type: other`
and forbids it otherwise; a concrete numeric extension identifies an exact
type, while an unresolved variable retains its domain. Reuse its uint16 and
payload checks. A free-text string named `other` is not an enum sentinel.

## Portable contract boundary

The #1067 authority handoff is the incumbent, but its current representation
has material limits:

- `ResolvedRealizationAuthorityModel` permits bounds only in constrained mode;
  `ProvisioningPlanModel` permits one entry per address/concern and one per
  payload pointer. Neither an open entry with hidden bounds nor duplicate
  concern entries is a valid shortcut.
- `materialize_realization_authority` publishes only approved capability/OS
  domains and process-limit bounds. An arbitrary variable domain is not
  automatically publication-safe. `identity_digest` bound lookup currently
  has process-limit semantics in both portable selection and runtime checks.
- Plan reconstruction in `planner.realization_authority._compiled_runtime_view`
  is an independent consumer. Compiler-only leaf metadata disappears at the
  HTTP/plan handoff unless the canonical carrier preserves its meaning.

Extend that carrier only as necessary to express binding leaves plus delegated
remainder and membership. Keep exact values in the existing operation payload;
authority identifies constraints without copying raw values. Reuse
`RealizationAuthorityBound`, `DomainDescriptor`, `scalar_in_domain` and canonical
identities where their semantics fit. Do not publish generic `allowed_values`
or smuggle authoring models into payloads. Both backend selection admission and
returned-value evaluation must consume the same preserved demand; absence of a
diagnostic must not manufacture satisfaction/provenance for missing evidence.
Backend selection must not overwrite the trusted declared payload used as the
comparison reference. Mixed-result provenance must not promote backend choices
to author intent or describe a violated leaf as honoured.

If a case cannot be represented safely, use the existing
`realization.authority-bound-unavailable`/authority-demand diagnostic family,
with a safe concern/path and actionable explanation of the unsupported bound.
Reject before mutation. This is a fallback for unsupported cases, not completion
of #1200: inherited open packages with an exact nmap child must execute, allow
other permitted packages, and reject nmap mutation in the final correction.

Any published shape/meaning change must follow ADR-009/061 and the #1067
handoff: review `contracts/schemas/plans/`, its actual authority consumers,
`contracts/schema-publication-manifest.json` and publication entries, Python
dataclasses and closed contract models, serializers, HTTP DTO conversion,
fixtures and `schema_bundle()` parity. Decide compatibility/versioning
explicitly; old readers must not silently ignore binding constraints. Do not
relax `extra=forbid`, mode/bounds checks, pointer validation or registry-derived
completeness merely to admit a new representation.

## Cross-cutting layers to preserve

Python module names below are relative to `implementations/python/packages`.

| Layer / canonical incumbents | Required boundary behavior |
| --- | --- |
| SDL parse, composition and validation: `raes._base.SDLModel`, `parse_sdl`, `SemanticValidator`, `realization_designation`, instantiation provenance | Keep typed local/cross-model validation, duplicate checks, qualified namespace ownership, RFC 6901 escaping and concrete revalidation. Resolve inherited designation with explicit descendants; do not bypass base validity or confuse an omitted field with an authored default. |
| Semantic projection: `realization_concerns`, `realization_typed_runtime_projection`, `realization_concern_observations` | Validate through existing `TypeAdapter`/owning models before semantic comparison; preserve exclusion of description/evidence/readiness fields. Match typed values/domains, including boolean-versus-integer distinctions. Observation normalization is not new author intent. |
| Plan and apparatus admission: `realization_authority_materialization`, `realization_authority_diagnostics`, `realization_support_diagnostics`, `realization_envelope_diagnostics` | Retain complete canonical authority, legal payload pointers, non-delete resource/address binding, selected manifest/envelope and supported observation posture. Do not silently redefine universal `subsumes` as witness selection; broader quantifier correction belongs to #1201/#1204. |
| HTTP/security: `control_plane_api_guards.RequestSizeLimitMiddleware`, `control_plane_api._auth`, `ControlPlaneSecurityConfig`, `ProvisioningPlanModel`, `control_plane_api_models._provisioning_plan` | Retain bounded request parsing, target/role authentication and lossless DTO conversion. `RuntimeControlPlane` trusted planner-plan digests authorize the exact plan; authentication, request fingerprints and caller-recomputed hashes are not planner attestation. No new auth/config surface is needed. |
| Submission and backend mutation: `control_plane_submission`, `backend_realization_authority`, `raes_contracts.realization_authority.planned_realization_selection_diagnostics`, reference `realization.py`, libvirt `realization/_plan.py` | Enforce preserved demand through both direct and control-plane execution before calling drivers. Keep backend/operator capability, privilege and supply-chain policy independent of author openness. Reuse adapter admission; no per-backend interpretation of SDL or package-name special cases. |
| Returned state and evidence: `backend_calls`, `realization_authority_disclosure`, `realization_runtime_common`, `realization_observation_admission`, observation-binding contracts | Retain snapshot address/transition/shape checks, matching observation identity, scope/strength and manifest corroboration, and applicable operation/envelope binding. Synthetic disclosure demonstrates only the bounded test path. Unknown/missing observations cannot establish an exact fact; no equality claim from an echoed plan. |
| Secrets and environment bindings: `runtime_environment.RuntimeEnvironmentVariable`, `runtime_values.enforce_observed_value_redaction`, concern projections/sanitizers, `raes_contracts.canonical` | Keep `value`/`value_from` exclusivity, reference and classification rules, protected raw-value rejection, presence markers and existing commitments. Compare safe semantic projections. Do not serialize sensitive bounds, hash absence as secret equality, introduce secret argv/env configuration, or add shell/guest execution to classification. Host/backend details stay at existing driver boundaries. |
| Errors, observability and persistence: `Diagnostic`, `ApplyResult`, `backend_calls._sanitize_backend_realization`, `realization_snapshot_sanitization`, `control_plane_api._operation_routes` redacted exception handlers, control-plane audit/receipt and `control_plane_store*` | Use existing failure codes/envelopes and safe concern/path messages, without raw validation inputs, expected/actual values, credentials or arbitrary backend exception text. Preserve sanitization on success and failure before store/API/history, baseline handling and provenance only for admitted claims. Reuse snapshot serialization/reload; no second store, constraint ledger, exception hierarchy or logging channel. |

## Verification guardrails and scope

Reuse `test_sem_218_explicitness.py`, `test_sem_218_runtime_realization.py`,
`test_issue_985_realization_projection.py`,
`test_issue_1067_resolved_realization_authority.py`, #1043 corroboration tests,
realization-honesty conformance and the reference/libvirt admission fixtures.
`complete_test_realization_authority` is a test helper, not evidence that the
compiler preserved the demand. Keep the compiler-produced counterexample
through plan serialization/readmission and `RuntimeManager`/backend result
processing. Retain the direct evaluator exact-mode negative control; it alone
does not establish end-to-end enforcement.

Positive/negative pairs must distinguish constraint rejection from unrelated
admission failure: unchanged db identity versus mutation; permitted open
variation versus exact-leaf mutation; in-domain versus out-of-domain constrained
siblings; missing/duplicate/renamed members versus allowed additions and
reordering; numeric DNS extension versus changed/invalid code; unknown/missing
observation versus valid corroboration; legacy enum sentinels versus literal
strings. Include inherited open plus exact nmap and closed collection controls,
safe committed values and malformed observations, and plan/DTO/store round trips
where the carrier changes. Keep #1099's pass-local explicitness reuse; avoid
rescanning the whole scenario per leaf or enumerating domain Cartesian products.

Workflow incumbents are `.ground-control.yaml`, `.gc/plan-rules.md`,
`noxfile.py`, `tools/nox_support`, `Makefile` and `.pre-commit-config.yaml`.
Use repo policy before/after edits and canonical verification for implementation,
including generated-schema parity if affected. This issue has no formal
requirement: do not fabricate a UID; the existing `--skip-requirement` workflow
supports that case. Accepted ADR pins, source-size rules and release-owned
version/changelog files remain governed.

Non-goals: implementing the broader vocabulary/package-profile redesign,
making all fields required or optional, closing all inventories, changing
abstract-model completeness, adding backend recipes/catalogs, deploying or
testing a live backend, new observation/retention/export obligations, and
rewriting evidence/capture or persistence architecture. #1200 preserves
constraints and makes its required delegated-choice cases executable; existing
selected verification obligations remain honest without becoming universal
experimental collection policy.
