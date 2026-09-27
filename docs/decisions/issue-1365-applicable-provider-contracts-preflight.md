# Issue #1365 — Applicable-provider contract preflight

Date: 2026-09-27. Scope: guidance for API-424 contract publication, not an
implementation plan or a claim of runtime adoption. The issue is the delivery
contract; [ADR-111](adrs/adr-111-control-applicability-and-effect-decisions.md),
[CA-01–CA-09](../../specs/formal/participant-semantics/control-applicability-and-evaluation.md),
and the [migration contract](../migration/control-applicability-and-evaluation.md)
fix its meaning. The [original API-424 preflight](issue-1072-api-424-provider-contracts-preflight.md)
and [#1352 preflight](issue-1352-control-applicability-preflight.md) already
identify the broader boundaries; no new ADR or semantic algebra is needed.

## Contract decisions and observed gaps

Package paths below are relative to `implementations/python/packages/`.

| Existing contract | Required revised boundary |
| --- | --- |
| `raes_contracts/contracts/participant_control_selection.py` and `participant_control_composition.py::ParticipantControlRequestModel` | Retain the complete admitted B, its digest, profile obligations, instance/configuration/authority/provenance and finite bounds. Represent exact-cut coverage separately: applies with complete slot and support mapping, profile-owned proven inapplicable with evidence, or unresolved. Derive A(B,K) as references into B, including required input closure. The current request requires every binding to match K; filtering B or treating profile presence as coverage changes the wrong identity. Valid empty A requires total obligation accounting and all incumbent gates. |
| `raes_backend_protocols/protocols.py::ParticipantControlProvider.resolve`, `raes_contracts/contracts/participant_control_results.py`, and `raes_runtime/participant_control_orchestration.py::_mechanism_results` | A provider/v1 call receives one common request per instance, so it cannot establish A.fact → B.assessment → A.rule. Publish a separately negotiated slot/stage-aware protocol input carrying requested slots, exact invocation identity, detached typed predecessor results or content-bound refs, authorized projection and pinned committed/tentative shared-state inputs. Bind each output to that invocation and its complete input identity. Missing or invalid mandatory inputs block; explicit evaluated false trigger is distinct from absent effect. No ambient result lookup or provider-supplied authority index. |
| `participant_control_results.py::ControlEffectiveSupportModel`, `raes_backend_protocols/participant_control_admission.py`, and `participant_control_composition.py::_support_blockers` | Admit required strength, coverage, constraints and evidence per obligation/input. Resolve against API-407's incumbent feature support and exact installed binding at K. Current all-exact, all-instance blocker is wrong for supported bounded requirements and optional loss. Required-input closure M fixes availability; advisory content does not itself veto. Incomplete/invalid mandatory results block with their reason. Normalize only a rejected optional contribution at its invocation boundary, discard its state/effects and retain safe lost-advice evidence; role comes from B/M, never the response. A malformed apparatus or unresolved required coverage cannot become optional failure. |
| `participant_control_effects.py`, `participant_control_effect_composition.py`, `participant_control_composition.py::admitted_effect_phase` | Publish unscheduled parent permit/deny/withhold separately from executable typed effects. Parent denial/withhold is invariant across legacy-shaped phases. Each effect retains its own target/owner, origin, phase, exact prerequisite event/outcome and allowed parent dispositions; independently admitted audit may follow denial. A required predecessor withholds until its exact owner outcome and fresh reevaluation. A later consequence waits for its declared parent admission/application event, never just an intent or accepted receipt. Check the combined parent/effect graph and target conflicts, not merely the slot DAG or one global phase. |
| `participant_control_coordinates.py::ControlProviderStateModel` and `participant_control_results.py::next_provider_state` | Pin state scope and version separately from participant memory and profile identity. Declare sharing/writers and whether a speculative update commits on evaluation or only on parent release. Multiple writers need an explicit tentative-state chain or conflict. State, complete decision/coverage/results, accepted effect intents/claims and consumed budgets join one expected-head transaction; a failed commit publishes none. Do not expose private state through predecessor inputs. |

Keep declaration, installed capability, effective support, composition eligibility,
committed intent, owner outcome and observed realization distinct. `ControlDecisionModel`,
the closed `ControlEffectTarget` alternatives, API-409/API-423 crossing and
control carriers, and SEM-233's exact security relation remain their owners;
do not create a universal target, state, decision or operation DTO. The finite
[#1352 cases](../research/control-applicability/cases.md) are semantic witnesses,
not live protocol or store evidence.

## Whole-repository gates

| Layer and canonical incumbents | Contract publication guardrail |
| --- | --- |
| Portable ingress and shape: `raes_contracts/json_ingress.py::parse_bounded_json_object`, `contracts/base.py`, `participant_control_coordinates.py`, `parse_participant_control_evaluation` | Bound artifact bytes, JSON depth, graph nodes/edges, stages, predecessor material, result count and provider iteration. Reject duplicate members, non-finite numbers, coercion, unknown variants, duplicate IDs and cycles on JSON and direct Python ingress. Frozen `ContractModel` wrappers are not deeply immutable; detach nested inputs and revalidate returned portable projections. Structural validity never proves trusted coverage. |
| Artifact/configuration and authority: `raes_contracts/contracts/participant_control_profiles.py`, `raes_contracts/participant_flow_policy_profiles.py`, `raes_contracts/corpus.py`, `raes_contracts/participant_configuration.py`, `contracts/experiment_bindings.py`, `participant_control_resolution.py::validate_participant_control_resolved_context` | Resolve exact revision/digest and configuration owner; use trusted non-wire indexes for profile obligations, applicability, predecessor contents, support, disclosure, state scope, receipts and current K. Reuse `_canonical.py`/`control_digest` with defined hashed projections and canonical set-array order. No latest fallback, caller-selected search root or digest-as-permission rule. |
| Auth and effect policy: `raes_runtime/control_plane_api/_auth.py`, `ControlPlaneSecurityConfig.strict_defaults()`, `control_plane_api_guards.py::RequestSizeLimitMiddleware`, `participant_effect_authority.py`, `participant_control_receipts.py` | This publication adds no route. A consumer still verifies bearer/proxy identity, actor/role/target/audience, incumbent action/crossing/projection/final-sink gates and each effect owner's current policy. An effect acts for its originating principal; a drain caller is separately authorized before reading committed state. Provider references grant no authority. |
| Secrets, environment and host: `raes_contracts/secret_references.py`, `raes/runtime_environment.py::RuntimeEnvironmentVariable`, `runtime_values.py::enforce_observed_value_redaction` | Portable predecessor, state and evidence data contain only disclosure-authorized bounded values/refs, never credentials, raw prompts, private provider memory or rejected payloads. Any downstream env binding keeps name and `value`/`value_from` shape checks, source classification and redaction. The contract adds no launcher; backend-owned host/process/network protection remains separate. Never put sensitive material in argv, shell text, environment, temporary names or stdout/stderr. |
| Errors and observation: `raes_contracts/diagnostics.py`, `raes_runtime/backend_result_diagnostics.py`, `participant_control_diagnostics.py`, `control_plane_api/_responses.py`, `_operation_routes.py`, `control_plane_audit.py`, `raes/observability_plane_semantics.py` | Use value-independent bounded reasons and existing receipt/audit envelopes. Sanitize provider errors, validation paths and references before constructing diagnostics; `portable_diagnostic_payload` validates shape, not redaction. Apply plane classification and participant/audience projection to coverage, dependencies, denial, review existence and timing. No new exception hierarchy, logger or audit channel. |
| Persistence and recovery: `raes_contracts/participant_control_evaluation_history.py`, `raes_runtime/participant_control_causal_state.py`, `participant_control_records.py`, `participant_control_receipts.py`, `control_plane_store_record_migration.py`, memory/local `ControlPlaneStore` implementations | The new wire meaning must remain representable at the existing expected-head store boundary. Historical evaluation validation, folds and effect admission must select the recorded interpretation; a new reducer cannot rewrite old claims, budgets, receipts or pending work. No second state store, snapshot metadata shortcut or implied exactly-once external execution. Runtime/store adoption is a separate delivery gate. |

`raes_backend_protocols` imports neutral `raes_contracts` DTOs only. Keep the
package boundary in `tools/policy/adr_policy.yaml` and
`tools/policy/repo_policy.py::_check_backend_protocol_contract_annotations`;
do not import runtime, concrete backend or conformance sanitizers into the
public protocol. Shared structural/composition rules belong in
`raes_contracts/contracts/participant_control_*`; independently trusted joins
belong in `participant_control_resolution.py`. Runtime routes, stores and
conformance must consume those decisions rather than replicate them.

## Publication, evolution and evidence boundary

The selection/evaluation schemas are draft in
`contracts/schemas/participant-runtime/`; ADR-061 permits a recorded draft edit,
but old and amended meanings still need explicit interpretation and exact
schema-content negotiation. A changed provider invocation cannot silently
remain `participant-control-provider/v1`. Keep its original reader/adapter only
for an independently verified dependency-free fragment; a `resolve` method
check does not establish revised support. Stable breaking changes require a
new contract ID. Historical records with no reliable interpretation pin keep
the legacy interpretation or an explicit unsupported/unverifiable disposition,
never inferred new coverage or executable effects.

Publish each chosen revision coherently through normative schemas; matching
`raes_contracts/contracts/bundle_runtime.py` and exports; explicit
`tools/generate_contract_schemas.py` routing (otherwise it defaults to
`control-plane`); `contracts/schema-publication/entries/` hashes and
`last_change` under manifest v2; `manifest_authority.py` and API-407
capability admission; `schema_invariants.py` and `x-raes-invariants` for
non-schema joins; `raes_conformance/conformance/validators.py`; packaged corpus
in `implementations/python/pyproject.toml`; and public/migration docs. Reuse
`tools/check_generated_schemas.py`, `check_schema_publication.py`, authority,
concept and lineage checks. A schema-only pass is not trusted-context validation.

Keep `docs/explain/reference/modular-participant-control-contracts.md` and
`docs/public/participant-control.md` claim language scoped to the interpretation
their cited code actually implements. The retained v36/v37 formal-semantic and
specification-coverage bundles and the #1352 finite model do not establish
revised provider invocation, runtime adoption or backend realization. Follow
the existing `test_api_424_*` split for structural, trusted-context,
composition, publication and governance evidence, then use the RUN-320
memory/local-store fixtures for versioned replay and zero-dispatch claims when
those consumers adopt the revision. Keep ownership and traceability aligned
with `tools/policy/requirement_order.yaml` and
`docs/governance/requirement-scopes/1072.json`.

The essential paired examples are disjoint sinks under one B; an applicable
obligation with no slots versus proven inapplicability; A → B → A with exact
predecessor binding; optional malformed/unsupported advice versus required
input loss; false trigger versus missing result; bounded support against an
admitted requirement; denial/withhold in every phase; independently authorized
audit on denial; a later consequence awaiting actual parent application;
combined phase cycle; conflicting shared-state writers/failed commit; and
old/new history replay. Distinguish schema-invalid from structurally valid but
context-invalid fixtures, and do not promote finite-model evidence into a live
provider, backend or durability claim.

The extension seam is the admitted obligation relation plus exact-cut
invocation/dependency, state-scope, support-constraint and typed prerequisite
bindings. Another sink or independently installed provider can use those
coordinates without editing the canonical algebra or adding backend-name
branches. New domain/effect meaning still requires governed closed publication.

Non-goals for #1365: runtime scheduler, provider installation, effect dispatch,
store migration, HTTP endpoint, plugin host, policy interpreter, backend
instrumentation or parity, new credential/config framework, and historical
reinterpretation. `.ground-control.yaml`, `.gc/plan-rules.md`,
`tools/policy/requirement_order.yaml`, `noxfile.py`, `tools/nox_support/` and CI
remain workflow owners. Local verification stays targeted; CI owns full suites.
