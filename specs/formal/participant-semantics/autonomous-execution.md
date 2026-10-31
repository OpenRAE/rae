# Autonomous participant execution

This specification defines DSL-437 execution as a composition of existing
participant semantics and the shared time model. It introduces no background
actor, inject, or private clock.

## ACT-605 baseline behavior profile coverage

ACT-605's declarative baseline and background behavior profiles are the
versioned autonomous participant policies defined below. Ordinary user,
automation, and ambient scenario activity reuse the same participant, action,
observation, shared-time, native-execution, and evidence invariants. ACT-605
adds no separate profile root or actor kind and changes none of the v1, v2, or
v3 policy semantics.

## V1 authored policy

For behavior specification \(B\), autonomous policy \(P\) contains:

- a non-empty participant set \(A_P \subseteq A_B\);
- an ordered action sequence \(Q_P \subseteq Q_B\);
- observation boundary \(V_P \in V_B\);
- participant implementation reference \(I_P\);
- shared clock \(C_P\), progression policy \(G_P\), and temporal constraints
  \(T_P\);
- finite action-attempt and in-flight bounds;
- failure disposition; and
- evaluation-authority mode and references.

Every participant action and observation in \(P\) must already be admitted by
the participant and parent behavior specification. \(G_P\) and every member of
\(T_P\) use \(C_P\). Exactly one member of \(T_P\) is a cadence constraint.
Cadence starts must be non-negative. For stepped progression, its start and
period must be integer multiples of `step_ticks`; unreachable cadence points
are invalid. Externally paced policies remain valid SDL; reference-runtime
admission rejects them until its transition driver supports them.
Runtime-owned wall pacing drives `real_time` and `dilated`
policies only when the bound clock declares runtime authority. Backend,
system, and external clock authorities are never advanced by the participant
driver. Stepped and event-driven clocks advance only through shared-time
control.

## V2 activity policy

`participant-autonomous-execution/v2` preserves the same participant, action,
observation, implementation, clock, progression, authority, and native
execution boundaries. It replaces v1 cadence/order fields with:

- a non-empty work-window set \(W_P\) and optional pause-window set \(H_P\);
- inclusive positive timing bounds \([d_{min}, d_{max}]\);
- stable keyed candidates \(q_i=(action_i, weight_i, dependencies_i,
  retryClasses_i, maxRetries_i, cooldown_i)\);
- an `agent-policy` stochastic-control reference; and
- positive finite occurrence, attempt, burst, and in-flight bounds.

Every availability reference is a finite shared-time `window` on \(C_P\) that
names the governed behavior specification or every governed participant.
Eligibility at tick \(t\) is:

\[
eligibleTime(P,t) =
  (\exists [s,e) \in W_P : s \le t < e)
  \land
  \neg(\exists [s,e) \in H_P : s \le t < e)
\]

Declaration order is not semantic. For stepped progression, both timing bounds
are integer multiples of `step_ticks`. A drawn tick outside eligibility follows
the authored disposition exactly: `skip` terminates that scheduling path;
`next_opening` performs a finite forward search over declared work windows. It
never clamps, redraws, sleeps on wall time, or consults host calendar state.

## V3 scoped resource policy

`participant-autonomous-execution/v3` preserves all v2 activity semantics and
adds one required `resource_budget`. A policy declares a finite owner table,
one fairness obligation, and a complete typed demand vector containing:

- action-rate (`actions`, windowed counter);
- concurrent-action (`actions`, reservable gauge);
- storage-growth (`bytes`, growth counter);
- inference-token (`tokens`, windowed or cumulative counter);
- image-generation (`images`, windowed or cumulative counter); and
- accelerator (`accelerator_milliseconds`, lease).

Each demand binds exactly one owner, logical pool, unit, accounting mode,
meter profile, limit, reservation quantity, and reset owner. Owner kinds are
participant, deployment tenant, shared service, and fleet. Participant,
deployment-tenant, and shared-service refs resolve to their existing canonical
addresses; a resource owner grants no participant authority or cross-tenant
access. Deployment-tenant ownership must match an authorized execution target,
and shared-service ownership must match both the exact target and an explicit
tenant `uses_shared_service` edge. The optional parent relation is acyclic,
preserves resource kind, unit, accounting mode, and meter, and cannot increase
or overcommit its parent limit. Two budget ids cannot alias one canonical pool.
Storage growth resets only through evidence-backed reconciliation. The single
participant-owned concurrent-action limit equals `max_in_flight`, so execution
service and budget readback cannot become independent authorities.

V1 and v2 limits compile into the same canonical demand representation with
`legacy_maximum` provenance. They do not acquire v3 capacity, fairness,
isolation, or runtime-accounting requirements.

## Bounded action guarantees (ACT-614)

An action temporal contract opts into `participant-shared-time/v1` through
`shared_time_binding`. Legacy temporal descriptions retain their meaning;
cadence, waiting and cooldown never imply a deadline or continuous dwell.
The binding selects a declared clock and a constraint naming that action.
The selected event must appear in the action's declared event points. An
autonomous policy and its bound actions use the same shared clock.

- A deadline selects `start`, `end` (completion), `observed`, or `effective`.
  The selected event coordinate must be at or before the inclusive deadline.
  Submission after that bound is rejected before native dispatch. Submission
  before it does not prove completion or effects occurred on time.
- Dwell selects an action precondition, observation boundary and nonempty
  half-open window `[start, end)`. Before dispatch, evidence must cover that
  entire interval continuously with the condition true. Samples, gaps,
  overlapping coverage and intervals crossing a pause are insufficient.
  The boundary must belong to the behavior and each bound participant, and
  match the autonomous policy's observation boundary. Condition support must
  be observable there; condition evidence must be declared there.

Coordinates are ordered by segment, tick, then microstep. Authored bounds are
relative to the current shared-clock segment. Each attempt binds its action,
participant, episode, segment, execution generation and clock-history cut.
Reset/replay creates a new attempt identity and requires new evidence; stale
completions cannot commit into the new generation. Pause stops admission and
does not certify continuous dwell while the clock is frozen.

Compilation hashes the resolved guarantee, clock, time domain and constraint;
dwell also covers its condition and observation declaration. One manifest
execution offer must cover the action/target/implementation combination,
requested limits and all its temporal digests. Unrelated offers cannot be
combined to infer support. Empty, partial and rich support declarations are
valid; insufficiency rejects only the requested pairing.

Runtime assessments are `met`, `missed` or `indeterminate`, separate from
native action status and effects. Missing, mismatched or insufficient proof
cannot produce `met`. An unsatisfied guarantee stops automatic retries; it
does not establish cancellation or rollback. A failed guarantee after a
shared-time advance does not erase that advance or committed native history.
Durable and API readback validate context continuity, clock cuts and evidence
against the assessment. Reference tests establish protocol behavior, not
native application fidelity or continuous-monitoring implementation.

Every proof must match an exact runtime-issued context and its authorized
observation boundary. Duplicate or foreign proofs and unauthorized evidence
references fail protocol validation before history commit. Backend callbacks
receive detached request graphs; they cannot alter the runtime's validation
authority. Manual admission uses compiled temporal requirements, not backend
capability claims, to prevent bypass of the reference temporal driver.

A pre-dispatch rejection records a temporal applicability precondition
`shared-time:<temporal_id>` and `precondition_unsatisfied`; it reports no
native effects. Its assessment explicitly records `not_dispatched`.

The reference execution path supports these bindings through autonomous
v1/v2/v3 policies. It rejects unbound manual execution at runtime admission;
this is not an SDL restriction or a required backend architecture.

## Non-evaluated authority invariant

When `evaluation_authority.mode = none`:

\[
\forall a \in A_P : role(a) = green
\]

and \(B\) has no outcome-interpretation or authority-scope refs, no objective
names \(a\) as its actor, and the authority record has no objective, proof,
score, or receipt refs. This is a semantic rejection condition, not guidance.

## Deterministic selection

For the v1 `ordered_cycle` strategy, scheduler state for participant \(a\) is:

\[
S_{P,a} = (digest(P,T), episode, segment, nextTick, nextAction, attempted, succeeded, failed, state)
\]

At a due tick, the selected action is:

\[
Q_P[attempted \bmod |Q_P|]
\]

The scheduler makes no random draw. A stochastic participant implementation is
run apparatus and must use the existing random-stream control and experiment
apparatus contracts; it does not change this selection relation.
The digest covers the resolved clock, time domain, progression policy, and
temporal constraints, not only their addresses.

For v2, let \(E(S,t)\) be candidate ids whose dependencies are present in the
typed completed-candidate set and whose cooldown is not later than \(t\).
Candidate ids are sorted canonically before compilation. With exact positive
integer weights and an addressed bounded draw:

\[
r \in [0,\sum_{i \in E} weight_i - 1]
\]

the selected candidate is the first canonical prefix interval containing
\(r\). Dependency filtering precedes the draw. An empty set follows the
authored `complete` or `wait` disposition and never falls back to all
candidates. Timing, selection, and burst-size draws use the immutable
`blake3-xof-participant-v1` profile and the closed address:

\[
(namespace, policyAddress, participantAddress, segment,
 occurrenceOrdinal, purpose, localCoordinate)
\]

Retries retain the occurrence ordinal, selected candidate, timing tick, and
selection draw. Retry number, worker identity, call order, wall time, and
backend availability are not stream coordinates. Activity draws are within-run
policy execution and are separate from scenario-family variation and trial
compilation.

## Execution and evidence

Compilation derives an exact relation

\[
R_P \subseteq Q_P \times Targets \times Implementations
\]

from each action contract's effect and precondition support references. A
backend execution binding must cover each required tuple in \(R_P\). Declaring
all actions and all targets separately does not establish the Cartesian
product and is insufficient for admission.

An action may commit only in this order:

1. resolve the run-selected participant implementation;
2. require its manifest reference to equal \(I_P\);
3. bind the participant, action, observation boundary, and every temporal
   constraint;
4. invoke the backend-native participant action;
5. require a typed native outcome distinct from control-operation success;
6. append action, state-transition, and observation events; and
7. update typed scheduler readback.

V3 inserts an atomic reservation of the complete resource vector before step
4. Physical capacity is owned by one canonical pool ledger shared across
policies. An exactly-once commit occurs only after the native result supplies
the complete matching operation, generation, resource, unit and meter
measurement vector with evidence. Protocol failure or an absent or untrusted
vector releases or rolls back the reservation.
If any dimension or ancestor pool cannot reserve, no dimension reserves and
the native action is not invoked. Stable action identity makes reservation and
settlement idempotent. Every throttle, reservation, commit, release, or reset
reconciliation is a typed, generation-fenced event; metadata and log text are
not authoritative accounting.

The scheduler applies these checks to every participant-runtime implementation,
not only implementations derived from the reference base class. A result is
invalid when it has the wrong type, is absent or non-terminal, or is bound to
another episode. It is also invalid when it reports an observation point outside
the bound temporal contexts or lacks the matching terminal history event. The
scheduler commits neither the native snapshot nor the portable behavior history
of an invalid result. The failed attempt is recorded only in scheduler
accounting so the same action instance cannot be replayed. If native execution
reports a valid terminal failure, no successful behavior history is fabricated.
The current action must append exactly the ordered attempted, transition, and
terminal observation events, and the attempted event's actor provenance must
match the selected participant implementation.
`stop` marks the scheduler failed; `continue` advances the bounded attempt
counter and cadence.

Every autonomous action request carries the resolved native target addresses,
execution-service scope, and execution generation. The runtime checks that the
service is running, ready, accepting work, and still at that generation before
calling the native adapter. It checks the generation again on the returned
snapshot before committing history. A stale work item or completion is
rejected without committing native state.

When at least two participants are due and the admitted policy and backend
limits permit it, native calls execute concurrently against one immutable
predecessor. Results commit one at a time. For every changed portable map
entry, the commit requires the current value to equal either the predecessor
or the incoming value; otherwise it reports a concurrent-commit conflict.
Scheduler attempt/in-flight counters are reserved before dispatch and settled
after each serialized commit.

For v2, a retry is admitted only when the typed terminal failure class is in
the selected candidate's declared retry set and the per-occurrence retry and
global attempt bounds both remain. Each retry has a distinct attempt id and
names its predecessor. Protocol-invalid or indeterminate work is not retried.
A terminal occurrence updates dependency completion and cooldown state before
the next selection. A burst performs at most `max_burst_size` serialized
occurrences at one due tick; each remains a distinct occurrence and action
attempt.

Every committed v2 behavior-history event carries safe occurrence provenance:

- policy and profile;
- occurrence and attempt identity;
- predecessor and dependency ids;
- candidate, timing tick and disposition, and burst position;
- terminal outcome; and
- the safe control, profile and address identity.

It never carries root entropy,
derived keys, raw blocks, or backend-private objects.

## Invocation tool actions

`participant-invocation-tool-actions/v1` composes participant tool actions
with one active autonomous invocation \(o\). The invocation keeps the ordered
three-event rule above. A tool action \(c\) is a distinct action of the same
participant with its own identity, admission and typed outcome.

Compilation derives, for policy \(P\) with behavior specification \(B\):

\[
T_P = \{(f, q, V_f, A_f \cap A_P, targets(q), bound(q))\}
\]

for each authored affordance \(f\) of \(B\) and each action \(q\) of \(f\).
\(V_f\) is the affordance observation-boundary set. \(targets(q)\) uses the
same effect and precondition derivation as \(R_P\). \(bound(q)\) is true when
\(q\) has a shared-time binding. The policy digest covers non-empty \(T_P\).

A request \(r\) for \(c\) inside \(o\) is admitted only if:

- the port of \(o\) is open;
- participant, live episode, implementation reference, outer action instance,
  execution scope and generation of \(r\) equal those of \(o\);
- exactly one member of \(T_P\) has the affordance and action of \(r\) and
  includes its participant, with \(bound(q)\) false;
- the observation boundary of \(r\) is in \(V_f\), and its targets form a
  non-empty subset of \(targets(q)\);
- exactly one manifest execution-binding offer has \(q\) and the selected
  implementation and covers every target of \(r\);
- \(P\) is not a v3 policy, and no participant-crossing policy is installed;
- the enclosing operation is live, the engine and run admit effects, and the
  run holds no unresolved indeterminate operation;
- the selected store retains the accepted child record; and
- the admitted and dispatched counts of \(o\) are below the declared limits.

A refusal has a fixed code, causes no native call and adds no history. A tool
call identity is stable within \(o\). The runtime-issued action identity is a
digest of the outer action, episode, execution generation and tool call
identity. An identical replay returns the retained
decision. A different request under the same identity is refused.

The port is inactive while the backend attaches it and refuses every operation.
The scheduler activates it only as the outer dispatch begins. Each admitted
action follows:

```text
admitted --dispatch--> dispatched --complete--> completed
admitted --cancel|close--> withheld
dispatched --report_unknown|close--> indeterminate
```

Dispatch is a one-use grant, and effects start only after it. A completion
carries a terminal typed outcome bound to the participant, episode, action
instance and action contract. It must also pass the canonical binding
validation for the exposure policy, compiled boundary evidence and observation
point. After dispatch, a cancel request is refused, because it does not prove
that effects stopped. The first unknown effect fences the port: later
admissions and grants refuse, and accepted work can still settle. The scheduler
then dispatches no further outer invocation in the pass. A grant also rechecks
the live-authority condition above. A grant whose authored interaction
footprint conflicts with an active hosted action or another invocation's outer
action is refused under the scheduler's conflict rule. The unknown-effect fence
is set before its settlement write and applies to every port in the pass. Closure happens before the scheduler
validates the outer result. Closure and admission are serialized.

The scheduler commits every settled tool action on every outer terminal path.
This includes valid, protocol-invalid, raised and cancelled outer results. Each
tool action appends one ordered triple. Every event carries
`invocation_tool_context` with the version, outer action instance and contract,
affordance, tool call identity, admission ordinal, settlement, scope and
generation. Triples follow admission order, immediately before the outer
triple, or at the end of the participant history when the outer triple did
not commit. Predecessor and peer histories stay unchanged. A withheld action
records status `withheld`. An indeterminate action records status `unknown` and
observation status `orphaned_action`. It also marks the participant scheduler
`failed`. A changed generation or episode commits no tool history. Unknown
effects are never replayed.

Each tool action is also a child operation record of the enclosing due
operation. The store retains the accepted claim before the decision, the
running state before the grant, and the terminal state before the settlement
answer. A failed write refuses the operation. After a restart, an accepted
record becomes cancelled and a running record becomes indeterminate. Tool
history commits atomically with the enclosing due operation.

## Lifecycle

One execution-service scope owns each autonomous policy. Its portable state
separates desired/observed lifecycle, generation, health, readiness, work
admission, finite capacity, reservation/in-flight counters, quiescence,
resource release, shared-time provenance, and evidence. Legal control
transitions are:

```text
stopped --start--> running --pause--> paused --resume--> running
running|paused --drain(timeout)--> quiescent
quiescent --reset(generation+1)--> running
quiescent --teardown--> terminated
```

Drain rejects new work and succeeds only after reserved and in-flight work are
zero within its finite timeout. Teardown is idempotent after termination.
Every transition publishes an operation reference and evidence reference.
Portable fields are readback, not an implementation of these operations.
The backend owns the native transition, scheduler/shared-time coordination,
bounded wait, and resource release. The control boundary rejects nominal
success unless the backend returns the action-specific observed state, a
changed operation reference, and new evidence.

Pause changes non-terminal scheduler states on the governed clock to `paused`;
resume returns them to `running`. Reset begins a new shared-time segment,
resets each bound participant episode, and restores the initial cadence,
action index, and counters. Reapplying an unchanged plan preserves state.
Reapplying a materially changed policy at the same address fails before
mutation. A participant belongs to at most one autonomous execution policy.
Clock transitions that would cross a due cadence without executing it fail
before clock mutation. Reset-capable autonomous policies require the backend
manifest to advertise `supports_coordinated_participant_reset`. Runtime
registration then requires the time authority's `reset_with_participants`
operation and the participant runtime's atomic `reset_many` operation through
capability-specific runtime protocols. Together they form one backend
transaction: the implementation must prepare all clock and episode changes
before commit, return one coherent snapshot on success, and leave no externally
observable mutation on failure. Scheduler
counters are updated locally only after that transaction succeeds. A copied
predecessor snapshot is not treated as rollback of backend side effects.
Participant runtimes with additional native reset state must supply their own
atomic batch implementation rather than inherit the reference in-memory
transaction.
Durable and conformance validation require scheduler segment/lifecycle and
episode identity to agree with the bound shared clock and live episode.
V2 reset also clears occurrence, retry, dependency, cooldown, and burst
continuation, then derives the next timing and burst values under the new
shared-time segment. The segment is part of every activity address, so reset
generations cannot alias prior draws. Participant/service state changes remain
owned by native action results and existing episode/reset contracts; scheduler
timestamps alone make no causal or rollback claim.

The service readback binds the policy, execution relation, and admitted
shared-time declaration by digest and names its scheduler states. Shared-clock
pause/resume changes both scheduler and execution-service readiness. A
shared-clock reset advances the execution generation. Loss of runtime wall
pacing marks the service degraded, not ready, and paused and appends an
explicit pacing-deviation evidence reference; it is never silently treated as
successful timing.

V3 reset reconciles outstanding reservations before advancing the execution
generation. A `time_segment` boundary clears only dimensions owned by that
boundary. Tenant, shared-service, fleet, and persistent storage use survive
participant or segment reset unless their own declared reset/reconciliation
rule applies. Execution-service resource refs name the authoritative budget
states; its concurrency capacity, reservation, and in-flight projection must
equal the referenced concurrent-action state.

## Backend admission

Let backend capability \(K\) declare supported strategies and finite maxima.
Admission requires:

\[
|A_P| \le K.participants
\]

\[
P.maxAttempts \le K.actionAttempts
\]

\[
P.maxInFlight \le K.inFlight
\]

and \(P.strategy \in K.strategies\). This establishes only that the backend
claims it can attempt realization. Admission also requires:

\[
Q_P \subseteq K.actions
\]

\[
V_P \in K.observationBoundaries
\]

\[
targets(Q_P) \subseteq K.targets
\]

\[
R_P \subseteq K.executionBindings
\]

and every parent behavior feature required by \(P\) must be in the backend
feature set. A reset-capable policy additionally requires the coordinated
participant-reset capability and runtime method. Runtime state, typed native
action outcome, history, and backend evidence establish what occurred.

Autonomous admission does not require native lifecycle controls or concurrency.
Require concurrency only when the policy requests more than one in-flight
action. Each lifecycle request requires that exact claimed operation.
Conditional conformance exercises only claimed capabilities, with valid
preconditions supplied independently for partial control sets. Claims without
the corresponding typed outcomes and evidence fail conformance.

V2 additionally requires exact admission of:

- `participant-autonomous-execution/v2`;
- work windows, weighted selection, occurrence provenance, and any additional
  activity features actually requested (variation, dependencies, retries,
  cooldowns, or bursts);
- `weighted`;
- `blake3-xof-participant-v1`;
- shared-time `window`; and
- occurrence, retry-per-occurrence, and burst-size maxima.

Missing or differently named support fails admission; no compatible-profile,
transform, or strategy fallback is inferred.

V3 additionally requires exact, all-or-nothing admission of:

- the complete six-kind demand vector and owner/parent graph;
- bounded or exact backend support for every owner, kind, accounting mode,
  reset mode, and fairness policy;
- one configuration-bound pool entry matching each demand's canonical owner,
  pool, kind, unit, accounting mode, and meter;
- configured capacity at least equal to the admitted limit;
- tenant-partitioned isolation for every declared cross-range pool; and
- the budget state and event realization contracts.

Manifest support, configured capacity, and measured realization are distinct
authorities. A capability declaration is not utilization evidence; a runtime
sample cannot enlarge configured capacity. Fairness is explicit and
role-independent: priority class, weight, protected posture, borrowing,
reclaim, queue bound, and starvation bound are admitted as one obligation.
Backends may not infer priority from participant color or evaluation
authority.

## Nonclaims

This contract does not prove participant intelligence, human realism, service
fidelity, throughput, causal attribution, evaluator correctness, or
golden-range equivalence. Those claims require their existing RAES evidence and
conformance surfaces.

## Delivery status

The reference implementation covers:

- authored validation and canonical compilation;
- exact fail-closed capability admission;
- RuntimeManager-driven shared-clock execution;
- native binding and typed action outcomes;
- policy identity and lifecycle;
- automatic real-time and dilated cadence driving;
- transactional backend clock and participant reset admission and invocation;
- durable, API and conformance cross-surface scheduler state; and
- focused race and negative cases.

The wall driver re-reads clock state after waits, remains
owned until its thread exits, and records unexpected termination. Externally paced autonomous
execution remains rejected because no portable transition-notification
contract is yet governed. This establishes the portable protocol behavior only. A
production backend still must prove that its selected participant
implementation, native adapter, targets, evidence, and readback faithfully
materialize a scenario. V3 additionally covers canonical legacy projection,
atomic multi-resource admission and reservation, typed runtime state/events,
generation-fenced settlement and reset reconciliation, durable/control-plane
projection, and cross-range isolation rejection. Invocation tool actions cover
the compiled relation, the capability claim and registration, port admission
and refusal, one-use dispatch, closure, serial and concurrent settlement, and
history-view projection. No conformance probe family exercises them yet.
