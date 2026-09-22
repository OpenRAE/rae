# Reusable mixed-control policies and occurrences

Semantic decision: `mixed-control-policy-occurrence/rev1`, under
[ADR-110](../../../docs/decisions/adrs/adr-110-reusable-mixed-control-policies-and-occurrences.md).
This is the normative amendment for ACT-617, API-409, RUN-310 and DSL-142.
Its semantic revision is independent of the existing occurrence wire version,
policy revision, schema publication hash and store version.

This publication establishes the design contract. The current SDL, compiler,
API-409 v1 and runtime implement the earlier fixed-coordinate form; their
schemas and executable behavior do not acquire these semantics by publication.
The [migration contract](../../../docs/migration/reusable-mixed-control.md)
defines the required producer/reader boundary. The
[worked cases](../../../docs/research/reusable-mixed-control/cases.md) distinguish
abstract-model evidence from implementation conformance.

## MC-01 — Policy permissions and occurrence facts

An ACT-617 policy remains nested in one behavior specification and controls
exactly one declared participant. It pins a semantic interpretation, immutable
policy identity/revision, initial controller state, controller-state graph,
permitted edges, order strategy, validity constraints, evidence requirements
and conflict dispositions. Controllers remain `self` or declared agents;
`self` resolves to the controlled participant's canonical identity.

| Reusable permission | One application of that permission |
| --- | --- |
| Stable local edge identity and control kind | Fresh event/occurrence identity and its exact edge reference |
| Permitted source and destination controller states | Actual prior/resulting states and expected/resulting state revisions |
| Controller, authority-basis and non-widening scope constraints | Acting controller, resolved grant and scope at the evaluated cut |
| Required target kind and eligibility | Exact proposal/target identity, revision, episode and predecessor evidence |
| Order strategy and validity requirements | Admitted effective order/domain, evaluated validity bounds and clock coordinates |
| Evidence requirements | Evidence produced for this occurrence, provenance, markings and disposition |

A policy edge carries no fixed traversal number, future proposal identity,
future receipt, actual state revision or actual occurrence order. Static
evidence of policy establishment is distinct from evidence of its application.
Graph validation establishes references, authority constraints and supported
forms; it does not unroll a runtime history or fix how many visits occur.
The compiler preserves typed nested identities and dependencies, with one edge
per permission rather than synthetic edges for successive visits.

The revised closed ingress boundary requires exact integer coordinates: booleans,
numeric strings and lossy coercions are invalid revisions/orders. Preserve the
existing bounded JSON/YAML ingress, duplicate-member rejection before parsing
loses ambiguity, depth/byte limits and resolved portable identifiers. These
scalar rules must agree across authoring, wire, in-process and stored readers;
legacy readers keep their explicit historical interpretation.

## MC-02 — Reusable policies and finite scripts

The semantic forms are explicitly distinguished as **reusable-policy** and
**finite-script**. These are design-level discriminants, not new SDL syntax
accepted by the current parser. Neither missing fields nor graph topology may
select a form implicitly.

A reusable-policy permits any finite trace admitted by its edges and ordinary
authority, lifecycle, budget and validity gates. An edge never schedules itself.
Cycles authorize neither automatic firing nor an infinite execution.

A finite-script pins a finite ordered list of distinct step identities. Each
step names an edge and may narrow its target, exact revision, order and validity
constraints. It cannot widen the edge's authority. A committed application
must match the current step as well as the common occurrence relation. Only
acceptance advances the script cursor; rejection retains the step, and an
idempotent retry cannot advance it again. Exhaustion admits no further step.
Corrected submissions require fresh operation identities and ordinary retry
bounds; rejection itself schedules nothing. Repeated edge references are
expressible as separate explicit steps.

Thus a script containing `A→B, B→A` still permits only one cycle even when its
referenced graph is reusable. This reuses the existing
[workflow declaration/execution distinction](../workflows/state-machine.md),
without importing workflow DTOs, attempt counters, joins or a new scheduler
into controller state. Legacy fixed-coordinate authoring keeps its original
interpretation; conversion is subject to the migration contract.

## MC-03 — Exact state relation and repeated cycles

For one admitted target/run/participant/episode, let the accepted control state
be `C = (policy pin, state id, state revision, accepted order, script cursor)`.
Let `H` be the append-only occurrence history, whose head/append position is
separate from state revision. The trusted evaluation cut additionally binds
episode status, grants/revocation, target lifecycle, relevant crossing/effect
heads, shared-time coordinates and resource limits.

For a fresh request `q` and edge `e`, acceptance requires all of:

1. The episode is admitted and running; the semantic and policy pins match.
2. `q.expected_state = C.state = e.source` and
   `q.expected_revision = C.revision`, with exact relevant history/store heads.
3. The acting controller and grants satisfy MC-04; targets satisfy MC-05.
4. Order and validity satisfy MC-06; script and resource constraints hold.
5. Required occurrence-specific evidence is resolved and the atomic commit
   succeeds at the same cut. A changed grant, clock, target or history fence
   forces rejection or a new evaluation, never substitution of new coordinates
   into the original request.

The accepted successor is `C.state := e.destination` and
`C.revision := C.revision + 1`. **Every accepted control kind advances revision**,
including proposal, denial and same-state transitions. Returning to `A` at
revision 2 does not recreate `A` at revision 0. State identity, state revision,
proposal revision, occurrence revision and history head are separate values.

Rejection preserves accepted state, order and script cursor. A durable rejected
attempt may advance history append position, so it cannot be folded as a state
advance or registered as a usable proposal, decision or authorizing target.
All dispositions remain available as appropriately authorized historical
facts. Only an `accepted` occurrence is eligible for control-state advancement;
eligibility to authorize another operation additionally depends on kind and
current lifecycle. In particular, an accepted denial authorizes no action.

## MC-04 — Acting controller, authority and handoff

This revision retains the incumbent source-controller rule: the acting
controller is the resolved controller of the edge's **source** state. Its
authority bases must be declared by that agent, active at the cut, and valid
for the transition kind and affected targets. Controlled scope must be within
the behavior specification's authority scope, the controller's operating scope
and the resolved grant. Omitted or unresolved authority never widens scope.

Only a `handoff` changes the controller identity in this revised form; it must
change that identity and supply completion evidence for this exact transfer.
Other kinds may move between policy states with the same controller. A
destination controller's presence does not authorize its own takeover. Initial
and resulting controller authority must independently resolve and be valid.
No implicit supervisory exception or new delegation mechanism is introduced.
External supervision uses explicitly established controller state; behavior
mode and autonomous action execution are separate from who controls a
supervisory transition. Legacy approvals that also changed controllers retain
their old meaning and require an explicit author decision for conversion.

An authenticated principal must independently pass role, target/run and
participant/controller subject-binding checks. It is not the semantic actor.
Control-plane identities, credentials, provider processes, inject senders and
general external inputs do not become participant controllers. Receipt access
and participant disclosure have their own authorization checks.

## MC-05 — Targets, proposals and conflicting decisions

The following closed target meanings reconcile authoring, occurrence contracts,
runtime resolution and directed-inject bindings:

| Kind | Target meaning |
| --- | --- |
| proposal | Creates a fresh proposal occurrence; it targets no prior proposal by pretending an edge is an occurrence. |
| approval / denial | Exactly one live, unresolved proposal identity/revision. |
| external-direction | An existing proposal, action or control occurrence, as explicitly permitted by the edge. |
| intervention | An existing action, control occurrence or attempt. |
| handoff | Source/destination controller state and this transfer's completion evidence. |
| override | Existing control or decision occurrence; separately identified replacement and supersession relation. |
| cancellation | Existing proposal, decision, admitted action or attempt, with actual lifecycle and effect evidence. |

Existing-target relations must resolve at the evaluated cut, in the exact
participant and episode, with the required kind and revision. A later record
in an imported batch, a self-reference or a dependency cycle cannot satisfy
this obligation. Prospective replacement/evidence requirements are obligations,
not proof that their future targets exist. Trusted indexes come from the owner;
a provider or client cannot submit its own authoritative target index.

Within an episode a proposal identity has one immutable content/revision
binding. A changed or transformed proposal gets a fresh identity, preserving
its source identity/revision, transformation provenance and markings. Proposal
revision is not copied from controller-state revision. Every new control cycle
that proposes new work creates fresh proposal/decision identities.

Approval and denial are mutually exclusive resolutions of the same pending
proposal revision. A second distinct decision does not reopen that proposal.
Explicit override/cancellation may append a superseding fact only when its
current target lifecycle permits it. An approval ceases to authorize further
progress when superseded/cancelled, its proposal is replaced, its validity or
grant is no longer effective at admission, or its episode ends. Prior actions
and evidence remain historical facts. A direction to a proposal never doubles
as approval. Approval, direction and handoff still require independent action
admission, crossing/flow policy and execution gates.

## MC-06 — Order, concurrency and live validity

Retain the closed `total-effective-order` strategy. Its domain is explicitly
bound to the admitted participant/episode and pinned policy. The admitted
ordering authority supplies each candidate's coordinate; HTTP arrival, lock
acquisition, map order and host timestamps are not undeclared tie breakers.
An unsupported strategy or ambiguous group has no winner and fails closed.
When distinct admitted coordinates order competing requests, evaluate in that
order against the newly committed cut. After one advances revision, another
request at the old revision is stale; never automatically rebase it.

Accepted effective order increases strictly. A rejected attempt records its
attempted coordinate and evaluated cut but does not consume an accepted-order
position. Its independent append sequence can increase. This makes a stale or
out-of-window attempt representable without asserting a valid application.
Ingress failures that cannot be safely bound to an admitted participant/episode
remain bounded operation/audit rejections, not invented participant facts.

Order-window endpoints are inclusive and interpreted only in their named
control-order domain. They do not claim elapsed-time expiry. Temporal validity
uses the existing [shared-time model](../time-model/README.md): exact clock,
domain, segment, tick and microstep coordinates, with inclusive window endpoints
and explicitly admitted mappings. Order is never implicitly converted to a
tick. Unmapped domains and invalid/reset segments cannot satisfy a window.
Where both constraints apply they conjoin, and current grant revocation defeats
either. Resolve coordinates and grants from trusted owners at the decision and
commit cut; authoring consistency alone proves no live validity.

API-409 rejected-attempt semantics must preserve both attempted coordinates
and the observed current cut, reason and no-state-change result. They must not
copy fictitiously valid coordinates into the accepted-occurrence shape merely
to make validation pass. Historical v1 rejections are not reinterpreted.

## MC-07 — Commit, retry and evidence

Reuse the existing owner evaluator and commit boundaries for direct control,
governed control ingress and separately admitted API-424 handoff effects.
Occurrence, resulting state, operation/idempotency record and actor-bound audit
commit atomically with the relevant crossing/evaluation histories. A failed
commit exposes no accepted transfer. Callback re-entry cannot change the cut;
client disconnect does not establish rollback or participant cancellation.

The existing operation claim key is `(principal, operation kind, client key)`
within a target/run store. Participant, episode, policy, target and semantic
input are request commitments, not extra retry-key namespaces. After current
receipt-access authorization, an identical retry returns the retained receipt
without re-executing or validating a new occurrence at today's cut. Changed
content under that key conflicts, including a changed episode. A fresh visit
uses a fresh operation key and occurrence identity. The reusable edge is
neither key. Retain the incumbent canonical fingerprint/digest rules.

A fresh control occurrence does not automatically mean a fresh API-424 logical
effect. Preserve trigger-root/rule/slot/firing-epoch identity, the originating
principal's admitted scope, causal budgets and consumption. A drain caller
cannot lend authority. Recovery of indeterminate external work requires the
owner's reconciliation evidence; a new cycle cannot conceal a duplicate effect.
An accepted operation receipt alone proves neither accepted control nor a
successful external effect. Cancellation records actual prevented/partial/late
outcomes only from their lifecycle/evidence authority, never from target kind
or a desired outcome. No control fact rewrites delivered observations.

## MC-08 — Episode admission, replay and limits

Existing episode lifecycle owns initialization, running and termination. Initial
controller state is established with an admitted policy pin and valid authority
at revision zero. Fresh control applications require `running`; initialization
is not a control occurrence, and terminal episodes admit no fresh application.
Authorized reads and exact receipt retries may still inspect historical facts.

Reset/restart admits a new episode under the existing lifecycle, with explicit
predecessor linkage and freshly validated initial authority/policy. It does not
carry pending proposals, decisions or the prior script cursor into that episode.
Prior histories remain retained and episode-qualified. A clock reset creates a
new clock segment, not an episode. A process restart reconstructs the same
episode, not a new trial or permission to repeat an effect. Provider/phase
handoff is not controller transfer or episode restart.

Pin policy for the entire episode. Live policy replacement within an episode
is unsupported by this revision. A new episode can select a new revision;
historical reconstruction uses each episode's original policy and authority/cut
evidence. Replay verifies continuity and retained evidence without dispatch or
evaluation against today's grants/clock. Missing historical context yields an
explicit unverifiable result, never substitution of the latest policy. Semantic
clock replay and a new experimental trial remain separately admitted operations.

Use admitted resource and history limits. Coordinate/ref ranges must fit every
selected consumer, including API-424's strict count bound of 1,000,000 and
bounded references where that consumer applies. Reject unsupported ranges or
exhaustion before commit; never wrap revisions, truncate identities/history or
reset root budgets at a handoff/new episode. Derived indexes must be
reconstructible and fenced to authoritative store revisions. No liveness,
unbounded replay-cost or exactly-once external-effect claim follows.

## MC-09 — Participant-directed injects

Keep DSL-111 orchestration identity, its event/script/story anchor, the DSL-142
participant binding, control-policy edge, actual control occurrence, delivery
occurrence and observation occurrence distinct. An ordinary inject remains
orchestration input; an explicit binding discloses only its governed result.
It never grants access to the inject's hidden body or environment effects.

Reusable authored direction/intervention bindings pin a permitted edge and its
kind/target/authority/evidence constraints. Each realized application must join
an **exact accepted** control occurrence identity/revision, participant/episode,
edge/policy pin, acting source controller, scope, target, evaluated cut and
validity evidence. Never select the latest event with the same edge. Declaration
references and matching version strings alone establish no agreement.

Delivery-policy and control-policy identity/revision are pinned independently;
they need jointly satisfied constraints, not equal revision strings. Keep the
delivery window independently valid at delivery. Each `(control occurrence,
participant binding)` authorizes at most one logical delivery in this revision.
That delivery's exact retries preserve its identity/consumption; further
delivery needs a fresh application. Fan-out uses separate explicit participant
bindings, independently admitted. Repetition does not replay an event schedule
or environment effect automatically.

Resolve authored refs to canonical compiled addresses with existing compiler
indexes before joining; a field called `participant_address` performs no such
normalization. Reuse the trusted non-wire
`ParticipantControlValidationContext.inject_deliveries` seam, authored-binding
digest, owner input/cut/projection and ordinary final-sink validation. Effective
disclosure, audience, markings, transformations and capability support are
revalidated at the delivery/observation cut under SEM-226/230/233 and ADR-095.
Authenticated audience binding is independent of control-subject authorization.
Disclosure-only bindings carry no control authority.

Ordinary disclosure can preserve the same source/result item identity where
its existing contract permits. An API-424 inject effect instead creates a fresh
DSL-111 occurrence and fresh produced result with source provenance, as ADR-108
requires. Neither identity renaming nor a control receipt proves transformation,
delivery or observation. Reuse the existing API-423 stage records and realized
exposure/evidence owners; require explicit emission/acknowledgment/observation
basis. A later delivery failure cannot erase accepted control. Required
predecessor delivery keeps its parent withheld under RUN-320 until evidenced
and revalidated. These are semantic obligations, not a new delivery service.

## Invariants and evidence boundary

MC-01/02 preserve permission versus trace; MC-03 preserves exact continuity;
MC-04/05 preserve acting authority and target eligibility; MC-06 rejects
ambiguous, stale or invalid coordinates; MC-07 preserves atomicity/idempotency;
MC-08 preserves episode and historical interpretation; MC-09 preserves exact
delivery joins and independent disclosure authority.

The bounded reference relation in
[`test_issue_1351_mixed_control_design.py`](../../../implementations/python/tests/test_issue_1351_mixed_control_design.py)
uses the existing pytest workflow. It checks finite state/order/retry/target
and delivery-join projections with trusted resolution and atomic commit as
assumptions. Its replay check validates state continuity only, not the entire
historical authorization proof. It does not implement DTOs, a sequencer, a
clock mapping, persistence, effect dispatch or a backend. Worked cases cover
the wider semantic contract and identify these limits explicitly.
