# Issue #1072 — API-409 control-effect binding preflight

Date: 2026-09-20. Inspection baseline: `3fa5187724f21c54196a3259f7b46b2eb1d2db4f`.
Scope: API-409's incumbent control facts within API-424 publication; no
implementation or implementation sequencing.

## Authority and existing delivery

[ADR-108](adrs/adr-108-modular-participant-control-and-governed-effects.md),
[PC-01–PC-15](../research/modular-participant-control/composition.md), accepted
at `ebb70a34b8e7d1cc8964c443841ae57e12ed1014`, and the published
[SEM-235/MPC-01–15](../../specs/formal/participant-semantics/modular-participant-control.md)
settle the design. No new ADR is necessary. #1070's semantic publication is
present locally; downstream consumption still needs exact released artifacts,
not just a UID, local file or DRAFT status.

Read this alongside the existing [API-424 preflight](issue-1072-api-424-provider-contracts-preflight.md)
and [API-407 preflight](issue-1072-api-407-feature-support-preflight.md).
This note closes the occurrence-to-effect binding gap. The historical
[#252 preflight](issue-252-api-409-participant-intervention-contracts-preflight.md)
predates delivered API-409, API-423 and RUN-310 code; its future-tense delivery
statements and pre-rename package/invariant names are not current instructions.

`participant-control-occurrence-v1` already publishes eight closed variants:
proposal, approval, denial, external direction, intervention, handoff, override
and cancellation. Reuse its unchanged `ParticipantRuntimeBaseEnvelopeModel`,
ACT-617 declaration coordinates and owning contextual validator. #1072 adds
closed provider-result/effect bindings to these facts, not another occurrence
family or a reimplementation of API-409.

## Binding decisions and limits exposed by the incumbents

Package paths below are relative to `implementations/python/packages/`.

- `raes_contracts/contracts/participant_control.py` owns occurrence kinds,
  dispositions, proposal/decision revisions and typed targets.
  `ParticipantControlDisposition` is **recorded, accepted, rejected, limited,
  superseded, cancelled**. Do not expand it with provider resolution statuses,
  composition conflict, capability strength or applied realization. An
  accepted approval is still not action admission or execution.
- `participant_control_validation.py::validate_participant_control_occurrence_context`
  owns declaration agreement, identity reuse, proposal revision/order,
  transformation lineage and typed target joins. Compose it with
  `participant_crossing_validation.py` and the trusted resolver entry point
  in `participant_flow_control_validation.py`. API-424 adds only the missing
  modular joins. A wire-supplied declaration/index cannot authenticate itself.
- The declaration join requires `actor_ref == controller_ref`; the runtime
  constructs both from compiled controller authority. Mechanism instance,
  producer, authenticated principal and controller are distinct identities.
  Bind the requesting mechanism and rule in API-424; do not replace the
  occurrence actor with a provider id or let a provider mint controller refs.
- Rejected occurrences still require declaration agreement but deliberately
  skip target validation and target registration. Their presence is valid
  rejection evidence, never a usable approval, fulfilled predecessor or
  realized effect. Non-rejected target resolution alone also does not prove
  acceptance, current authority, completion or present-cut validity.
- The validator's target index admits one revision/scope per `(kind, ref)`;
  it is not a temporal history resolver. Identical event replay is accepted
  there, while `raes_contracts/participant_control_history.py` forbids duplicate
  stored event ids, requires contiguous occurrence revisions and preserves
  the append-only prefix. Preserve these different contracts. Occurrence
  revision, controller-state revision, proposal revision, effective order,
  history head and transport idempotency key are not interchangeable.
- Handoff shape advances state revision by one and the contextual check
  matches prior state. Those checks do not resolve resulting controller
  authority or authenticate completion evidence. Override target resolution
  does not by itself validate the replacement. Cancellation's declared
  effect does not prove a backend was stopped. Trusted owner evidence must
  establish each claimed outcome, scope, cut and causal predecessor.
- `participant_flow_control_incumbent_validation.py::_validate_control_binding`
  already joins event, kind/revision, participant/episode, controller,
  authority, policy revision, kind-specific identity, related refs and
  predecessors. Reuse that mapping for SEM-233 bindings; do not copy a second
  kind switch into each provider. It is a coordinate check, not a full
  occurrence fingerprint or fulfillment predicate: disposition, target/state
  details and actual effect evidence still need their owning validation.

MPC-03 requires exact run/apparatus, participant/episode, crossing/direction,
sink/audience/destination, controller/authority, policy revision, state cut,
expected history heads, inputs/provider state, memory, clock/order and trigger
bindings. Missing applicable coordinates are not wildcards. Every contributor
retains exact profile, mechanism, implementation/protocol, configuration digest,
evidence and limitations. Declarations, installed support, effective support,
requests and observed realization remain separate claims.

## Effect ownership and the extension seam

| Requested effect | Required binding and boundary |
| --- | --- |
| Review | A closed API-424 obligation binds the withheld parent, exact proposal revision, supervisory authority, approval/denial refs and governed expiry/resumption. API-409 approval/denial facts do not themselves represent the outstanding obligation. Approval satisfies only that obligation; resumption reevaluates every gate at a fresh cut. |
| Direction, intervention, handoff, override, cancellation | Bind the appropriate API-409 variant and ACT-617 transition, exact target and revision, scope and authority. RUN-310 owns mediation and realized transitions. A handoff preserves participant identity and influence; cancellation cannot erase prior execution. |
| Transform, mask, route | Preserve API-423 derivation/projection/destination authority and API-409 trusted-edit lineage where applicable. Use a fresh candidate/proposal and new admission; source approval, admission and idempotency cannot transfer. Route is not controller handoff; masking is not declassification. |
| Inject | Preserve DSL-111 occurrence, DSL-142 addressee/delivery and API-423 disclosure. Bind API-409 only for directions/control changes. IFC-triggered content retains both source and trigger influence; scheduling is not delivery or observation. |
| Delay, interrupt, shutdown | Publish the missing closed request bindings, using API-421/RUN-308 time and RUN-310 lifecycle owners. Explicitly distinguish participant, episode, execution scope and run targets; do not turn `ParticipantControlTargetKind` into a universal enum. Pause, cancel, interrupt and terminate are distinct; no PID/native handle or process signal is portable authority. |
| Audit, permit, deny, withhold | Reuse existing evidence/audit and API-423 disposition/projection owners. A denied parent may cause a separately authorized audit/review only under its admitted rule; there is no new output channel. |

The seam is a closed typed request binding parameterized by owner/target,
rule/revision, authority, exact context, causal root/predecessors, phase and
bounded parameters/artifact references. An operator-bound provider protocol
belongs in `raes_backend_protocols`; plain data/shared validation stay in
`raes_contracts`. A second implementation of the same profile changes admitted
implementation/configuration/evidence bindings, not profile meaning or API-409
history. New effect meanings require governed closed variants/revisions, not
callbacks or open `effects`, `policy`, `taint`, `labels`, `context`, `plugin`
or mechanism-metadata maps.

Retain MPC-07/10–12: incompatible targets/replacements conflict; provider order
is not precedence. Required predecessor effects withhold the parent; subsequent
effects have separate outcomes. Logical effect identity is `(run, trigger root,
rule id/revision, slot, admitted firing epoch)`, independent of retries/cuts.
Same key/different canonical intent conflicts. Attempts preserve the allocated
identity, causal budgets and expiry across handoff/reset/restart. Uncertain
external dispatch stays indeterminate until exact owner evidence resolves it.

## Cross-cutting gates to reuse

These are contract obligations and downstream integration constraints, not
claims that #1072 implements runtime enforcement.

| Layer | Canonical incumbent and required satisfaction |
| --- | --- |
| Bytes and shape | `raes_contracts/json_ingress.py::parse_bounded_json_object`, bounded reads/byte/depth limits, `ContractModel`, shared scalar/schema constraints and discriminated variants. Reject duplicate keys and unknown fields; check finite numbers even for overflow such as `1e999` and direct Python inputs. Closure is not strict typing, bounded size, redaction or deep immutability. Detach and freeze nested provider inputs without globally tightening existing carriers. |
| Semantic joins and conformance | The API-409/API-423/SEM-233 validators above, `contracts/schema_invariants.py` and `x-raes-invariants`, with `raes_conformance/conformance/validators.py`. API-409's current registry entry invokes model validation, not the multi-record declaration join; do not report it as contextual evidence. Trusted resolution must establish applicable cuts, evidence, authority and owner outcomes; schema-valid dishonest claims remain contextual failures. |
| Configuration, artifacts and support | `participant_configuration.py`, `contracts/experiment_bindings.py` owner/type/normalization checks, `_canonical.py`/`satisfiability.py` digests, `participant_flow_policy_profiles.py` exact safe revision/digest loading and packaged `corpus.py`. Use `manifest_authority.py`, `contracts/feature_support.py`, `participant_manifests.py` and `raes_backend_protocols/participant_feature_admission.py`; importability, method presence or manifest text is not realized support. No caller-selected paths, latest fallback or executable selectors. Canonicalize set-valued arrays before hashing; a digest establishes neither trust nor disclosure permission. |
| Authentication and live authorization | Later adapters retain `ControlPlaneSecurityConfig.strict_defaults()`, `control_plane_api/_auth.py`, role/target bindings and `RequestSizeLimitMiddleware`. `participant_control_mediation.py` resolves compiled transitions through `ControlPlaneIdentity.participant_control_subjects`; the caller-intent DTO in `participant_control_intents.py` is deliberately not the runtime-owned occurrence. Preserve that trust split. Independently conjoin `participant_binding.py` action admission, crossing/projection and `participant_flow_sink.py` final-sink gates; provider permit or supervisory approval cannot bypass them. |
| Secrets, environment and host | Safe bounded refs only: no prompt, credential, private state, raw rejected payload, native handle or external-apparatus detail. Evidence existence, reason and timing also require audience projection. No new environment bag or executable loading is needed. Later environment consumers retain `raes/runtime_environment.py::RuntimeEnvironmentVariable` name/source/exclusivity checks and `runtime_values.py::enforce_observed_value_redaction`. No payload/secret in argv, shell interpolation, filenames or stdout/stderr; installation and host isolation remain operator/backend responsibilities. |
| Errors and observability | Reuse `raes_contracts/diagnostics.py`, existing dispositions/receipts, `backend_result_diagnostics.py`, coarse `_participant_routes.py`/`_responses.py` errors and `_operation_routes.py` redacted 422/500 handlers and rejection auditing. `portable_diagnostic_payload` validates shape; it does not redact. Sanitize messages and addresses before serialization; never expose raw `ValidationError`, provider exception text, unknown keys or model reprs. Conformance uses its own sanitizer without reverse imports. Retain SEM-224 planes and SEM-220/226/230 audience projection; add no exception tree, logger or audit channel. |
| Persistence and dispatch | `RuntimeSnapshot.participant_control_history`, `participant_control_history.py`, `ControlPlaneStore`/`AtomicControlPlaneStore`, `commit_control_transition`, both memory/local stores, receipts and `AuditEvent` are the incumbents. No snapshot metadata authority or separate trigger/history store. RUN-320 owns modular atomic state/intent/budget commits, invocation fencing and recovery. A local commit, accepted occurrence or shape-valid receipt proves neither external success nor exactly-once effects. |
| Publication, packages and workflow | Follow `contracts/README.md`, ADR-009/061, normative `contracts/schemas`, v2 publication index/per-contract entries and removal tombstones; keep `schema_bundle()` parity and explicit `tools/generate_contract_schemas.py` routing (default is control-plane). Preserve exports, installed corpus packaging in `implementations/python/pyproject.toml`, manifest allowlists, concept placement, invariant/observability annotations and lineage. Respect `tools/policy/adr_policy.yaml` dependency directions. `.ground-control.yaml`, `.gc/plan-rules.md`, `noxfile.py`, `tools/nox_support/`, schema-publication/generated-schema, authority/concept and lineage checks remain the workflow. |

Use `RAES_REQUIREMENT_UID=API-409` for this requirement-specific preflight;
#1072 implementation belongs to API-424's `modular-control-contracts` phase in
`tools/policy/requirement_order.yaml`. API-409's earlier delivery phase does not
waive #1070 or authorize implementation under the semantic-publication phase.
Keep DOCUMENTS versus IMPLEMENTS/TESTS traceability honest; no implementation
delivery or lineage derivation claim follows from this note.

## Acceptance evidence and exclusions

Reuse API-409 model/schema/fixture tests in
`implementations/python/tests/test_api_409_participant_control_occurrences.py`,
API-423 crossing tests, `test_sem_233_flow_control_contracts.py`, and
`test_run_310_supervisory_lifecycle.py` patterns. Contract acceptance needs
multi-mechanism and IFC-triggered-inject examples plus counterexamples for
forged controllers/evidence, rejected occurrence as fulfillment, wrong target
revision/cut, handoff with unresolved completion, stale approval after transform,
expired review, incompatible effects, unsupported lifecycle scope, authorized
downgrade versus dishonest support, replay/content conflict and secret-bearing
errors. Separate schema-invalid fixtures from valid shapes rejected by trusted
context, and exercise installed-package imports/resources. Bounded fixtures
prove neither backend realization nor noninterference/bisimulation.

Non-goals: no executable plugin loading, concrete provider selection, runtime
effect execution, new endpoint, controller state machine, persistence migration,
validation framework, exception hierarchy or workflow runner. Do not broaden
the common envelope or clone occurrence, action, crossing, evidence or audit
schemas. No generic intervention substitutes for review, delay or shutdown;
no advisory result grants authority; no transformation, handoff or cancellation
erases history/influence. Runtime delivery remains #1069/RUN-320; reusable
assurance remains #1071/ASR-538.
