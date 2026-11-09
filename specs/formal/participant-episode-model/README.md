# Participant episode and budget model formal design

This document is the issue #122 formal design artifact for:

- `SEM-222` - Participant Episode, Reset, And Termination Semantics
- `SEM-223` - Participant Budget, Quota, And Exhaustion Semantics
- `DSL-120` - Participant Episode Structure And Termination Surface
- `DSL-121` - Participant Interaction Budget Surface
- `ACT-623` - Participant Episode Structure (first-class concern)
- `ACT-624` - Participant Interaction Budgets And Quotas

It is governed by **ADR-013** (participant episode lifecycle boundaries) and
**ADR-097** (scoped participant resource budgets and shared-service fairness).
It composes the participant behavior model (ADR-067), participant semantics
(ADR-022), decision-epoch/state-cut semantics (ADR-095), the shared time model
(ADR-090/091), and autonomous execution (ADR-092) into one authored, portable
episode + budget surface. **It is a design artifact, not an implementation
artifact**: executable SDL syntax, published schemas, validators, runtime
carriers, and tests are owned by the spawned child issues #305-#310. All six
requirements remain `DRAFT`; this design unblocks them.

## Why episode and budget are one design

Six requirements across three layers (SEM = semantics, DSL = authored surface,
ACT = model / first-class support) form one coherent model along two domains:

| Layer | Episode domain | Budget domain |
| --- | --- | --- |
| SEM (semantics) | SEM-222 | SEM-223 |
| DSL (authored surface) | DSL-120 | DSL-121 |
| ACT (model / first-class support) | ACT-623 | ACT-624 |

The episode and budget boundaries depend on each other.
An authored episode may declare interaction budgets whose exhaustion is an authored terminal/truncation condition.
A budget's reset scope is relative to the episode reset boundary.
Both use the same participant identity, generation, order, clock, and evidence coordinates.
Separate designs would duplicate those shared coordinates.

## Current coverage and the gap this design fills

Existing coverage this design **reuses and must not duplicate**:

- **ADR-013** and `implementations/python/packages/raes_contracts/participant_episode.py`
  own the runtime/contract episode surface: `ParticipantEpisodeExecutionState`,
  `ParticipantEpisodeHistoryEvent`, the `ParticipantEpisodeStatus` /
  `ParticipantEpisodeTerminalReason` / `ParticipantEpisodeControlAction`
  taxonomies, snapshot-stream integrity, and `RUN-311` runtime realization.
- **ADR-097** and the `ParticipantResource*` family
  (`implementations/python/packages/raes/participant_resource_budgets.py`,
  `implementations/python/packages/raes_contracts/contracts/participant_resource_budgets.py`,
  `implementations/python/packages/raes_runtime/participant_resource_reservation.py`,
  `participant_resource_accounting.py`, `participant_resource_pool_ledger.py`)
  own scoped resource budgets, capacity, atomic admission, accounting, fairness,
  and reset reconciliation.
- **ADR-095** names the reset participant-memory scope
  (`episode_local_reset` vs `persistent_across_episodes`) and the decision-epoch
  reset boundary.
- **ADR-054** records RL/game `termination` and `truncation` signals as distinct
  from the ADR-013 episode terminal reason, related "only via an explicit closure
  record" (invariant I28) — a closure record this design defines.
- **SEM-211** already carries the `resource` precondition class, the
  `resource_exhausted` failure class, and the `exhausted` constraint state in
  `specs/formal/participant-semantics/README.md`.

The gap (each item is greenfield at the SEM/DSL/ACT layers):

- the cross-stage *semantic meaning* of episode boundaries, each terminal
  reason, and reset (SEM-222 was only a `partial` coverage row with no spec
  section);
- the *interaction-level* consumption→exhaustion→effect semantics (SEM-223 was
  `planned`);
- an *authored* SDL surface for episode structure and interaction budgets
  (DSL-120/121 did not exist — ADR-013 §6 and ADR-054 previously excluded a new
  SDL episode-authoring surface; ADR-013's `## Amendments` records the decision
  to open it for authored *intent* that compiles to the existing contracts); and
- treating episode structure and interaction budgets as *first-class* authored
  and model concerns (ACT-623/624 did not exist).

## Model summary

```text
ParticipantEpisodeAndBudgetModel =
    AuthoredEpisodeStructure           (DSL-120)
  + EpisodeBoundaryAndTerminationRules (SEM-222)
  + FirstClassEpisodeConcern           (ACT-623)
  + AuthoredInteractionBudgets         (DSL-121)
  + BudgetConsumptionAndExhaustionRules(SEM-223)
  + FirstClassBudgetConcern            (ACT-624)
  bound to
    the ADR-013 ParticipantEpisode* runtime/contract surface, and
    the ADR-097 ParticipantResource* budget family.
```

The model has three layers, linked by stable references and never
interchangeable (mirroring the ADR-067 behavior model):

1. **Authored layer** - SDL episode-structure and interaction-budget
   declarations expressing participant *intent* (initialization conditions,
   turn/interaction structure, terminal and truncation conditions, reset policy,
   and interaction-budget allowances).
2. **Realization layer** - compilation to the existing `ParticipantEpisode*`
   contract addresses and projection of authored interaction budgets into the
   ADR-097 canonical `ParticipantResourceBudgetPolicy` demand, plus backend
   capability/support claims.
3. **Evidence layer** - the ADR-013 episode state/history stream, the ADR-097
   budget state/event/pool records in `RuntimeSnapshot`, terminal-reason events,
   consumption events, exhaustion dispositions, and evidence refs.

## Episode domain

<!-- vale RAES.HeadingCase = NO -->
### SEM-222 - episode boundary and termination semantics

Design commitments:

<!-- vale RAES.HeadingCase = YES -->

- **Identity and generation.** Episode identity, generation, and cross-reset
  lineage are ADR-013's (`participant_address` stable; a new distinguishable
  `episode_id` per instance; seq-0 = `INITIALIZE`, seq>0 = `RESET`/`RESTART`
  with a distinct `previous_episode_id`). SEM-222 adds the portable *meaning* of
  those boundaries, not a second identity scheme.
- **Terminal reasons are distinct semantic events.** `completed`, `timed_out`,
  `truncated`, and `interrupted` each name a different closure meaning and are
  not interchangeable labels. Truncation is a bounded, non-failure early stop;
  timeout is a temporal-limit stop; interruption is an externally-induced stop;
  completion is a goal/terminal-condition stop. None of them is a synonym for
  budget exhaustion, action rejection, backend process failure, workflow
  completion, cancellation, or teardown.
- **Authored terminal/truncation condition vs realized reason.** The *condition*
  that should end or truncate an episode is authored intent evaluated over
  declared conditions, propositions, temporal contracts, and evidence; the
  realized terminal *reason* is an ADR-013 runtime fact. A condition maps to a
  terminal reason only through an explicit, evidence-bearing transition.
- **Episode terminal reason vs participant/objective/scenario outcome.** Per
  ADR-022 these remain distinct: a participant may complete its episode while
  the objective fails, or be truncated while the scenario continues. A relation
  exists only through a named outcome-interpretation rule (SEM-215), never by
  equating the coordinates.
- **RL termination/truncation closure record (fills ADR-054 I28).** When a
  backend reports an RL/game `termination` or `truncation` signal, its relation
  to the ADR-013 episode terminal reason is expressed as an explicit closure
  record carrying the source signal, the mapped terminal reason, the deriving
  authority, and evidence refs. Absent that record the two remain unrelated
  coordinates.
- **Reset/replay boundary and memory scope.** Reset/restart create a new episode
  generation and never rewrite prior history (ADR-013 §4). Every reset-scoped
  claim declares a participant-memory scope of `episode_local_reset` or
  `persistent_across_episodes` (ADR-095 §10); decision epoch and episode-local
  progress reset to zero, while already-delivered observations and evidence are
  not retroactively erased.

<!-- vale RAES.HeadingCase = NO -->
### DSL-120 - authored episode structure and termination surface

Design commitments:

<!-- vale RAES.HeadingCase = YES -->

- **A typed, versioned authored episode-policy record** attaches to the existing
  participant behavior specification (ACT-606), parameterized by
  participant/episode generation. It declares: initialization conditions,
  turn/interaction structure, terminal conditions, truncation conditions, and
  reset-related policy. It is *intent*, never an execution record: it cannot
  assert that an episode initialized, a turn was observed, a reset occurred, or a
  terminal condition was realized.
- **Reuse of closed authoring surfaces.** Conditions, propositions/assertions,
  temporal contracts, evidence requirements, and participant/deployment identity
  are the existing closed refs (`SDLModel(extra="forbid")`, `parse_sdl`,
  `SemanticValidator`) - not a new workflow language, scheduler, generic state
  machine, timeout engine, or free-form policy blob. Authored conditions are
  never backend expressions, callables, or shell/env fragments.
- **Compilation target is ADR-013.** The authored policy compiles to stable
  `participant.episode-policy.<name>` runtime refs beside the existing
  `ParticipantEpisode*` addresses; it does not publish a parallel episode schema
  family or backend DTO.

<!-- vale RAES.HeadingCase = NO -->
### ACT-623 - participant episode structure as A first-class concern

Design commitments:

<!-- vale RAES.HeadingCase = YES -->

- Episode structure is a **named, versioned, traceable, reviewable** member of
  the participant model aggregate - not a backend-local convention and not only a
  runtime contract. It aggregates the DSL-120 authored policy, the SEM-222
  boundary semantics, and refs to the ADR-013 realization/evidence surface.
- Interaction/turn ordering uses the existing scheduler, decision-epoch
  (ADR-095), and shared-time (ADR-090) authorities. The episode
  `sequence_number` orders episode *instances* only; it never becomes a global
  action/turn-order surrogate.
- No implication that every participant exposes an internal reasoning loop; this
  is an observable participant/runtime episode structure.

## Budget domain

<!-- vale RAES.HeadingCase = NO -->
### SEM-223 - budget, quota, consumption, and exhaustion semantics

Design commitments:

<!-- vale RAES.HeadingCase = YES -->

- **One budget family (ADR-097 v3), four separated authorities.** Authored/
  admitted demand (`ParticipantResourceBudgetPolicy`), configured pool capacity
  (`ParticipantResourcePoolCapacity` in `backend-manifest-v2`), runtime
  reservation/use/exhaustion (`ParticipantResourceBudgetState`,
  `ParticipantResourcePoolState`, append-only budget events), and measured
  realization (exact native measurement vector + evidence). Intent ≠ capacity ≠
  availability ≠ measured use ≠ evidence; never collapsed to one number.
- **Consumption→exhaustion is an interaction-level accounting state machine**
  layered on the ADR-097 reserve → admit/reject → commit/release → reconcile
  accounting: each governed dimension accumulates committed use across repeated
  reserve→commit cycles and stays admissible while remaining capacity
  `rem = limit − used − reserved` is positive, becoming exhausted only when
  `rem ≤ 0`. A committed measurement never terminally consumes the dimension; it
  advances cumulative use and the dimension re-opens for the next reservation
  until the allowance is spent. Consumption events are ordered, generation-fenced,
  append-only; stale, future, or cross-generation events fail closed.
- **Limit-triggered effect is an explicit, evidence-bearing mapping.** Reaching a
  limit produces a typed disposition (deny the action, throttle, truncate the
  episode, interrupt, or emit a `resource_exhausted` failure class). Exhaustion
  maps to an episode terminal reason (`truncated`/`interrupted`) *only* through
  the explicit SEM-222 terminal-condition transition - it never silently becomes
  a terminal reason, backend error, or workflow state.
- **Reuse of SEM-211.** The `resource` precondition class, the
  `resource_exhausted` failure class, and the `exhausted` constraint state are
  the existing semantic anchors; SEM-223 defines their interaction-budget
  meaning, not a new failure taxonomy.
- **Reset scope.** An episode/segment reset resets only episode-generation-owned
  budget state. Tenant, shared-service, fleet, persistent-growth, and
  unreconciled-reservation state follow ADR-097's typed reset/reconciliation
  owner; an episode reset never zeroes aggregate use or releases active leases
  without that owner's rule.

<!-- vale RAES.HeadingCase = NO -->
### DSL-121 - authored interaction budget surface

Design commitments:

<!-- vale RAES.HeadingCase = YES -->

- **Interaction budgets are authored allowances that project into the ADR-097
  canonical demand**, mirroring how V1/V2 autonomous limits project with
  `legacy_maximum` provenance - not a second interaction-budget root, generic
  `dict[str, number]` quota map, or free `max_*` field.
- **step / turn / time / token / tool-use are distinct governed dimensions**,
  never silently substituted:
  - a *step/turn* budget is a metered interaction count (governed
    `resource_kind` + meter profile), distinct from an action-attempt count;
  - a *time* budget uses the ADR-090/091 clock/temporal authority for a
    logical-scenario elapsed-time limit - host watchdog wall-clock time is *not*
    a portable scenario-time quota;
  - a *token* budget reuses ADR-097's `inference_tokens` dimension;
  - a *tool-use* budget binds exact action-contract/execution-binding identity -
    a tool invocation is not implicitly an action unless the authoring contract
    defines that equivalence.
- **New dimensions extend the catalog, not the schema shape.** A dimension the
  initial catalog lacks (e.g. turn count, tool-invocation count, logical-scenario
  time) is added through the governed `resource_kind` + `meter_profile` seam with
  a compatible accounting mode and reset/clock basis, together with the SDL,
  contract, compiler, schema-publication, fixture, and conformance updates ADR-097
  requires - not an optional side field.

<!-- vale RAES.HeadingCase = NO -->
### ACT-624 - participant interaction budgets and quotas as first-class support

Design commitments:

<!-- vale RAES.HeadingCase = YES -->

- Interaction budgets/quotas attach to the **participant/behavior-specification
  aggregate itself**, so they apply across participant implementation kinds
  (human, scripted, RL, LLM, autonomous), not only the ADR-092 autonomous
  profile. The corresponding runtime IR/state and the backend capability
  declaration for interaction-level budgets ride the existing
  `participant_runtime` manifest capability root.
- Fairness, priority, borrowing, reclaim, and starvation bounds remain ADR-097's
  explicit obligations; role color or evaluation status never implies priority.
- Backend enforcement (OCI/cgroup limits, service quotas, accelerator claims) is
  realization *evidence*, not portable proof; support ≠ configured capacity ≠
  current availability ≠ measured use.

<!-- vale RAES.HeadingCase = NO -->
## Abstract state machine (FM3)

This design is **FM3 (stateful / control semantics)** per ADR-018/ASR-505. The
authored/semantic layer's abstract state machine, over one participant
`(participant_address, episode_generation)`:

<!-- vale RAES.HeadingCase = YES -->

```text
Episode states:      DECLARED_INITIALIZED
                     RUNNING
                     TERMINAL{ completed | timed_out | truncated | interrupted }
Control actions:     initialize | reset | restart
Budget accounting    (per governed resource dimension d, per episode generation):
  quantities:        limit L(d); cumulative committed used(d); outstanding reserved(d);
                     remaining rem(d) = L(d) - used(d) - reserved(d)
  admission:         OPEN(d)      while rem(d) > 0   (accepts new reservations)
                     EXHAUSTED(d) while rem(d) <= 0  (derived from remaining capacity across
                                                      repeated cycles; not a one-shot state)
  reset:             used(d), reserved(d) := 0 for episode-local dimensions on T2;
                     aggregate/tenant/fleet/persistent dimensions follow ADR-097's reset owner

Transitions (fail-closed; unknown/stale/future/cross-generation input rejected):
  T1 initialize(gen=0)         : (-)               -> RUNNING                [seq 0, no previous_episode_id]
  T2 reset|restart             : RUNNING|TERMINAL  -> RUNNING (gen+1)        [new episode_id, previous_episode_id set,
                                                                             episode-local used/reserved reset,
                                                                             aggregate/tenant/fleet preserved]
  T3 terminal_condition_met(c) : RUNNING           -> TERMINAL(reason(c))    [reason via explicit evidence-bearing map]
  T4 timeout(clock)            : RUNNING           -> TERMINAL(timed_out)    [ADR-090 clock authority]
  T5 truncation_condition_met  : RUNNING           -> TERMINAL(truncated)    [bounded non-failure early stop]
  T6 interruption(external)    : RUNNING           -> TERMINAL(interrupted)
  T7 reserve(d, q)             : OPEN(d), q <= rem(d)  => reserved(d) += q   [atomic all-or-nothing across the vector]
  T8 commit(d, q, m)           : outstanding q, m <= q => used(d) += m;      [exact measured m + evidence; the dimension
                                                          reserved(d) -= q    stays OPEN while rem(d) > 0, so it supports
                                                                             many reserve->commit cycles until rem(d) <= 0]
  T9 release(d, q)             : outstanding q         => reserved(d) -= q   [exactly once; on cancel/timeout/stale/fail]
  T10 reject(d, q)             : q > rem(d)            => no state change     [typed rejection disposition]
  T11 exhaustion_effect(d)     : EXHAUSTED(d) or T10   -> {deny | throttle | T5 | T6 | resource_exhausted}
                                                                             [typed disposition; T5/T6 only via T3-style map]
```

The following fail-closed obligations apply:

- Exhaustion is derived from remaining capacity `rem(d)` across repeated reserve->commit cycles, never a one-shot flag.
- T2 must not zero aggregate/tenant/fleet/persistent budget.
- T7 admits only when `q <= rem(d)` and is atomic across the full resource vector against one pool ledger.
- T8 records an exact measured vector `m <= q` with matching operation/generation/meter/evidence.
  It leaves the dimension open while `rem(d) > 0`.
- T9 settles each outstanding reservation exactly once.
- T11 reaches a terminal reason only through the explicit T3-style transition with evidence.

## Cross-clause invariants

| ID | Invariant | Primary clauses |
| --- | --- | --- |
| EBM-01 | An authored episode/budget declaration is intent; runtime episode state, history, and budget accounting remain the ADR-013 / ADR-097 contract surfaces. | SEM-222, SEM-223, DSL-120, DSL-121 |
| EBM-02 | `completed`, `timed_out`, `truncated`, `interrupted` are distinct terminal reasons; truncation is not timeout, budget exhaustion, cancellation, backend failure, or workflow completion. | SEM-222 |
| EBM-03 | Reset/restart create a new episode generation and never rewrite history; an episode reset never zeroes tenant/shared-service/fleet/persistent budget or releases active leases without ADR-097's reset owner. | SEM-222, SEM-223, ACT-623, ACT-624 |
| EBM-04 | Authored interaction budgets project into the ADR-097 canonical demand; there is no second budget root, generic quota map, or free `max_*` field. | DSL-121, ACT-624 |
| EBM-05 | step, turn, time, token, and tool-use are distinct governed dimensions; none is silently substituted, and host watchdog time is not a portable scenario-time quota. | DSL-121, SEM-223, ACT-624 |
| EBM-06 | Budget exhaustion maps to an episode terminal reason only through an explicit, evidence-bearing terminal-condition transition. | SEM-222, SEM-223 |
| EBM-07 | Hidden quota/limit or terminal-condition state is participant-visible only through an explicit view/disclosure rule; it is never leaked through diagnostics, errors, or evidence. | SEM-223, DSL-120 |
| EBM-08 | Consumption and episode-history events are ordered, generation-fenced, and append-only; stale, future, or cross-generation events fail closed. | SEM-222, SEM-223 |
| EBM-09 | Backend enforcement is realization evidence, not portable proof; capability support ≠ configured capacity ≠ current availability ≠ measured use. | SEM-223, ACT-624 |
| EBM-10 | The RL/game termination/truncation signal relates to the ADR-013 episode terminal reason only through an explicit closure record. | SEM-222 |

## Source-to-contract-to-test matrix (the issue #122 readiness bar)

Each obligation maps to an existing typed contract/helper, a lifecycle enforcement point, a positive fixture, and a negative fixture.
This design **names** the fixtures and enforcement code.
Their deferred owner delivers them.
The required negative fixtures cover these cases:

- Cross-episode budget leakage.
- A global counter treated as participant-local state.
- Stale/future consumption events.
- Hidden quota state exposed without a view rule.
- Exhaustion bypassing controlled failure/outcome semantics.

| Obligation | Typed contract / helper (incumbent) | Enforcement point | Positive fixture | Negative fixture | Deferred owner |
| --- | --- | --- | --- | --- | --- |
| Distinct terminal reasons (EBM-02) | `ParticipantEpisodeTerminalReason`, terminal-event→reason map | `SemanticValidator` + episode history validation | episode declaring each of completed/timed_out/truncated/interrupted with distinct conditions | truncation authored as an alias of timeout / budget exhaustion | #305 SEM-222 |
| Authored episode policy is intent (EBM-01) | new `participant.episode-policy.<name>` compiled ref; `ParticipantEpisodeExecutionState` | compiler + `SemanticValidator` | authored policy compiling to episode refs | authored policy asserting realized initialization/turn/terminal state | #307 DSL-120 |
| Reset generation + lineage (EBM-03, EBM-08) | `ParticipantEpisodeControlAction`, snapshot-stream integrity checks | `iter_participant_episode_snapshot_violations` | reset creating gen+1 with `previous_episode_id` | reset rewriting prior history / reusing `episode_id` | #305 SEM-222 |
| RL termination/truncation closure record (EBM-10) | closure-record ref over `ParticipantEpisodeTerminalReason` | runtime episode validation | backend truncation mapped via closure record | backend `terminated` equated to episode terminal reason with no record | #305 SEM-222 |
| Interaction budget projects into ADR-097 demand (EBM-04) | `ParticipantResourceBudgetPolicy`, legacy-maximum projection | `raes_processor.compiler.participant_autonomous_execution` | step/turn/time/token/tool-use budget projecting to canonical demand | a parallel `max_turns` field bypassing the resource family | #308 DSL-121 |
| Distinct governed dimensions (EBM-05) | governed `resource_kind` + `meter_profile` catalog | planner capability admission (`participant_resource_budget_gaps`) | turn-count and tool-use as separate governed kinds | token count aggregated across incompatible meters; watchdog time as scenario-time quota | #306 SEM-223, #310 ACT-624 |
| Consumption→exhaustion→effect (EBM-06, EBM-08) | `ParticipantResourceBudgetState`, append-only budget events | `reserve/commit/release/reconcile` accounting | exhaustion producing a typed `resource_exhausted` disposition | exhaustion bypassing controlled failure/outcome semantics to force a silent terminal state | #306 SEM-223 |
| Reset budget scope (EBM-03) | ADR-097 typed reset/reconciliation owner; canonical pool ledger | runtime reconciliation, generation fencing | episode reset preserving tenant/fleet aggregate use | episode reset zeroing a shared pool counter (cross-episode budget leakage) | #306 SEM-223 |
| Budget-as-participant-local vs aggregate (EBM-03) | owner graph (`ParticipantResourceOwner`) | `participant_resource_budget_owner_errors` | participant-local budget under a distinct owner | a global counter treated as participant-local state | #306 SEM-223, #310 ACT-624 |
| Hidden limit/quota view rule (EBM-07) | participant context view (SEM-214/216), observation boundaries | view-rule projection | quota surfaced only through an explicit view rule | hidden quota state exposed without a view rule | #308 DSL-121, #306 SEM-223 |
| First-class attachment across kinds (ACT-623/624) | participant behavior specification aggregate | `SemanticValidator` behavior-spec verification | budget/episode policy attached to a non-autonomous participant | budget available only on the autonomous profile | #309 ACT-623, #310 ACT-624 |

## Child-issue mapping

| Issue | UID | Executable ownership (waived from this design run) |
| --- | --- | --- |
| #305 | SEM-222 | Episode/termination semantic gates, closure record, invariant oracle coverage. |
| #306 | SEM-223 | Budget consumption/exhaustion/effect semantic gates and reset-scope enforcement. |
| #307 | DSL-120 | Authored episode-structure SDL syntax, validation, generated schema, compiled refs. |
| #308 | DSL-121 | Authored interaction-budget SDL syntax, projection into the ADR-097 demand, validation, schema. |
| #309 | ACT-623 | First-class episode-structure model member, aggregate attachment, conformance. |
| #310 | ACT-624 | First-class interaction-budget model member, backend capability declaration, conformance. |

## Verification expectations

Any executable child issue that claims this model must provide:

- parser/model negative tests for unknown fields and variable-created keys on the
  authored episode-policy and interaction-budget surfaces;
- semantic validation tests for unresolved condition, temporal, evidence, owner,
  meter, and reset refs (fail closed);
- generated-schema and schema-publication-manifest checks when a portable
  contract is added or changed;
- valid and invalid fixtures for every new portable contract, including the
  mandated negative fixtures above;
- runtime/conformance tests that prove episode identity/terminal-reason,
  budget reserve/commit/release/reconcile, generation fencing, reset scope, and
  redaction invariants; and
- Ground Control IMPLEMENTS/TESTS traceability appropriate to the artifact.

Issue #122 satisfies the design requirement by recording ADR-013's amendment,
ADR-097's dimension clarification, this formal spec, and the joint preflight
notes (`docs/decisions/issue-122-sem-222-episode-budget-model-preflight.md`,
`docs/decisions/issue-306-sem-223-participant-resource-budget-preflight.md`).

## Primary-source review

The design starts from participant-local lifecycle and resource invariants, not
from counters or timeout fields:

- **Episode / termination / truncation lineage.** RL environment interfaces
  (the Gymnasium episode model, adopted as the `episodes` concept-family lineage
  in `specs/concept-authority/reference-models.md`) separate *termination* (a
  terminal state reached by the task's own dynamics) from *truncation* (an
  externally imposed early stop such as a time/step limit). SEM-222 preserves that
  distinction as separate terminal reasons rather than a single "done" flag, and
  keeps reset/replay a new-episode boundary rather than an in-place mutation.
- **Budget / quota lineage.** Agent and participant benchmarks routinely impose
  explicit interaction budgets - step, turn, wall/scenario time, token, and
  tool-use limits - that materially shape behavior and how outcomes are compared.
  SEM-223/DSL-121 treat those as first-class authored allowances with defined
  exhaustion effects rather than backend-local conventions, projecting them into
  the ADR-097 resource-budget authority so consumption, capacity, availability,
  and measured use stay distinct.

Both lineages are pinned through the existing concept-authority reference-model
and lineage-ledger surfaces; child issues that add a governed dimension or term
update the matching pinned source artifact in the same change.
