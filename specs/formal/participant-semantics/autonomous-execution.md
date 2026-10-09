# Autonomous Participant Execution

This specification defines DSL-437 execution as a composition of existing
participant semantics and the shared time model. It introduces no background
actor, inject, or private clock.

## ACT-605 Baseline Behavior Profile Coverage

ACT-605's declarative baseline and background behavior profiles are the
versioned autonomous participant policies defined below. Ordinary user,
automation, and ambient scenario activity reuse the same participant, action,
observation, shared-time, native-execution, and evidence invariants. ACT-605
adds no separate profile root or actor kind and changes none of the v1, v2, or
v3 policy semantics.

## V1 Authored Policy

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

## V2 Activity Policy

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

## V3 Scoped Resource Policy

`participant-autonomous-execution/v3` preserves all v2 activity semantics and
adds one required `resource_budget`. A policy declares a finite owner table,
one fairness obligation, and a complete typed demand vector containing:

- action-rate (`actions`, windowed counter);
- concurrent-action (`actions`, reservable gauge);
- storage-growth (`bytes`, growth counter);
- inference-token (`tokens`, windowed or cumulative counter);
- image-generation (`images`, windowed or cumulative counter); and
- accelerator (`accelerator_milliseconds`, lease).

The vector may also carry the optional DSL-121 interaction dimensions defined
below.

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

## SEM-223 Budget Consumption, Exhaustion, And Limit Effects

SEM-223 gives the v3 resource budget its interaction-level meaning. It follows
the FM3 state machine in `specs/formal/participant-episode-model/README.md`
(transitions T2 and T7 to T11). It reuses the ADR-097 budget family and the
SEM-211 `resource` precondition class and `resource_exhausted` failure class.
It adds no budget root, quota map, failure taxonomy, resource kind, or schema.

### Semantic coordinates

- **Participant scope.** Every dimension has exactly one typed owner. The
  policy reserves one vector for every action of every participant it governs,
  so a participant-owned dimension is participant-local only when the behavior
  specification governs exactly one participant. The governed participants are
  the agents named in `participant_refs` plus every agent whose effective role
  is in `participant_role_refs`. A participant owner on a behavior
  specification that governs several participants is rejected as a
  policy-wide counter presented as participant-local state. Shared counters use
  deployment-tenant, shared-service, or fleet owners. A participant-owned
  dimension may aggregate into a parent of another owner kind, but no other
  owner's dimension may aggregate into a participant-owned parent.
- **Resource domain.** Kind, unit, accounting mode, and meter profile identify
  a dimension. Dimensions that differ in any of them never aggregate through
  the parent graph, never share a physical pool ledger, and never admit against
  each other's configured capacity. A native measurement with a different meter
  is untrusted, so the reservation is released rather than committed.
- **Observation point.** Consumption is decided at the scheduler's pre-dispatch
  admission point for one governed attempt, before the native adapter is
  called. It is settled at that attempt's terminal native result.
- **Consumption event.** A commit records the exact measured vector, bounded
  by the reservation, with native evidence refs. RAES measures DSL-121 logical
  time itself and cites the clock-history cut. Every reserve, commit,
  release, throttle, reject, and reconcile is an append-only event fenced to
  its execution generation.
- **Exhaustion condition.** For dimension \(d\),
  \(rem(d) = \min(limit, configuredCapacity) - used(d) - reserved(d)\), where
  \(used(d)\) is cumulative committed use for counter modes and current use for
  gauge and lease modes. The dimension is exhausted while \(rem(d) \le 0\).
  Exhaustion is derived from budget state; no carrier stores it as a flag. A
  committed measurement leaves the dimension open while \(rem(d) > 0\), so it
  supports repeated reserve and commit cycles.
- **Failure and effect class.** A reservation whose quantity exceeds
  \(rem(d)\) on any dimension is a `reject` event and changes nothing else
  (T10). Every dimension's logical budget is checked before any shared pool,
  so the disposition does not depend on the order of the vector. The attempt
  then fails through SEM-211 (T11): the scheduler records an undispatched
  `rejected` attempt whose only precondition is the unsatisfied `resource`
  precondition `participant-resource-budget`, with the `resource_exhausted`
  failure class. Like the ACT-614 shared-time pre-dispatch rejection, the
  attempt reports only the runtime-owned precondition that failed, because the
  action's authored preconditions were never evaluated. The `reject` event and
  the attempt commit together: if the attempt cannot be committed, the
  scheduler keeps neither. The policy's failure disposition settles the
  attempt: `continue` consumes it and keeps scheduling, and `stop` fails the
  scheduler. For an action bound to shared time, the rejected attempt carries
  no temporal assessment, so the ACT-614 rule that an unassessed guarantee
  never authorizes a retry applies. A shared physical pool that cannot admit a
  quantity the logical budget allows is a `throttle` event, not exhaustion, and
  it fails the scheduler pass. Repeating a refused reservation for the same
  operation records no second event.
- **Terminal effects.** Exhaustion never becomes an episode terminal reason, a
  backend error, or a workflow state by itself. Relating exhaustion to
  truncation or interruption requires an explicit SEM-222 terminal-condition
  transition (EBM-06). The reference runtime authors no such transition, so an
  exhausted participant's episode keeps running.
- **Visibility of remaining budget.** The participant learns only that a
  resource precondition failed. The rejected attempt names no budget, pool,
  quantity, or remaining capacity (EBM-07). Operators read budget state through
  the runtime snapshot and its existing read authorization. The DSL-121
  section below defines the only view rule that discloses a quota.
- **Provenance and evidence basis.** The governed attempt and its `reject`
  event share the action instance id. A result that claims the portable
  `participant-resource-budget` precondition without a runtime `reject` event
  presents a backend-local limit as a portable budget limit and is rejected
  (EBM-09). A backend may report its own resource failure under its own
  precondition id.

### Reset scope

A shared-clock reset crosses the `time_segment` boundary. It crosses the
`episode` boundary only when every bound participant's live episode changed.
The coordinated reset that durable validation admits for scheduler-governed
participants always resets those episodes. Reconciliation clears only the
dimensions whose reset owner is a crossed boundary. Dimensions with `run` or
`reconciled` reset keep their use, so tenant, shared-service, fleet, and
persistent storage use survive an episode reset (EBM-03). Reconciliation
appends evidence and never deletes prior events.

Settlement is fenced to the reservation's own generation. A reservation made
before a reset can neither commit nor release after it, so pre-reset use cannot
leak into the next generation. Each reservation settles exactly once: a commit
after a release, or a release after a commit, is refused, and repeating the
same settlement is idempotent.

### Fail-closed checks

`raes_contracts.participant_resource_exhaustion` makes these rules checkable
over runtime snapshots. The runtime result path and published runtime-snapshot
conformance both apply it to:

- future-generation events, settlements outside their reservation's
  generation, repeated settlements, over-measured commits, and budget states
  whose head event is not in their own event stream;
- applies that remove or rewrite an earlier budget event; and
- a `reject` event without its governed attempt, a governed attempt that is
  not a rejected `resource_exhausted` result with the unsatisfied budget
  precondition, and a governed attempt that discloses the budget identity.

### SEM-223 Traceability

| Obligation | Invariant | Enforcement point | Positive test | Negative test |
| --- | --- | --- | --- | --- |
| Exhaustion is derived from remaining capacity and refused with a typed rejection | EBM-06 | `reserve_participant_resources` (`participant_resource_remaining`) | `test_exhaustion_is_derived_from_remaining_capacity_across_reserve_commit_cycles` | `test_logical_exhaustion_rejects_while_shared_pool_contention_throttles` |
| Exhaustion is a controlled SEM-211 failure, never a silent terminal state | EBM-06 | scheduler pre-dispatch admission, `iter_participant_resource_exhaustion_violations` | `test_exhaustion_becomes_an_undispatched_resource_exhausted_attempt`, `test_exhaustion_under_stop_policy_fails_the_scheduler_through_the_attempt` | `test_exhaustion_cannot_bypass_controlled_failure_or_disclose_hidden_quota`, `test_published_snapshot_conformance_rejects_exhaustion_outside_sem211`, `test_rejected_attempt_failing_protocol_validation_leaves_no_reject_event` |
| Hidden quota state is not participant-visible without a view rule | EBM-07 | rejected-attempt construction, `iter_participant_resource_exhaustion_violations` | `test_participant_visible_attempt_names_no_budget_quantity_or_identity` | `test_exhaustion_cannot_bypass_controlled_failure_or_disclose_hidden_quota` |
| Consumption is ordered, generation-fenced, settled once, and append-only | EBM-08 | `commit_participant_resource_reservation`, `release_participant_resource_reservation`, `iter_participant_resource_budget_event_violations`, history transition check | `test_accounting_matches_the_reference_state_machine` | `test_consumption_events_fail_closed_when_stale_future_or_unordered`, `test_pre_reset_reservation_cannot_settle_into_the_next_generation`, `test_each_reservation_settles_exactly_once`, `test_runtime_refuses_a_transition_that_drops_or_rewrites_budget_history` |
| A reset clears only use owned by a crossed boundary | EBM-03 | `reconcile_participant_resource_budgets`, shared-clock reset | `test_coordinated_reset_clears_only_episode_and_segment_owned_use`, `test_accounting_matches_the_reference_state_machine` | `test_clock_reset_without_an_episode_reset_keeps_episode_owned_use` |
| Participant-local budgets never count other owners' use | EBM-03 | `participant_resource_budget_owner_errors`, policy parent-graph validation | `test_aggregate_counter_cannot_nest_under_a_participant_local_budget` | `test_aggregate_counter_cannot_nest_under_a_participant_local_budget`, `test_participant_owned_budget_cannot_count_several_participants` |
| Dimensions with incompatible meters never aggregate or admit | EBM-05 | policy parent-graph validation, `participant_resource_budget_gaps` | `test_admission_is_atomic_for_complete_vector_and_exact_meters` (issue #899: the six-kind vector admits against exactly matching pools); the turn and tool-use kinds and their positive fixture belong to DSL-121 (#308) | `test_incompatible_token_meters_never_aggregate_or_admit` |
| A backend-local limit is not a portable budget exhaustion | EBM-09 | `iter_participant_resource_exhaustion_violations` | `test_backend_local_limit_cannot_pose_as_portable_budget_exhaustion` | `test_backend_local_limit_cannot_pose_as_portable_budget_exhaustion` |

### SEM-223 nonclaims

- SEM-223 adds no resource kind. The DSL-121 section below adds the step,
  turn, tool-use, and logical-scenario time dimensions, and host watchdog time
  is never a portable scenario-time quota.
- Authors cannot select another limit effect. The reference runtime always
  denies the attempt with `resource_exhausted`; throttling, truncation, and
  interruption are not selectable effects.
- The reference runtime does not roll a `windowed_counter` window inside a
  generation. Its use resets only at the dimension's declared reset boundary.
- No fairness, throughput, isolation, or operating-system enforcement claim
  follows from these rules.

## DSL-121 Interaction Budgets

DSL-121 lets authors bound participant interaction with the same ADR-097
dimensions. An interaction budget compiles into the canonical demand vector
and is admitted, reserved, committed, exhausted, and reset like any other
dimension; RAES, not the backend, measures logical time. There is no
interaction-budget root, quota map, or `max_*` field: the closed policy and
behavior-specification models reject them.

The governed catalog adds four optional kinds. Each has one fixed unit and the
accounting modes that fit it:

| Interaction bound | `resource_kind` | Unit | Accounting modes | Meter |
| --- | --- | --- | --- | --- |
| Step | `interaction_steps` | `steps` | windowed or cumulative counter | the backend's step meter |
| Turn | `interaction_turns` | `turns` | windowed or cumulative counter | the backend's turn meter |
| Tool use | `tool_invocations` | `invocations` | windowed or cumulative counter | the backend's tool meter, scoped by `tool_affordance_refs` |
| Logical time | `scenario_time` | `ticks` | cumulative counter | `raes.shared-time-ticks/v1`, metered by RAES |

A token budget keeps using `inference_tokens`. Steps, turns, tool invocations,
logical time, tokens, and action attempts are distinct kinds and units, so the
parent graph, pool identity, and admission never let one stand in for another.
A turn is not an action attempt: one turn may span several actions, and one
action may take several turns. As for every dimension, the `reservation` is
the most one attempt may use, and an attempt that measures more is not
committed. A turn budget's reservation is therefore the most turns one action
may take.

- **Tool use.** A `tool_invocations` dimension must name one or more
  `tool_affordance_refs`, and no other kind may. Each ref names a tool
  affordance of the same behavior specification. The affordance is the authored
  contract that makes an invocation of its tool equivalent to an attempt of its
  action contracts. At least one of those actions must be dispatched by the
  policy, and the dimension counts only the dispatched ones. Any other attempt
  reserves zero from it, which keeps the measured vector complete. A zero
  quantity never rejects or throttles. A child tool budget's affordances must
  be within its parent's.
- **Logical time.** A `scenario_time` dimension bounds the elapsed logical time
  of the policy's governed shared clock under ADR-090. Its meter must be
  `raes.shared-time-ticks/v1`, so a host or watchdog meter is rejected. RAES
  meters it from the clock history, and no backend reports it. Elapsed time is
  the ticks the clock advanced since the dimension's reset boundary: the latest
  clock reset for `time_segment`, or clock initialization for `run`. A pause
  adds no ticks, and a jump or replay opens a segment without adding ticks.
- **Charging logical time.** Each admitted attempt reserves the ticks that
  elapsed since the dimension was last charged plus its `reservation`
  allowance. It commits the elapsed ticks with the clock-history cut as
  evidence, so ticks between attempts count. Once less than the allowance
  remains, every attempt is rejected as `resource_exhausted` until the boundary
  resets. An `episode` or `reconciled` reset is rejected, because an episode
  need not begin at a shared-clock boundary.
- **Quota disclosure.** A quota stays hidden by default. The only way to make
  one participant-visible is a `resource_budget` view rule on the policy's
  observation boundary whose `information_ref` is the dimension's
  `behavior_specifications.<spec>.autonomous_execution.resource_budget.dimensions.<id>`
  ref. The class is sensitive, so exposure requires `disposition: disclosed`
  and a `disclosure_rule`, and the ref must also be declared in `hidden_refs`.
  Validation rejects such a ref in `observable_refs`, under another class, in a
  view transition, or for a dimension governed through a different boundary.
- **Disclosed amounts.** When a disclosed dimension rejects an attempt, the
  rejected attempt's `observations` report the dimension ref, its used amount,
  its authored limit, what remains under that limit, and the attempt's
  requested amount. A shared pool smaller than the limit is backend
  configuration, so no amount reveals it. Only the policy's own rejection of
  that attempt is read. Otherwise the attempt reports no budget at all.

Composition rewrites dimension refs in observation boundaries when a module is
imported under a namespace, and validation accepts the namespaced refs.
Validation and compilation resolve a tool scope with one shared rule. The
`participant-resource-budget-policy-v1` contract can carry the scope: a
`tool_invocations` demand requires `action_contract_refs`, the canonical action
contract addresses, and other kinds forbid it. The reference compiler records
the same addresses on the compiled runtime demand.

### DSL-121 Traceability

| Obligation | Invariant | Enforcement point | Positive test | Negative test |
| --- | --- | --- | --- | --- |
| Interaction budgets project into the canonical ADR-097 demand | EBM-04 | `raes_processor.compiler.participant_autonomous_execution` | `test_interaction_dimensions_compile_into_the_canonical_demand` | `test_parallel_limit_fields_cannot_bypass_the_resource_family` |
| Step, turn, tool use, logical time, and tokens stay distinct, and watchdog time is not scenario time | EBM-05 | catalog quantity semantics, policy parent-graph validation | `test_interaction_dimensions_compile_into_the_canonical_demand`, `test_backend_must_declare_each_interaction_kind_it_admits` | `test_interaction_dimensions_are_distinct_governed_kinds`, `test_scenario_time_contracts_must_meter_shared_time` |
| Logical time is elapsed shared-clock time that RAES meters | EBM-05 | `participant_resource_scenario_time`, scheduler admission | `test_scenario_time_is_metered_from_the_shared_clock`, `test_scenario_time_elapses_only_while_the_shared_clock_advances` | `test_interaction_dimensions_are_distinct_governed_kinds` |
| A tool-use budget binds exact tool affordances and counts only their dispatched actions | EBM-05 | `tool_affordance_action_contracts`, `participant_resource_budget_scope_errors`, `action_resource_quantities` | `test_tool_scoped_dimension_reserves_only_for_its_tool_actions`, `test_published_policy_contract_carries_the_tool_scope_and_time_basis` | `test_tool_use_budget_binds_exact_tool_affordances`, `test_only_tool_use_budgets_carry_a_tool_scope` |
| A quota is participant-visible only through an explicit view rule | EBM-07 | `resource_budget` view rules, `disclosed_resource_budget_refs`, rejected-attempt disclosure | `test_quota_is_participant_visible_only_through_an_explicit_view_rule`, `test_quota_disclosure_compiles_onto_the_disclosed_dimension_only` | `test_quota_cannot_be_exposed_without_an_explicit_view_rule`, `test_quota_disclosure_requires_a_disclosure_rule`, `test_disclosure_reports_only_this_policys_rejection_against_the_authored_limit` |
| The authored surface rejects unknown fields and variable-created keys, and composition keeps its refs bound | EBM-04 | closed SDL models, parser, composition, validation | `test_imported_quota_disclosure_follows_the_namespaced_behavior_specification` | `test_interaction_budget_keys_cannot_come_from_variables`, `test_parallel_limit_fields_cannot_bypass_the_resource_family`, `test_imported_quota_stays_hidden_unless_disclosed` |

### DSL-121 nonclaims

- Interaction budgets attach only to the v3 autonomous profile here. Budgets on
  other participant kinds belong to ACT-624.
- Steps, turns, and tool invocations are counted by the backend's native
  measurement vector under the declared meter. RAES checks each measurement's
  identity, kind, unit, meter, and bound, not the native count.
- Logical time is relative to a shared-clock reset or to the run. No
  episode-relative logical-time budget is defined.
- Disclosure reports the quota of a rejecting dimension in the rejected
  attempt. No other participant view reports quota usage.
- The reference implementation does not publish a
  `participant-resource-budget-policy-v1` document from a compiled scenario.

## Bounded Action Guarantees (ACT-614)

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

## Non-Evaluated Authority Invariant

When `evaluation_authority.mode = none`:

\[
\forall a \in A_P : role(a) = green
\]

and \(B\) has no outcome-interpretation or authority-scope refs, no objective
names \(a\) as its actor, and the authority record has no objective, proof,
score, or receipt refs. This is a semantic rejection condition, not guidance.

## Deterministic Selection

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

## Execution And Evidence

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
the complete matching operation/generation/resource/unit/meter measurement
vector with evidence; protocol failure or an absent/untrusted vector releases
or rolls back the reservation.
If any dimension or ancestor pool cannot reserve, no dimension reserves and
the native action is not invoked. Stable action identity makes reservation and
settlement idempotent. Every throttle, reservation, commit, release, or reset
reconciliation is a typed, generation-fenced event; metadata and log text are
not authoritative accounting.

The scheduler applies these checks to every participant-runtime implementation,
not only implementations derived from the reference base class. If the result
has the wrong result type, is absent, non-terminal, bound to another episode,
reports an observation point outside the bound temporal contexts, or lacks the
matching terminal history event, the native snapshot and portable behavior
history are not committed. The failed attempt is recorded only in scheduler
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
policy/profile, occurrence and attempt identity, predecessor and dependency
ids, candidate, timing tick/disposition, burst position, terminal outcome, and
the safe control/profile/address identity. It never carries root entropy,
derived keys, raw blocks, or backend-private objects.

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
generation. A shared-clock reset clears only dimensions owned by a boundary it
crosses: `time_segment` always, and `episode` when it reset the bound episodes
(see SEM-223 above). Tenant, shared-service, fleet, and persistent storage use
survive participant or segment reset unless their own declared
reset/reconciliation rule applies. Execution-service resource refs name the authoritative budget
states; its concurrency capacity, reservation, and in-flight projection must
equal the referenced concurrent-action state.

## Backend Admission

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

## Delivery Status

The reference implementation covers authored validation, canonical
compilation, exact fail-closed capability admission, RuntimeManager-driven
shared-clock execution, native binding and typed action outcomes, policy
identity and lifecycle, automatic real-time/dilated cadence driving,
transactional backend clock/participant reset admission and invocation,
durable/API/conformance cross-surface scheduler state, and focused race and
negative cases. The wall driver re-reads clock state after waits, remains
owned until its thread exits, and records unexpected termination. Externally paced autonomous
execution remains rejected because no portable transition-notification
contract is yet governed. This establishes the portable protocol behavior only. A
production backend still must prove that its selected participant
implementation, native adapter, targets, evidence, and readback faithfully
materialize a scenario. V3 additionally covers canonical legacy projection,
atomic multi-resource admission and reservation, typed runtime state/events,
generation-fenced settlement and reset reconciliation, durable/control-plane
projection, and cross-range isolation rejection. SEM-223 additionally covers
derived exhaustion, typed rejection versus throttling, undispatched
`resource_exhausted` attempts, exactly-once settlement within the reserving
generation, episode-boundary reconciliation, participant-local owner rules, and
the runtime and conformance checks listed in its traceability table.
