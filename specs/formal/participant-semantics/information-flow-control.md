<!-- vale RAES.HeadingCase = NO -->
# SEM-230 participant information-flow and control semantics

Classification: FM3.

<!-- vale RAES.HeadingCase = YES -->

Requirement: `SEM-230`.

Authority revision: `sem-230/rev2`.

## Scope and authority

This specification defines the participant-relative information-flow and
control semantics adopted by ADR-085. It composes the existing participant and
runtime objects; it does not add another carrier family, policy engine, gateway,
transport, store, logger, or audit stream.

The machine-readable relation binding is
`policy-noninterference` in taxonomy `raes-behavioral-relations`, revision
`rev2`, published by
`contracts/concept-authority/behavioral-relations-v1.json`. The contract name
remains `behavioral-relations/v1` because the closed JSON shape is unchanged;
`rev2` is the revision of the relation taxonomy carried by that shape.

This document is definition authority. The executable cases in
`implementations/python/tests/test_sem_230_information_flow_control.py` are
bounded falsification evidence. Neither artifact is production enforcement or
a universal proof.

Revision `sem-230/rev2`, adopted by ADR-095, makes decision-surface output a
first-class low observation, binds policy decisions to exact state cuts, and
quantifies the baseline over adaptive participant strategies. Revision
`sem-230/rev1` remains the historical open-loop formulation; its
`observation/order` scalar must not be reused as a v2 decision epoch or
state-cut identity.

## Prior-art adaptation rule

SEM-230 does not rename settled formal concepts as RAES inventions.
It imports the strongest clearly applicable prior definition and applies it to existing RAES carriers.
It adds an RAES-specific coordinate only when the prior formulation lacks information needed by participant/runtime governance.

| Semantic element | Formal lineage reused | RAES adaptation | Necessary extension, not reinvention |
| --- | --- | --- | --- |
| participant-relative information state and low equivalence | Fagin, Halpern, Moses, and Vardi's interpreted-systems construction: points in runs are indistinguishable when the agent-local state agrees | local state is the existing `V_p,c` plus occurrence-preserving `H_{tr,rho}(p,e,c)` and every projection-visible control/policy coordinate | policy decision, audience, marking, memory scope, and declared cut/order model are included because they can change the RAES projection |
| noninterference and purge | Goguen and Meseguer's policy-relative noninterference and purge treatment of high actions, extended by reactive noninterference over strategies | high variation is evaluated against RAES crossings, and low observations are participant-projected history support sets under adaptive low strategies | policy changes are evaluated at each occurrence's exact state cut; the baseline composes an explicit declassification schedule and strategy class |
| declassification | Sabelfeld and Sands' dimensions and principles for what may be released, by whom, where, and when | release records bind source dimensions, participant/audience, actor/controller/authority, policy decision, state cut, markings, evidence, and provenance | RAES adds stable carrier/evidence coordinates and deny-first intersection with admission and marking; it does not redefine declassification as redaction |
| labelled transition and hidden-action treatment | Milner's labelled transition/`tau` discipline and van Glabbeek's separation of trace and branching-time relations | the SEM-230 alphabet maps each label to an existing RAES action, lifecycle, visibility, control, delivery, or evidence owner | observability is indexed by participant, audience, exact-cut policy decision, and declared order model; this definition does not claim weak or strong bisimulation |
| visible history and knowledge persistence | interpreted systems and the existing ADR-054 constructive visible-history/perfect-recall treatment | disclosure appends a stable visible occurrence to `H`; later concealment or revocation changes future projection | RAES preserves evidence/provenance and visible-order identity across rollback and supersession |
| causal and partial ordering | Lamport happened-before plus the Winskel event-structure and Mazurkiewicz trace-theory lineage already adopted by ADR-054 | SEM-230 reuses the existing `R_c`, visible partial order, and simultaneity groups | policy decisions and declassification events are located at exact cuts; no new clock or concurrency formalism is introduced |

The indirect derivations in the final two rows are intentional: SEM-230 reuses
the accepted participant-runtime authority and its formal sources instead of
copying or forking those definitions. Timed, probabilistic, divergence-sensitive,
or proof-bearing variants must extend the catalog with the corresponding prior
art and stronger evidence rather than silently strengthening this baseline.

## Existing objects and state

For participant `p`, episode `e`, trace `tr`, policy sequence `rho`, and exact
state cut `c`, SEM-230 reuses:

- `W_c`: world, backend, and evaluator truth;
- `V_p,c`: the participant view relation from ADR-022;
- `H_{tr,rho}(p,e,c)`: the occurrence-preserving participant-visible local
  history under the effective projection, marking/redaction rules, and visible
  order relation;
- `X_c`: archival evidence and authorized audit state;
- existing action proposals, admission records, results, observation
  envelopes, lifecycle histories, and evidence/provenance references;
- `R_c`: the declared total, partial, causal, simultaneous, or
  backend-serialized order relation; and
- `C_c` and `A_c`: controller coordinates and participant/actor authority
  coordinates at `c`.

The SEM-230 policy state is:

```text
Q_c = (W_c, V_p,c, H_{tr,rho}(p,e,c), X_c,
       R_c, C_c, A_c, M_c, rho_c)
```

where `M_c` is the governed marking state and `rho_c` is the exact-cut policy
decision. These coordinates remain distinct. In particular, `W_c` is not a
participant observation, `X_c` is not participant egress, and control-plane
caller authorization is not participant authority.

## Revisioned crossing relation

A crossing decision is evaluated over:

```text
C = (participant, episode, audience, direction, interaction_kind,
     source_ref, actor, controller, authority_basis,
     action_or_projection_ref, decision_epoch, state_cut_ref,
     order_model, policy_id, policy_revision,
     markings, authorization, admission, visibility,
     declassification, redaction_or_transformation,
     disposition, backend_posture, evidence_refs,
     provenance_refs, loss_and_limitations)
```

`C` is a relation over existing typed carriers and stable references. It is not
a payload bag. Unknown required coordinates fail closed. An owning vocabulary
may represent an optional coordinate as `not-applicable`, `unknown`,
`unsupported`, or disclosed loss; none of those states is implicit success.

For an attempted crossing `x` at exact state cut `c`, let:

```text
Effective(rho, c) = the unique authoritative policy decision r_c
                    returned for exactly c
```

The policy sequence is valid only when decision, revision, state-cut identity,
and applicable order model are explicit and unambiguous. A later or
incomparable decision cannot authorize `c`. Decision epoch, receipt order,
timestamp equality, last-writer-wins, or a later final-state snapshot cannot
substitute for state-cut resolution.

The deny-first admission predicate is:

```text
MayCross(x, Q_c) =
  AuthenticatedActor(x.actor)
  and TargetAuthorized(x.actor, x.source_ref)
  and ParticipantAuthority(x.participant, x.controller, x.authority_basis, c)
  and ApplicableAndAdmitted(x.action_or_projection_ref, c)
  and VisibleTo(x.source_ref, x.participant, x.audience, V_p,c)
  and MarkingAuthorized(x.markings, x.participant, x.audience, c)
  and DeclassificationOK(x.declassification, Effective(rho, c))
  and BackendSupports(x, c)
  and TransformationResultValid(x.redaction_or_transformation, c)
```

Each conjunct has its existing owner and evidence. No successful conjunct can
widen a failed or unresolved conjunct. Redaction and transformation validity
never grant authority. A transformed action has a new identity and provenance
and must pass structural, semantic, and admission validation again.

Retries preserve their idempotency identity only while policy, controller,
authority, subject, marking, and relevant state coordinates remain equal. A
change to any of those coordinates requires a fresh decision.

## Distinct operations

The following operations are not synonyms and cannot be collapsed into one
Boolean or disposition:

| Operation | Semantic effect | Explicit non-effect |
| --- | --- | --- |
| authentication and authorization | Bind a caller to a target and authority scope. | Do not establish participant authority, visibility, or current admission. |
| admission | Decide whether one action or crossing may proceed at the current state/order point. | Does not establish delivery, observation, or future admissibility. |
| withholding | Record intentional non-release. | Does not erase a prior release. |
| projection or masking | Select the participant/audience-relative view. | Does not grant authorization or change the source. |
| redaction | Change the representation of content already authorized for the audience. | Does not authorize release or declassify the source. |
| declassification | Change the governed release basis for named content, dimensions, audience, authority, revision, and order interval. | Does not itself prove delivery, backend realization, or erasure. |
| disclosure | Record an authorized release decision. | Does not prove delivery or participant observation without their evidence. |
| delivery | Record a participant-facing occurrence at a declared order point. | Does not prove consumption, acknowledgement, or interpretation. |
| concealment | Change future projection or availability. | Does not remove a prior visible occurrence from local history. |
| revocation | Withdraw future authority or availability. | Does not retroactively withdraw participant knowledge. |
| transformation | Create a new result identity with rule/revision, provenance, markings, evidence, and loss. | Does not inherit source admission or silently remove markings. |
| loss | Disclose unavailable fidelity or information. | Is not successful security enforcement. |
| weakening | Remove a stronger capability or relation claim and disclose the weaker posture. | Is not conformance to the stronger claim. |

Presentation, candidate membership, eligibility, selection, approval,
admission, attempt, result, disclosure, delivery, observation, and archival
retention are separate transition facts. Audit retention is an evidence
audience, not participant egress.

## Labelled transitions

The closed semantic alphabet for revision `sem-230/rev2` is:

| Label class | State owner or incumbent | Visibility rule |
| --- | --- | --- |
| proposal | participant action proposal or decision surface | Relative to participant, audience, and current projection. |
| approval / denial | control and authority decision | Neither is execution or admission. |
| direction / intervention | existing mixed-control and intervention coordinates | May differ by participant and audit audience. |
| handoff / override / cancellation | controller and authority state | Effective only at the declared order point. |
| admission / rejection | SEM-211 action admission | Decision at one state/order point. |
| attempt / result | behavior history and action-result carriers | Visibility follows the applicable observation boundary. |
| disclosure / withholding | policy decision | Disclosure is not delivery; withholding is append-only evidence. |
| transformation | source/result provenance and fresh admission | The result has a new identity. |
| delivery / observation | runtime occurrence and observation envelopes | Delivery order, observation, and acknowledgement remain distinct. |
| concealment / revocation | view transition and future authority | Cannot erase an earlier visible occurrence. |
| policy change | revisioned policy state | Never applies retroactively. |
| evidence / audit | archival state `X_c` | Visible only to its authorized evidence audience. |

Let `Q -l-> Q'` mean a valid transition carrying one label from this table and
its owned evidence. Labels are semantic classes; they do not authorize a new
implementation-local enum or wire field in issue #796.

## Participant-relative projection and hiding

For participant `p`, audience `a`, policy decision `r_c`, and state cut `c`,
define a revisioned projection:

```text
Pi[p,a,r_c,c] : labelled occurrence history -> visible occurrence history
```

An occurrence is retained only when the effective `V_p,c`, audience scope,
marking/declassification intersection, delivery basis, and order model retain
it. Retained occurrences preserve stable occurrence identity, visible order,
and simultaneity. Equal payload values never collapse repeated occurrences.

The hidden set is:

```text
Tau[p,a,r_c,c] = { l | Pi[p,a,r_c,c](l) = epsilon }
```

Membership is participant-, audience-, policy-, and order-relative. It is not
an intrinsic event flag. Backend-internal work is not automatically `tau`.
The baseline projection removes finite `tau` stuttering and does not treat
hidden divergence, termination, progress, or wall-clock duration as visible.
Any stronger divergence-, progress-, termination-, or timing-sensitive claim
must select another governed relation and evidence it.

Concealment, revocation, rollback, supersession, redaction, and later policy
change alter future projection or append new visible occurrences. They never
delete or mutate an occurrence already present in `H_{tr,rho}(p,e,c)`.

## Low equivalence, dynamic purge, and declassification

Fix participant `p`, episode scope `e`, audience `a`, policy sequence `rho`,
and initial state cut `c0`.

Two initial states are low-equivalent,
`q1 ~=_{p,e,a,rho,c0} q2`, exactly when these participant-policy coordinates
are equal:

- participant and episode identity;
- `V_p,c0`, participant-visible local history, delivered decision-surface
  views, and visible occurrence order;
- controller identity and participant/actor authority visible to `p`;
- exact policy-decision identity/revision and its state-cut ref;
- public markings, declassification authority visible to `p`, and declared
  loss/weakening state; and
- every other state coordinate that `Pi[p,a,rho,c0]` retains.

`W_c0` and `X_c0` may differ only in coordinates classified high for this
participant-policy comparison. Equality of hidden backend state is not
required. Conversely, calling two states low-equivalent without naming all
projection-affecting coordinates is invalid.

For a run prefix `alpha`, dynamic purge is:

```text
purge[p,e,a,rho](alpha) =
  the occurrence-preserving subsequence that retains
    admitted low inputs,
    policy-change events,
    and permitted declassification events,
  while removing unauthorized high inputs at the exact state cut where
  each input was evaluated
```

Purge is dynamic: each occurrence is evaluated against the authoritative
policy decision at its exact state cut. A later or incomparable policy decision
cannot cause an earlier high input to be retained. A permitted declassification
event records at least the released dimensions, participant/audience,
actor/controller/authority basis, policy identity/revision/decision, exact
state-cut ref, markings, evidence, and provenance.

Two declassification schedules are equal only when those governed coordinates
and their visible order are equal. Merely releasing equal values is
insufficient.

## Baseline reactive policy-noninterference obligation

Fix:

- participant `p`, episode scope `e`, and audience `a`;
- model `M` and valid-transition predicate;
- environment class `Env`, scheduler class `Sched`, and order model `Ord`;
- policy sequence `rho` and permitted declassification schedule `D`; and
- initial state cut `c0`;
- participant-memory scope `Mem` (`episode_local_reset` only with
  authoritative reset of every visible memory channel, otherwise
  `persistent_across_episodes`); and
- a class `Sigma_L` of low participant strategies mapping delivered local
  histories to proposal choices or nondeterministic choice sets.

Let `Runs(M, q, sigma, Env, Sched, Ord, rho, D, Mem)` be every valid run
generated when strategy `sigma` reacts only to its participant-visible local
history under those fixed parameters. Let:

```text
LowHist(M, q, sigma, ...) =
  { Pi[p,a,rho](tr) |
      tr in Runs(M, q, sigma, Env, Sched, Ord, rho, D, Mem) }
```

For total order, each element is an occurrence-preserving sequence. For partial
or causal order, each element is the declared visible order relation and
simultaneity groups—not one convenient linearization.

The baseline obligation is:

```text
forall q1, q2, sigma in Sigma_L:
  ValidInitial(q1) and ValidInitial(q2)
  and q1 ~=_{p,e,a,rho,c0} q2
  and StrategyIsLow(sigma, p, a, rho, Mem)
  and DeclassificationSchedule(q1) = D
  and DeclassificationSchedule(q2) = D
  => LowHist(M, q1, sigma, Env, Sched, Ord, rho, D, Mem)
     =
     LowHist(M, q2, sigma, Env, Sched, Ord, rho, D, Mem)
```

The same strategy is run against both low-equivalent initial states, but its
future choices may differ when the delivered low histories differ. The
obligation requires those complete projected support sets not to differ due
only to unauthorized high variation. Fixed open-loop input histories remain a
useful special case and falsification model, not the complete claim for an
adaptive human or agent.

The quantifiers over states, strategies, traces/runs, environments, schedulers,
and observations are explicit above. `M`, `Env`, `Sched`, `Ord`, `rho`, `D`,
`Mem`, and `Sigma_L` are fixed parameters of one claim; changing any of them
defines another claim instance. A probabilistic strategy requires a governed
probability kernel and measure-sensitive relation; support-set equality alone
does not establish probabilistic noninterference.

### Assumption boundary

- **Nondeterminism:** the obligation compares complete declared support sets of
  projected histories. One trace, one scheduler sample, or equality of sampled
  histories cannot establish it.
- **Termination, progress, and divergence:** the baseline is insensitive to
  termination and progress and removes hidden finite stuttering. It makes no
  divergence-sensitive claim.
- **Time:** wall-clock timing and duration are excluded. Declared logical or
  causal order remains part of visible history. A timing-sensitive claim is a
  different governed relation.
- **Concurrency and partial order:** the claim fixes the concurrency/order
  semantics. A partial-order claim compares the governed visible relation and
  simultaneity groups, not an arbitrary serialization.
- **Probability:** support sets are compared, not probability measures. A
  sampled support is not a measure. Probabilistic noninterference requires a
  separately governed probabilistic relation, kernel, bound, and evidence.
- **Environment and scheduler:** both classes are named and fixed. No result
  universalizes to an omitted environment or scheduler.

## Bounded executable evidence

The test-local model exercises these falsification cases:

1. unauthorized high variations are purged and leave the same projected
   support set;
2. authorized declassification changes visible history only at its exact
   governed state cut;
3. a future or incomparable policy decision cannot authorize another cut;
4. hiding varies by participant and audience;
5. authorization, admission, visibility, marking, backend support, and
   transformation validity compose deny-first;
6. redaction does not grant authority and a transformation requires fresh
   admission;
7. concealment and revocation do not erase prior participant knowledge;
8. nondeterministic support-set differences are detected;
9. adaptive low strategies cannot react to undelivered high variation but do
   react when that variation leaks;
10. reset preserves persistent participant information unless an
    authoritative episode-local memory reset is declared; and
11. positive noninterference prose must bind the governed relation and an
    evidence boundary.

These are finite counterexamples and mutation/property checks. They can refute
the bounded model when an invariant is broken. They do not establish the
universal obligation above, and they do not establish production or backend
realization.

## Clause-to-artifact-to-assurance matrix

| SEM-230 clause | Normative / machine-readable artifact | Executable or policy evidence | Assurance status and nonclaim |
| --- | --- | --- | --- |
| participant-relative world, view, local history, archival evidence, controller, authority, and order coordinates | this specification, “Existing Objects And State” | existing participant/runtime validators plus the bounded model | defined; existing adjacent carriers are partly implemented; no complete runtime policy path claimed |
| revisioned crossings, exact-cut policy decisions, labels, transitions, hidden actions, and projection | this specification, crossing/label/projection sections | exact-cut resolution, audience-relative hiding, append-only-history, memory-scope, and adaptive-strategy tests | defined and bounded-tested; no wire contract or universal runtime enforcement claimed |
| authorization, admission, withholding, projection, redaction, declassification, disclosure, concealment, revocation, transformation, loss, and weakening remain distinct | this specification, “Distinct Operations” | deny-first, redaction, transformation, concealment, and revocation tests | defined and bounded-tested; no production enforcement claimed |
| exact reactive noninterference relation, low equivalence, purge, declassification, participant memory, strategy quantifiers, scheduler/environment, order, termination/progress/timing, nondeterminism, and probability | this specification plus catalog relation `policy-noninterference` | finite support-set, adaptive-strategy, exact-cut, and memory-scope cases | definition complete; test status bounded; proof deliberately unproved |
| claims bind through the relation catalog with evidence status and nonclaims | behavioral-relation catalog revision `rev8` and claim surface `participant-information-flow-policy` | `tools/check_behavioral_relation_claims.py` and catalog/claim tests | catalog implemented and tested; no claim truth inferred from a valid binding |
| intellectual lineage and exact RAES mappings | `docs/explain/sdl/lineage.md`, lineage ledger, and source audit | SDL-lineage policy gate | reviewed derivation record; no source syntax or compatibility claim |

## Follow-on ownership and nonclaims

SEM-230 owns the semantic coordinates and relation definition. It leaves these
extension points explicit for:

- issue #810: opacity and supervisor-policy visibility;
- issue #811: a separately selected proof-bearing bisimulation target;
- issue #812: the adversarial participant/control threat model; and
- issue #813: simulation and federation realization precedents.

The existence of those seams is not evidence that SEM-230 already establishes
their properties.

SEM-230 does not add SDL fields, compiler IR, public DTOs, APIs, runtime
mediation, persistence, transport, backend adapters, capability terms, or
migration logic. It does not certify API-408 as participant-safe egress or any
backend as realizing the policy. It makes no universal noninterference, trace
inclusion/equivalence, simulation, refinement, strong/weak bisimulation,
epistemic indistinguishability, timed-security, probabilistic-security, or
erasure claim.

## Primary sources

- Goguen and Meseguer, “Security Policies and Security Models” (1982), DOI
  `10.1109/SP.1982.10014`.
- Sabelfeld and Sands, “Declassification: Dimensions and Principles” (2009),
  DOI `10.3233/JCS-2009-0352`.
- ADR-022, ADR-054, ADR-081, ADR-083, and ADR-085.
