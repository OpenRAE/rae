# Issue #1351 — Reusable mixed-control architecture preflight

Date: 2026-09-22. Inspection baseline: `c22ae7f94f2e3269dbebc0d05c32f3808c6a4577`.

Scope: ACT-617, API-409, RUN-310 and DSL-142 preflights for issue #1351.
This is guidance, not an accepted semantic decision,
requirement amendment, implementation plan, or claim of runtime support.
The referenced diagnosis was inspected from this repository's Git object
`077f7d04:docs/research/runtime-refactor/diagnosis.md`; it is absent from the
current working tree. Its F03 finding is confirmed by the current code.

## Architecture boundary

Separate a reusable permission from its applications under the existing
owners: ACT-617 owns authored policy, API-409 owns portable control facts,
RUN-310 owns live mediation/history, and DSL-142 owns participant-directed
inject bindings. Keep the policy beneath `ParticipantBehaviorSpecification`,
scoped to one controlled participant, with stable local transition identities
and typed compiler children. A return to the same controller state is a new
occurrence at a new state revision, not reuse of an old occurrence identity.

The accepted decision must distinguish permitted source/destination states,
controller/authority/scope constraints, target requirements and evidence
requirements from actual occurrence identities, proposal/target revisions,
expected/resulting state revisions, order, evaluated validity and evidence.
Authored evidence requirements do not establish completion. Moving checks to
their proper owner must preserve exact occurrence checks; deleting revision
checks or assigning wildcard revisions is not a repair.
Reuse `MixedControlTransitionKind` and the existing disposition owners rather
than copying their enums across authoring, contract and runtime packages.

The intended change is FM3 under
[ADR-007](adrs/adr-007-lightweight-formal-methods-policy.md): repetition,
re-entry, concurrency and replay alter stateful control semantics. The accepted
design needs an explicit abstract state machine and invariants, with typed
contract coverage and targeted property/differential evidence where useful.
TLA+ or Alloy is recommended for these risks, not an unconditional tool mandate.
This preflight does not substitute for that model or its evidence.

Use [ADR-085](adrs/adr-085-participant-information-flow-and-control.md),
[ADR-095](adrs/adr-095-participant-decision-epoch-state-cut-and-delivery-semantics.md),
[ADR-104](adrs/adr-104-runtime-control-plane-architecture.md) and
[ADR-108](adrs/adr-108-modular-participant-control-and-governed-effects.md) as
the surrounding boundaries. Permission, proposal, supervisory decision,
admission, execution, delivery and observation stay distinct. A policy graph
does not schedule itself. Existing [workflow semantics](../../specs/formal/workflows/state-machine.md)
already separate declarations from lifecycle/outcome/attempt state; reuse that
distinction without reusing workflow DTOs as participant state or adding a
second workflow engine.

The extension seam belongs at the policy-to-occurrence binding: explicit
semantic revision, permitted transition identity, occurrence-specific target
bindings and a typed order/validity basis. The next cycle supplies fresh
coordinates without editing the policy. The accepted decision must explicitly
choose whether finite scripted authoring remains supported and how it is
identified. If retained, scripted sequence constraints govern applications of
policy; they must not create another mediation path. If not retained for new
authoring, legacy scripts still need an explicit reader/migration policy.
Do not infer reusable versus scripted meaning from missing fields, magic
revision values or graph topology. Keep unsupported order strategies closed;
a future causal-order variant needs governed semantics, not an open metadata
map. Reusable permission does not imply unlimited automatic firing or retries;
existing episode/resource and modular causal budgets still apply.

## Findings the semantic decision must resolve

Package paths below are relative to `implementations/python/packages/`.

| Current coupling | Required guardrail |
| --- | --- |
| `raes/participant_behavior_specification.py::MixedControlTransition` fixes revisions, order and proposal links; `MixedControlParticipantOperation` validates established revision pairs. | Separate graph validity from occurrence continuity. Merely returning to a named state cannot reset its revision. State identity, state revision, proposal revision, occurrence revision, policy revision and history head are different coordinates. Define whether every accepted control kind advances state revision, including a same-state transition; the current fold advances for all accepted kinds. |
| `raes_contracts/contracts/participant_control_validation.py` indexes declarations by `(declaration_ref, participant_address, episode_id)` and requires exact order/revision equality. | A reusable declaration cannot supply different occurrence coordinates under that key. Keep one policy identity and a separately validated occurrence context; do not generate synthetic policy edges per visit or overwrite declaration indexes. Occurrence context must come from trusted policy/history resolution, not caller-supplied assertions. |
| API-409 proposal and typed-target indexes admit one meaning/revision/scope per identity. `raes_runtime/participant_control_targets.py` also projects accepted lifecycle facts. | Explicitly define identity and revision scoping for repeated proposals, decisions and targets. Never treat a reusable transition reference as a proposal occurrence. Fresh proposals cannot inherit a previous cycle's approval; changed inputs under the same identity conflict. Preserve transformation provenance and markings. |
| ACT-617 authoring requires an external direction to name a proposal; API-409 directions target proposal, action or control, and interventions target action, control or attempt. | Reconcile the target sets explicitly in ACT-617/API-409/RUN-310 and DSL-142. Do not silently broaden authority, erase typed targets, or fabricate proposals to conceal disagreement. |
| DSL-142 repeats order, validity, authority and evidence from the authored transition; its validator binds the destination controller, while RUN-310 derives the occurrence actor from the source controller. | Define the acting controller versus resulting controller for each kind and any permitted controller change. Bind each directed delivery to its actual authorized control occurrence, preserving the inject/event/script/story identity and participant observation/evidence requirements. A declaration reference alone cannot establish which repeated occurrence authorized delivery. |
| `_verify_delivery_control_time` compares `(control_effective_order, 0)` with temporal ticks. RUN-310 tests an authored order against authored windows. | Do not carry this implicit order-to-time conversion into reusable semantics. Specify the trusted coordinate source and scope, inclusive/exclusive endpoints, expiry/revocation evaluation and the decision/commit cut. Preserve the distinction between declaration consistency and live validity. |
| API-409's base model requires effective order to lie within its interval even for rejected occurrences; the runtime copies declaration coordinates into rejection records. | Define a representable rejected-attempt record that distinguishes attempted and evaluated coordinates without asserting validity or advancing accepted state. Rejected attempts cannot become usable proposals, targets or satisfied predecessors. Do not silently reinterpret historical rejected records. |

### API-409 carrier and consumer guardrails

Keep `ParticipantRuntimeBaseEnvelopeModel` embedded exactly once. Its event
identity, actor/producer distinction, timestamps, ordering basis, predecessor
refs, provenance, evidence and markings remain shared authority. New control
coordinates belong on the owning control contract, not on every runtime
event or an undifferentiated external-input envelope. Payloads remain
references/digests; resolving one must not imply permission to disclose it.

Disposition needs an explicit eligibility rule: API-409's
`_register_record_targets` indexes every disposition except `rejected`, while
RUN-310's `participant_control_targets.py` exposes only `accepted` records.
Define which dispositions can be referenced as historical facts, authorize a
new request, and advance controller state. These are different predicates;
neither presence in an index nor a non-rejected disposition grants permission.
An accepted denial is a successfully recorded denial, not proposal approval.
Cancellation and override append facts; they never rewrite the old disposition.

`validate_participant_control_occurrence_context` pre-indexes the entire
batch. Its typed-target check establishes kind, revision and participant/episode
scope, not target availability at the evaluated cut. Approval additionally
checks proposal order and a predecessor link, but those checks do not define
every control kind's causal rules. An existing-target relation must resolve at
the admitted cut, not merely somewhere in the batch; self/future/cyclic
dependencies cannot supply authority. Prospective replacement or completion
obligation references need their own explicit meaning. `known_targets` must
remain an independently trusted projection. Extend the owning contextual
validator and RUN-310 resolution together; do not copy a state machine into
HTTP handlers, conformance dispatch or API-424 adapters.

Specify conflicting approval/denial, override and cancellation eligibility
against the exact proposal/decision revision. Distinct decision IDs alone do
not resolve contradictory decisions. The decision must say when an earlier
approval ceases to authorize progress, without erasing that historical fact.
Replay/import must validate the history with pinned policy and cut context;
snapshot shape, contiguous append revisions and an intact stored digest do
not alone prove authorized state continuity.

The consumer intersection constrains the extension seam. API-424's
`ControlHandoffEffectModel` requires a changed controller; a same-state control
occurrence must not be mislabeled as handoff. Its `ControlRef` bounds length
and characters, and `ControlCount` requires a strict integer no greater than
1,000,000, while API-409's current integer aliases have no such upper bound.
Define supported coordinate ranges and explicit exhaustion at these joins;
never truncate identities, wrap revisions or relax a consumer validator to
make a cycle fit. SEM-233's `_validate_control_binding` joins by event ID and
checks occurrence revision and related identities: returning to the same state
or target must not coalesce two occurrences into one flow binding.

Concurrency must retain exact expected state, current controller, policy
revision, target revision and relevant history heads. Define who establishes
the admitted total order and at which atomic boundary; HTTP arrival, lock
acquisition, dictionary order and wall time cannot silently become semantic
precedence. Ordered contenders are revalidated after the first accepted
transition. Ambiguous ordering fails closed, and a stale contender cannot be
made valid by substituting the new revision. Define rejection's effect on the
order coordinate separately from its append position.

The authorization check must describe the **acting** controller and the grant
allowing this kind of transition at its pre-state. A destination controller
cannot authorize its own takeover merely by appearing in the destination
state. Initial and resulting authority must independently satisfy the existing
agent anchors and scope rules; any supervisory exception needs explicit
semantics within those owners. Include policy/authority changes in the trusted
cut revalidated at commit so a grant cannot be revoked between check and use.
Completion evidence must bind the particular handoff and its declared
completion condition; a caller-supplied reference alone proves neither a
controller transfer nor a backend effect.

The [shared time model](../../specs/formal/time-model/README.md) owns clock
authority, domains, segments, ticks/microsteps and explicit mappings.
Occurrence order is not automatically a clock, elapsed duration, workflow
attempt count or episode turn. Clock reset/replay creates a new segment;
unmapped domains are incomparable. If temporal validity is supported, reuse
`raes.time_model`, its validator/compiler, `raes_contracts.contracts.time_model`
and `raes_runtime.time_coordinator`; no mixed-control clock or timestamp
taxonomy is warranted. An order-window limit must not claim wall-clock expiry.

RUN-310 currently folds accepted history per episode from revision zero but
uses `occurrence_revision = len(participant_history) + 1` across episodes and
rejections. Preserve that historical distinction. State reconstruction must
use retained occurrences and their pinned historical policy, never the latest
policy's rewritten edges. Non-handoff v1 records rely on compiled transitions
for resulting state; retain that dependency rather than inventing past data.
Declare policy replacement behavior and old-policy replay explicitly; do not
apply a new policy in the middle of an episode by address coincidence.

Episode admission, terminal state, reset and restart belong to
`raes_contracts/participant_episode.py`, `participant_episode_snapshot.py` and
`raes_runtime/participant_episode_control.py`, under
[ADR-013](adrs/adr-013-participant-episode-lifecycle-boundaries.md).
The new semantics must say which established episode states admit control,
how initial authority is established, and how a new episode binds policy.
An arbitrary caller-supplied episode id is not proof of initialization.
Reject cross-episode proposal/approval reuse. Process recovery reconstructs
the existing episode; it does not create a fresh episode or permission to
repeat external effects. Distinguish history reconstruction, idempotent request
retry, semantic clock replay and a new experimental trial.

Repetition also changes the resource risk: current mediation folds, validates
and copies growing histories on each submission. Define admitted work/history
bounds and explicit exhaustion behavior with the existing resource owners;
do not truncate authoritative history or reset budgets to make cycles cheap.
Any derived index must be reconstructible and tied to the store revision.
Reusable policy does not establish bounded replay cost or justify a new store.

### RUN-310 runtime and effect boundaries

Keep one occurrence evaluator across the existing entry paths. Their different
commit sets are intentional; a reusable-policy change must preserve each:

| Entry path | Existing boundary and required preservation |
| --- | --- |
| Direct supervisory intent | `participant_control_mediation.py` binds trusted policy, resolves targets, validates candidate history and claims the operation before `commit_control_transition`. Preserve the occurrence, terminal operation and actor-bound audit as one commit. |
| Governed control ingress | `participant_crossing_boundary.py` uses `admit_ingress_sinks` and rebinds any transformed intent before `prepare_participant_control_transition`. Preserve subject agreement and the atomic control/crossing/API-424 evaluation histories through `commit_participant_transition`; do not route reusable policies around those gates. |
| Separately admitted handoff effect | `participant_control_effects.py` binds the API-424 effect to its owner input and submits through `record_participant_control`. Preserve current-cut owner admission, durable effect/owner claims and append-only realization evidence. Committing a parent evaluation is not completing its handoff. |

The following distinctions are required by those joins:

- **Retry identity is not a visit counter.** `control_plane_store.py` owns
  `require_idempotency_key`, `idempotency_claim_identity` and replay checks.
  Its claim key is `(actor, operation kind, client key)` inside an admitted
  target/run store; participant and episode are request commitments, not
  additional key namespaces. Reusing that key for another episode therefore
  conflicts. `client_correlation_id` is currently fingerprinted intent, not a
  separately enforced uniqueness ledger. Specify any stronger semantics
  explicitly; do not weaken the existing claim scope to enable repetition.
  Direct mediation currently prepares candidate history before claim lookup.
  The revised binding must let an authorized exact retry resolve its retained
  receipt without requiring a new policy occurrence to be valid at today's
  cut, and without bypassing current receipt-access authorization.
- **A fresh occurrence need not be a fresh logical effect.** API-424 keys
  already include run, trigger root, rule id/revision, slot and firing epoch.
  `participant_control_receipts.py` and `participant_control_causal_state.py`
  retain their claims and consumption. A repeated handoff must explicitly
  bind the appropriate firing epoch and occurrence coordinates; a new
  evaluation id or attempt cannot reuse an applied receipt as proof of another
  transfer or reset a root's budget. Do not replace these keys with the
  reusable policy-edge identity.
- **Drain authority is not effect authority.** Reuse `require_drain_authority`
  and `origin_principal`: the caller requesting dispatch cannot lend its
  privileges to the effect. The originating principal's scopes are retained
  from admission; current code has no principal registry to re-resolve them.
  Define controller grant revocation/expiry at the owner cut separately from
  this retained principal scope. Retroactively withdrawing admitted effects
  on principal revocation would be a change to the
  [existing effect contract](../explain/reference/modular-participant-control-contracts.md),
  not an incidental consequence of reusable policies. Uncertain dispatch
  remains subject to `control_plane_recovery.py`; never retry it as a fresh
  cycle to escape an indeterminate operation.
- **Execution outcome has its own authority.** `OperationReceipt.accepted`
  can be true for a rejected control attempt. Read the owner's terminal status
  and occurrence disposition; an accepted denial still authorizes no action.
  `participant_control_targets.py` retains historical action/admission/attempt
  targets with revision 1, so target existence does not prove current stage
  or cancellability. Resolve effects against the lifecycle at the admitted
  cut; cancellation/override cannot revoke an already delivered observation
  or manufacture backend acknowledgment.
- **Provider transfer is not controller transfer.**
  `mixed_runtime_phase.py` appends a composition `handoff` alongside phase
  progression; that record alone does not append a RUN-310 controller-state
  transition. Preserve SEM-234's allocation, quiescence and forward-phase
  bounds and its explicit control-event link. Repeated controller cycles do
  not authorize provider fallback, phase rewind or a new episode.

Keep the shared `RuntimeMutationAuthority` and its
`external_control_plane_call` fence around resolver/provider callbacks,
including `fenced_validation_context`. A reentrant callback must not advance
the state cut while its enclosing request is being validated. HTTP calls keep
`control_plane_api/_offload.py`'s bounded admission, asynchronous reservation
and worker-settlement behavior; client disconnect/coroutine cancellation does
not mean RUN-310 cancellation or rollback of a durable mutation. No second
participant queue, controller lock, retry worker or cancellation engine is
warranted by reusable policy.

### DSL-142 delivery bindings and repeated occurrences

Retain the participant-local `ParticipantInjectDelivery` relation and typed
`ParticipantInjectDeliveryRuntime` compiler child. The
[original DSL-142 preflight](issue-797-dsl-142-participant-inject-delivery-preflight.md)
still explains its authoring boundary; its statements about future runtime
work are historical. Current API-423/RUN-319 and API-424/RUN-320 already own
governed crossings and inject effects. Extend their joins, not a new delivery
service, receipt schema, transition registry or orchestration plan domain.
Compiler metadata does not itself schedule or perform those operations.

Keep these identities separate: the DSL-111 inject and event/script/story
anchor, the participant delivery declaration, the reusable control-policy
edge, its API-409 application, and the actual delivery/observation occurrences.
The authored `occurrence` triple establishes narrative membership; it carries
no episode, runtime firing identity or control occurrence revision. A repeated
edge therefore cannot identify a delivery by itself. Preserve one addressee
per binding; fan-out uses separate bindings, authorization and evidence.
Absence of a binding remains environment-only. An explicit binding discloses
only its governed result item, not the inject body or its environment effects.

The extension seam is the existing delivery-to-control relation: pin the
semantic interpretation and control-policy edge, then resolve application
identity/revision, participant/episode, typed target, authority, state cut and
delivery occurrence through their owning contracts. Authored reusable
constraints cannot contain fictitious future receipts. Define whether an
application permits one delivery or multiple explicitly identified deliveries,
and what consumes that permission. Repetition of control does not automatically
repeat the narrative schedule, disclose the same item again, or re-execute
environment effects. A new API-424 inject effect requires its own DSL-111
occurrence under ADR-108; retain the original declaration as provenance.

The following existing joins constrain that seam:

| Observed coupling | Required decision or guardrail |
| --- | --- |
| `_verify_delivery_control_identity` equates `delivery_policy.policy_revision` with the mixed-control policy revision. | Projection/disclosure policy and control policy are different authorities. Specify their independently pinned identities/revisions and required agreement at the evaluated cut. Equal version strings prove neither policy identity nor authority. Preserve the old equality rule for historical interpretation; do not silently repurpose its field. |
| Delivery controller/scope/evidence bind the target controller state, while RUN-310 acts from the source state. | Specify the acting and resulting controller for direction and intervention, including any state change, using the common occurrence semantics above. Never let receipt of an instruction confer authority on its sender or recipient. Disclosure-only bindings continue to exclude control fields. |
| `_verify_delivery_control_bounds`, `_verify_delivery_control_time` and `_verify_delivery_control_evidence` copy fixed order/windows/evidence from a transition and target state. | Split reusable constraints from actual application facts. Resolve time domain, clock and segment before comparing coordinates; retain the delivery window independently of control eligibility. Required control evidence, delivery evidence requirements and produced receipts must each retain their own meaning. Static refs cannot prove a new cycle completed. |
| `_verify_delivery_observation` checks authored view rules; several policy/audience refs are opaque strings. | Static consistency is not effective authorization. Reuse SEM-226 exposure resolution and SEM-230/ADR-095 policy-at-cut semantics for the exact result, audience and delivery. Revocation, changed markings, transformation or a later observation cut cannot be waived by an earlier valid declaration. Preserve influence/provenance through the final sink. |
| API-424 `ControlInjectEffectModel` requires a fresh result identity; DSL-142 permits `source_item_ref == result_item_ref`. | Declare the compatibility boundary for ordinary disclosure versus a newly produced inject result. Do not weaken the effect validator, rename a source as proof of transformation, or silently reject legacy SDL that never requested that effect. |
| `participant_control_resolution._validate_inject` compares the authored delivery digest and raw participant/inject/anchor/item/disclosure refs with the effect. RUN-320 `_inject_bindings` additionally binds the view result, episode, cut and projection. | Preserve both contextual joins. Define the authored-ref to compiled-address mapping explicitly; the DTO field name `participant_address` does not normalize an authored agent ref. Digest equality binds content, not authorization. Bind the chosen control application as well as the owning delivery; do not infer it from the latest event with the same edge or controller. |

`ParticipantControlValidationContext.inject_deliveries` is already the trusted,
non-wire resolution seam. Providers must not supply their own authoritative
delivery, policy, evidence or history indexes. Reuse `control_digest` and the
existing artifact projection rules; API-424 hashes the full authored delivery,
whereas some occurrence digests exclude unset optional fields. A new semantic
pin or coordinate changes that commitment and must be handled by the existing
compatibility/publication rules, not a second digest implementation.

The live owner path is
`participant_control_effects.dispatch_participant_control_effects` →
`ParticipantRetrievalMixin.deliver_participant_directed_view` →
`participant_crossing_egress.serialize_participant_view`. Preserve authenticated
target/role checks and `ParticipantAudienceSubjectBinding`, independently of
`ParticipantControlSubjectBinding` and semantic controller grants. Reuse
`participant_crossing_policy` and `resolve_participant_feature_support` for
`participant_directed_inject_delivery`, egress/transformation and any other
applicable capabilities. Required semantics fail closed when the exact owner
or support is unavailable; a general environment inject is not a fallback.

Egress keeps exact subject/digest and policy resolution, SEM-233 final-sink
checks, API-424 composition, trusted transformation revalidation, and atomic
crossing/operation/audit commit before returning the governed view. The
current directed-view owner accepts a `ParticipantStatusViewModel`; this does
not establish a generic payload transport or an automatic executor for all
compiled DSL-142 bindings. No new route, config, environment binding or backend
dispatch is warranted merely to publish the reusable semantics.

State what evidence the existing owner actually records. Delivery-attempt,
delivery and observation records in `_with_opacity_egress_observation` are
conditional on opacity enforcement; an operation receipt alone does not
satisfy every DSL-142 evidence requirement. Reuse API-423's distinct stage
records and contextual validation and SEM-226's realized-exposure contracts.
Any emission-is-delivery/observation basis must be explicit under ADR-095;
successful serialization proves neither remote acknowledgement nor human
consumption. Control admission, delivery and observation can fail separately.
A subsequent delivery failure cannot erase an accepted control occurrence;
where delivery is a required predecessor, preserve RUN-320 withholding and
fresh revalidation instead of claiming a cross-system atomic transaction.

Authored refs still pass `_mapping_scopes`, `_declarations`,
`composition/_behavior.py::_rewrite_participant_inject_delivery`, instantiation,
`SemanticValidator` and compiler alias/address resolution. Namespace external
refs while keeping binding/edge IDs local; pin external policy references
without inventing module-local policy declarations. Re-admit after variable
substitution. Preserve typed metadata and every dependency, including
`compiler/time_model.py`'s delivery-subject mapping; `spec` is not runtime
authority or a place for payload/credential data. Some legitimate semantic
evidence refs have no runtime resource address (the directed-delivery test
uses an entity ref); retain those refs rather than dropping their meaning or
inventing executable resources. Conversely, source/result items required to
compile to an address must resolve uniquely, with a bounded diagnostic on
failure rather than an unchecked index into an empty address list.

DSL-142 is currently embedded in **five** published schemas: SDL authoring,
instantiated scenario, instantiated snapshot, materialized scenario and
satisfiability evidence. The older preflight's four-schema inventory predates
materialization. Reuse schema-bundle/publication checks and
`tools/check_sdl_catalog_parity.py`, including the normative sections/reference
tables; changing only the Python declaration leaves other ingress paths stale.
Model closure, semantic admission, compiler dependencies and live contextual
admission have different responsibilities; none replaces the others.

### Minimal repeated-cycle witness

This is a semantic acceptance witness, not proposed SDL syntax. For one
participant, episode and pinned policy, let `A` mean self-controlled and `B`
mean controlled by a declared supervisor. The same two permitted handoff
edges must support the following, with valid grants and occurrence-specific
completion evidence at every application:

| Policy edge | Fresh occurrence | Exact pre-state | Accepted post-state | Control order |
| --- | --- | --- | --- | --- |
| `A → B` | `h1` | `A, revision 0` | `B, revision 1` | 10 |
| `B → A` | `h2` | `B, revision 1` | `A, revision 2` | 20 |
| `A → B` | `h3` | `A, revision 2` | `B, revision 3` | 30 |
| `B → A` | `h4` | `B, revision 3` | `A, revision 4` | 40 |

The order values belong to a declared control-order domain, not time ticks.
The incumbent fixed edge for `h1` cannot admit `h3`: its expected revision is
still zero. A correct repair changes where occurrence coordinates are bound,
while retaining the exact revision check. A competing request expecting
`A, revision 2` after `h3` is stale even if `h4` later restores state `A`.
Rejection leaves accepted state unchanged and may append a rejected fact;
history position then diverges from accepted-state revision.

An equivalent authorized retry of `h1` must return its original receipt;
changed content under the same request identity conflicts. Reuse the existing
idempotency claim authority to distinguish a retry before treating it as a
fresh occurrence; rebuilding it against today's policy must not turn it into
a new transfer. A fresh cycle uses fresh proposal/decision identities as well
as fresh control occurrences. A finite script authorizing only `h1` and `h2`
must still forbid `h3` after migration.

For DSL-142, add two permitted direction/intervention applications `c1` and
`c2` of the same edge after re-entry, each with its exact pre-state revision,
target, authority and order. Bind delivery `d1` to `c1` and `d2` to `c2`, retaining
their inject/event/script/story provenance. Using `c1`'s completion evidence
to claim `c2` completed, or a `d1` receipt to claim `d2` was delivered, must fail
even when the edge, controller and payload are identical. Shared policy/grant
refs may remain shared; their occurrence-specific satisfaction cannot.
An authorized exact retry of `d1` resolves its retained result;
changed content under that retry identity conflicts. A newly attempted `d2`
must fail if its disclosure policy was revoked after control admission, and
that failure does not undo `c2`. A second participant, a new episode, an
expired delivery window or a different clock segment cannot inherit the old
authorization. A disclosure-only delivery still needs no control transition,
and an unbound environment inject creates no participant occurrence.

## Cross-cutting layers and canonical incumbents

These are requirements on the intended design and downstream implementation,
not assertions that all current code already enforces the revised semantics.

| Layer | Incumbent and required satisfaction |
| --- | --- |
| SDL bytes, shape and identities | `raes/parser.py`, `_yaml_loader.py::load_sdl_yaml`, source limits, structural/map-key normalization, `SDLModel` and `_identifiers.PortableIdentifier`. Keep duplicate/canonical-key rejection, closed shapes and variable-key restrictions. New nested maps must be classified in `_mapping_scopes.py`; no raw-dictionary compatibility bypass. |
| Semantic authority and references | `SemanticValidator`, `DeclarationIndex`, `validator/_mixed_control.py`, `_participant_inject_deliveries.py` and `_participant_relationships.py`. Resolve exact domains and aliases; retain mode/policy co-presence, one controlled participant, controller authority anchors, behavior scope and controller operating scope. Reconcile the source/destination authority checks and compare resolved identities, including `self`. A role or policy label cannot grant authority. |
| Composition and compilation | `raes/composition/_behavior.py`, `raes_processor/compiler/_mixed_control.py`, `participant_inject_deliveries.py`, `models/behavior_resources.py`, existing compiled-address and dependency helpers. Rewrite external refs during namespacing while retaining local IDs; compile deterministic typed children under the behavior owner. No top-level controller registry or raw `spec` authority. |
| Portable ingress and contextual validation | `ContractModel`, shared scalar types, `ParticipantRuntimeBaseEnvelopeModel`, discriminated API-409 variants and `validate_participant_control_occurrence_context`. Use `raes_contracts/json_ingress.py::parse_bounded_json_object` at applicable serialized boundaries; preserve byte/depth/duplicate/non-finite checks and HTTP size limits. Model closure alone does not establish strict numeric types, bounded inputs or trusted joins. Keep Python and JSON Schema constraints aligned, including direct in-process callers. |
| Authentication and authorization | `ControlPlaneSecurityConfig.strict_defaults()`, `control_plane_api/_auth.py`, `ParticipantControlSubjectBinding` and `participant_control_mediation.py`. Authenticate the principal and authorize target/role/subject before mutation or receipt disclosure; then independently resolve controller/authority/scope from admitted policy and current state. Retain caller-intent DTOs in `participant_control_intents.py`; clients cannot submit an accepted occurrence or grant themselves a subject binding. `actor_ref` remains the semantic controller; operation/audit identity remains the authenticated principal. |
| Crossing, flow and effect admission | `raes_runtime/participant_crossing_boundary.py`, `participant_flow_sink.py`, `participant_control_orchestration.py`, `raes_contracts/contracts/participant_flow_control_incumbent_validation.py` and `raes_contracts/participant_binding.py`. Preserve exact-cut API-423/SEM-233 joins, mandatory modular constraints and final-sink checks. API-424 effects and SEM-234 mixed-runtime handoffs consume the occurrence; update their joins under the same authority. Approval, provider permit or handoff cannot bypass action admission or erase influence. |
| Configuration, secrets and host exposure | `ControlPlaneOptions`/`ControlPlaneConfiguration` own runtime options, profile and normalized run scope; `ControlPlaneSecurityConfig` validates/fixes identity maps and header names. This semantic change needs no new config bag, environment binding, token source, CLI flag, subprocess, socket or host privilege. Controllers/evidence refs must carry no credentials or executable selectors. If later realization uses environment values, keep `RuntimeEnvironmentVariable` name/classification/source-exclusivity checks and `enforce_observed_value_redaction`; secret refs use `raes_contracts.secret_references.SecretReferenceId`. Never put credentials in argv, shell interpolation, authored policy, snapshots, evidence or diagnostic output. Host/provider isolation remains with the existing backend boundary. |
| Errors, audit and visibility | `SDLParseError`/`SDLValidationError`/`SDLInstantiationError`, compiler/runtime `Diagnostic`, existing operation dispositions, `AuditEvent`, `_participant_routes.py` coarse 403/409 responses and `_operation_routes.py` redacted 422/500 handlers with bounded rejection audit. Preserve stable reason codes, sanitize messages/addresses, and avoid raw Pydantic input, exception text or payload dumps. Diagnostic shape validation is not redaction. Keep operational logs, participant-visible projection and experiment evidence distinct under ADR-066; no new exception hierarchy or logging channel. |
| Persistence, concurrency and recovery | `RuntimeSnapshot.participant_control_history`, `raes_contracts/participant_control_history.py`, `control_plane_mutation`, `operation_admission_context`, canonical request commitments and store idempotency claims. Reuse `ControlPlaneStore.commit_control_transition`/`commit_participant_transition`, snapshot revision comparison, expected heads, actor-bound atomic audit/record commits and memory/local-store parity. Retain the P1/P2 single-owner lease and target/run scope. No sidecar controller database, snapshot metadata history, independent lock-only authority or multi-writer claim. Commit failures expose no partial accepted state; recovery never blindly redispatches effects. |

Three implementation traps need explicit treatment at those layers:

- **Ingress is not uniformly strict today.** `ParticipantControlIntentBase`
  uses coercible integers, as do API-409's shared integer aliases; SDL uses
  `StrictInt`. Pin the new semantic boundary's scalar rules and exercise
  boolean/string revision inputs without changing legacy readers implicitly.
  The HTTP route currently accepts a FastAPI-parsed intent;
  `RequestSizeLimitMiddleware` limits bytes but does not apply
  `parse_bounded_json_object`. Reject ambiguous raw JSON before duplicate keys
  are lost, with explicit byte/depth limits using that shared parser. Do not
  claim these protections merely because the helper exists elsewhere.
- **Construction gates still apply.** `control_plane_composition.py` admits
  crossing resolvers, final-sink enforcement and modular bindings;
  `control_plane_profiles.py` and `control_plane_store_compatibility.py` own
  profile and atomic-store admission. Unsupported capabilities must fail
  closed, not select an older interpretation. P0/P1 trust the embedder for
  authentication; constructing `ControlPlaneIdentity` does not authenticate
  external input. P2 retains exact target binding, role checks, explicit
  proxy trust and bearer-token failure without proxy fallback.
- **Durable bytes cross another boundary.** Retain snapshot model/history
  validation, `control_plane_store_snapshots.py` round trips and the local
  codec's integrity checks. `control_plane_store_paths.py` and
  `control_plane_store_lease.py` own private filesystem paths, SQLite sidecars
  and process ownership. A new policy pin must survive these existing paths;
  it must not introduce an unvalidated side file or a second store. Host TLS,
  proxy header stripping, secret loading and worker configuration remain the
  embedder's responsibilities under ADR-104.

General DSL-111 injects may affect an environment without a participant.
DSL-142 adds a declared addressee and, for direction/intervention, explicit
control agreement. Neither a general inject, an authenticated external
principal, an MCP endpoint nor a provider becomes a participant/controller by
this change. Keep controllers as `self` or declared agents; independent
non-participant supervisory authority would need a separate justified design.

## Compatibility, publication and evidence boundaries

The eventual issue delivery must amend the canonical statements/rationales and
traceability in `docs/requirements/{ACT-617,API-409,RUN-310,DSL-142}/requirement.md`
and reconcile their normative owners: the ACT-617 section in
`specs/formal/participant-behavior-model/README.md`, SDL sections/reference
tables and the owning API/runtime semantic contracts. A research note or ADR
alone cannot amend those requirements. Existing ACTIVE status and old tests
do not demonstrate the new behavior. The old #251/#252/#255 guidance records
the earlier fixed-transition design; do not copy its constraints or historical
package names as the new contract.

The accepted decision must give producer/reader and persisted-history
compatibility rules for legacy scripted declarations, new reusable policies,
v1 occurrences, snapshots and mixed histories, including unsupported-reader
failure. Preserve old identities, order, dispositions, revisions and evidence;
never relabel historical occurrences as new semantics. Any conversion of old
authoring must preserve its finite constraints and reject ambiguous/lossy
cases. Do not silently turn a finite script into unbounded permission. Define
whether live upgrade is supported; durable state alone does not imply it.

Use [ADR-061](adrs/adr-061-published-schema-evolution-policy.md) and
`specs/evolution/versioning-deprecation-and-migration.md`. The current
`participant-control-occurrence-v1` publication is **draft**; a filename suffix
does not confer stability, and draft status does not waive this issue's
historical-meaning requirement. Use an explicit semantic discriminator/pin
and reader boundary where interpretation changes. Policy revision, wire
version, schema lineage, publication hash and store version are not synonyms.

Downstream publication must account for embedded schemas as well as direct
ones: SDL authoring, instantiated scenario/snapshot, materialized scenario,
satisfiability evidence, participant-control occurrences and runtime snapshots.
Check API-423, SEM-233/API-424 and mixed-composition consumers rather than
assuming their existing reference fields prove compatibility. Reuse
`contracts/schema-publication-manifest.json`'s per-contract records under
`contracts/schema-publication/entries/`, `last_change` hashes and removal
tombstones, plus `schema_bundle()`, `tools/check_generated_schemas.py`,
`tools/check_schema_publication.py` and schema coverage/catalog checks.
`contracts/schema-publication/README.md` documents the current split registry;
do not replace it with another ledger. Accepted ADR edits require ADR-059
amendment rows and pins. This preflight adds no ADR or publication change.

Worked acceptance cases must expose a second cycle in the **same** episode,
same-state control, two contenders with the same expected revision,
identical retry versus changed-content conflict, old-proposal approval,
expiry/revocation, unauthorized controller, directed delivery joined to the
wrong repeated occurrence, terminal/reset/new-episode boundaries and replay
with the original policy after a policy update. Include finite-script
compatibility, disposition eligibility, future-target/contradictory-decision
cases, consumer coordinate bounds and failed atomic commit/crash cases.
State the support limits;
cycles do not prove liveness, exactly-once external effects or cancellation.
The current cancellation-effect classifier derives an outcome from target
kind; it is not backend acknowledgment and must not become stronger evidence
in the revised semantics.

Reuse `test_act_617_mixed_control.py`,
`test_api_409_participant_control_occurrences.py`,
`test_run_310_supervisory_lifecycle.py`,
`test_dsl_142_participant_inject_delivery.py`, their published fixture families,
shared-time tests and existing final-sink/mixed-runtime/store tests. Schema
acceptance and contextual rejection need separate evidence: the API-409 entry
in `raes_conformance/conformance/validators.py` currently invokes model
validation, not the declaration/history contextual join. No parallel harness
or text-presence test can establish occurrence semantics.

For RUN-310, retain the memory/local-store witnesses in
`test_run_310_supervisory_lifecycle.py` and the #1003 final-sink, #1016
mixed-runtime and #1069 orchestration/effects/durability families. The revised
semantics need witnesses at each entry path above, including a repeated
handoff with a fresh logical effect versus replay of the old effect, a drain
by a different principal, callback re-entry, and restart between owner commit
and realization recording. Assert terminal status, exact histories and zero
prohibited dispatch/disclosure, not merely `receipt.accepted` or HTTP success.

For DSL-142, reuse the authoring/composition/instantiation and environment-only
cases in its existing test family, plus `test_api_424_control_resolution.py`,
`test_api_424_control_effects.py` and the RUN-319/#1003/#1069 families for live
joins. Cover namespaced refs, independent policy revisions, the same-result
compatibility boundary, transformed-result identity, differing clock domains,
missing delivery evidence and the repeated-delivery witness above. Existing
positive authoring tests do not establish live authorization or delivery.

`.ground-control.yaml`, `.gc/plan-rules.md`, `noxfile.py` and
`tools/nox_support/` remain the workflow owners; use targeted local checks and
the existing CI graph. This branch has no requirement UID in its name, so set
`RAES_REQUIREMENT_UID` to the requirement under review (`API-409` for the
contract preflight; `ACT-617` for authoring; `RUN-310` for lifecycle; `DSL-142`
for participant-directed delivery), and retain all four requirements in the
eventual issue scope. `tools/policy/` owns
module boundaries and the source-file cap; neither SDL nor portable contracts
should import runtime/store code to resolve occurrences. No new verification
script, release version edit or changelog is warranted.

Non-goals here are the accepted design and requirement amendments themselves,
executable SDL/DTO/runtime changes, schema publication, persistence migration,
backend cancellation/inject execution repairs, provider composition redesign,
new controller identity kinds, registration, a generic policy interpreter and
a new workflow/time engine. The upcoming #1351 delivery establishes semantics
and migration obligations; executable fulfillment requires its own scoped work
and evidence, not a claim that publishing the decision changed runtime behavior.
