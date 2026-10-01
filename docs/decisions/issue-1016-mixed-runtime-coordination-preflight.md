# Issue #1016 — Mixed runtime coordination preflight

Date: 2026-09-20

Scope: coordinate one already-admitted mixed participant trial through the
existing runtime control plane, RUN-310 supervision, RUN-319/API-423 crossing
mediation, and component `RuntimeTarget` boundaries. This note is architecture
guidance, not an implementation plan. It adds no runtime behavior, contract,
schema, endpoint, backend capability, or realization claim.

[ADR-102](adrs/adr-102-mixed-cross-backend-participant-control.md), the
[#1013 semantic preflight](issue-1013-sem-234-mixed-participant-control-preflight.md),
the [#1014 contract preflight](issue-1014-mixed-composition-contracts-preflight.md),
the [#1015 admission preflight](issue-1015-mixed-staged-trial-admission-preflight.md),
and `sem-234/rev1` already decide the architecture. No new ADR is needed. The
runtime must consume their exact identities and preserve their nonclaims.

## Decisive architecture decisions

### Keep one control plane, one run scope, and one state authority

One admitted composition runs under one `RuntimeControlPlane`, one target/run
store scope, one `RuntimeMutationAuthority`, and one authoritative snapshot
revision. The admitted composition may bind several component-specific
`RuntimeTarget` values, but those targets are effect boundaries under the one
control-plane authority. They do not receive child control planes, stores,
operation ledgers, controller states, or participant histories.

The control-plane target identity remains the authenticated logical target for
the whole admitted run. Component ids and backend target names are resolved
only from the sealed `AdmittedMixedCompositionBindingModel` and its exact
`MixedParticipantCompositionProfileModel`; a request, header, query value,
runtime fact, environment variable, backend response, or availability probe
cannot select a component. This is the narrow mixed-runtime clarification of
the ordinary one-control-plane/one-target profile: component targets are
delegated effect sinks, not independent authority domains or API tenants.

The incumbent backend apply contract gives the selected in-process target a
deep-copied `RuntimeSnapshot`. Configured component targets are therefore
trusted runtime dependencies in this bounded design; deep copying prevents
alias mutation but does not provide confidentiality isolation between
components. If a deployment needs least-privilege component snapshots or an
out-of-process trust boundary, that requires a separately versioned projection
and transport contract. Do not imply that isolation by filtering an ad hoc
dictionary or by treating API-423 participant disclosure policy as backend
plugin authorization.

Use a trusted, immutable runtime binding from admitted `component_id` to an
already shape-validated `RuntimeTarget`. Validate every component target's
manifest identity and digest, realization-envelope membership, required
runtime component, and current profile-relative support against the sealed
profile before the run becomes ready. Do not synthesize a union manifest,
borrow one component's manifest for the composition, infer support from method
presence, or update backend support declarations before #1017 establishes the
corresponding capability and conformance surface.

Mixed activation must require a crossing-policy resolver, its required
SEM-233 resolution support, and final-sink enforcement. The legacy branches
in `participant_submission_options.py`, `ParticipantCrossingControlIngressMixin`,
and `ParticipantRetrievalMixin` permit some operations without a resolver;
`enforce_final_sink_flow_control=True` alone does not close those branches.
Reject an incomplete mixed configuration before readiness, including on
restart; preserve legacy single-target compatibility without importing its
opt-outs into an admitted mixed run.

`raes_processor.trial_realization.realize_admitted_trial_entry()` currently
rejects `AdmittedMixedCompositionBindingModel`. That refusal is the honest
boundary to replace. Mixed realization must still enter through
`revalidate_admitted_trial_plan()`, the exact entry/profile join, the existing
scenario instantiation and compiled-address authorities, and the per-component
apparatus/envelope validation from trial admission. It must not create a
parallel plan, run id, scenario snapshot, compiler, or realization lifecycle.

### Add only the missing composition-owned runtime fact

The portable composition profile is sealed intent and deliberately contains no
current phase or mutable status. RUN-310 owns controller state and API-409
history. API-423 owns crossing request, decision, transformation, delivery,
observation, loss, and their lineage. `ControlPlaneOperationRecord` owns
operation lifecycle, while `AuditEvent` is operational audit. None owns the
current composition phase or the MCB-032 phase-transition fact.

Runtime coordination therefore needs one closed, composition-owned current
state plus append-only history carrier in `RuntimeSnapshot`. It must bind at
least the admitted plan/entry/run and profile identities, current phase and
revision, exact active component/allocation/edge set, predecessor event, trigger
and evaluator refs, governed order, relevant controller/authority/policy/time
cut refs, disposition, mapping loss/weakening refs, and evidence/provenance
refs. Runtime events should reference owning RUN-310 and API-423 event ids when
handoff, delivery, or observation occurs; they must not copy those occurrence
payloads or invent a second control/crossing state machine.

The current state is a derived fold over the validated append-only composition
history and sealed initial phase, not a mutable metadata flag. The snapshot
carrier must receive the usual model/schema/codec/key-identity, aggregate-size,
restart-validation, and exact-prefix transition checks. Classify it as
runtime-owned in `backend_snapshot_contracts.py` so a component backend cannot
edit the active phase, allocation, decision cut, or coordination history in an
`ApplyResult`. Do not place it in `RuntimeSnapshot.metadata`, operation
`result_payload`, audit details, scheduler memory, adapter-local state, or a
side event stream.

This is a published `RuntimeSnapshotEnvelopeModel` surface. Any implementation
change must follow ADR-009/ADR-061 and the existing schema authority:
`schema_bundle()` parity, explicit generation routing, publication-manifest
`last_change`, fixtures, compatibility classification, strict store/HTTP
round trips, and migration handling. Optional defaulted fields do not excuse
the publication workflow or persisted-state validation.

### Extend the incumbent exact-cut transaction

The exact pre-effect cut is one joined authority, not a collection of checks
performed at unrelated times. It includes:

- plan id/digest, entry id/digest, run scope, profile id/revision/digest, and
  active composition phase/revision;
- compiled participant/action/observation/crossing target, allocation id,
  selected provider component, applicable edge, component manifest and
  realization-envelope pins;
- authenticated caller and logical target, participant, episode, acting
  controller, authority basis and scope, action admission, audience, policy
  revision/decision cut, and final-sink disposition;
- effective component capability and authorized downgrade, mapping loss,
  source/target clocks, admitted time/order mapping and runtime readback; and
- snapshot revision plus episode, behavior, control, crossing, and composition
  history heads, outstanding-operation/quiescence result, and required
  evidence/provenance refs.

Build on `expected_participant_history_heads()` and
`ControlPlaneStore.commit_participant_transition()`. Extend their expected-head
cut with the composition history/state coordinates; do not add a composition
store or perform separate snapshot, control, crossing, phase, operation, and
audit writes. Both `InMemoryControlPlaneStore` and `LocalControlPlaneStore`
must provide the same revision/history compare-and-swap outcome through the
existing durability and readback/poisoning discipline.

Extend the closed history-key dispatch in
`control_plane_store_history.participant_history_head()` as well as the cut
producer; adding a key only to `expected_participant_history_heads()` is
rejected by both stores. Keep persisted decision/result heads and replay
validation consistent. A successful operation advances its own heads: retain
the incumbent decision-or-result-head replay rule without interpreting a
retry as fresh permission under a later phase.

The existing atomic operation lifecycle remains authoritative. Take the
actor/kind/target/run-scoped idempotency claim, commit the prepared exact
decision and `RUNNING` record before a component call or serialization, invoke
the external boundary outside the store transaction while retaining the one
logical mutation reservation, then commit the result snapshot, terminal
record, safe audit event, and new history facts atomically. A phase transition
uses the same operation lifecycle with a distinct closed operation kind or an
explicitly owned parent-operation relation; it must not masquerade as a
participant-control occurrence, crossing, workflow cancellation, or backend
result.

An exact retry returns the durable incumbent result only after the same actor,
operation kind, target/run, profile, phase, allocation, policy, mapping, and
state-cut commitment agrees. It never re-resolves availability, renews a
permit, advances a phase, or calls a provider again. Conflicting reuse and CAS
loss return the incumbent coarse conflict behavior without disclosing the
winning provider or cut.

### Resolve, commit, then dispatch through the existing final sink

The action path must remain inside
`ParticipantCrossingControlIngressMixin`/`execute_action_ingress_crossing()`.
After ordinary participant/controller binding, RUN-319/API-423 resolution,
SEM-233 final-sink resolution, action binding/admission, and exact composition
resolution all agree, the combined prepared state is committed before
dispatch. `submit_bound_participant_action()` must no longer choose a backend
by directly assuming `control_plane._target.participant_runtime`; the trusted
allocation cut supplies exactly one active admitted component target.

Invoke the selected component through `apply_authorized_participant_action()`
and `_call_backend_apply()`, preserving deep argument isolation,
`participant_effect_authority()`, backend result shape/size checks, changed
address accounting, snapshot carrier ownership, participant history transition
checks, credential sanitization, materialization/realization gates, and safe
backend diagnostics. A coordinator or adapter must not call
`participant_runtime.admit_action()` outside that boundary or accept a native
success after any RAES gate failed.

Require all requested effects/resources to fit the selected allocation's
resolved effect coverage before invocation; reject a straddling request unless
an admitted decomposition owns every sub-effect. Bind that scoped authority
through `participant_effect_authority()` and reuse
`backend_effect_transitions.py` for returned-state ownership and actual
change accounting. A valid participant result is not automatically a valid
result for that component. Reject cross-component changes, including omitted
`changed_addresses`; do not merge whole returned snapshots from parallel
providers or silently discard unauthorized changes and report success.

The same final-boundary rule applies to participant/external serialization.
API-408 retrieval and `serialize_participant_view()` keep audience binding,
API-423 policy/transformation, SEM-233 final-sink, stable subject, result
payload, and revision-pinned projection semantics. Composition routing may
narrow an already-authorized projection; it cannot widen one, serialize before
the decision commit, treat an edge as a crossing occurrence, or use audit
retention as participant visibility.

This boundary includes `deliver_participant_directed_view()` and the trusted
ingress/egress transformers, whose returned typed carrier must match the
governed subject. Already-projected inject content still needs delivery-time
audience, phase, edge, capability and policy checks; it proves no observation.
Transformers/evaluators are trusted computation, not dispatch hooks, and may
not disclose or call a provider while preparing an uncommitted decision.

Audit every reachable effect entry point, not just action submission:
`participant_episode_control.py`, `participant_execution_control.py`,
`time_control.py`, `control_plane_submission.py`/`observation_admission.py`,
and nested calls in `participant_scheduler_operations.py` still use a single
runtime dependency. An outer time/execution permit does not authorize each
nested action or exchange. Thread the admitted cut through the incumbent
boundary or refuse an unsupported mixed operation before any component call.
Observation support must resolve against its allocated source, with collection,
retention and export retaining their existing independent gates. Do not add a
second scheduler or silently enable unsupported service paths.

### Keep control, provider responsibility, and native ownership separate

A RUN-310 approval, denial, direction, intervention, handoff, override, or
cancellation remains a runtime-built API-409 fact over the compiled ACT-617
declaration. It does not dispatch an action or change the active provider. A
composition phase transition changes admitted provider responsibility only
after its own revision-fenced commit. Backend-native ownership or bridge
routing remains an observed responsibility/movement fact and changes neither
acting controller nor disclosure authority.

The coordinator must call the incumbent `bind_participant_control_request()`,
`prepare_participant_control_transition()`, target resolver, rejection ordering,
context validator, and combined RUN-310/RUN-319 final-sink commit. It must not
accept caller-built API-409 occurrences, create a provider-handoff control kind,
map component ids to controllers, or infer completion from a nonempty evidence
ref or backend acknowledgement.

Approval remains before SEM-211 action admission; admission remains before an
attempt; an attempted effect remains distinct from delivery; delivery remains
distinct from observation. Cancellation after an attempt cannot erase an
effect, delivery, participant knowledge, control occurrence, crossing record,
or composition fact. The composition history links these owners by stable refs
and exact cuts rather than collapsing them into one status.

### Phase progression is sealed, quiescent, and fail closed

The active phase starts only from the admitted profile's `initial_phase_id`.
Progression may follow only one sealed transition whose source equals the live
phase and whose trigger/evaluator, progress bound, target membership,
allocations, edges, mappings, policy, failure disposition, and evidence
obligations still resolve at the live cut. Trigger evaluation is a trusted
injected dependency and runs under `external_control_plane_call()` so it cannot
re-enter mutation. Runtime facts can supply typed evaluator inputs; they cannot
select a target phase or provider.

Quiescence is evaluated from the authoritative operation/state records and
crossing delivery history, not an adapter boolean or a duplicate pending-work
counter. Pending, indeterminate, or uncommitted work stays with its original
phase/provider. Transition timeout or cancellation follows the sealed failure
disposition and appends a safe fact when storage is available; it does not mark
work complete, switch provider, restore an old snapshot, or perform cleanup.
Only the phase commit makes the new allocation active, and it occurs before any
new-phase effect.

Inactive pinned components cannot act or receive an exchange. Missing or
unhealthy active providers do not authorize fallback. A component outside the
sealed possible-membership set cannot join. Phase change preserves plan,
entry, run, controller, participant memory, operation records, and every
history prefix. Deactivation is not teardown, cleanup, rollback, or evidence
that external state disappeared; existing trial cleanup/resource ownership
contracts remain authoritative.

### Failure evidence is bounded by what actually committed

Pre-effect denial, stale cut, unsupported capability, a mapping that cannot
establish a required comparison, invalid phase, unadmitted component,
unresolved policy/evidence, or failed authorization commit produces zero
provider calls and zero external or
participant disclosure. When the store remains available, record the bounded
denial in the existing operation/audit and owning history transaction. When
the store itself cannot commit, do not invent durable failure evidence.

After authorization commit, backend failure is a distinct attempt/result fact
with sanitized diagnostics. A crash or unknown store outcome after a possible
external effect follows the existing reconciliation and durability-poisoning
rules. It is never automatic replay, successful delivery, rollback,
compensation, or exactly-once execution. Retraction or concealment appends a
fact and cannot erase a prior delivery or participant-visible fact.

Startup reconciliation must recover the exact provider binding committed for
the interrupted effect and use only that component target's matching
`RecoveryObserver` and declared recovery capability. The current
`_observe_running_record()` default to `control_plane._target` is insufficient
for a mixed effect and must not silently select the logical target, another
component, or an available fallback. Missing, mismatched, or unobservable
provider recovery remains `INDETERMINATE`; the durable request commitment keeps
the logical target/run identity and the provider binding remains a separate
value-free coordinate of the exact cut.

## Canonical incumbents and required reuse

| Concern | Canonical owner and required fit |
| --- | --- |
| Semantic and profile authority | `specs/formal/participant-semantics/cross-backend-participant-control.md`, ADR-102, MCB-001–045, `MixedParticipantCompositionProfileModel`, and `validate_mixed_composition_context()`. Consume the sealed graph and limits; do not restate it in runtime DTOs. |
| Trial/run admission | `AdmittedTrialPlanModel`, `AdmittedMixedCompositionBindingModel`, exact profile input refs, `revalidate_admitted_trial_plan()`, trial identity profiles, cleanup/isolation, and `TrialInstantiationProvenance`. No second plan/run identity or runtime fallback. |
| Component targets | `RuntimeTarget`, `RuntimeTargetComponents`, registry shape/method checks, backend manifests, realization envelopes, component-specific manifest pins, and current API-407 support resolution. Preserve each component identity; do not union manifests or capability sets. |
| Runtime authority | `RuntimeControlPlane`, `ControlPlaneConfiguration`, `RuntimeMutationAuthority`, operation admission/context, `ControlPlaneOperationRecord`, `OperationReceipt`/`OperationStatus`, and the target/run-scoped store lease. One coordinator owns the complete cut. |
| RUN-310 control | Compiled mixed-control declarations, `participant_control_mediation.py`, `participant_control_rejections.py`, `participant_control_targets.py`, API-409 contextual validation, and append-only control history. Provider/phase change never becomes controller state. |
| RUN-319/API-423 and final sinks | `participant_crossing_boundary.py`, `participant_crossing_{mediation,commit,egress}.py`, `participant_flow_sink.py`, the policy resolver/context, API-423 contextual validation, SEM-233 resolution, and exact participant history heads. Extend the combined cut; do not add a gateway or bypass path. |
| Action and observation | `ParticipantActionAdmissionRequest`, compiled action/observation bindings, `participant_effect_authority()`, participant result/history validators, API-408 projections, and scoped observation demand. Approval, admission, attempt, delivery, observation, collection, retention, and export remain separate. |
| Time and order | `TimeModelDeclarationModel`, `TimeRuntimeStateModel`, time-domain/clock/mapping declarations, `ParticipantRuntimeOrderingBasis`, shared-time transition validation, and runtime readback. No wall-time, phase-index, list-order, or receipt-order causality. |
| Persistence and replay | `ControlPlaneStore`, `ControlPlaneStoreCommitAdapter`, in-memory/local providers, expected snapshot revision/history heads, owner lease, strict local codec/migration, terminal audit binding, startup reconciliation, and durability poisoning. Extend the existing transaction only. |
| Backend boundary | `apply_authorized_participant_action()`, `_call_backend_apply()`, `backend_*_contracts.py`, snapshot carrier ownership, changed-address accounting, credential sanitization, and backend result diagnostics. Every selected component crosses the same validation boundary; the incumbent full-snapshot call is a trusted-component boundary, not component confidentiality isolation. |
| Errors and observability | `Diagnostic`, portable diagnostic conversion, stable operation states, `_conflict_detail()`, redacted request-validation and generic 500 handlers, `AuditEvent`, and `operational_apparatus_summary()`. Use bounded ids/codes; audit and logs are not scientific or participant evidence. |
| Contract/publication | `ContractModel(extra="forbid")`, runtime snapshot model/codecs, `schema_bundle()`, hand-governed schemas, publication manifest/fixtures, ADR-061 compatibility, and existing schema checks. No duplicate schema base, serializer, registry, or compatibility process. |
| Workflow | `.ground-control.yaml`, `.gc/plan-rules.md`, issue-bound requirement scope, canonical nox/policy/schema/semantic checks, and existing real-boundary conformance tests. Add no workflow or verification lane. |

## Cross-cutting security and host-layer path

The intended implementation must pass every layer below in order.

1. **Profile and plan ingress.** External profile bytes use
   `parse_mixed_composition_profile()` and its bounded duplicate/depth/node
   checks. External/caller-held plans use `parse_admitted_trial_plan_json()` or
   `revalidate_admitted_trial_plan()`. Closed models, digests, exact refs,
   contextual composition validation, and trial-admission joins all pass before
   runtime construction. There is no YAML, remote include, path/URL fetch, or
   caller-supplied trusted context.
2. **Configuration and target shape.** `ControlPlaneConfiguration` rejects
   unknown constructor options and validates normalized `PlanScope` run ids.
   `RuntimeTarget.__post_init__`, registry method-signature checks, manifest
   capability/component presence, realization envelopes, and exact
   component/profile bindings validate every delegated target. Component
   lookup is immutable and admitted; ambient configuration cannot choose it.
3. **HTTP request admission.** Any public mutation stays behind
   `create_control_plane_app()`, `RequestSizeLimitMiddleware`, the bounded
   offload queue, closed Pydantic request models, and the canonical
   `Idempotency-Key` validator. Do not add a route-only parser or accept plan,
   profile, provider, phase, policy, mapping, disposition, or result fields
   from a control request unless an owning closed contract explicitly requires
   them.
4. **Authentication and authorization.** `_ControlPlaneApiAuth`,
   `ControlPlaneSecurityConfig.strict_defaults()`, constant-time bearer
   resolution or explicitly trusted proxy identity, role checks, exact logical
   target binding, participant/controller subject bindings, and audience
   bindings all remain mandatory. A backend role, token, OS account, component
   target, provider id, or native owner supplies no participant authority.
5. **Semantic/final-sink policy.** Compiled ACT-617 policy, RUN-310 rejection
   order, SEM-211 action admission, API-423 policy/context, SEM-233 final-sink,
   exact allocation/phase/provider, current capability, policy/release,
   clock/order mapping, loss, and evidence joins must all permit the same cut.
   Missing, stale, ambiguous, or resolver-failed required input refuses the
   effect. Under MCB-023, an admitted partial-order mapping may authorize only
   comparisons it actually establishes. Incomparability must neither become
   invented total order nor reject unrelated exchanges that the profile
   permits; weak support needs its explicit admitted downgrade and evidence.
6. **Persistence and concurrency.** The store-scoped atomic claim, one mutation
   authority, owner lease, snapshot revision CAS, complete history-head CAS,
   strict snapshot reconstruction, restart validation, and indeterminate-work
   block precede effect. SQLite/WAL is admitted only through the local store's
   private-directory, permission, identity-pinned-open, sidecar, synchronous,
   integrity, and single-owner checks. A shared database or extra ASGI worker
   does not supply distributed coordination.
7. **Secret and environment handling.** New coordination records, operation
   contexts, diagnostics, audits, fixtures, and commitments carry only
   governed refs and safe facts, never tokens, credentials, resolved secrets,
   policy/evidence bodies, hidden participant state, backend handles, host
   paths, or environment values. Reuse `secret_references.py`,
   `experiment_bindings.py`, `participant_configuration.py`,
   `raes/runtime_environment.py`, runtime-fact binding policy,
   `RuntimeFactDispatchCommand`, and account-credential value-free/sanitizing
   paths. Keep `RuntimeEnvironmentVariable` name, `value`/`value_from`
   exclusivity, classification and redaction checks; generated `value_from`
   cannot claim `operator_secret`. Configuration normalization must preserve
   literal/secret-reference disposition and exact secret-reference identity.
   Existing payload/history owners retain authorized content under their own
   audience rules; do not copy that content into coordination evidence or
   treat a digest of a low-entropy secret as safe disclosure. The coordinator
   is not a secret resolver.
8. **OS and process exposure.** The core adds no shell, subprocess, daemon,
   socket, file-name authority, or environment binding. Never place a token,
   profile, action payload, policy, evidence body, component command, or host
   path in argv, environment dumps, stdout, or stderr. The existing
   `control_plane_store_lease.require_single_worker_configuration()` gate for
   `WEB_CONCURRENCY`/`UVICORN_WORKERS` remains mandatory; component adapters use
   their incumbent configuration and must not use caller-derived argv or
   `shell=True`.
9. **Backend result and error envelope.** Deep-copied inputs cross the existing
   backend call wrapper. Result type, bounded diagnostics/details, snapshot
   shape and owner transitions, changed addresses, histories, credentials,
   realization authority, and time transitions are revalidated before a
   result can commit. Provider exceptions reduce to stable diagnostics;
   expected conflicts use coarse fixed responses, validation errors remain
   redacted, and unexpected HTTP failure remains exactly
   `{"detail":"internal server error"}`. Logs/audits contain safe ids,
   dispositions, and reason codes only.
10. **Egress and evidence audience.** Participant views are projected from one
    pinned snapshot revision and pass audience/policy/final-sink mediation
    before serialization. Audit, composition history, API-423 observation,
    experiment evidence, and archival run provenance retain separate audience
    and retention rules. One cannot be substituted for another. MCB-021 also
    covers membership, destination, size/cadence, synchronization, ownership,
    retraction and differential-failure metadata; payload redaction alone
    establishes no metadata noninterference.

## Extensibility seam

The runtime seam is a trusted immutable binding of the admitted profile and
plan entry to `component_id -> RuntimeTarget`, plus a bounded resolver for the
live composition cut and trigger/time/readback facts. The coordinator consumes
that interface and the existing backend call contract; it does not branch on a
backend name, adapter class, HLA/FMI/HELICS term, or host topology. Adding a
backend or adapter supplies another validated target and exact profile context,
without editing allocation, policy, persistence, idempotency, or result
validation logic.

That binding also supplies the exact component recovery observer after a crash;
recovery does not rediscover a provider. A later least-privilege or remote
component boundary belongs behind a versioned snapshot projection/transport
contract while preserving this same admitted component and exact-cut identity.

The live cut explicitly carries profile/phase revision, selected allocation
and provider, mapping identity, order basis, state/history heads, and expected
evidence. This permits another accepted mapping or backend implementation
without restamping old facts. A future lease, arbitration/failover,
multi-controller, joint-control, or non-quiescent phase protocol requires a
new accepted semantic/profile revision and its own fencing/failure rules; it
cannot enter through an extension map, optional callback, or new enum value in
revision 1.

## Assurance guardrails

Reuse `test_run_310_supervisory_lifecycle.py`,
`test_run_319_participant_flow_policy.py`,
`test_issue_1003_final_sink_flow_enforcement.py`, the #1014/#1015 fixtures,
`control_plane_conformance_fixtures.py`, `control_plane_crash_fixtures.py`, and
the #1186/#1187 recovery/security/durability suites. Add assertions to these
incumbent boundaries, not a parallel coordinator-only harness.

Evidence must drive the real `RuntimeControlPlane` through the selected
component `RuntimeTarget` boundary. Instrumented targets must prove exactly one
admitted provider call for a permitted fresh cut and zero calls/serializations
for denied, stale, unsupported, unmapped, inactive, unadmitted, conflicting,
or failed-commit cases. Exercise pure single-component, simultaneous mixed,
and pre-admitted staged fixtures from the existing #1014/#1015 families.
Include absent resolver/enforcement opt-out, nested scheduler effects,
cross-component result mutation, inject delivery after a phase change, and
positive as well as negative partial-order comparisons.

Run the same exact-cut, idempotency, CAS, append-only, restart, corruption, and
failure-injection assertions against `InMemoryControlPlaneStore` and
`LocalControlPlaneStore`. Cover concurrent intervention versus phase change,
stale handoff, provider/manifest drift, trigger mismatch, pending and
indeterminate work, partial order/incomparable time, authorized downgrade,
backend exception/invalid result, authorization-commit failure, terminal-commit
uncertainty, prior-delivery retraction, and history-prefix tampering. Verify
safe diagnostics/audit plus absence of credentials, policy/evidence bodies,
backend exception text, paths, and hidden state from every public surface.

Tests must assert the relationships among approval, action admission,
pre-effect decision, backend attempt, delivery, observation, phase commit,
audit, and archival evidence rather than merely count history rows. Passing
reference-coordinator tests establishes bounded #1016 behavior only; it is not
backend-native mixed capability, conformance, interoperability, transfer,
IFC/noninterference, trace inclusion, bisimulation, or equivalence evidence.

## Repository workflow guardrails

At preflight, `docs/governance/requirement-scopes/1016.json` does not exist.
The issue assigns SEM-234, RUN-310, RUN-319, and API-423, so implementation
needs one exact issue-bound scope containing those four UIDs and every delivery
file. Do not run the change under RUN-310 alone, omit a UID because its
incumbent code is reused, or copy #1014's contract-publication scope.

The current `mixed-participant-composition` phase explicitly owns semantic,
contract, admission, and documentation artifacts and says mixed-runtime
implementation is not active there. `RUN-310` and `RUN-319` also have no
dedicated phase mapping in `tools/policy/requirement_order.yaml`, and the
current ownership list does not authorize the runtime/store/snapshot files
that #1016 must change. Establish a narrow runtime activation, prerequisites,
ownership, and traceability mapping before delivery. Do not borrow
`semantics-expansion`, widen an unrelated runtime phase, use a broad directory
glob, or weaken the checker.

Keep Ground Control IMPLEMENTS/TESTS traceability aligned for every owning
requirement. Reuse the existing nox, policy, schema, publication, semantic
coverage, and full verification commands from `.ground-control.yaml`; add no
CI lane. `CHANGELOG.md` and the package version remain release-please owned.

## Gotchas and anti-patterns

Avoid:

- one control plane or store per component, cross-store two-phase commit,
  adapter-local policy/history, or a child operation ledger;
- a synthetic union manifest/capability set, borrowing one component's
  identity for the graph, method-presence support, or updating #1017 claims to
  make runtime tests pass;
- accepting provider, component, phase, mapping, target, policy, authority,
  controller, disposition, history head, or evidence satisfaction from a
  request or backend response;
- treating provider, adapter, route, HLA ownership, authenticated principal,
  role, behavior mode, or process identity as controller/action/disclosure
  authority;
- dispatching directly from approval, direction, intervention, handoff,
  override, cancellation, runtime fact, trigger, or phase membership;
- using API-409 control history, API-423 crossing history, workflow history,
  audit, operation details, snapshot metadata, or backend status as the missing
  composition phase history;
- copying control, crossing, delivery, observation, or evidence bodies into a
  generic composition event, `details` map, or nullable mega-event;
- selecting a provider by availability, fallback, native ownership, source
  order, phase list order, arrival time, wall clock, retry count, or backend
  completion order;
- calling a component outside `apply_authorized_participant_action()` /
  `_call_backend_apply()`, trusting an adapter success, or letting backend
  output mutate runtime-owned composition state;
- separate writes for authorization, phase, crossing, operation, snapshot, or
  audit; a phase-local retry cache; lookup-then-save idempotency; or holding a
  store transaction across an external call;
- automatic replay after a crash, treating authorization commit as delivery,
  restoring an old snapshot after a possible effect, or claiming exactly-once
  execution;
- erasing/replacing prior handoff, delivery, observation, loss, failure,
  participant knowledge, or composition history on rollback, retraction,
  concealment, cancellation, or phase change;
- raw resolver/Pydantic/backend exception text, credentials, tokens, policy or
  evidence bodies, hidden content, action payloads, manifests, environment
  values, paths, SQL, or tracebacks in contracts, state, diagnostics, audit,
  logs, fixtures, argv, or stdout/stderr;
- claiming component confidentiality, sandboxing, or process isolation from
  deep copies, output validation, API-423 policy, or one logical target; and
- a new gateway, scheduler, workflow engine, store, repository, event bus,
  audit channel, logger, exception hierarchy, schema base/registry, serializer,
  configuration parser, secret resolver, or verification workflow.

## Non-goals and implementation boundary

- No new portable SDL syntax, scenario composition meaning, trial compiler,
  backend selection language, plan/run identity, or runtime fallback.
- No backend-native realization, mixed-capability declaration, conformance
  result, HLA/FMI/HELICS compatibility, provider handshake, or generic bridge
  protocol; #1017 owns capability/conformance and #1018 owns demonstration.
- No multi-controller, scoped simultaneous control, joint/fused control,
  leases, failover/arbitration, late joins, unbounded dynamic membership, or
  progress/livelock guarantee.
- No distributed transaction, multi-owner/P3 service, durable broker,
  exactly-once external effect, automatic retry, rollback of external effects,
  compensation, cleanup, or proof that deactivation removed external state.
- No confidentiality, tenant, process, or fault isolation among configured
  component targets; a separately versioned projection/transport boundary owns
  such a future claim.
- No replacement of ACT-617/RUN-310 control, SEM-211 admission, SEM-230/233
  policy, RUN-319/API-423 crossing, API-408 retrieval, shared time, scoped
  observation demand, experiment evidence, or archival provenance.
- No claim that approval proves admission, admission or authorization commit
  proves execution, attempt proves delivery, delivery proves observation,
  audit proves participant visibility, or reference coordination proves
  interoperability, transfer, trace inclusion, bisimulation,
  IFC/noninterference, or backend equivalence.
