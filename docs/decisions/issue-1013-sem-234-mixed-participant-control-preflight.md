# Issue #1013 — Mixed participant-control semantics preflight

Date: 2026-09-17

Scope: SEM-234 semantic publication, composing SEM-230, SCE-002, API-423,
RUN-310, and their existing dependencies. SCE-002, API-423, and RUN-310
are incumbent authorities, not permission to reopen their
implementations or broaden their published carriers.

This is supplementary architecture guidance, not a semantic implementation or
implementation plan. [ADR-102](adrs/adr-102-mixed-cross-backend-participant-control.md)
and the [#813 preflight](issue-813-cross-backend-participant-control-preflight.md)
already decide the architecture; no new ADR is needed. At preflight,
`specs/formal/participant-semantics/cross-backend-participant-control.md` is
recorded as DRAFT. Its existence and #813's structural tests do not establish
published semantics, mixed runtime support, or backend realization.

## Binding progressive-specification clarification

The maintainer explicitly requires alignment with #1198's correction and
accepted [ADR-105](adrs/adr-105-recursive-partial-description-semantics.md).
References below to closed shapes/vocabularies govern authority, operational
dispositions and interpreted exchanged data, not exhaustive backend catalogs.
Open materialization delegates unspecified descendants while exact constraints
remain binding. Complete abstract models need no hidden machine recipe.
Admission of a negotiated supported witness differs from universal envelope
coverage. Reporting, observation, collection, retention, export and operational
inputs remain separate; evidence requirements apply to selected obligations.
The semantic publication must not restore compulsory recipes, internal-profile
declarations or universal telemetry by interpreting the older design literally.

## Publication boundaries that need precision

- **One semantic authority.** Publish the revisioned meaning in the existing
  formal specification. The research program's
  `mixed-cross-backend-participant-control-v1@rev1` identifies the intended
  profile; a profile revision, document status, future wire-schema version,
  and behavioral-taxonomy revision are different coordinates. Preserve
  stable MCB clause identities and explicit revision applicability. Research
  sketches and worked examples must reference that authority rather than
  become competing definitions. Accepted ADR-102 is subject to ADR immutability.
- **Composition and phase names retain their owners.** SCE-002 combines
  atomic scenarios into an SDL family; SEM-234 composes realization providers
  for a selected scenario. Experiment condition/allocation bindings are not
  provider allocation. SDL authored/expanded/instantiated/snapshot phases,
  scenario workflow stages, and apparatus activation phases are distinct.
  Alternative realizations must state the scenario/policy identity being held
  fixed and retain separate apparatus and run provenance. No activation phase
  reselects the family, consumes a new experiment draw, or reinstantiates SDL.
- **Forms, topology, and modes differ.** Alternative realization relates
  separately admitted trials; simultaneous composition describes coexisting
  providers in one trial. Merely having several components or a
  `federated-composition` label does not identify which allocations are
  simulated, emulated/operational, or hardware/native. State those meanings
  explicitly without inferring them from backend names, adapter classes,
  hosts, or topology. Preserve the parent's closed vocabulary and explain its
  dimensions; do not silently redefine terms during publication.
- **Allocation must be phase-relative.** The draft's unindexed relation
  `A` and phase-sensitive `provider(u, phase, cut)` need consistent domains.
  Separate sealed possible membership from currently active membership and
  eligible allocation. Completeness, eligibility, and non-overlap must hold
  at each admitted active phase. Sequential providers must not look like
  simultaneous overlap, and an inactive but pinned provider cannot act.
  Resolve overlaps across the five allocation kinds, not only identical
  keys: a participant-runtime allocation and an action-family allocation
  must not silently authorize competing providers of the same effect.
  Subscope disjointness needs incumbent semantic evidence, not string-prefix
  comparison. Revision 1 supplies no arbitration or failover profile.
- **Graph closure precedes admission.** Every active edge must resolve its
  endpoints, scope, adapter, mappings, policy/release basis, clocks, support,
  loss, and failure disposition at matching revisions/digests. No implicit
  reverse edge, transitive authority, or trusted bridge follows from topology.
  Nested profiles need closed, resolvable references and bounded traversal;
  recursive profile references must not permit infinite admission work.
  Distinguish invalid recursive references from valid feedback edges, whose
  progress/deadlock assumptions must be explicit. Do not assume a DAG or
  progress merely because the phase list is finite. Downstream graph-size,
  depth, and work ceilings belong beside `TrialCompilationLimitsModel`;
  existing trial-product limits do not already bound graph traversal.
  Exhaustion rejects the whole admission rather than truncating the graph.
- **Controller identity does not guarantee current authority.** The incumbent
  `MixedControlControllerState` has one controller reference, active/revoked
  authority, scope, and validity order. The draft's “exactly one acting
  controller” must preserve revoked, expired, stale, and unsupported states;
  it cannot force an authorized actor to exist at every cut. Provider or
  backend object/attribute ownership transfer never grants control, action,
  or disclosure authority. Transfer vocabulary is a semantic disposition,
  not authorization for a second control-occurrence enum or protocol.
- **Partial order is not an admission waiver.** MCB-023's partial/unknown
  clock relation and MCB-010/040's fail-closed mapping requirement must agree.
  An admitted mapping that preserves a partial order differs from a missing
  mapping. An unresolved required comparison cannot authorize an edge,
  transfer, or phase transition. Do not linearize concurrent histories by
  timestamps, receipt order, or backend availability. Existing control
  occurrences use scalar effective/validity order; sequence and causal cuts
  have distinct incumbent models. A mapping must name its domain, authority,
  revision, preserved order, and loss rather than pretend these are one type.
- **Finite phases do not pre-authorize future effects.** Sealing pins possible
  members, transition rules, triggers, mappings, policy/authority expectations,
  and failure behavior. Admitted trigger evidence may enable only an admitted
  transition; fresh exact-cut admission remains necessary. The profile must
  identify the trigger evidence and its trusted evaluator: SCE-002 runtime
  fact bindings currently fill typed action inputs and are not a phase engine
  or apparatus selector. Phase failure, in-flight
  delivery, timeout, retry, replay, and cancellation must have explicit
  dispositions. They cannot discover a provider or erase prior delivery,
  controller/crossing history, or participant memory. Inter-trial changes
  create linked new entries/runs; within-run phases preserve trial identity.
  Deactivation is not cleanup or clean-state evidence. Resource ownership,
  outstanding effects, and cleanup obligations must remain accountable under
  `TrialExecutionAuthorityModel` and the incumbent trial-cleanup contracts.
- **Commit is not completion.** The existing durable decision/history commit
  precedes an external effect; it is not a distributed transaction with a
  backend. A crash after authorization or a partial backend effect cannot
  become a successful delivery, an automatic retry, or a claim of exactly-once
  execution. Scope “zero prohibited effects” to failed pre-effect gates;
  distinguish safe failure evidence from prohibited disclosure, and do not
  promise durable failure evidence when the store itself is unavailable.

## API-423 compatibility constraints

The existing `participant-crossing-occurrence-v1` schema and
`raes_contracts/contracts/participant_crossing{,_validation,_vocab}.py` already
own crossing facts. The following constrain SEM-234's definitions and worked
examples; resolving a downstream contract gap is outside #1013.

- **A topology edge is not a participant carrier.** API-423 ingress/egress
  is relative to the participant boundary, not source/destination component
  direction. Identify which participant, audience, and incumbent subject an
  edge actually mediates. Preserve API-406 observations/views, API-409 control
  occurrences, and DSL-142 inject bindings as the payload owners. Do not wrap
  every inter-component exchange in API-423 or invent a generic bridge
  message, carrier payload, or envelope extension for graph/phase data.
- **Context resolution is a trusted input, not authentication.**
  `validate_participant_crossing_occurrence_context()` checks agreement with
  supplied subject/policy/evidence/authority indexes; it does not authenticate
  their source or establish the contents of an evidence artifact. Reuse
  `ParticipantCrossingPolicyResolver` and `ParticipantCrossingValidationContext`
  from `raes_runtime/participant_crossing_mediation.py`. A caller/backend
  cannot nominate its own known-authority set, permit, or `not-applicable`
  gate. Required evidence references describe obligations, not proof that
  delivery or observation occurred.
- **Successor joins retain exact coordinates.** The contextual validator
  requires the same participant/episode, direction, interaction kind,
  audience, controller, authority refs, complete policy reference, and order
  model; it also requires a named predecessor and strictly increasing scalar
  effective order. A new phase, audience, controller, policy cut, or clock
  mapping cannot be spliced into that chain by restamping an old record.
  Describe fresh admission and explicit lineage at the appropriate boundary.
  These scalar joins do not encode arbitrary cross-component partial order.
- **Transformation branching is not already supported.**
  `_validate_transformation_graph()` allows one result identity per source
  `(subject_kind, subject_ref)` in the supplied history and rejects cycles.
  `_next_crossing_snapshot()` validates the retained participant history, not
  just the new edge. Thus parallel audience-specific transformations of one
  source are not established by the current contract. A worked example that
  needs them must identify the downstream compatibility obligation for #1014;
  do not weaken the validator, drop historical records, or manufacture source
  identities to make it appear satisfied. Policy indexing likewise requires
  one exact policy reference per `(policy_id, policy_revision)` in that context.
- **Stages and evidence have bounded meanings.** A `delivered` stage can
  carry a failed/unknown/unsupported disposition; only a successful delivery
  can support observation. Attempt/delivery/observation owner refs must join
  their exact typed subjects. API-423 uses `disclosed-weak`, whereas API-407
  uses `disclosed_weak`; reuse `_resolve_backend_support()` in
  `raes_runtime/participant_crossing_policy.py`, not string equality or a
  replacement shared enum. Retain transformation
  rule/revision, source/result identity, inherited markings, release authority,
  and explicit loss/weakening. The [participant-control guide](../public/participant-control.md)
  bounds the shipped inject probe to a projected status-view delivery; it
  does not establish compiled DSL-142/DSL-111 event/script/story lineage.
- **Historical validation is not current permission.** Preserve the exact
  prefix through `raes_contracts/participant_crossing_history.py` and retain
  trusted historical resolution material after phase change or revocation.
  Resolving an old authority reference must not reactivate it at a new cut.
  Evidence/provenance stays out of line and audience-governed. Nonempty refs
  and HTTP byte limits do not bound history growth, reference resolution, or
  transformation traversal; downstream limits need explicit count/work
  budgets and exhaustion behavior, without truncating validated history or
  silently fetching caller-selected URLs/paths.

## RUN-310 lifecycle compatibility constraints

The [RUN-310 preflight](issue-255-run-310-supervisory-lifecycle-preflight.md)
and its delivered mediation already own supervision. SEM-234 must compose
that lifecycle; MCB-013–017 and MCB-026/031/038–040 do not authorize a second
controller machine or imply that the current runtime coordinates providers.

- **Keep the three kinds of outcome separate.** The closed application
  `ParticipantControlIntent` union is caller intent; API-409
  `ParticipantControlOccurrenceModel` is a runtime-built fact; an
  `OperationReceipt` acknowledges an operation. In
  `participant_control_operation.py`, `receipt.accepted=True` can accompany
  a failed operation and rejected occurrence. Conversely, an accepted
  `denial` occurrence is a valid supervisory decision denying a proposal.
  Neither is provider-transfer completion. MCB transfer states such as
  `pending` and `committed` must retain their semantic owner rather than be
  copied into these existing kinds, dispositions, or operation states.
- **Preserve declaration, control-state, and history coordinates.**
  `raes/participant_behavior_specification.py`, `raes/validator/_mixed_control.py`,
  and `raes_processor/compiler/_mixed_control.py` own closed ACT-617 graph
  validation, controller/scope/evidence resolution, and compiled addresses.
  Each declared transition advances state revision by one and has a unique
  scalar effective order. `participant_control_mediation.py` folds only
  accepted occurrences for the selected episode. By contrast,
  `raes_contracts/participant_control_history.py` numbers every appended
  occurrence across that participant's retained history, including rejections
  and other episodes, and requires globally unique event ids and an unchanged
  prefix. A phase must not reset either history, reuse an occurrence identity,
  or replace compiled declarations needed to replay an earlier policy cut.
- **Order and conflict handling remain owned by RUN-310.** Reuse
  `participant_control_rejections.py`: unsupported order, stale request policy,
  stale state, stale transition policy, invalid target, revoked authority,
  then authority-window failure determine its bounded rejection reason.
  The shipped order strategy is `total-effective-order`; ACT-617's conflict
  rules are `order-then-revalidate` and `reject-no-state-change`. A lock or
  successful sequential replay is not evidence of cross-backend concurrent
  ordering. SEM-234 must explain required comparisons and rejection without
  silently converting partial order, phase index, arrival order, or wall time
  into this scalar order. Unknown order requires an admitted mapping or an
  explicit unsupported boundary, not another local conflict engine.
- **A resolved target is a scoped historical fact.** Reuse
  `participant_control_targets.py` and
  `validate_participant_control_occurrence_context()`. Proposal, decision,
  control, action, admitted-action, and attempt remain different target kinds.
  The resolver binds kind/ref/revision/participant/episode, while the API-409
  contextual index rejects reuse of `(target_kind, target_ref)` with a
  different revision or scope. Phase/provider-local ids cannot alias retained
  targets. A transformed proposal needs a fresh identity, exact source
  revision, inherited markings, and source/transformation provenance; an
  earlier approval cannot authorize it. Historical target existence alone
  supplies neither current authority nor current action admission.
- **Handoff evidence is not backend acknowledgement.** A handoff intent names
  a compiled declaration and completion-evidence ref; the declaration supplies
  prior/resulting controller state. The current builder copies the supplied
  evidence ref, and API-409 contextual validation does not verify its artifact
  contents or a provider handshake. SEM-234 must identify who can attest the
  required completion facts and their exact cut. Pending or failed transfer
  grants no new authority; the prior controller can act only while its own
  authority remains valid. Backend ownership and provider/phase activation
  require their separate admitted evidence and cannot be inferred from the
  handoff record, an authenticated backend role, or a nonempty reference.
- **Lifecycle recording does not dispatch effects.** Approval is before
  admission; external direction, intervention, override, and cancellation
  also produce control facts without backend dispatch. In
  `participant_control_occurrences.py`, cancellation reports `prevented` for
  proposal/decision, `partial-limitation` for admitted action, and `too-late`
  for an attempt. Those target-stage dispositions do not prove backend abort,
  compensation, cleanup, rollback, delivery, or observation. Preserve
  SEM-211 action admission and API-423 delivery/observation owners, and state
  separately what can still be prevented after an effect starts.
- **Use the composed commit boundary.**
  `ParticipantCrossingControlIngressMixin` in `participant_crossing_boundary.py`
  prepares RUN-310 and RUN-319 facts together, applies the final-sink gate,
  rebinds transformed intent, and commits through
  `ControlPlaneStore.commit_participant_transition()`. Its expected heads
  cover episode, behavior, control, and crossing histories via
  `participant_crossing_state_cut.py`, in addition to snapshot revision.
  Do not call the bare recorder or write provider/control/crossing state
  independently to bypass that cut. The bare path remains available without
  a crossing resolver, and the current HTTP control route in
  `control_plane_api/_participant_routes.py` does not supply crossing evidence;
  neither establishes a public mixed-control ingress satisfying all gates.
  Required resolver/evidence absence fails closed; downstream ingress support
  belongs to #1016, not a new endpoint in #1013.
- **Replay a result without renewing its permit.** The bare recorder scopes
  idempotency by target, principal, kind, participant, episode, and client key,
  and fingerprints intent plus compiled transition. The governed path uses
  the crossing record's fingerprint and decision/result history heads.
  Reuse these paths; do not introduce a phase-local retry cache. Returning a
  committed historical receipt does not authorize another effect after
  handoff, revocation, or a changed provider/mapping cut. New phase/allocation
  fences need governed downstream contract support: the existing four history
  heads do not encode those facts by implication.

Publication witnesses must distinguish an accepted denial, a stale rejected
decision, equivalent retry versus conflicting key reuse, concurrent intervention
versus handoff, cancellation at each target stage, and history replay across
episodes/phases. Reuse the assertions in
`test_run_310_supervisory_lifecycle.py`,
`test_api_409_participant_control_occurrences.py`, and
`test_issue_1003_final_sink_flow_enforcement.py` as compatibility evidence.
Their passing does not establish provider transfer, a phase engine, or
cross-backend concurrency correctness.

## Canonical reuse and security boundaries

Paths below `raes*` refer to packages under
`implementations/python/packages/`. These are compatibility obligations on
the published semantics and examples. #1013 does not modify these runtime
layers or claim that they already implement mixed composition.

| Layer and incumbent | Required fit |
| --- | --- |
| SDL ingress: `raes` parser (`parse_sdl`, `parse_sdl_file`), `SDLModel`, `SemanticValidator`, scenario phase validation | Portable scenario meaning stays backend-neutral. No backend selector, allocation graph, or generic `mixed`, `open`, `federated`, or `constraints` bag in SDL. Reuse structural, semantic, and instantiated validation; a new textual reference does not create an SDL construct. |
| Stable identities: `raes_contracts/addressing.py`, `raes_processor/compiler/addresses.py`, `raes_contracts/canonical.py` | Allocation resolves canonical compiled addresses and typed incumbent refs, including target existence and kind. Reuse `require_compiled_address()` and canonical digest helpers; well-shaped text alone does not resolve a target. Host paths, worker ids, timestamps, and adapter object identities are not portable scope identities. |
| Trial/configuration admission: `AdmittedApparatusBindingModel`, `raes_contracts/admitted_trial_plan_ingress.py`, `raes_processor/trial_compiler/{compiler,apparatus}.py`, `raes_processor/trial_realization.py` | The current apparatus binding has one realization envelope; multiple manifest refs do not admit a component graph. Preserve digest-pinned manifest matching, deterministic admission, and plan/run identities. Reconstruct caller-held plans through `revalidate_admitted_trial_plan()` before realization; a typed object alone is not admission. `ExperimentApparatusContextModel` is observed evidence, not pre-run authorization. Contract/compiler changes belong to #1014/#1015. |
| Selection and randomness: `raes/selected_scenario.py`, `raes/experiment_selection.py`, `raes_processor/trial_compiler/{policies,profiles}.py`, `raes_contracts/random_stream_engine.py` | Preserve complete selection and semantic admission, versioned coordinate/identity/draw profiles, and sealed stochastic outcomes. Provider availability, phase order, and retries cannot reseed or advance experiment randomness. Common random numbers require an explicit experiment namespace/seed choice; backend nondeterminism remains realized evidence, not proof of repeatability from a shared seed. |
| Contract shapes and ingress: `raes_contracts._base.ContractModel`, `raes_contracts/json_ingress.py`, `raes_contracts/experiment_spec.py`, published `contracts/schemas/`, `schema_bundle()`, contextual validators | Closed shape checking and contextual resolution are distinct gates. Reuse bounded JSON parsing with duplicate/non-finite rejection and bounded experiment YAML parsing with duplicate/alias rejection. Reuse `StrictJsonIngressError`, `AdmittedTrialPlanIngressError`, and existing redacted ingress errors, not a composition exception hierarchy. Reuse primitive identities, vocabularies, and reference owners; do not duplicate API-409/API-423 carriers, time models, or validators. No schema or DTO is published by this issue. |
| Authentication and target binding: `_ControlPlaneApiAuth`, `ControlPlaneSecurityConfig`, `ControlPlaneIdentity`, `ParticipantControlSubjectBinding`, `ParticipantAudienceSubjectBinding` | Caller authentication, role, exact target, participant/controller, and audience bindings remain independent of provider membership. A manifest, ownership report, header, or caller-supplied policy decision cannot supply trusted authority. Governed retrieval remains in `participant_retrieval.py` and `control_plane_api_participant_retrieval.py`. No new auth endpoint is needed. |
| Control and crossing admission: `validate_participant_control_occurrence_context()`, `validate_participant_crossing_occurrence_context()`, `participant_control_mediation.py`, `participant_crossing_mediation.py`, `participant_crossing_state_cut.py` | Bind the same participant, episode, controller, authority, policy decision/revision, state revision, history heads, audience, capability, and governed order. Denial or unresolved context in any owner denies the composed operation. Fresh transformed action identity/provenance requires fresh validation and admission; routing and redaction do not authorize release. |
| Final sink and flow labels: `ParticipantFlowControlRelationModel`, `validate_participant_flow_control_resolved_context()`, `participant_flow_sink.py` | SEM-233/ADR-101 already own independent confidentiality/integrity obligations, declassification/endorsement, provenance, and final-sink decisions. Reference the existing relation and incumbent carrier joins. Do not create another label algebra or trust an adapter-supplied permit. The current gate permits a legacy API-423-only path when enforcement is disabled and no resolver hook exists; that path is not evidence of SEM-233 enforcement. A profile requiring the stronger gate must reject its absence. |
| Time and capabilities: `raes_contracts/contracts/time_model.py`, `participant_decision_state_cut.py`, `raes_backend_protocols/time_capabilities.py`, `participant_feature_admission.py` | Reuse time declarations, cuts, mappings, realized readback, and `resolve_participant_feature_support()`. API-407 separates declared/effective strength, required contracts, evidence, and authorized downgrade. Support must hold for the selected component/edge/phase, not the union of unrelated providers' capabilities. Timestamp-only support is `disclosed_weak`; serialization requires its named service and evidence. |
| Persistence and replay: `ControlPlaneStore.commit_participant_transition()`, `control_plane_durability.py`, `control_plane_store_revision.py`, shipped memory/local stores | Reuse snapshot-revision and expected-history-head compare-and-swap, scoped idempotency, operation records, and restart checks. A changed phase/provider/mapping or policy/authority/capability cut must not reuse a prior permit. No side database, new event stream, or distributed-commit claim. Store recovery and later results append facts. |
| Runtime ownership and OS storage: `control_plane_mutation.py`, `control_plane_lifecycle.py`, `control_plane_api/_offload.py`, `control_plane_store_local.py`, `control_plane_store_lease.py` | Preserve bounded mutation admission/offloading and guarded runtime ownership. The local store commits snapshot, operation, and audit in one SQLite transaction and uses an exclusive OS owner lock with safe-file checks. `WEB_CONCURRENCY` and `UVICORN_WORKERS` must be one, with reload disabled. Multiple providers do not justify multiple control-plane writers or turn the store-owner lock into a participant authority lease. No new process or storage surface is needed for this publication. |
| Configuration/secret shapes: `raes_contracts/contracts/experiment_bindings.py`, `participant_configuration.py`, `secret_references.py`, `raes/runtime_environment.py` | Manifest-owned configuration targets already validate type, alias, sensitivity, complete normalization, and digest. Secret targets accept logical `SecretReferenceId` references only and have no portable secret defaults. Runtime env values retain name/classification/provenance validation: literal `value` and `value_from` are exclusive; generated values cannot claim `operator_secret`; protected raw values are redacted. No credentials or executable expressions in edge/adapter refs, examples, or a generic config dictionary. |
| Late-bound facts and secret dispatch: `raes_contracts/contracts/runtime_facts.py`, `raes_runtime/runtime_fact_binding_policy.py`, `runtime_fact_bindings.py`, `runtime_fact_dispatch.py` | Preserve run/participant/episode/workflow scope, source/type/sensitivity/authority/freshness checks, audience projection, and explicit absence dispositions. Resolve secret references only at the trusted action sink through `RuntimeFactBindingAdmission` and `RuntimeFactDispatchCommand`. Provider changes cannot retarget a binding or convert observations into configuration or apparatus authority. No general string interpolation or second secret resolver. |
| Host/OS and backend boundary: component-specific `RuntimeTarget` calls, `backend_call_contracts.py`, `backend_result_diagnostics.py` | This semantic publication adds no subprocess, environment, file-materialization, or host-network surface. Downstream resolution keeps raw secrets out of argv, command strings, portable artifacts, snapshots, logs, and environment dumps. Backend output is untrusted and must pass existing result/transition validators; native success cannot override failed admission. No generic dispatcher that bypasses component-specific effect gates. |
| Errors, size limits, and observability: `control_plane_api_guards.py`, API exception handlers, `Diagnostic`, `OperationReceipt`, `AuditEvent`, `_backend_call_failed()` | Retain request-size/closed-DTO gates, safe operation/error envelopes, value-independent rejection reasons, and existing audit correlation. Never serialize raw exceptions, validation input, hidden values, policy bodies, secret refs revealing protected identity, or private host paths. Audit is a separately authorized audience. Membership, size/cadence, clock grants, transfer, destination, retraction, and differential errors/timeouts also need projection or explicit exclusion from the observer/claim model. |

SEM-230's reactive strategy, memory, projection, declassification, and
exact-cut definitions remain authoritative. SEM-233 final-sink enforcement,
API-423 occurrence stages, and SEM-230 noninterference are different concerns.
Neither schema validity, routing/filtering, encryption, nor successful
per-edge checks establish a composed noninterference result. Earlier visible
occurrences cannot become hidden retrospectively; phase changes do not reset
an adaptive participant's memory by implication.

## Extensibility without new machinery

The extension seam is the revisioned composition profile and its referenced
allocation, edge-mapping, time/order, authority, and observer subprofiles.
Trigger/evidence rules and finite resource bounds belong in those admitted
profiles or their compiler authority inputs, not hard-coded backend branches.
Another backend supplies pinned manifest/adapter identities, eligible scopes,
mapping revisions, capabilities, loss/failure behavior, and evidence through
those seams. Backend-name conditionals and a new portable scenario field are
unnecessary. The three independent axes remain control-loop posture, world
assumption, and admitted membership; closed-loop posture grants no authority,
and bounded-open-world posture does not widen closed vocabularies.

RUN-310's existing order-strategy input, injected principal/controller bindings,
and expected-head store operation are the downstream extension seams. Extend
their governed cut coverage when adding admitted phase/allocation state; do not
hide new authority in snapshot metadata or overload a control-history revision.
Historical declaration/evidence resolution must remain separate from the
current authority check when profiles evolve.

A later lease, simultaneous scoped-controller, or joint/fused-control design
requires a new accepted authority profile with renewal/fencing or arbitration,
ordering, failure, and evidence semantics. It cannot arrive as extra fields,
an extension dictionary, or an interpretation of multiple providers. Profiles
requiring unavailable semantics fail closed rather than degrading silently.

## Evidence and repository workflow

The following are publication acceptance boundaries, not an implementation
sequence:

- Alternative, simultaneous mixed, linked inter-trial, and pre-admitted phase
  examples must identify their profile/revision, scopes, components, directed
  edges, policy/authority and time cuts, outcomes, and limitations. Include
  missing/ambiguous mappings, cross-kind overlap, stale/revoked authority,
  unadmitted joins/fallback, incomparable cuts, and metadata leakage. An
  intentionally invalid example must be identified as such. These are
  semantic witnesses/counterexamples, not runnable mixed-backend fixtures.
- The MCB clause-to-artifact-to-assurance mapping must separate definition,
  structural checking, finite falsification, runtime enforcement, backend
  declaration/realization/conformance, model checking, and proof. Reuse
  `BehavioralClaimBindingModel`, `validate_behavioral_claim_binding()`, and
  `contracts/concept-authority/behavioral-relations-v1.json` for any governed
  relation claim. Do not add an “equivalence” relation just to describe
  composition. Fixed strategies, sampled traces, and scalar serializations
  cannot substitute for SEM-230's quantified adaptive/partial-order model.
- `test_issue_813_cross_backend_participant_control_design.py` checks design
  program structure. It does not execute MCB admission. The existing SEM-230
  bounded model/tests, API-409/API-423 contextual tests, SEM-233 flow-contract
  tests, SCE-002 trial-compiler tests, and API-421 time tests supply incumbent
  meanings and negative-case patterns, not mixed-runtime evidence.
- Reuse `.ground-control.yaml`, `.gc/plan-rules.md`, and `noxfile.py` with
  `tools/nox_support/`; set `RAES_REQUIREMENT_UID=SEM-234` on this branch.
  `.pre-commit-config.yaml`, `.github/workflows/ci.yml`,
  `.github/workflows/canonical-verification.yml`, and
  `.github/workflows/docs.yml` already route verification; do not add a
  parallel workflow. `tools/policy/adr_policy.yaml` owns package boundaries:
  contracts stay below processor/runtime consumers, and SDL cannot import
  processor/runtime orchestration.
  Keep requirement/document traceability explicit without rewriting #813's
  historical DRAFT dispositions as if they were current fulfillment.
- **Observed governance blocker (2026-09-17):** the strict requirement gate
  rejects this pre-existing preflight path under `SEM-234` with
  `requirement-ownership-mismatch`. `tools/policy/requirement_order.yaml`
  selects repository-backed requirement authority and its
  `semantics-expansion` ownership list does not include this note. Reconcile
  the delivery's exact document ownership through the canonical governance
  mechanism before claiming verification complete. Do not switch to an
  unrelated UID, disable the gate, or broaden ownership as a workaround.
  This preflight changes no policy configuration or requirement records.
  Delivery resolution: #1013 assigns exact publication paths to a dedicated
  `mixed-participant-composition` ownership phase for SEM-234, retaining the
  reference-implementation prerequisites. Its regression test admits this
  note and rejects runtime implementation paths. No gate is disabled.
- The actual publication is subject to `check_repo_policy.py`,
  `check_requirement_governance.py`, `check_adr_immutability.py`,
  `check_semantic_coverage.py`, `check_assurance_policy.py`,
  `check_specification_coverage.py`, `check_sdl_lineage.py`,
  `check_behavioral_relation_claims.py`, and repository docs validation.
  Reuse `docs/explain/reference/shared-semantic-integrity.md`,
  `docs/explain/reference/fm-classification-ledger.yaml`,
  `specs/formal/assurance-fulfillment.yaml`,
  `contracts/provenance/sdl-lineage-ledger-v2.json`, its source mappings, and
  the existing claim gate. These general gates do not themselves check MCB
  semantic completeness. Do not introduce a parallel checker or mark
  production coverage complete from prose. Preserve exact source editions
  and prior-art/nonclaim dispositions from #813 rather than inventing
  compatibility claims.
- A later published schema change belongs to #1014 and must satisfy
  `contracts/schema-publication-manifest.json`, `check_schema_publication.py`,
  generated-bundle parity (`check_generated_schemas.py`), schema fixtures, and
  contextual validation. No weakening of `extra="forbid"` or use of observed
  apparatus metadata is a substitute for that governed extension.

## Non-goals

#1013 publishes semantic authority only. It does not publish a wire contract,
DTO, SDL backend selector, compiler change, coordinator, adapter, HLA gateway,
policy engine, exception hierarchy, logger, store, or new workflow. #1014–#1017
own the downstream contract/admission/runtime/backend work; #1018 owns the
demonstration and #1019 its claim reconciliation.

No leased, simultaneous scoped-owner, joint/fused-controller, unadmitted
dynamic-membership, or implicit failover support is established. No live
realization, interoperability, universal transfer, cross-backend equivalence,
IFC/noninterference, covert-channel protection, or distributed exactly-once
guarantee follows from this note or semantic publication.
