# Issue #1363 — Reusable mixed-control adoption preflight

Scope: ACT-617, API-409 and DSL-142. Inspected 2026-10-15 at HEAD
`f9b10167`, including the working tree. Existing merge conflicts affect schema
publication, materialized SDL and participant relationship/delivery validators;
this note does not resolve them or certify the merged implementation.

This supplements the [#1351 preflight](issue-1351-reusable-mixed-control-preflight.md)
for authoring and portable-contract adoption. [ADR-110](adrs/adr-110-reusable-mixed-control-policies-and-occurrences.md),
[MC-01–MC-09](../../specs/formal/participant-semantics/reusable-mixed-control.md)
and the [migration contract](../migration/reusable-mixed-control.md) already own
the decision. No new ADR or semantic amendment is needed. The integration plan
is recorded on [issue #1363](https://github.com/OpenRAE/rae/issues/1363#issuecomment-6184543185).

## Decisions and boundaries

- ACT-617 owns permissions nested under one behavior specification and one
  controlled participant. API-409 owns immutable applications. RUN-310 owns
  live mediation/history. DSL-142 owns participant-directed delivery. Control
  permission, control acceptance, action admission, execution, effect realization,
  delivery and observation remain separate facts with separate evidence.
- Reuse `raes/participant_mixed_control_policy.py` and
  `participant_mixed_control_vocabulary.py`. Legacy fixed-coordinate declarations
  keep their reader. New forms require the explicit semantic pin and
  `reusable-policy`/`finite-script` discriminator. Finite steps narrow the same
  permission relation; exhaustion is binding. No edge unrolling or scheduler.
- MC-04 retains source-controller authority. Resolve `self` to canonical identity
  before comparison. Only handoff changes controller, with fresh transfer evidence
  and independently valid destination authority. A principal, provider, behavior
  mode, policy label or inject sender cannot grant itself controller authority.
- Reuse `raes_contracts/contracts/participant_control_validation.py` as the
  contextual entry point and `participant_control_occurrence_v2_validation.py`
  as the rev1 fold. `participant_control_occurrence_v2_state.py` owns target
  eligibility/lifecycle. Do not create a second evaluator in processor/runtime.
  Wire shape validation cannot establish a trusted policy, grant or target.

Current adoption is deliberately limited: rev1 SDL compiles, API-409 v2 has a
carrier and contextual reader, but live execution is refused. Preserve all of
`raes_processor/planner/mixed_control_admission.py`,
`raes_runtime/mixed_control_admission.py` and the construction gate in
`control_plane_configuration.py`. Manifest assertions cannot override them.
RUN-310 snapshots, target projection and mediation still use v1 readers; an
API-409 v2 archive is not an executable runtime snapshot. API-424's inject join
also refuses rev1. Publishing or validating v2 does not justify advertising it
in `manifest_authority` capability/support lists.

## Cross-cutting layers the design must pass

Package paths below are relative to `implementations/python/packages/`.

| Layer and canonical incumbents | Required satisfaction |
| --- | --- |
| Source ingress: `raes/parser.py`, `_yaml_loader.py`, `_source_profile.py`, `_mapping_scopes.py` | Keep safe YAML construction, byte/token/graph limits, duplicate and normalized-key ambiguity checks before construction, and source diagnostics. `permitted_transitions` is an authored-ID map; preserve key spelling. Use the existing variable-instantiation pipeline and revalidate its result. A model accepting a dict does not prove source ingress safety. |
| Structural and semantic validation: `SDLModel`, `participant_behavior_specification.py`, `participant_mixed_control_policy.py`, `validator/_mixed_control.py`, `validator/_mixed_control_policy.py` | Keep closed fields, strict bounded integer coordinates, form/kind exclusivity and graph checks. Reuse named/targetable reference indexes and controller-state checks for declared authority, agent operating scope and behavior scope. Reject unresolved or widened authority. Authored evidence references are requirements, not completed receipts. Graph consistency does not establish a live admissible trace. |
| Composition and compiler: `raes/composition/_behavior.py`, `raes_processor/compiler/_mixed_control_policy.py`, `compiler/addresses.py`, `compiler/alias_index.py`, `models/mixed_control_resources.py` | Rewrite external participant/controller/scope/evidence refs using the existing symbol maps; keep state/edge/step refs local. Preserve absent kind-specific fields rather than inserting forbidden empty arrays. Compile deterministic typed children and dependencies, one per edge/step; do not interpret raw `spec` dictionaries as authority. Check expanded canonical addresses against consumer limits after namespacing. |
| Portable occurrence boundary: `ContractModel`, `ParticipantRuntimeBaseEnvelopeModel`, `participant_control_coordinates.py`, `participant_control_occurrence_v2.py`, `raes_contracts/json_ingress.py` | Reuse closed discriminated carriers, shared refs/counts and lineage dispatch. Strict integer rules must hold for Python callers and JSON Schema alike, including boolean/string inputs. At serialized ingress use `parse_bounded_json_object` before duplicate keys disappear, with explicit byte/depth bounds and non-finite rejection. Existing FastAPI intent parsing plus size middleware does **not** establish duplicate-member rejection; retain refusal until any future live rev1 ingress satisfies that boundary. |
| Trusted joins: compiler `occurrence_policy_projection`, contract `ParticipantControlOccurrencePolicyModel`, `ParticipantControlOccurrenceTarget`, `participant_control_validity_bounds` and the common fold | Resolve policy and targets from trusted owners, pinned to participant/episode and exact history. These projections are non-wire inputs, not client authority. Intersect edge, step, source and destination validity windows. Require preceding targets, exact revisions, immutable proposal bindings and accepted eligibility; rejected records never become authorizing targets. Historical checks do not establish current grant validity. |
| Authentication and authorization: `ControlPlaneSecurityConfig`, `control_plane_api/_auth.py`, `ParticipantControlSubjectBinding`, `participant_control_intents.py`, `participant_control_mediation.py` | Any later live path must authenticate and authorize role, target/run and subject before mutation or receipt disclosure, then independently evaluate semantic controller/grant/scope at the commit cut. Clients submit intent, never accepted occurrences or trusted indexes. Preserve sealed route authority, explicit proxy trust and invalid-bearer refusal without proxy fallback. In-process identity construction alone does not authenticate an external caller. |
| Configuration, secrets and host boundary: `ControlPlaneOptions`, `ControlPlaneConfiguration`, `RuntimeEnvironmentVariable`, `enforce_observed_value_redaction`, `SecretReferenceId` | This authoring/contract change requires no new configuration bag, environment binding, credential source, CLI switch, subprocess or socket. References carry logical identities, never credentials or executable selectors. If later realization needs environment bindings, preserve name, classification, provenance and literal/value-from exclusivity validation and redaction; use existing secret-reference shapes. No credential in argv, shell interpolation, authored policy, diagnostics, snapshots or evidence. TLS, proxy stripping, credential loading and worker isolation stay with existing host/backend owners. |
| Errors and visibility: `raes/_errors.py`, `raes_contracts/diagnostics.py`, `AuditEvent`, `control_plane_api/_participant_routes.py`, `_operation_routes.py` | Reuse SDL parse/validation/instantiation errors, typed diagnostics and existing dispositions/reason codes. Preserve coarse 403/409 and redacted 422/500 envelopes and bounded rejection audit. Never expose raw Pydantic input, exception text or payloads through diagnostics/logs. Diagnostic shape is not sanitization. Operational logs, participant disclosure and experiment evidence stay distinct under ADR-066; no new exception hierarchy or logging channel. |
| Persistence and recovery: `RuntimeSnapshot.participant_control_history`, `raes_contracts/participant_control_history.py`, `control_plane_mutation`, `operation_admission_context`, `ControlPlaneStore.commit_control_transition` / `commit_participant_transition` | Future execution must reuse exact heads, snapshot revisions, canonical commitments and actor-bound atomic history/state/receipt/audit commits in every selected store. Keep snapshot round-trip/integrity validation, append-only prefixes, local private-path/SQLite-sidecar/lease checks and existing profile/store admission. No controller side database or lock-only authority. Recovery reconstructs the same episode without blind effect redispatch. These obligations are not met by the present v1-only snapshot reader. |
| Downstream admission: `participant_crossing_boundary.py`, `participant_flow_sink.py`, `participant_control_orchestration.py`, API-424 effect contracts and shared-time owners | Preserve exact-cut crossing/flow and final-sink authorization, causal budgets and retained effect identity. A fresh control occurrence is not necessarily a fresh effect. Order is not a tick; no implicit clock mapping. Existing refusal remains until selected runtime and delivery/effect consumers can join the exact accepted occurrence. Cancellation outcomes require owner evidence, never inference from target kind. |

## Extensibility and compatibility guardrails

The extension seam is already the compiler's policy-to-occurrence projection,
parameterized by `episode_id` and the explicit semantic/policy/form pin. Each
cycle supplies fresh application/proposal/decision identities and exact state,
history, target and order coordinates without changing the authored edge.
Keep state revision, participant-wide append position, proposal revision, policy
revision, wire version, schema hash and store version distinct. Every accepted
application advances state revision once, including same-state transitions;
rejection changes no accepted state/order/script cursor. Never rebase a stale
request or resolve ambiguous order through arrival time or lock order.
Retain the closed `total-effective-order` strategy. Repeated cycles establish
neither liveness nor exactly-once external effects.

An additional target or order strategy belongs in the existing closed vocabulary,
typed contracts and versioned relation, with consumer admission and parity
evidence. Do not add an open metadata map or another policy language. Preserve
consumer bounds from the shared coordinate/ref types (including 1,000,000 counts
and 256-character control refs); reject exhaustion/overflow without wrapping or
truncation. A new episode may select a new policy; live policy replacement inside
an episode remains unsupported.

### DSL-142 delivery boundary

For participant-directed delivery, [MC-09](../../specs/formal/participant-semantics/reusable-mixed-control.md#mc-09--participant-directed-injects)
and [EI-05](../../specs/sdl/external-injects.md#ei-05--optional-participant-composition)
already settle the design. The [#797 preflight](issue-797-dsl-142-participant-inject-delivery-preflight.md)
records the legacy form: its equal-policy-revision, destination-controller and
fixed-order checks must remain confined to that reader. Reuse
`ParticipantInjectDeliveryControl`, `_participant_inject_delivery_control.py`,
the composition rewrite and typed compiled child for rev1. Delivery policy and
control policy retain independent identities/revisions. The control block names
a permitted edge, without actual occurrence coordinates or future receipts.

The following constraints apply across the layers above; they do not authorize
removing the present live-admission refusals:

- **References and merge reconciliation.** Use `DeclarationIndex`,
  `_validate_named_ref` and `_reference_targetability.py` with the proper purpose
  for each individual ref before set comparison: authority scopes use
  `AUTHORITY_SCOPE`, evidence uses `TARGETABLE`. The delivery helper's current
  `_resolved_control_refs` unions unrestricted resolutions; a missing ref can
  disappear beside a valid ref. A nonempty subset therefore proves neither
  completeness nor eligibility. The incoming purpose-specific
  `_verify_mixed_control_state` signature also disagrees with the rev1 caller's
  `targetable_index` argument. Reconcile callers and indexes with both semantic
  forms, rather than just removing merge markers. Retain semantic-only evidence
  refs when they have no runtime address. Required source/result addresses must
  resolve uniquely; `compiler/participant_inject_deliveries.py` currently indexes
  the resolver result with `[0]`, so missing projections need a bounded diagnostic.
  Keep `compiler/time_model.py`'s delivery-subject mapping and dependency closure.
- **Disclosure agreement.** Preserve participant/behavior/boundary ownership,
  result visibility, policy basis, markings and source provenance. In
  `_verify_delivery_observation`, allowed disposition and matching
  visibility/disclosure basis are currently separate existential checks over
  matching rules. They must agree under the same admitted rule or an explicitly
  supported rule-combination semantics; permission from one rule cannot excuse
  a hidden result under another. Source content, administrative views and hidden
  effect details are not disclosed merely because the result is eligible.
- **Exact application and current cut.** Through the trusted non-wire
  `ParticipantControlValidationContext.inject_deliveries` seam, retain the authored
  binding digest and its compiler-resolved association. Do not rewrite hashed
  source objects to equal compiled strings. Resolve the exact accepted control
  identity/revision, participant/episode, edge/policy, source controller, typed
  target/revision, scope, validity and occurrence-specific evidence through the
  existing occurrence evaluator and owner projections. Never use the latest visit
  to an edge, a rejected/future occurrence or a provider-supplied acceptance flag.
  Disclosure-only bindings acquire no control authority. At pending emission,
  independently revalidate audience, disclosure, flow and delivery time through
  `participant_crossing_policy.py`, the crossing boundary and final sink. Legacy
  `_verify_delivery_control_time` compares order with ticks; rev1 must resolve
  clock/domain/segment/tick/microstep and explicit shared-time mappings. Control
  admission cannot freeze disclosure authority or the delivery window.
- **Two uniqueness boundaries.** Existing actor/operation/client-key claims do
  not by themselves consume `(exact control occurrence, participant binding)`.
  Reserve that pair through the authoritative crossing/history/receipt commit
  before emission, retaining immutable binding and policy pins. Another key,
  principal, policy revision or concurrent request cannot obtain a second logical
  delivery from that pair. A lost acknowledgment/crash retains the reservation;
  reconcile uncertain delivery instead of blind re-emission. Authorized exact
  receipt retries reuse the retained result without fresh control/effect work;
  still-pending emission requires current delivery gates. Fan-out uses explicit
  separately admitted participant bindings. No side database, second lock owner
  or new delivery exception/lifecycle hierarchy is justified.
- **World composition and evidence.** Reuse `inject_occurrence_outcome.py`'s
  `validate_inject_occurrence_correlation` to recompute the exact occurrence,
  validated outcome and produced-result join from trusted sources. Constructing
  `InjectOccurrenceCorrelationModel` only checks its reference shape; it does
  not establish applied effects, result provenance, participant delivery or
  observation. Ordinary disclosure may retain source/result identity; API-424
  inject effects require a fresh world occurrence/result. The current
  `participant_control_effects.py::_submit` delivers a view and proves no world
  execution. Use the existing effect owner, originating principal, logical effect
  key, causal budgets and predecessor withholding; delivery retries must never
  redispatch that effect. An applied world effect and accepted control remain
  recorded after delivery failure. Required delivery withholds composed success
  and dependent progress until separately evidenced and revalidated. Reuse
  API-423 attempt/delivered/observed records and the realized-exposure owners;
  evidence requirements, emission, acknowledgment and observation remain distinct.
  `participant_crossing_egress.py` records observed facts for its admitted retrieval
  projection; copying that helper's `delivered=True` path does not establish
  observation of an arbitrary inject or remote transport delivery.
- **Closed extension and publication.** The next seam is a versioned delivery
  application join in the existing owner context, parameterized by exact
  participant/episode, binding/control pins, current cut and optional validated
  world-result correlation. An unscheduled occurrence needs explicit supported
  reader/capability semantics; do not make legacy event/script/story fields
  optional, fabricate anchors or add an opaque metadata/transport registry.
  Preserve independent world/control/disclosure admission. Coordinate any later
  adoption with API-424's closed effect carrier, RUN-319/320 and snapshot readers;
  the existing correlation schema alone does not supply this delivery join.
  At all five embedded SDL schemas, require Python/schema agreement for control
  block versus flat fields, delivery-kind exclusions and complete agreements.
  A focused probe of the current `sdl-authoring-input-v1` definition accepts
  `delivery_kind: disclosure` with a rev1 `control` object, although the Python
  model explicitly refuses it. Existing exclusivity-only parity cases do not
  cover this gap. Published constraints and the existing bundle generator must
  agree; a Python-only validator or a second schema copy is insufficient.

Delivery evidence must distinguish repeated applications `c1`/`c2` of the same
edge, wrong-revision/episode/result substitution, binding-digest mismatch,
same-rule disclosure agreement, unresolved/ineligible refs and unmapped/reset
clocks. Reuse the DSL-142 and `test_issue_1363_*` families for authoring,
composition, post-instantiation validation and all embedded schema verdicts.
Future live adoption additionally needs real crossing/store/final-sink witnesses
for concurrent different-key pair claims, changed-content retries, revocation
between control and emission, failed commit, lost acknowledgment/restart,
effect-applied/delivery-failed withholding and independently evidenced
observation. The #1351/#1353 bounded models are semantic projections, not those
witnesses. No new harness or runtime-conformance claim follows from this note.

Use `raes/mixed_control_migration.py` and the
[finite-script conversion record](../migration/mixed-control-finite-script-conversion.md).
Only a proven trace-preserving explicit conversion is automatic; ambiguous
branches, controller changes, time mappings and delivery-policy conflation
require author decisions. Preserve source/report digests and finite extent.
Never rewrite historical occurrence bytes or replay against the latest policy.
Missing historical context is unverifiable, not a reason to invent evidence.
Store retry keys remain principal/operation/client-key scoped; episode/participant
and policy belong in the request commitment. A changed episode conflicts under
the same key; a new cycle needs a fresh key. Receipt access remains authorized.

## Repository conventions and evidence boundaries

Published schemas under `contracts/schemas/` remain normative under ADR-009/061.
Reuse `raes_contracts/contracts/bundle.py::schema_bundle`, generated-schema parity,
schema coverage and SDL catalog tooling. Account for embedded definitions in
authoring, instantiated scenario/snapshot, materialized scenario and satisfiability
evidence as well as direct occurrence contracts. Preserve runtime-snapshot refusal
unless its own adoption is explicitly delivered. Reuse the split publication index
and per-contract `entries/` records with `last_change` hashes and removal tombstones;
do not introduce a second ledger. Resolve merge conflicts semantically, then
recompute affected hashes. Do not alter accepted ADR pins without ADR-059 procedure.

Reuse `test_issue_1363_*`, `mixed_control_rev1_scenarios.py`,
`mixed_control_v2_support.py`, the #1351 bounded model, legacy ACT-617/API-409/
DSL-142 tests and published fixtures. Required evidence distinguishes source
parsing, model/schema parity, semantic/contextual rejection, imported references,
two cycles through the same edge, finite-script exhaustion and admission refusal.
Conformance carrier validation is not a contextual history check. Runtime
fulfillment additionally needs real episode, store/failure/retry, live-authority,
final-sink and effect witnesses; abstract folds cannot substitute for them.

`.ground-control.yaml`, `.gc/plan-rules.md`, `tools/policy/`, `noxfile.py` and
`tools/nox_support/` own workflow, layering and verification. Set
`RAES_REQUIREMENT_UID` to the requirement under review (`DSL-142` for delivery,
`ACT-617` for authoring, `API-409` for occurrence contracts) on this branch,
which lacks a requirement UID.
Use targeted local checks; full suites stay in CI. No new harness, workflow engine,
version edit or changelog. This preflight changes guidance only; runtime realization,
backend cancellation, new controller kinds, persistence migration and operational
support claims are outside its scope and outside this authoring/contract delivery.


## Historical-record interpretation

The dated #252 and #797 preflights are immutable historical records. Current
#1363 adoption guidance belongs in this note; their classified content digests
remain unchanged. For DSL-142, the dated #797 note records the legacy fixed-coordinate form.
Its equal policy-revision, destination-controller and fixed-order guidance does
not govern `mixed-control-policy-occurrence/rev1`. For that form, use the
[#1363 delivery preflight](issue-1363-reusable-mixed-control-preflight.md#dsl-142-delivery-boundary),
[MC-09](../../specs/formal/participant-semantics/reusable-mixed-control.md#mc-09--participant-directed-injects)
and [EI-05](../../specs/sdl/external-injects.md#ei-05--optional-participant-composition).
Retain the original reader and historical meaning; this notice changes neither.

## API-409 detailed adoption boundary

For reusable-policy adoption, read the historical guidance below through
[ADR-110](adrs/adr-110-reusable-mixed-control-policies-and-occurrences.md),
[MC-01–MC-09](../../specs/formal/participant-semantics/reusable-mixed-control.md)
and the [migration contract](../migration/reusable-mixed-control.md). Those
authorities supersede the earlier fixed-coordinate assumptions and prospective
delivery statements. No new ADR is needed; the implementation plan is recorded on issue #1363.

The working tree already contains the API-409 v2 carrier, contextual reader,
published schema and publication record. Authoring/compilation and archive
validation are the supported boundary. Planning, runtime admission,
control-plane construction and control mediation explicitly refuse rev1 live
execution. `participant_control_history.py`, runtime target projection and
SEM-233 incumbent joins still read v1; API-424's inject resolver also refuses
rev1 delivery bindings. Preserve these gates and `manifest_authority.py`
support restrictions until each selected consumer has its own adoption
evidence. A wire version of `2.0.0` is not executable support or the independent
`mixed-control-policy-occurrence/rev1` semantic pin.

Package paths in this amendment are relative to
`implementations/python/packages/`.

- Reuse `raes_contracts/contracts/participant_control_occurrence_v2.py`, the
  unchanged `ParticipantRuntimeBaseEnvelopeModel`, shared control coordinates
  and `raes/participant_mixed_control_vocabulary.py`. Preserve closed accepted
  variants and the separate rejected-attempt shape. Attempted coordinates must
  not be replaced with observed state or acquire valid-application assertions.
  Rejection may append history but advances no accepted state, order or script
  cursor. Direction targets proposal/action/control; intervention targets
  action/control/attempt. Proposal identities never identify policy edges.
  Every accepted kind, including denial and same-state transitions, advances
  state revision exactly once. `ContractModel` closure does not freeze models
  or nested lists: detach and revalidate owner inputs and retain canonical
  snapshot serialization/integrity checks, without globally tightening the base.
- Keep `raes_contracts/contracts/participant_control_validation.py` as the contextual entry
  point. Its v2 path checks complete participant-wide prefixes, event identity,
  per-episode lineage/pins and cross-episode handoff-evidence reuse before or
  around the shared fold. Do not expose
  `fold_participant_control_episode_v2()` as a replacement archive validator:
  it does not perform all those surrounding checks. Retain rejection records
  in prefixes. `participant_control_history_verifiability()` reports context
  availability, not semantic validity or permission to advance state.
- Trusted policy/target projections in
  `raes_contracts/contracts/participant_control_occurrence_v2_policy.py` are non-wire inputs.
  `available_at` establishes preceding existence, not external action/attempt
  lifecycle eligibility. The current target-authorization helper checks
  lifecycles produced by its fold; it does not independently establish those
  external lifecycles. Compiler-projected authority status is not a live grant
  lookup. Rejected-record validation checks the observed state and limited
  consistency, not independent proof of every rejection reason. Any future
  live adapter must resolve episode status, grants/revocation, evidence,
  target eligibility and time from their owners at the same fenced commit cut.
  Neither caller-supplied indexes nor a successful archive fold supplies that
  authority. Preserve runtime refusal until those joins exist.
- Preserve source-controller authority, handoff-only controller changes and
  independently valid destination authority. Approval/denial resolve one live
  proposal revision; competing decisions stay explicit rejected/conflicting
  historical facts rather than a second acceptance.
  Historical reference, current authorizing eligibility and accepted-state
  advancement use the separate predicates in
  `raes_contracts/contracts/participant_control_occurrence_v2_state.py`. Accepted denial
  advances control state but authorizes no action. Control acceptance, action
  admission, execution, cancellation outcome, delivery and observation retain
  their separate owners and evidence.

The repository boundaries beyond these models remain binding:

| Layer and canonical incumbent | Required guardrail |
| --- | --- |
| SDL ingress/composition: `raes/parser.py`, `_yaml_loader.py`, `_source_profile.py`, `_mapping_scopes.py`, `validator/_mixed_control_policy.py`, `composition/_behavior.py` | Preserve safe YAML, duplicate/normalized-key checks and resource limits before construction. Revalidate instantiated/imported models, rewrite external refs through existing symbol maps and retain local edge/step identities. Check expanded canonical addresses against consumer bounds. |
| Serialized contracts: `raes_contracts/json_ingress.py`, `ContractModel`, `participant_control_coordinates.py`, lineage parser and public contextual validator | Reject duplicate JSON members before conversion to a mapping; set byte/depth bounds and reject non-finite numbers. Apply strict integer/ref limits to Python and schema readers alike. Existing HTTP body-size limits and FastAPI DTO parsing do not establish duplicate-member rejection. Do not reuse the legacy intent DTO as proof of rev1 scalar validation. |
| Auth/configuration: `ControlPlaneSecurityConfig`, `control_plane_api/_auth.py`, `ParticipantControlSubjectBinding`, `ControlPlaneOptions`/`ControlPlaneConfiguration` | Preserve sealed administrative route authority, immutable validated principal maps, role/target/run and subject binding, then independently check semantic controller authority. Principal actor/scope strings must fit `OperationAdmissionContext`; subject-binding participant addresses cannot contain `:` even though a generic control ref can. Keep canonical addresses; do not encode authority in arbitrary strings or add a configuration bag. |
| Secrets/environment/host: `SecretReferenceId`, `raes/runtime_environment.py::RuntimeEnvironmentVariable`, `runtime_values.py::enforce_observed_value_redaction` | This change needs no secret loader, environment binding, socket or subprocess. Refs are logical identities, never executable selectors or credentials. Any later binding retains name, provenance/classification and literal/value-from exclusivity checks; no credentials or rejected payload in argv, shell interpolation, diagnostics or artifacts. Host TLS/proxy stripping and worker isolation stay with their owners. |
| Errors/observability: `raes/_errors.py`, `raes_contracts/diagnostics.py`, `AuditEvent`, `control_plane_api/_participant_routes.py`, `_operation_routes.py`, `control_plane_api_guards.py` | Reuse existing errors, typed reasons and bounded rejection audits. Preserve coarse 403/409, redacted 422/500 and `no-store` responses, including retries. Diagnostic shape does not sanitize values. Never serialize raw validation input, exception text or model representations. Keep operational logs, participant disclosure and experiment evidence separate under ADR-066. |
| Persistence/recovery: `RuntimeSnapshot.participant_control_history`, `control_plane_mutation.py`, `control_plane_operation_context.py::operation_admission_context`, `ControlPlaneStore.commit_control_transition`/`commit_participant_transition`, store profile/path/lease checks | Reuse exact heads, snapshot CAS, canonical request commitments and atomic state/history/receipt/actor-bound audit commits in every selected store. Current snapshot readers remain v1-only. No metadata authority, controller database or lock-only ordering. Preserve private local-store/SQLite-sidecar permissions, ownership/link checks, worker admission and recovery without blind effect redispatch. |

The extension seam is `raes_processor/compiler/_mixed_control_policy.py::occurrence_policy_projection`,
parameterized by episode and explicit policy/form/semantic pin, composed with
owner-supplied exact-cut targets. Repeated cycles supply fresh occurrence,
proposal and decision identities without editing or unrolling an edge.
Keep state revision, append position, proposal revision, policy revision, schema
hash and store version separate. Retain closed `total-effective-order`; order
is not time. A future target/order variation belongs in the existing versioned
vocabulary and typed owner join, with consumer admission, not an open map or
another evaluator. DSL-142 pins disclosure policy independently and binds one
exact accepted application; API-423/424 and final-sink authorization remain
independent gates.

Retain store-scoped `(principal, operation kind, client key)` retry identity.
Participant/episode/policy belong in the request commitment; changing episode
under the same key conflicts. An authorized exact retry returns the retained
receipt, while a new cycle needs fresh operation identity. Neither permits
effect redispatch or resets causal budgets. Reject coordinate overflow and
reference exhaustion before commit; never wrap, truncate or silently rebase.

Published schemas remain normative. Reuse `schema_bundle()`,
`tools/generate_contract_schemas.py`, generated/schema-coverage/catalog checks
and the existing split publication index, per-contract `entries/` hashes and
removal tombstones. Include embedded authoring, instantiated scenario/snapshot,
materialized scenario and satisfiability definitions when affected. Preserve
legacy readers and bytes; ambiguous conversion requires author decisions via
`raes/mixed_control_migration.py`, and missing historical context is explicitly
unverifiable. Conformance's v2 registry entry performs model validation, not
the contextual history join.

Reuse `test_issue_1363_occurrence_v2_contract.py`,
`test_issue_1363_occurrence_v2_context.py`, `test_issue_1363_schema_parity.py`,
their existing support fixtures, legacy API-409/ACT-617/DSL-142 cases and the
#1351 bounded model. Carrier/schema parity and abstract cycles cannot establish
live authorization, durable atomicity, delivery or exactly-once external effects.
Use `.ground-control.yaml`, `.gc/plan-rules.md`, `tools/policy/` and
`tools/nox_support/` for workflow; set `RAES_REQUIREMENT_UID=API-409` for this
requirement and run targeted local checks only. The current merge conflicts
include publication records, materialized SDL and participant validators;
resolve them semantically before claiming a coherent implementation baseline.

This amendment adds guidance only. New DTO bases, schemas for trusted indexes,
policy languages, validator/error hierarchies, stores, log channels and workflow
engines are unnecessary. Runtime adoption, backend cancellation, new controller
kinds, persistence migration, live policy replacement and operational support
claims remain outside this authoring/portable-contract delivery.
