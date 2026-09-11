# Participant Semantics Formal Design

This document is the issue #71 formal design artifact for:

- `SEM-208` - Participant Behavior Semantics
- `SEM-209` - Multi-Participant Interaction Semantics
- `SEM-210` - Visibility And Information-Boundary Semantics
- `SEM-211` - Participant Preconditions, Effects, And Failure Semantics
- `SEM-212` - Participant Causality And Attribution Semantics
- `SEM-213` - Temporal Participant Semantics
- `SEM-215` - Participant Outcome Interpretation Semantics
- `SEM-219` - Participant Tool And Affordance Semantics
- `SEM-220` - Participant Decision-Surface Semantics
- `SEM-226` - Participant Exposure And Visibility-Boundary Semantics
- `SEM-230` - Participant Information-Flow And Control Semantics
- `SEM-231` - Participant-Relative Predicate Opacity Semantics
- `SEM-232` - Proof-Bearing Participant-Crossing Bisimulation
- `SEM-233` - Adversarial Participant Boundary Information-Flow Control
- `SEM-234` - Mixed Cross-Backend Participant-Control Composition
- `ASR-536` - Intentional-Subversion Participant Control Evaluation
- `ASR-537` - Cross-Backend Participant-Control Realization And Transfer Evidence
- `DSL-437` - Benign Participant Autonomous Execution

It is a design artifact, not an implementation artifact. It establishes the
semantic model that later child implementation issues must realize in SDL
models, semantic helpers, compiler/runtime contracts, evidence/provenance
contracts, and tests.

Issue #119 and ADR-083 extend the original issue #71 design with the joint
`SEM-219`, `SEM-220`, and `SEM-226` decision-surface model. Their executable
implementation remains owned by issues #294, #295, and #296.

Issue #796 and ADR-085 add the revisioned SEM-230 composition boundary. Its
normative model is the focused sibling specification
[`information-flow-control.md`](information-flow-control.md); this README's
world, view, history, action, visibility, and ordering objects remain the
incumbent carriers that model composes.

Issue #810 and ADR-099 add the focused SEM-231 composition boundary. Its
normative model is
[`participant-predicate-opacity.md`](participant-predicate-opacity.md). It
reuses SEM-230 policy, release, memory, strategy, supervisor, exact-cut,
scheduler, and order coordinates while keeping selected-predicate opacity
distinct from policy noninterference and projected-history equality.

Issue #811 and ADR-100 add the focused SEM-232 theorem and proof-program
boundary. Its normative design is
[`participant-crossing-bisimulation.md`](participant-crossing-bisimulation.md).
It selects a complete finite abstract crossing LTS and an independently
derived formal API-423/RUN-319 crossing-kernel LTS under one closed
participant/audience projection. It does not report the downstream
model-check, runtime mapping, backend conformance, noninterference, or opacity
result.

Issue #812 and ADR-101 add the SEM-233 boundary-flow and ASR-536
intentional-subversion evaluation design. Issue #1001 publishes the exact
`sem-233/rev1` two-coordinate obligation algebra, carrier mapping, and bounded
falsification evidence. Issue #1002 publishes the immutable flow profile and
portable relation contract; ASR-536 remains design-only. Their normative profiles are in
[`adversarial-flow-control.md`](adversarial-flow-control.md). The design
extends the existing participant, control, crossing, runtime, backend, and
experiment carriers with independent confidentiality and integrity
coordinates, conservative derivation, final-sink mediation, and explicit
attack-protocol variables. The #1001 SEM-233 finite model is not the #1002 portable contract,
runtime enforcement, backend realization, monitor-honesty, covert-channel, or
adversarial-robustness result.

Issue #813 and ADR-102 add the SEM-234 mixed-composition and ASR-537
realization/transfer-evidence design. Their normative profiles are in
[`cross-backend-participant-control.md`](cross-backend-participant-control.md).
The design supports both alternative simulation/emulation realization and
simultaneous mixed realization, plus linked inter-trial and finite
pre-admitted within-run changes. It keeps portable SDL backend-neutral and
preserves one acting controller in revision 1. It does not report runtime or
backend realization, multi-controller support, interoperability, transfer,
IFC/noninterference, or cross-backend equivalence.

Issue #861 and ADR-092 add deterministic autonomous execution for ordinary
participants. The focused normative composition is
[`autonomous-execution.md`](autonomous-execution.md): it binds existing
participant actions and observations to the shared time model, participant
implementation selection, backend-native execution, and typed runtime
readback. It adds no parallel actor or private time semantics.

## Current Sufficiency Finding

The existing implementation is not sufficient for `SEM-208` through `SEM-215`.

What exists:

- `agents.*` declares participant framing inputs: `entity`, `actions`,
  `starting_accounts`, `initial_knowledge`, `allowed_subnets`,
  `starting_assertions`, `authority_anchors`, and `operating_scope`.
- ADR-020 defines identity, role, starting conditions, authority anchors, and
  operating scope as authored participant framing.
- ADR-013 and the participant-episode contracts define lifecycle state and
  history for initialization, reset, restart, termination, and terminal reason.
- Objective, workflow, assessment, planner, runtime-result, and semantic-profile
  surfaces already provide patterns for shared semantic helpers and contract
  boundaries.

What is missing:

- no normative participant action contract beyond action names
- no observation model that distinguishes world truth from participant-visible
  projection
- no visibility, discovery, concealment, disclosure, or inference semantics
- no precondition/effect/side-effect/failure taxonomy for participant actions
- no joint-action model for coordination, contention, interference, or
  shared-state change among participants
- no temporal participant behavior model for cadence, dwell, deadlines,
  latency, schedule, or time-windowed action interpretation
- no evidence-labeled causality and attribution model connecting participant
  actions to state changes, detections, alerts, or downstream outcomes
- no participant-local outcome interpretation layer relating action/episode
  outcomes to objectives, workflows, evaluations, rewards, and evidence

The repository therefore remains at `partial` participant-semantics coverage
where runtime implementation slices are incomplete. Issue #487 adds
`implementations/python/tests/test_participant_semantics_invariant_oracle.py`
as the executable FM-2 assurance artifact for the abstract model invariants
`I1` through `I18`: it is implementation evidence for the published invariant
oracle, not a claim that every staged SEM-208 through SEM-215 runtime contract
is complete.

## Primary-Source Review

### Agent Environment Interfaces

[OpenAI Gym](https://arxiv.org/abs/1606.01540) and
[Gymnasium](https://arxiv.org/abs/2407.17032) provide the standard single-agent
environment abstraction: observation, action, reward, termination/truncation,
reset, and reproducibility-oriented wrappers. They justify making participant
action, observation, reward, and episode concepts explicit.

[PettingZoo](https://papers.nips.cc/paper/2021/hash/7ed2d3454c5eea71148b11d0c25104ff-Abstract.html)
extends this ecosystem to multi-agent environments through the Agent Environment
Cycle model. It is a useful precedent for explicit per-agent turns and
multi-agent API consistency, but RAES cannot adopt a turn-only worldview because
real cyber ranges also need concurrent, asynchronous, and backend-realized
action ordering.

[OpenSpiel](https://arxiv.org/abs/1908.09453) is relevant because it supports
multi-player, cooperative, zero-sum, general-sum, perfect-information, and
imperfect-information games. It reinforces that information structure and game
form are part of the experiment definition, not incidental implementation
details.

### Partial Observability And Multi-Agent Control

Kaelbling, Littman, and Cassandra's POMDP treatment frames sequential action
under incomplete observation; the core lesson for RAES is that a participant's
observation stream is not the environment state. Local history and belief matter
when interpreting behavior.

Littman's Markov games and the Dec-POMDP/POSG literature generalize this to
multi-agent interaction. Bernstein, Givan, Immerman, and Zilberstein
(Mathematics of Operations Research, 2002) show that decentralized control
under partial observability is fundamentally harder than centralized MDP/POMDP
control. Oliehoek and Amato's Dec-POMDP monograph fixes the standard vocabulary
RAES reuses for joint policies, action-observation histories, and information
states. RAES should not pretend that one global state and one global
observation stream are enough for multi-participant experiments.

Mean-field game theory — Huang, Caines, and Malhamé (2006) and Lasry and Lions
(2007), brought to MARL by Yang et al. (2018) — covers the population-limit
regime where individual interaction is replaced by interaction with a
population distribution. RAES's runtime layer records mean-field updates as
environment state over a population scope, not as hidden participant actions;
this lineage is why population-distribution disclosure is a first-class runtime
record in `specs/formal/participant-runtime/`.

### Knowledge, Information Structure, And Information Flow

Fagin, Halpern, Moses, and Vardi's interpreted-systems framework gives the
formal basis for participant-relative information: an agent's knowledge at a
point is determined by indistinguishability over its local state across global
runs. RAES's view relation `V_p,t`, local history `H_p,t`, and the
visible-history indistinguishability relation in
`specs/formal/participant-runtime/` are interpreted-systems constructions, not
ad hoc bookkeeping.

Dynamic epistemic logic (Baltag, Moss, and Solecki's announcement logics; van
Ditmarsch, van der Hoek, and Kooi's treatment) models information change as
explicit epistemic actions. This is the lineage for SEM-210's time-indexed
`view_transition` discipline: discovery, inference, disclosure, concealment,
and deception are recorded transition events that update a participant's view
relation, never silent side effects of topology or scheduling.

Kuhn's extensive-form game analysis (1953) is the original formal source for
information sets and perfect recall. Perfect recall is a property of an
information partition; a runtime claim that a participant history satisfies it
therefore needs a constructive, checkable witness over the visible projection.
The participant-runtime specification defines that witness; this document only
records the obligation.

Goguen and Meseguer's noninterference (1982) gives the information-flow reading
of the hidden-truth boundary (I2): hidden world state and adjudication assets
must be noninterfering with participant-visible projections in the absence of
an explicit disclosure rule. Sabelfeld and Sands' declassification dimensions
(2009) frame RAES disclosure rules as governed declassification policies: every
permitted release of hidden information declares what is released, where in the
view relation, when (the transition anchor), and by whose authority.

### Action Languages And Planning Formalisms

The precondition/effect/failure discipline in SEM-211 descends from the
planning literature. STRIPS (Fikes and Nilsson, 1971) introduced the
precondition/add/delete action model; PDDL standardized typed action schemata
with explicit preconditions and effects (Haslum et al.'s language introduction
is the consolidated reference); PDDL2.1 (Fox and Long, 2003) added durative
actions, temporal preconditions/effects, and numeric resources — the direct
ancestors of RAES temporal preconditions and resource preconditions; PPDDL
(Younes et al., 2005) and RDDL (Sanner, 2010) added probabilistic effects and
stochastic transition models, the lineage for RAES's non-deterministic effect
and `unknown_effect` classes.

RAES action contracts deliberately exceed this lineage: planning formalisms do
not carry visibility effects, evidence expectations, realization profiles,
fidelity claims, or mapping-loss labels, and they assume a closed-world effect
axiomatization that a cyber range cannot honestly claim. RAES therefore fails
closed on unresolved preconditions instead of assuming closed-world frame
axioms, and treats declared effect classes as disclosure obligations rather
than complete world models.

### Cyber Agent Environments

[CybORG](https://arxiv.org/abs/2108.09118) is the closest cyber-agent precedent.
It defines scenarios with agents, action spaces, observations, rewards, and
reset; it also supports simulation and emulation. The sim-to-emulation transfer
failures reported in the results discussion of Standen et al. (2021) are
directly relevant: an agent can overfit to an observation artifact that does
not exist in the emulator. RAES must therefore record observation provenance
and realized backend disclosure, not just action results.

[CyberBattleSim](https://www.microsoft.com/en-us/research/project/cyberbattlesim/)
shows the value and limits of abstract cyber-network simulation. It is useful
for studying automated agents, but its high-level abstraction reinforces the
need to disclose which action/effect/observation semantics are realized rather
than assuming simulation results transfer to operational environments.

[CyGIL](https://arxiv.org/abs/2109.03331) and its follow-on
[unified emulation-simulation training environment](https://arxiv.org/abs/2304.01244)
are relevant because the unified design derives simulation transitions from
emulated traces, preserving the same action space across the sim-to-real loop.
They motivate RAES's requirement that action and observation contracts survive
across backend fidelity modes.

CyGIL also exposes a negative design lesson: an abstract action such as
"network discovery" is too coarse to transfer honestly to a real or emulated
network when concrete tools, parameters, network configuration, and observation
effects differ. RAES action contracts therefore need declared behavioral
granularity, procedure basis, and realization profile, not only a tactic or
technique label.

### Cybersecurity Agent Benchmarks

[Cybench](https://arxiv.org/abs/2408.08926) specifies CTF-derived tasks with
task descriptions, starter files, evaluators, executable environments,
observations, and subtasks. It is useful precedent for executable task
specification and partial-progress evaluation, but it also shows why hidden
answer keys, starter-file exposure, scaffold differences, and subtask guidance
must be part of the semantic and provenance record.

[AutoPenBench](https://arxiv.org/abs/2410.03225) adds penetration-test tasks,
gold steps, generic and specific milestones, autonomous and human-assisted
agent variants, and repeated execution. It reinforces that result
interpretation cannot be reduced to final flag capture: progress milestones,
human assistance, task memory, and run-to-run stochasticity are part of the
instrumentation.

[CAIBench](https://arxiv.org/abs/2510.24317) argues that isolated offensive,
defensive, static-knowledge, and execution-only benchmarks miss integrated
cybersecurity performance. Its Attack-and-Defense and privacy categories
reinforce RAES's role-neutral multi-participant model and the need to record
privacy/redaction semantics in observation and evidence surfaces.

[AI Agents That Matter](https://arxiv.org/abs/2407.01502) and the
[LLM offensive-security benchmarking-practices study](https://arxiv.org/abs/2504.10112)
are broader benchmark-methodology critiques. They motivate explicit holdout
discipline, anti-contamination controls, scaffold and cost/resource
provenance, baseline disclosure, and standardized run records. RAES does not
turn these papers into benchmark policy here, but participant semantics must
not make those controls impossible.

### Cyber Range Scenario Semantics

[Open Cyber Range SDL](https://documentation.opencyberrange.ee/docs/sdl/) is
the authoring-surface lineage for scenarios, but it does not provide the
participant behavior semantics required here.

[VSDL](https://arxiv.org/abs/2001.06681) gives formal meaning to cyber range
infrastructure through satisfiability constraints and solver-backed scenario
realization. It is strong precedent for formal scenario meaning, but its scope
is infrastructure constraints, not participant observations, causal
attribution, or multi-agent behavior.

CRACK's Datalog verification is similar prior art for executable cyber range
feasibility. It supports RAES's policy of making semantic claims checkable, but
does not remove the need for participant-specific semantics.

[CyRIS](https://www.jaist.ac.jp/~razvan/publications/cyris_facilitating_training.pdf)
is important because it automatically and repeatably creates cyber ranges from
YAML descriptions with topology, content, and security-incident features.
It strengthens the lineage for reproducible range construction, while also
showing the boundary of construction systems: repeatable deployment is not the
same as portable participant behavior, observation, causality, or outcome
semantics.

Ear, Remy, and Xu's automated cyber-range design framework
([arXiv:2307.04416](https://arxiv.org/abs/2307.04416)) treats range
architecture selection as an explicit requirements-matching problem. For RAES,
the lesson is that architecture, teaming model, fidelity, observability,
concurrency, resetability, and updateability are experiment requirements that
must be surfaced instead of disappearing into backend choice.

### Adversary Emulation And Security Events

The CALDERA planning-and-acting work argues that automated adversary emulation
is not only planning: adversaries interleave acting and sensing under open-ended
uncertainty. This motivates RAES's explicit distinction between actions that
change foothold, actions that change knowledge, and actions that do both.

[MITRE ATT&CK](https://www.mitre.org/news-insights/publication/mitre-attck-design-and-philosophy)
is an empirically grounded behavior vocabulary. It can classify participant
actions, but ATT&CK technique labels are not RAES action contracts.

[OCSF](https://ocsf.io/) provides vendor-neutral security event structure and
normalization. It is appropriate for observations, detections, findings, and
evidence references, but it is not a participant-visible-state model by itself.

[CACAO v2.0](https://docs.oasis-open.org/cacao/security-playbooks/v2.0/security-playbooks-v2.0.pdf)
separates workflows, commands, agents, targets, variables, and authentication
information. It is useful lineage for agent/target and action-step boundaries,
but RAES participant semantics must also handle observation, discovery,
concealment, and evaluation across heterogeneous participant implementations.

### Time, Ordering, And Causality

Lamport's happened-before relation establishes the key warning: distributed
systems have partial ordering, and physical timestamps alone are not the same as
causal ordering.

Lamport's scalar clocks only respect causality in one direction; they cannot
prove that two events are causally unrelated. Fidge (1988) and Mattern (1989)
introduced vector time, which characterizes the causal partial order exactly,
and Schwarz and Mattern (1994) survey what causal claims each clock mechanism
can and cannot support. This distinction is load-bearing for RAES: any
`VectorClock` ordering basis in the runtime layer claims the stronger
characterization and therefore needs the Fidge/Mattern lineage, not just
Lamport's.

Winskel's event structures and Mazurkiewicz's trace theory provide the
true-concurrency semantics behind RAES's realized-order model: a record of
"what happened" in a concurrent run is a labelled partial order with explicit
simultaneity/independence structure, not a single forced interleaving. This is
why RAES joint-action records carry partial orders and simultaneity groups
instead of a backend-chosen total order presented as ground truth.

Formal temporal contracts also have direct precedent: Allen's interval algebra
(1983) for window and interval relations, Koymans' metric temporal logic (1990)
for deadline/latency bounds, and Alur and Dill's timed automata (1994) for
machine-checkable real-time behavior. SEM-213's schedule, cadence, deadline,
dwell, and time-window contracts are bounded fragments of these formalisms with
declared time domains and clock authorities.

HLA time-management literature, Time Warp, DEVS, SimPy scheduling, ROS 2 clock
design, ns-3 realtime mode, and FMI all reinforce that clock authority, time
domain, advancement, pacing, synchronization, and event ordering are separate
semantic concerns.

[SISO Cyber DEM](https://cdn.ymaws.com/www.sisostandards.org/resource/resmgr/standards_products/siso-std-025-2023_cyberdem.pdf)
provides cyber objects and events for simulation interoperability. It supports
the idea that cyber events and effects need exchangeable representations across
simulation and range systems, but RAES still needs its own scenario/participant
semantics around those events.

Halpern and Pearl's structural-model causality motivates the attribution rule
in this spec: an observed alert after an action is not automatically caused by
that action. Causal claims require an evidence basis and, for strong claims, a
counterfactual or intervention model. Chockler and Halpern's structural-model
treatment of responsibility and blame (2004) extends this to the
multi-participant case SEM-212 must handle: when several actions jointly
produce an effect, attribution edges need graded responsibility semantics, not
a single binary cause label.

### DSL Evaluation And Language Critique

The software-language engineering evaluation literature warns that domain
familiarity is not enough to validate a DSL. Gabriel, Goulão, and Amaral's
[DSL evaluation review](https://arxiv.org/abs/1109.6794) specifically calls out
expressiveness, usability, effectiveness, maintainability, and domain-expert
productivity as concerns that can be skipped or relaxed. RAES's participant
semantics are therefore not academically complete if they only define a rich
semantic model; future child issues must also include authoring profiles,
examples, negative fixtures, and evidence that the notation can be used without
creating ambiguous or unreviewable experiments.

## Critical Re-Examination Against Known Failure Modes

The design above is necessary but not by itself sufficient. A critical reading
of existing SDLs, cyber-agent environments, and agent benchmarks identifies the
following failure modes that RAES must explicitly avoid.

| Failure mode | Direct evidence | Design correction |
| ------------ | --------------- | ----------------- |
| Prose-only or schema-only semantics | VSDL translates scenarios to SMT constraints; CRACK verifies SDL properties and tests deployed behavior against specification | Child implementations must publish executable contracts or abstract-state models plus negative fixtures; ADR prose and JSON-schema validation are not conformance |
| Deployment topology mistaken for experiment semantics | CyRIS, VSDL, CRACK, and automated range-design work focus on repeatable construction and feasibility | Participant semantics remain separate from deployment topology; backend realization, observation, causality, and outcomes require their own contracts |
| Technique labels treated as behavior | ATT&CK is a behavior vocabulary; CyGIL shows abstract cyber actions can fail to transfer to realistic networks | Action contracts carry behavioral granularity, procedure basis, realization profile, fidelity claims, and mapping-loss labels |
| Simulation and emulation observations conflated | CybORG reports agents overfitting to simulation-observation artifacts that were absent in emulation | Observation contracts record capture source, visibility basis, latency, capture granularity, loss/redaction, and realization profile |
| Flag success treated as full outcome meaning | Cybench uses tasks/subtasks/evaluators; AutoPenBench adds gold steps and milestones; CAIBench adds integrated A&D and privacy tasks | Outcome interpretation separates local action status, progress milestones, objectives, evaluations, rewards, evidence claims, privacy handling, and participant assistance |
| Benchmark contamination and hidden answer leakage | Cybench uses starter files, task servers, flags, and answer keys; broader agent-evaluation critiques identify weak holdouts and overfitting | Hidden truth, answer keys, canaries, holdout variants, public/private task material, and scaffold guidance are view-boundary objects with run/study provenance |
| Apparatus effects hidden from results | Cyber range architecture work treats monitoring, teaming, fidelity, concurrency, reset, and architecture as requirements | Evidence and observations disclose capture plane, observer effect, reset strategy, backend version, participant implementation, and unsupported guarantees |
| Language richness mistaken for language adequacy | DSL evaluation literature warns that expressiveness/usability/effectiveness/maintainability are often not evaluated | Future verification includes authoring-profile examples, ambiguity tests, round-trip tests, and domain-review evidence |

## Cross-Issue Coverage And Deferrals

The participant-semantics design intentionally remains partial for holistic
concerns that belong to other RAES design or evidence gates.

| Concern from the critique | Coverage after #71 | Owning issue(s) | Participant-semantics duty |
| ------------------------- | ------------------ | --------------- | -------------------------- |
| Scenario/run/study provenance | Partial | #87, #89, #105, #106 | Emit and consume named participant, action-contract, scaffold, backend, reset, and content-version provenance fields |
| Observability and evidence apparatus | Partial | #88, #127, #128, #170, #273 | Define participant observation/evidence semantics and disclose capture basis; defer full observability-plane design |
| Hidden truth, canaries, holdouts, answer keys, and adjudication assets | Partial | #125, #328, #333, #166 | Model participant visibility and leakage boundaries; defer benchmark asset lifecycle and corpus assurance |
| Trajectory, demonstration, replay, and dataset semantics | Partial | #124 and spawned trajectory issues | Preserve participant histories and local outcomes in a replay-compatible form |
| Backend realization and fidelity disclosure | Partial | #100, #165, #177, #239, #335 | Require action/observation realization profiles and mapping-loss labels |
| Machine-checkable semantic validation | Needs cross-gate evidence | #162, #168 | Provide participant-specific invariants and negative fixtures; do not treat ADR prose as conformance |
| DSL language adequacy | Needs dedicated evidence | #346 | Provide ambiguity, usability, maintainability, reviewability, and authoring-profile evidence for concrete syntax |

## Semantic Core

Let:

- `P` be the set of participants.
- `E_p` be the ordered set of episodes for participant `p`.
- `W_t` be the world state at logical instant `t`.
- `V_p,t` be participant `p`'s visible projection at logical instant `t`.
- `H_p,t` be participant `p`'s local history up to `t`.
- `A_p` be participant `p`'s available action contracts.
- `O_p,t` be observations delivered to participant `p` at `t`.
- `J_t` be the joint action set submitted or realized over an ordering
  interval containing `t`.
- `R_t` be the realized ordering relation for events in that interval.
- `X_t` be the archival evidence/provenance state at `t`.

World truth, participant-visible state, participant history, and evidence are
different objects. No implementation may substitute one for another without an
explicit semantics-preserving mapping.

### Participant Observation

An observation is a typed projection:

```text
Observation =
  participant_address
  episode_id
  observation_id
  observed_at
  source
  capture_basis
  capture_granularity
  capture_loss_model
  redaction_policy
  observer_effect
  visibility_basis
  subject_ref
  payload
  certainty
  latency
  disclosure_class
  evidence_refs
```

Observation invariants:

- `payload` is what the participant can receive, not necessarily what is true.
- `source` identifies the apparatus or scenario surface that produced the
  observation.
- `capture_basis` identifies the capture point or producer: participant
  surface, tool output, host telemetry, network sensor, backend adapter,
  evaluator, human input, synthetic disclosure, or replay.
- `capture_granularity`, `capture_loss_model`, `redaction_policy`, and
  `observer_effect` disclose whether the observation is complete, sampled,
  normalized, redacted, delayed, synthesized, or affected by the act of
  instrumentation.
- `visibility_basis` explains why the participant can see it: starting
  knowledge, operating scope, tool output, disclosure, inference,
  side-channel, deception, or backend-adapter disclosure.
- `latency` is part of observation meaning and may differ from event time.
- `evidence_refs` connect observations to archival evidence without disclosing
  hidden truth to the participant.

### Participant Action Contract

An action contract is a typed semantic object:

```text
ActionContract =
  action_id
  semantic_version
  action_kind
  behavior_granularity
  procedure_basis
  actor_scope
  target_scope
  parameter_schema
  preconditions
  effects
  side_effects
  failure_classes
  temporal_contract
  visibility_effects
  evidence_expectations
  fidelity_claims
  realization_profile
  backend_realization_requirements
```

Action execution is a transition attempt:

```text
Attempt(p, e, a, args, t_submit)
  -> Realization(accepted | rejected, t_start?, t_end?, ordering_token?)
  -> Outcome(local_status, failure_class?, effects_observed, observations, evidence)
```

The action name in the current SDL is not enough to define this contract. A
future implementation must either resolve action names to governed action
contracts or fail closed when a participant action is referenced by semantics
that require a contract.

`behavior_granularity` distinguishes intent, tactic, technique, procedure,
tool invocation, command, and realized system effect. `procedure_basis` names
the evidence for the procedure, such as an ATT&CK technique, CVE, exploit
module, CACAO command, OpenC2 command, human runbook step, emulated trace, or
experiment-specific procedure. External classifications use standalone
[concept binding documents](../../concept-authority/external-concept-bindings.md)
with explicit provenance and approximation/loss, not action-contract fields.
A mapping to ATT&CK, OCSF, CACAO, STIX, OpenC2, Cyber DEM, Metasploit, or a
benchmark milestone is not itself the RAES action semantics.
`fidelity_claims` and `realization_profile` distinguish portable intent from
simulation, emulation, live, human-mediated, or stubbed realization.

### State Transition

A participant action may produce any combination of:

- world-state mutation
- participant-local state mutation
- observation production
- evidence production
- disclosure or concealment change
- objective/workflow/evaluation refresh input
- no-op
- failed attempt
- unsafe withheld attempt

An action transition must not be treated as deterministic unless its contract
states so and the backend declares a realization profile that supports that
guarantee.

### Joint Action And Interaction

For an ordering interval `I`, a joint action set is:

```text
J_I = {Attempt(p_i, e_i, a_i, args_i, t_i)}
```

The processor/backend must assign or preserve a realized ordering relation
`R_I` that supports at least:

- happens-before edges required by participant episodes, workflows, and
  backend event delivery
- conflict/interference annotations
- simultaneity or concurrency claims only when supported by the backend
- explicit weakening when the backend serializes or drops concurrent attempts

Interaction classes:

- `coordination`: an action contract requires or synchronizes with another
  participant's action or state.
- `contention`: actions compete for an exclusive semantic resource.
- `interference`: one action changes another action's preconditions,
  observations, effects, or outcome.
- `shared_state_change`: multiple actions read or write the same object,
  contract surface, or evidence stream.

## Invariants

### I1 - Role-Neutral Participant Semantics

The semantic model applies to human participants, AI agents, scripts, playbooks,
simulated actors, and human-control proxies. Participant implementation type is
apparatus metadata, not a different semantic universe.

### I2 - Hidden Truth Boundary

World state and hidden benchmark assets must not be exposed as participant
observations unless an explicit disclosure rule permits it. Runtime evidence may
record hidden truth for adjudication without making it participant-visible.

### I3 - Observation Projection

An observation is never assumed to be complete truth. It has a source,
capture basis, visibility basis, latency, certainty, loss/redaction disclosure,
and evidence relationship.

### I4 - Fail-Closed Action Applicability

If an action's preconditions cannot be resolved or are not satisfied, the action
must be rejected, withheld, or marked unknown according to a declared failure
class. It must not silently execute under backend-local convention.

### I5 - Explicit Side Effects

Any participant action that may alter detection surface, telemetry, visibility,
shared state, or downstream objective/evaluation interpretation must declare
that class of side effect.

### I6 - Explicit Interaction Semantics

Coordination, contention, interference, and shared-state change must be visible
in the semantic model or provenance. Backend scheduler order must not be the
only record of interaction.

### I7 - Temporal Domain Separation

Episode step, scenario time, simulation time, backend time, and wall-clock time
are distinct. A deadline, dwell, cadence, timeout, or latency claim must name
the time domain and clock authority it uses.

### I8 - Ordering Before Causality

Causal attribution requires at least an ordering basis. A timestamp alone is not
enough; a happened-before, workflow, episode, or backend event-order relation
must be available.

### I9 - Evidence-Labeled Attribution

Attribution edges must declare their evidence strength: declared association,
temporal support, contract support, observation support, or counterfactual/
intervention support.

### I10 - Outcome-Layer Separation

Participant-local action status, episode terminal reason, objective success,
workflow state, evaluation result, and reward must remain separate until an
explicit interpretation rule relates them.

### I11 - Realization Disclosure

If a backend cannot realize a declared participant semantic guarantee, it must
fail capability validation or disclose the weaker realization before results are
used for comparison.

### I12 - Fidelity Claim Separation

A scenario may claim semantic portability without claiming fidelity
equivalence. Backends must disclose which behavior, observation, timing,
failure, and evidence guarantees are preserved, weakened, simulated, or
unavailable.

### I13 - Observation Apparatus Disclosure

Evidence and observations must disclose their capture basis, capture
granularity, loss model, redaction policy, and known observer effects.
Participant-visible observations must not be inferred from archival evidence
unless an explicit view rule permits that disclosure.

### I14 - External Mapping Loss Labels

Mappings to ATT&CK, OCSF, CACAO, STIX, OpenC2, Cyber DEM, CVE, Metasploit,
benchmark milestone, or other external vocabularies must declare whether the
mapping is exact, narrower, broader, approximate, lossy, or advisory.

### I15 - Run And Study Provenance

Claims spanning repeated runs, benchmark comparisons, ablations, or studies
require run-level provenance: scenario version, action-contract versions,
participant implementation version, backend version, reset strategy, random
seeds where applicable, scaffold/instruction disclosure, and relevant
environment fingerprints.

### I16 - Content And Contract Lifecycle

Participant action contracts, observation contracts, hidden assets, CTI-backed
labels, benchmark tasks, and external mappings are versioned content. They must
carry source, semantic version, freshness or validity basis, and deprecation or
replacement state when used for academic comparisons.

### I17 - Benchmark Leakage And Holdout Discipline

Hidden truth, answer keys, canaries, private references, task variants,
subtask guidance, public starter files, and adjudication material are
information-boundary objects. Their exposure or non-exposure must be recorded
as part of the participant view and run/study provenance.

### I18 - Language Evaluation Obligation

The participant-semantics language is not adequate merely because it is
expressive. Future concrete syntax and authoring profiles must be evaluated for
ambiguity, maintainability, domain-expert reviewability, and consistency across
examples, negative fixtures, and compiled contracts. Issue #346 tracks this as
a dedicated DSL language-evaluation evidence gate; this document only records
the participant-semantics obligation.

## Executable Invariant Oracle

`implementations/python/tests/test_participant_semantics_invariant_oracle.py`
is the executable oracle for the abstract model above. The oracle defines a
test-local `ParticipantProgression` model for episode, action, observation,
attribution, outcome, realization, provenance, lifecycle, mapping-loss, and
language-evaluation surfaces. Its `INVARIANTS` catalog maps each spec invariant
to a stable heading in this document and to the predicate that executes it.

The mapping is checked in both directions:

- the test suite extracts this README's `### I*` headings and requires them to
  match the oracle catalog exactly;
- every catalog entry stores the corresponding spec heading and requirement
  slice references;
- Hypothesis-generated valid progressions must satisfy every cataloged
  invariant;
- each invariant has a targeted mutation factory that produces at least one
  rejected counterexample.

| Spec invariant | Oracle predicate |
| --- | --- |
| `I1` | `_i1_role_neutral` |
| `I2` | `_i2_hidden_truth_boundary` |
| `I3` | `_i3_observation_projection` |
| `I4` | `_i4_fail_closed_action_applicability` |
| `I5` | `_i5_explicit_side_effects` |
| `I6` | `_i6_explicit_interaction_semantics` |
| `I7` | `_i7_temporal_domain_separation` |
| `I8` | `_i8_ordering_before_causality` |
| `I9` | `_i9_evidence_labeled_attribution` |
| `I10` | `_i10_outcome_layer_separation` |
| `I11` | `_i11_realization_disclosure` |
| `I12` | `_i12_fidelity_claim_separation` |
| `I13` | `_i13_observation_apparatus_disclosure` |
| `I14` | `_i14_external_mapping_loss_labels` |
| `I15` | `_i15_run_and_study_provenance` |
| `I16` | `_i16_content_and_contract_lifecycle` |
| `I17` | `_i17_benchmark_leakage_and_holdout_discipline` |
| `I18` | `_i18_language_evaluation_obligation` |

## SEM-208 - Participant Behavior Semantics

`SEM-208` requires explicit semantics for participant actions, observations,
state transitions, and role-neutral behavior interpretation.

Design commitments:

- behavior is modeled as episode-indexed action attempts and observation
  histories;
- actions resolve to action contracts, not untyped names;
- action contracts declare semantic version, behavioral granularity, procedure
  basis, realization profile, fidelity claim, and external mapping losses;
- observations are participant-specific projections of world/evidence state;
- state transitions can affect world state, participant-local state,
  observations, visibility, evidence, and outcome surfaces;
- behavior interpretation is role-neutral across participant implementation
  types.

Minimum future implementation artifacts:

- typed action/observation semantic helpers;
- participant behavior contract schemas;
- governed action-contract registry or equivalent source-of-truth mechanism
  with versioning, lifecycle state, and external mapping loss labels;
- validator checks for action contract references and observation-boundary
  declarations;
- compiler/runtime mapping from authored participants to participant contract
  addresses;
- cross-stage tests from SDL action declarations to compiled runtime contracts
  and observed participant history.

Current implementation artifacts for the `SEM-208` slice:

- `implementations/python/packages/raes/participant_behavior/__init__.py` defines
  typed action contracts and observation boundaries;
- `implementations/python/packages/raes/semantics/participant_behavior.py`
  and `implementations/python/packages/raes/validator/` fail closed on
  unbound action-contract and observation-boundary references;
- `implementations/python/packages/raes_processor/compiler/` maps authored
  participants to compiled participant action, observation, and behavior
  addresses;
- `implementations/python/packages/raes_processor/models/` defines
  participant behavior-history events and validates action/observation/state
  transition totality over compiled addresses;
- `implementations/python/tests/test_sem_208_participant_behavior.py` covers
  the cross-stage SDL-to-runtime behavior-history path.

## SEM-209 - Multi-Participant Interaction Semantics

`SEM-209` requires semantics for coordination, contention, interference, and
shared-state change among concurrent participants.

Design commitments:

- multi-participant execution is modeled over joint action sets, not isolated
  single-agent steps;
- coordination, contention, interference, and shared-state changes are explicit
  interaction classes;
- realized ordering must be preserved or disclosed;
- backend simultaneity, serialization, lock, conflict, and dropped-action
  behavior are semantic guarantees, not adapter details;
- participant-local histories can differ even when they refer to one shared
  event.

Minimum future implementation artifacts:

- joint-action/interference formal invariants;
- runtime provenance fields for realized order and conflict semantics;
- property or differential tests for serializable vs non-serializable backend
  behavior;
- explicit simultaneity and conflict-resolution claims for backends that do
  not serialize joint action attempts.

Current implementation artifacts for the `SEM-209` slice:

- `implementations/python/packages/raes/participant_behavior/__init__.py` defines
  interaction classes, target references, related actions, and shared-state
  references on action contracts;
- `implementations/python/packages/raes/semantics/participant_behavior.py`
  and `implementations/python/packages/raes/validator/` fail closed on
  unbound related actions, interaction targets, and shared-state references;
- `implementations/python/packages/raes_processor/compiler/` carries declared
  interaction classes and shared-state references into compiled participant
  action contracts;
- `implementations/python/packages/raes_processor/models/` records
  `joint_action_set_id`, `realized_order`, interaction class, interaction
  reference, and shared-state references in participant behavior history, and
  rejects duplicate realized orders within one joint action set;
- `implementations/python/packages/raes_conformance/conformance.py` applies the
  joint-action ordering invariant across participant-local histories in runtime
  snapshots.

This implementation follows the lineage above without adopting a framework
API: PettingZoo and OpenSpiel motivate preserving participant-local histories
and joint behavior as first-class data, while Lamport ordering motivates
recording realized order as provenance rather than treating timestamp adjacency
as causality. Cyber-agent systems motivate explicit action targets and
shared-state effects, but technique/tool labels remain external mappings, not
the RAES interaction semantics themselves.

## SEM-210 - Visibility And Information-Boundary Semantics

`SEM-210` requires semantics for what participants can observe, infer, conceal,
discover, or disclose over time.

Design commitments:

- visibility is an explicit view relation `V_p,t`, not a side effect of topology
  alone;
- initial knowledge, starting accounts, operating scope, authority anchors,
  tool outputs, telemetry streams, instructions, and hidden truth assets are
  distinct visibility inputs;
- public task statements, starter files, scaffold instructions, subtask
  guidance, private answer keys, canaries, and holdout variants are distinct
  information-boundary objects;
- discovery and disclosure are state transitions that alter future visibility;
- concealment and deception are permitted only when modeled explicitly;
- participant-visible artifacts and adjudication/evidence artifacts are
  separated.

Implemented transition discipline:

- `view_rules` define the initial view relation `V_p,0`; a transition
  `from_disposition` must match that current relation and cannot redefine the
  initial state;
- every `view_transition` carries an explicit integer `effective_order`, an
  `effective_from` label, a behavior-history anchor
  (`history_event_type`, plus `action_instance_id` except for `episode_close`),
  non-empty `evidence_refs`, `certainty`, and `latency_profile`;
- compiled participant observation boundaries sort transitions by
  `effective_order` and publish `view_relation_timeline` snapshots; dynamic
  discovery, inference, disclosure, concealment, and deception are read from
  those snapshots rather than from lifetime aggregate fields;
- runtime participant observation details that declare visible, disclosed, or
  evidence refs are checked against the compiled `V_p,t` snapshot derived from
  behavior-history anchors at or before the observation event, so future
  disclosure cannot justify earlier visibility;
- conformance diagnostics reject transition anchors that do not resolve to the
  corresponding participant behavior-history event; `episode_close` transitions
  resolve against terminal participant-episode history and do not authorize
  in-episode observation payloads.

Current implementation artifacts for the `SEM-210` slice:

- `implementations/python/packages/raes/participant_behavior/__init__.py` defines
  participant information-boundary classes, view dispositions, explicit view
  rules, time-indexed view transitions, realized-view disclosure metadata, and
  observation-boundary hidden, observable, and evidence-only reference
  separation;
- `implementations/python/packages/raes/semantics/participant_behavior.py`
  and `implementations/python/packages/raes/validator/` continue to
  fail closed on unbound participant observation-boundary references, view-rule
  references, and view-transition evidence references;
- `implementations/python/packages/raes_processor/compiler/` carries hidden,
  observable, discovered, inferred, concealed, disclosed, deceptive,
  evidence-only, and realized-view disclosure metadata into compiled
  participant observation boundaries, including an ordered
  `view_relation_timeline` snapshot series for `V_p,t`;
- `implementations/python/packages/raes_processor/models/` exposes the
  compiled visibility metadata for runtime planning, snapshots, and
  conformance consumers, and validates observation detail refs against the
  corresponding timeline snapshot;
- `implementations/python/tests/test_sem_208_participant_behavior.py` covers
  leakage fixtures proving hidden truth cannot enter participant observations
  without an explicit disclosure rule, cannot be used as evidence without an
  evidence-only rule, cannot be inferred or disclosed through static metadata,
  and cannot be justified by a transition whose temporal order or runtime
  anchor is invalid.

This implementation slice enforces the reference-level visibility relation for
observation detail refs. The complete observation payload apparatus (`payload`,
capture basis, loss, redaction, latency, observer effects, and evidence-capture
adequacy) remains owned by the downstream observation/evidence requirements
listed in ADR-022 rather than being silently claimed by `SEM-210`.

## SEM-211 - Preconditions, Effects, And Failure Semantics

`SEM-211` requires semantics for action applicability, effects, side effects,
and failure classes.

Precondition classes:

- `authority`: participant may attempt this action under scenario meaning;
- `capability`: participant has a tool, role, implementation, or apparatus
  binding capable of this action;
- `target`: target exists and is in action scope;
- `knowledge`: participant has enough information to form the attempt;
- `resource`: budget, quota, credential, session, account, or tool state is
  available;
- `temporal`: schedule, cadence, dwell, deadline, or cooldown condition holds;
- `interaction`: required lock, coordination partner, or shared-state guard
  holds;
- `realization`: backend and participant implementation can realize the action.

Effect classes:

- `intended_effect`;
- `side_effect`;
- `observation_effect`;
- `visibility_effect`;
- `detection_effect`;
- `evidence_effect`;
- `no_effect`;
- `unknown_effect`.

Failure classes:

- `precondition_unsatisfied`;
- `unsupported_action`;
- `target_unavailable`;
- `authority_denied`;
- `resource_exhausted`;
- `timeout`;
- `interrupted`;
- `contention_lost`;
- `partial_success`;
- `unsafe_withheld`;
- `backend_error`;
- `unknown`.

Current implementation artifacts for the `SEM-211` slice:

- `implementations/python/packages/raes/participant_action_semantics.py`
  defines controlled precondition, effect, and portable failure vocabularies
  plus typed action-contract declarations and backend failure mappings;
- `implementations/python/packages/raes/participant_behavior/__init__.py` embeds
  those typed declarations in governed participant action contracts;
- `implementations/python/packages/raes_processor/compiler/` carries the
  typed precondition classes, effect classes, failure classes, and backend
  failure mappings into compiled participant action contracts;
- `implementations/python/packages/raes_processor/models/` defines typed
  action precondition results, action effect results, action results,
  fail-closed validation for unsatisfied or unresolved preconditions, behavior
  history action-result embedding, compiled-contract validation for declared
  effects and failure classes, and backend diagnostic mapping to portable
  failure classes;
- `implementations/python/packages/raes_contracts/contracts/` publishes the
  action-result payload shape in the participant behavior-history and runtime
  snapshot schemas;
- `implementations/python/tests/test_sem_211_participant_action_semantics.py`
  covers positive contract compilation, controlled vocabulary rejection,
  fail-closed unresolved preconditions, portable failure round-tripping,
  participant-scope mismatch rejection, undeclared effect/failure-class
  counterexamples, required terminal action results, and backend diagnostic
  mapping.

## SEM-212 - Causality And Attribution Semantics

`SEM-212` requires semantics linking participant actions to observed state
changes, detections, alerts, and downstream outcomes.

Design commitments:

- attribution is an evidence-labeled edge, not an implicit consequence of time
  adjacency;
- every attribution edge names cause candidate, effect candidate, ordering
  basis, evidence basis, and confidence/strength;
- evidence basis includes the capture apparatus, granularity, loss model,
  redaction policy, and observer-effect disclosure for the evidence stream;
- strong causal claims require counterfactual, intervention, replay, ablation,
  or structural-causal evidence;
- weaker claims are allowed but must remain labeled as association, temporal,
  contract, or observation support;
- downstream objective/evaluation interpretation can consume attribution edges
  only according to explicit interpretation rules.

Current implementation artifacts for the first `SEM-212` slice:

- `implementations/python/packages/raes/participant_attribution_semantics.py`
  defines controlled candidate, ordering-basis, and support-class
  vocabularies;
- `implementations/python/packages/raes_processor/models/` defines typed
  attribution candidates, ordering bases, evidence bases, and attribution
  edges on participant behavior-history observation events;
- `implementations/python/packages/raes_processor/models/` validates
  participant/episode/observation scope, explicit ordering and evidence
  bases, outcome interpretation-rule refs, timestamp-adjacency limits for
  strong causal support, effect grounding in actual observations/action
  results, and participant-boundary authorization for attribution evidence;
- `implementations/python/packages/raes_contracts/contracts/` publishes the
  attribution-edge payload under participant behavior-history event contracts;
- `implementations/python/tests/test_sem_212_participant_attribution_semantics.py`
  covers positive attribution, missing bases, timestamp-only strong-causality
  rejection, cross-participant scope rejection, hidden evidence rejection,
  ungrounded effect candidates, downstream outcome interpretation rules, and
  schema publication.

## SEM-213 - Temporal Participant Semantics

`SEM-213` requires semantics for schedules, cadence, deadlines, dwell, latency,
and time-windowed participant behavior.

Design commitments:

- temporal claims name their time domain and clock authority;
- repeated-run and study-level temporal claims name reset strategy, replay
  boundary, randomization/seed basis, and backend pacing or synchronization
  guarantees;
- schedules define action eligibility windows;
- cadence defines repeated action/observation constraints;
- deadlines define latest acceptable realization or outcome times;
- dwell defines a minimum sustained condition over a named window;
- latency defines delay between cause/event/observation/action realization
  points;
- ordering and causality are separate from raw timestamp comparison;
- backend pacing/dilation/synchronization limitations must be disclosed.

Minimum future implementation artifacts:

- temporal participant contract fields aligned with the broader RAES time-model
  work;
- abstract state-machine model for deadlines, dwell, and timeout interaction;
- tests for ordering, delayed observation, and deadline/cadence edge cases.

Current implementation artifacts for the first `SEM-213` slice:

- `implementations/python/packages/raes/participant_temporal_semantics.py`
  defines typed time domains, temporal event points, schedule/cadence/deadline/
  dwell/latency/time-window contract kinds, backend timing disclosure kinds,
  support modes, and abstract temporal states;
- `implementations/python/packages/raes/participant_behavior/__init__.py` embeds
  temporal contracts and backend timing disclosures in governed participant
  action contracts, requires temporal preconditions to resolve to typed
  temporal contracts, and fails closed on unknown backend disclosure refs;
- `implementations/python/packages/raes_processor/compiler/` carries temporal
  contract ids, kinds, time domains, clock authorities, and backend timing
  disclosures into compiled participant action contracts;
- `implementations/python/packages/raes_processor/models/` defines runtime
  temporal context on participant behavior-history events, validates it
  against the compiled action contract, and exposes an abstract state-machine
  checker for cadence, deadline, dwell, timeout, reset, and replay interactions;
- `implementations/python/packages/raes_contracts/contracts/` publishes the
  runtime temporal-context payload in participant behavior-history and runtime
  snapshot schemas;
- `implementations/python/tests/test_sem_213_temporal_participant_semantics.py`
  covers positive SDL-to-runtime compilation, missing clock authority, unknown
  backend disclosure refs, invalid temporal contract shapes, runtime contract
  mismatches, bounded timing disclosures, and invalid cadence / deadline / dwell
  / timeout state-machine transitions.

This slice implements participant-local temporal contracts and conformance
checks. It does not claim the broader RAES clock/time-model work owned by
`SEM-227`, `SEM-228`, and `SEM-229`.

## SEM-214 - Portable Semantics For Derived Context Views

`SEM-214` requires explicit meaning and comparability semantics for derived
operational context views so their interpretation remains portable across
runtimes and backends.

Design commitments:

- a context view is participant-local and must name its audience scope;
- every view names the observation point at which the derived context applies;
- source layers are explicit and limited to governed snapshot, participant
  observation, participant history/status, evidence, derived-measure, and
  control-plane operation records;
- hidden/global runtime state is not a valid context-view source layer;
- future-state sources are not valid, and bounded stale sources require a
  freshness-basis reference;
- the transformation rule and input source ids are explicit;
- evidence and provenance references are required;
- comparability is an explicit claim with a comparison-basis reference,
  limitations, and backend disclosures whenever the claim is weakened or
  backend-specific.

Implementation artifacts:

- `participant-context-view-v1` carries the SEM-214 envelope in the existing
  API-408 control-plane carrier;
- `implementations/python/packages/raes_contracts/contracts/` defines the
  closed-world Pydantic model and JSON Schema reference output;
- `contracts/fixtures/control-plane/participant-context-view-v1/` contains
  positive and negative fixtures for source-layer, temporal, audience-scope,
  evidence/provenance, and comparability constraints;
- `implementations/python/packages/raes_runtime/participant_retrieval.py`
  constructs the SEM-214 envelope for the existing context retrieval path;
- `implementations/python/tests/test_participant_backend_contracts.py`,
  `test_runtime_control_plane.py`, and `test_runtime_control_plane_api.py`
  verify schema/model rejection, runtime construction, and HTTP response
  binding.

## SEM-215 - Participant Outcome Interpretation Semantics

`SEM-215` requires semantics for interpreting participant-local outcomes and
relating them to scenario, objective, workflow, and evaluation meaning.

Design commitments:

- participant-local action outcome, episode status, objective success, workflow
  result, evaluation result, evidence claim, and reward are distinct;
- mappings between those layers are explicit interpretation rules;
- a local action success does not imply objective success;
- a local action failure may still create evidence, detection, alert, or
  reward-relevant behavior;
- reward is a derived training/evaluation signal unless declared otherwise by a
  governed assessment rule;
- participant outcomes must preserve enough provenance for replay and academic
  critique;
- runtime interpretation records must ground participant-action outcome sources
  in the event `action_result`, evidence sources and evidence refs in evidence
  emitted by the event, and participant-episode status sources in terminal
  `participant_episode_history` records for the same participant and episode;
- progress milestones, subtasks, gold steps, human assistance, scaffold
  variants, cost/resource telemetry, and privacy/redaction results are outcome
  inputs only when declared by an interpretation rule; none substitutes for the
  full outcome model.

Implementation artifacts:

- outcome interpretation helper/contract;
- integration with objective and assessment semantics;
- tests for local-success/objective-failure and local-failure/evidence-success
  cases;
- evidence records that preserve participant-local outcome basis;
- runtime conformance checks that reject ungrounded action outcome, evidence
  claim, and episode-status interpretation sources.

## SEM-216 - Boundary Semantics For State, Evidence, Evaluation, Analysis, And Views

`SEM-216` requires explicit semantics distinguishing runtime-observable state,
captured evidence, derived evaluations, analysis outputs, and audience-specific
views so one stratum is never silently substituted for another.

`SEM-216` is a **boundary-semantics requirement over the existing contract
families**, not a new universal taxonomy. Per the architecture preflight
(`docs/decisions/issue-248-sem-216-boundary-semantics-preflight.md`) there is no
"state/evidence/result/view" super-schema: each stratum keeps its own governed
carrier, and cross-boundary movement is by typed references, source layers,
traceability blocks, checksums, and provenance refs only.

The five strata and their governing carriers:

- **runtime-observable state** is live, mutable control-plane/runtime material:
  `RuntimeSnapshot`, snapshot entries, workflow/evaluation results and history,
  participant episode/behavior/shared-state/joint-action records, operation
  status, and audit metadata. It is not archival run provenance by itself.
- **captured evidence** is the EXP-708 `experiment-evidence-record-v1` surface:
  typed source refs, content URI plus checksum or bounded summary, sensitivity,
  redaction state, loss disclosure, and provenance. A capture spec declares
  intent; it is not proof that evidence exists.
- **derived evaluations** are compiled evaluation result/history contracts and
  the EXP-709 `experiment-derived-measure-v1` archival measure; a raw evidence
  record is never a metric value, score, or measure.
- **analysis outputs** are study/report artifacts or derived measures with
  `measure_kind: analysis-output`, kept grounded through run traceability and at
  least one derived-measure reference; they must not float from raw runtime
  state or evaluator detail.
- **audience-specific views** are projections over recorded carriers
  (`participant-status-view-v1`, `participant-history-view-v1`,
  `participant-context-view-v1`), never sources of truth.

Design commitments:

- the five strata are distinct objects carried by named existing contracts; no
  contract may carry another stratum's shape (closed-world models reject it);
- archival evidence and derived evaluation/adjudication outputs reach a
  participant-visible view only through a governed view rule and a redaction
  policy, only when the archival source is mediated by the view transformation
  rather than passed through raw, and only when the disclosed `payload_ref` is
  the transformed view output rather than an alias of the raw archival ref;
- evidence claims disclose redaction and loss at the evidence boundary;
- backend-native observability is not an admissible portable view source and is
  not a portable semantic observation;
- analysis outputs remain grounded in run traceability and derived measures.

Boundary obligations (each is exercised by an adversarial negative fixture):

- **B1** - archived evidence must not become participant-visible without a view
  rule. A `participant_visible` `participant-context-view-v1` that draws on an
  `evidence_record` source layer must declare a `derivation_basis_ref` view rule
  and a `redaction_policy_ref` (published `allOf`), the evidence source must
  appear in `transformation.input_source_ids`, and `payload_ref` must not alias
  the raw evidence ref (both relational rules published as `x-raes-invariants`).
- **B2** - hidden adjudication / derived-evaluation outputs must not reach a
  participant view without redaction governance. A `participant_visible` view
  that draws on a `derived_measure` source layer must additionally declare a
  `redaction_policy_ref`, mediate the source through the transformation, and
  expose a transformed `payload_ref` rather than the raw measure ref.

The required-ref clauses of B1/B2 (and B4) are enforced both by the closed-world
model and by the published JSON Schema `allOf`, so schema-only consumers reject
them. The relational clauses that standard JSON Schema cannot express - archival
source mediation and `payload_ref` non-aliasing - are enforced by the model and
published as `x-raes-invariants` on `participant-context-view-v1` (the RAES
semantic-invariant profile, per ADR-009 §7 and the experiment-core convention),
so the portable contract advertises every obligation and names its validator.
- **B3** - derived analysis is never captured evidence. An
  `experiment-evidence-record-v1` record is closed-world and carries no
  `measure_kind`/`value`/metric shape, and its `evidence_kind` has no
  measure/analysis member.
- **B4** - evidence claims must disclose redaction/loss. A `redacted` or
  `withheld` evidence record must carry `raw_content.loss_disclosure`, enforced
  both by the model and by the published schema.
- **B5** - backend observability is not a portable semantic observation. Only
  the governed `source_layer` vocabulary is an admissible portable view source;
  raw backend-native observability streams are rejected by the closed enum.

Stratum boundary traceability:

| Stratum | Carrier (contract / model) | Enforcement point | Invariant |
| ------- | -------------------------- | ----------------- | --------- |
| runtime-observable state | `RuntimeSnapshotEnvelopeModel` / `RuntimeSnapshot` | runtime snapshot diagnostics in `raes_conformance/conformance.py` | I2, I13 |
| captured evidence | `experiment-evidence-record-v1` / `ExperimentEvidenceRecordModel` | `_validate_evidence_record`, `_validate_raw_content`, closed-world `evidence_kind` (B3, B4) | I3, I13 |
| derived evaluations | `experiment-derived-measure-v1` / `ExperimentDerivedMeasureModel` | `_validate_derived_measure`, typed `source_evidence_refs` | I10 |
| analysis outputs | derived measure `measure_kind: analysis-output` + `ExperimentRunTraceabilityModel` | `_validate_run_traceability` claim grounding | I10, I15 |
| audience-specific views | `participant-context-view-v1` / `ParticipantContextViewModel` | `_validate_sem214_source_binding` + `_validate_sem216_audience_boundary` (B1, B2, B5) | I2, I3, I13 |

The obligations are projections of the existing abstract invariants - **I2**
(hidden-truth boundary), **I3**/**I13** (observation projection / apparatus
disclosure), **I10** (outcome-layer separation), and **I15** (run/study
provenance) - so `SEM-216` introduces no new `### I*` invariant heading and the
invariant oracle is unchanged.

Current implementation artifacts for the `SEM-216` slice:

- `implementations/python/packages/raes_contracts/contracts/` adds
  `ParticipantContextViewModel._validate_sem216_audience_boundary` with its
  published `allOf` (required view rule + redaction policy) and
  `x-raes-invariants` (archival source mediation, `payload_ref` non-aliasing)
  for the B1/B2/B5 view boundary, and publishes the evidence
  redaction/loss-disclosure rule as a portable schema constraint on
  `ExperimentEvidenceRecordModel` (B4);
- `contracts/schemas/control-plane/participant-context-view-v1.json` and
  `contracts/schemas/experiment-core/experiment-evidence-record-v1.json` carry
  the regenerated boundary constraints, recorded in
  `contracts/schema-publication-manifest.json`;
- `contracts/fixtures/control-plane/participant-context-view-v1/` and
  `contracts/fixtures/experiment-core/experiment-evidence-record-v1/` add the
  positive mediated-view fixture and the five adversarial negative fixtures
  (B1-B5);
- `implementations/python/tests/test_sem_216_boundary_semantics.py` proves each
  boundary obligation is rejected by both schema and model, with the mediated
  view admitted; the existing fixture-walk tests in
  `test_participant_backend_contracts.py` and `test_runtime_contracts.py` carry
  the same fixtures.

## SEM-217 - External Knowledge Binding Semantics

`SEM-217` requires explicit semantics for external knowledge bindings so a
reference to UCO, another ontology, a vocabulary, or an interoperability
profile cannot silently rewrite RAES-native meaning.

An external knowledge binding has exactly the effect declared by the governed
RAES surface that carries it:

- **annotates** - an external reference, reviewed class, evidence source, or
  citation adds context for a native RAES concept without changing validation,
  planning, runtime, or conformance semantics by itself.
- **aligns** - a reviewed external authority has equivalent meaning for the
  native RAES family. In the current concept-authority slice, adopted UCO
  concept families align with UCO meaning and carry no divergence list.
- **refines** - a reviewed external authority is used with RAES-specific
  narrowing, loss, or divergence. In the current slice, adapted UCO concept
  families refine rather than align and must enumerate the divergence.
- **constrains** - a governed surface must bind a vocabulary, capability, or
  phase assumption to a declared concept family; missing, unknown, duplicate,
  or out-of-scope bindings are validation failures, not advisory metadata.

Design commitments:

- native RAES contracts, concept families, reference models, semantic profiles,
  and validators remain the authority for RAES behavior;
- external authority references are versioned, review-scoped evidence rather
  than live network dependencies;
- annotation never implies constraint, refinement never weakens existing RAES
  invariants, and alignment never means schema inheritance;
- artifact-local labels do not define portable semantics unless they bind to a
  governed concept family or controlled vocabulary surface.

Current implementation artifacts for the `SEM-217` slice:

- `implementations/python/packages/raes_contracts/semantic_binding_effects.py`
  resolves the four SEM-217 effects over the existing UCO alignment and shared
  semantic-profile records;
- `implementations/python/tests/test_sem_217_knowledge_bindings.py` proves that
  adopted UCO bindings annotate and align, adapted UCO bindings annotate and
  refine, profile required bindings constrain governed surfaces, phases without
  governed bindings do not create constraint effects, and the effect vocabulary
  is closed over the four SEM-217 terms;
- `docs/explain/reference/shared-concept-model.md` records the
  implementation-facing guardrails and anti-patterns for external knowledge
  bindings.

## SEM-219 - Participant Tool And Affordance Semantics

`SEM-219` requires explicit semantics for participant tool and affordance
availability, visibility, invocation, and constraint handling.

The semantic unit is a participant-meaningful **affordance binding**, not a tool
label. An affordance binding relates:

- a stable tool or artifact identity, when one exists;
- one or more governed participant action-contract refs;
- participant or behavior-specification scope;
- authority and operating-scope bases;
- observation-boundary and visibility bases;
- parameter, resource, temporal, interaction, and realization constraints;
- expected observation and side-effect classes;
- implementation-support and realized-exposure disclosures; and
- evidence/provenance refs.

Tool identity, affordance meaning, and apparatus expectation are different
facts. In particular:

- `participant-tool-affordance-expectations` is an implementation-manifest
  capability vocabulary. It does not grant an authored participant an action.
- `ParticipantExposurePolicyModel.tool_affordance_refs` records selected
  run-level references. It is not proof that an affordance was visible,
  invocable, or delivered.
- an action contract defines portable action meaning. A shell, browser, binary,
  API, prompt, ATT&CK technique, or UI control does not replace that contract.

For affordance `f`, participant `p`, episode `e`, and order point `o`,
the semantic state is a tuple rather than one availability boolean:

```text
AffordanceState(p, e, o, f) = (
  authored,
  visible,
  apparatus_supported,
  eligible,
  invocable_or_admitted,
  realized,
  constraint_state,
  evidence_and_limitations
)
```

Each predicate has its own authority:

- **authored** follows participant/behavior bindings and action-contract refs;
- **visible** follows `V_p,o`, the observation boundary, audience scope, and
  exposure policy;
- **apparatus-supported** follows the selected participant implementation and
  backend capability disclosures;
- **eligible** follows SEM-211 authority, capability, target, knowledge,
  resource, temporal, interaction, and realization preconditions;
- **invocable/admitted** follows a concrete admission decision for an attempt;
- **realized** follows runtime behavior history, results, observations, and
  evidence; and
- **constraint state** reports satisfied, unsatisfied, unknown, exhausted, or
  unsupported constraints through the owning typed failure semantics.

No predicate implies another. A visible affordance may be ineligible. An
eligible affordance may be unsupported by the selected apparatus. A supported
affordance may be hidden from this participant. An admitted invocation may
still fail with a declared SEM-211 failure class.

Constraint handling reuses SEM-211. Missing, unresolved, stale, exhausted, or
unsupported constraints fail closed; they do not fall back to a backend-local
default. Constraint effects on visibility, telemetry, shared state, or outcome
interpretation are explicit side-effect/observation obligations under I5 and
I13.

Issue #294 owns the executable authoring, validation, compilation, runtime, and
test bindings for this section. It must reuse action contracts, SEM-211
admission, participant implementation manifests/selections, exposure policies,
behavior history, and observation/evidence records.

### DSL-117 interactive-access specialization

For participant `p`, let `IA(p)` be a finite map from portable local
declaration ids to records `(target_ref, channel, account_ref?)`. Let
`resolve_N` and `resolve_A` be the fail-closed node and account resolvers after
composition, and let `COMPUTE` be the set of declared compute nodes.

The authored interactive-access specialization satisfies:

- **IA1 — participant locality:** `IA(p)` belongs only to `p`; no declaration
  is global and participant implementation kind does not change its meaning.
- **IA2 — stable identity:** every map key is a portable local identifier,
  cannot be a variable, and is preserved through composition and compilation.
- **IA3 — closed target/channel:** every concrete `target_ref` resolves to one
  member of `COMPUTE`, and every concrete channel is exactly `ssh` or `rdp`.
- **IA4 — account authority:** when `account_ref` is present, it resolves to an
  account on `resolve_N(target_ref)` and that account occurs in `p`'s concrete
  `starting_accounts` set.
- **IA5 — endpoint uniqueness:** for distinct ids `i,j` in `IA(p)`, the pairs
  `(resolve_N(target_i), channel_i)` and
  `(resolve_N(target_j), channel_j)` differ. The same pair may occur for
  different participants.
- **IA6 — explicit absence:** `IA(p) = {}` means no authored interactive access.
  OS, roles, images, services, listeners, ACLs, ports, accounts, credentials,
  actions, and apparatus capabilities cannot synthesize an entry.
- **IA7 — phase separation:** an entry is authored access-carrier availability,
  not operating scope, action/affordance meaning, visibility, apparatus
  support, invocation admission, runtime session state, or realization
  evidence. No predicate is inferred from another.
- **IA8 — no locator or secret carriage:** the closed record admits no host,
  address, URL, port, username, password, key, token, credential, provider
  option, or portal session. A backend may add realization data only outside
  SDL and must not rewrite the authored declaration.

Whole-field variables defer IA3-IA5 only until binding. Instantiation and direct
artifact admission rerun the same predicates over concrete values; unresolved
values cannot enter an instantiated scenario. The executable oracle is
`implementations/python/tests/test_participant_interactive_access.py`.

## SEM-220 - Participant Decision-Surface Semantics

`SEM-220` requires explicit semantics for open-ended action generation,
constrained action forms, candidate-action sets, and their selection meaning.

ADR-095 revises the executable coordinate system without changing the three
selection forms. For participant `p`, episode `e`, decision epoch `k`, runtime
state `q`, participant/audience `a`, exact policy decision `r_c`, and state cut
`c`, define:

```text
D(p, e, k) = Pi[p, a, r_c, c](
  q,
  behavior and action-contract refs,
  V(p, c) and observation-boundary state,
  participant context,
  participant-implementation selection and decision-control mode,
  SEM-211 eligibility state,
  affordance/support disclosures,
  marking, redaction, and participant-visible limitations
)
```

`k` is the zero-based participant choice opportunity. `c` is the exact total
prefix or causal frontier from which the view is derived. Lifecycle generation,
behavior-history index, policy-effective cut, derivation anchor, disclosure
decision, delivery occurrence, and participant observation are independently
typed coordinates. Equality of integer values never merges their meanings.

`participant-decision-surface-v1` retains its historical meaning:
`observation_order` indexes the supplied time-indexed participant behavior
history. It remains valid for historical data and is not relabelled or admitted
through the v2 path. `participant-decision-surface-v2` is the actionable
contract and has no `observation_order`.

V2 separates three trust planes:

- `participant_view` is the complete low payload actually eligible for
  participant delivery: surface/participant/episode identity, `decision_epoch`,
  information-state/context refs, visible context, action entries,
  affordances, form, markings, redaction, and disclosed limitations;
- `assurance` carries the exact derivation state cut, lifecycle or terminal
  observation anchor, policy decision, apparatus/boundary refs, per-item
  authorization, participant-memory scope and reset authority when applicable,
  evidence, provenance, and canonical RFC 8785 digest of the participant view;
  and
- `delivery` records the trusted occurrence by which that exact digest became
  available to the participant, including delivery basis, delivery cut,
  delivery authorization/policy decision, observation ref, evidence,
  provenance, and limitations.

Assurance metadata is not participant-visible merely because it accompanies
the same surface artifact. Event ids, anchor order, prefix length, policy
decision ids, authorization records, evidence topology, provenance, rejection
detail, entry ordering, refresh behavior, and surface identity can convey
information and must be included in the participant projection only when an
independent SEM-226 decision authorizes them.

The reactive sequential baseline is:

```text
episode_running
  -> derive and authorize projected D(p,e,0) from V(p,initial-cut)
  -> disclose -> deliver -> participant observes
  -> participant selects/proposes from the delivered digest
  -> validate -> admit -> action_attempted
  -> state_transition_recorded -> terminal observation_emitted
  -> derive D(p,e,1) from that exact behavior cut
```

Projection is not disclosure; disclosure is not delivery; delivery is not
acknowledgement or interpretation; presentation is not selection; selection is
not admission; admission is not attempt, result, or outcome. A projected
surface is valid assurance data but cannot be selected. A v2 selection binds
surface id, decision epoch, participant-view digest, and delivery ref.
Admission re-resolves both derivation and delivery before behavior can be
written.

`episode_running` grounds epoch zero while current-episode behavior history is
empty. Later epochs equal the number of completed terminal participant
observations, but their state cuts retain the complete behavior prefix and its
own anchor order. Reset and restart create a new episode and epoch zero. They
do not erase a persistent human, agent, controller, or shared-memory
participant history unless an explicit `episode_local_reset` memory authority
resets every participant-visible channel.

The three surface forms have distinct selection meaning:

- **Open-ended generation:** the participant implementation may propose an
  action and arguments, but the proposal must resolve to a governed action
  contract, validate and normalize concrete values against the argument shape
  compiled from that exact contract, and pass SEM-211 admission before it
  becomes an attempt. The resulting immutable validated-selection carrier is
  the backend input. Generation authority is not invocation authority.
- **Constrained form:** a form, grammar, or parameter editor maps to an action
  contract. Defaults, normalization, omitted values, validation, and lossy
  transformations are part of the mapping and must be disclosed.
- **Candidate-action set:** the surface presents a participant-local set of
  action-contract entries. Selection identifies a member and its arguments.
  A non-member is invalid unless an explicit open-extension path binds it to a
  governed contract and applies the same validation and admission gates.

These are content/selection forms, not new values for
`participant-decision-surface-modes`. The controlled vocabulary describes how
an implementation makes or relays decisions. It cannot carry action lists,
observations, prompts, instructions, or policy bodies.

Candidate membership does not imply eligibility, and surface presentation does
not imply selection. Selection does not imply admission, execution, success, or
outcome interpretation. Those transitions remain explicit and evidence-backed.

`ParticipantContextViewModel` is the reuse-first portable envelope because it
already carries participant/episode scope, observation point, governed source
layers, transformation, `payload_ref`, visibility projection, markings,
redaction policy, evidence, provenance, limitations, and comparability. Issue
#295 may introduce a new closed decision-surface payload contract only when the
independently portable payload cannot be represented through that envelope
without weakening SEM-214/216 invariants. Any new payload composes stable refs;
it does not duplicate action, observation, exposure, or implementation records.

## SEM-226 - Participant Exposure And Visibility-Boundary Semantics

`SEM-226` requires explicit semantics for participant-visible versus hidden
context across participant decision surfaces.

This requirement refines the existing time-indexed `V_p,t`, view-rule,
view-transition, observation-boundary, context-view, and audience-view
semantics. It introduces no parallel visibility taxonomy.

For item `x`, participant `p`, episode `e`, audience `a`, and exact state cut
`c`:

```text
Exposed(x, p, e, a, c) only if
  x is admitted by V(p, c)
  and its source layer and transformation are participant-facing
  and its audience/role scope includes (p, a)
  and its marking, redaction, withholding, and loss rules are satisfied
  and the exact policy decision at c authorizes the disclosure class
  and the item authorization is bound to c
```

The conjunction is fail closed. Backend reachability, operating scope,
participant authority, control-plane authorization, or the presence of an item
in global/cumulative context cannot substitute for it.

The source classes remain distinct:

- participant-visible observations;
- authored control-context artifacts;
- hidden world-truth assets;
- adjudication and evaluator-only assets;
- private references, answer material, canaries, and holdout variants;
- scaffold instructions or guidance;
- archival evidence and derived analysis; and
- augmentation supplied by a human, participant implementation, backend, or
  other governed source.

Augmentation names its source, transformation, audience, visibility basis,
evidence/provenance, marking/redaction, and limitations. A generic metadata or
context map is not an exposure authority.

Exposure is participant-local and state-cut-indexed. A future or incomparable
policy decision cannot authorize an earlier cut. A decision epoch is not a
policy order. Delivery authority is resolved again at the delivery cut; a
derivation-time authorization cannot be carried forward merely because
delivery occurs in the same epoch. Unknown, stale, cross-cut, cross-policy, or
incomparable authority fails closed. When participants have different
boundaries, roles, policy cuts, or transition histories, they may receive
different surfaces for the same world event without semantic inconsistency.

Realized exposure is separately evidenced. A manifest capability, selected
mode, or exposure-policy ref can explain intent and apparatus support, but
runtime history/observation evidence records what the participant actually
received. Issue #296 owns executable enforcement and adversarial leakage
fixtures for this section.

### Joint lifecycle and authority boundaries

The joint model preserves meaning across stages:

- **authoring** binds participants/behavior specifications to action contracts,
  observation boundaries, authority/scope, and affordance semantics;
- **validation** resolves every ref and fails closed on unknown vocabularies,
  ambiguous selection meaning, incomplete constraints, or conflicting
  visibility bases;
- **compilation** emits canonical participant/action/observation addresses and
  the inputs required to derive `D(p,e,k)` from an exact state cut;
- **planning** validates selected implementation/backend support and records
  declared weakening before execution;
- **execution** applies existing SEM-211 admission and records behavior history,
  results, and visibility transitions;
- **observation/retrieval** derives participant-local surfaces from the
  applicable `V_p,c` state cut rather than global or final state; and
- **conformance** compares authored, compiled, selected, realized, and evidenced
  facts and reports disagreement through existing diagnostics.

Live state remains in `RuntimeSnapshot` and `ControlPlaneStore`. Archival
claims remain in existing evidence/provenance contracts. The joint design adds
no decision-surface side store, metadata bag, audit channel, exception
hierarchy, or backend-specific semantic authority.

### Source-to-contract-to-test matrix

The positive and adversarial fixture names below are required implementation
cases, not new artifacts delivered by issue #119. Each implementation issue
must preserve or strengthen its rows.

| Source / clause | Typed carrier or canonical helper | Lifecycle enforcement point | Positive case | Adversarial negative case | Existing invariant / implementation owner |
| --- | --- | --- | --- | --- | --- |
| SEM-219 A: tool identity is distinct from affordance meaning | `ParticipantToolAffordance.tool_ref` plus `action_contract_refs` | scenario-content concept/reference validation and `ParticipantToolAffordanceRuntime` canonical addresses | one content identity exposes separately keyed action affordances | raw tool label or cross-family declaration accepted as identity/action meaning | I14, I16 / #294 |
| SEM-219 B: authored availability is participant-local | `ParticipantBehaviorSpecification.tool_affordances`, `agents.*`, authority/scope refs | `SemanticValidator`, role/participant subset checks, full post-instantiation validation | affordance remains within one behavior spec and every resolved participant | globally declared content or apparatus support synthesizes participant availability | I1, I4 / #294 |
| SEM-219 C: visibility is independent of availability | stable authored affordance ref, `ParticipantViewRule`, transition, observation boundary, `V_p,o` | explicit boundary classification plus compiled view timeline | authored affordance is independently observable or hidden | authored/global affordance appears without participant-local classification | I2, I3 / #294 |
| SEM-219 D: invocation is independently admitted | compiled affordance action addresses plus `ParticipantActionAdmissionRequest` | authoring locality gate followed by the existing runtime admission path | visible action remains a reference requiring independent admission | binding widens participant actions or visibility is treated as invocation | I4 / #294 |
| SEM-219 E: constraints fail closed | affordance action refs plus unchanged SEM-211 preconditions/failure classes | semantic validation and existing planner/admission/result gates | complete action constraints remain reachable through the compiled action address | binding copies, drops, or overrides exhausted/unknown constraints | I4, I7 / #294 |
| SEM-219 F: support is apparatus metadata | authored affordance IR remains separate from manifest/selection support | absence-preserving compilation plus existing apparatus validation | support can be joined later without changing authored meaning | installed content or backend support creates an affordance grant | I11, I12 / #294 |
| SEM-219 G: side effects and observations are explicit | affordance observation addresses plus action effects/evidence expectations | boundary classification, compiler IR, existing result/snapshot/conformance gates | tool output remains governed by referenced observation/effect contracts | tool output lacks a view rule or leaks hidden truth | I5, I13 / #294 |
| SEM-220 A: decision epoch and derivation cut remain distinct | `ParticipantDecisionSurfaceV2Model`, typed readiness/behavior anchor, and sequence/causal state cut | trusted snapshot/history resolution at projection and admission | `episode_running` grounds epoch zero with empty behavior; epoch one carries behavior anchor order two after one three-occurrence action | lifecycle, behavior, policy, delivery, or decision coordinates are collapsed into one scalar | I1, I3, I15 / #295, #909 |
| SEM-220 B: candidate membership is not eligibility | action-entry contract ref plus explicit SEM-211 eligibility state/reason refs | surface derivation followed by independent admission | visible candidate is marked ineligible with a typed reason | every presented candidate is implicitly executable | I4 / #295 |
| SEM-220 C: open-ended proposals bind before admission | compiled `ParticipantActionContractRuntime.argument_shape_ref`, `ParticipantValidatedActionSelection`, and SEM-211 admission helper | proposal resolution, concrete argument validation/normalization, immutable carrier binding, then runtime admission | generated proposal resolves and validates before an attempt | free-form generation bypasses applicability or invents backend-local meaning | I4, I11 / #295, #303 |
| SEM-220 D: constrained forms preserve mapping meaning | `ParticipantActionArgumentDefinition`, canonical compiled shape identity, and explicit default/normalization/omission/loss disclosure | closed authoring validation, compiler mapping, `resolve_participant_action_arguments()`, and conformance comparison | form values map deterministically to validated action arguments | omitted/defaulted field changes meaning without disclosure | I12, I14, I16 / #295, #303 |
| SEM-220 E: delivery, selection, admission, attempt, and outcome are separate | projected/delivered lifecycle, canonical participant-view digest, delivery record, v2 selection, behavior history, action result, outcome interpretation | delivery-time authority, admission-time anchor/delivery re-resolution, then existing execution validators | exact delivered digest is selected and admitted once before attempt/result | projected, stale, reset, replayed, forged, or undelivered surface creates behavior | I10 / #295, #909 |
| SEM-220 F: implementation kind does not change semantics | participant implementation manifest/selection, explicit `participant-decision-surface-v2` support, and stable surface refs | capability declaration plus exact-cut apparatus validation and cross-run conformance | human proxy and autonomous implementation realize equivalent refs with disclosed differences | implementation type or undeclared v2 consumption silently changes action or selection meaning | I1, I11, I12, I15 / #295, #909 |
| SEM-226 A: exposure is scoped by `V_p,c` | compiled view relation, observation boundary, exact-cut policy decision, and `ParticipantDecisionSurfaceExposureBindingV2Model` | `project_participant_decision_surface_v2()` resolves policy and item authority at the derivation cut | disclosed item is authorized at the exact cut independently of decision epoch | caller-supplied, stale, future, cross-cut, or incomparable policy state enters a view | I2, I3 / #296, #909 |
| SEM-226 B: source strata remain distinct | `ParticipantContextViewModel.source_layers` plus resolved authorization-record source/result, transformation, marking, and provenance refs | trusted item-authorization resolution followed by the deny-first exposure selector | archival evidence is mediated through an authorized participant-facing transformation with inherited markings and provenance | truth/adjudication/evidence payload or a self-attested transform aliases the visible context payload | I2, I3, I13 / #296 |
| SEM-226 C: role/audience scope is explicit | context-view audience fields plus resolved authorization participant, episode, audience, order, apparatus, and policy coordinates | exact authorization/surface agreement and separately resolved implementation-selection checks before serialization | role-scoped context reaches only the intended participant audience | private or role-specific context appears through a synthetic selection or another participant's authorization | I2, I17 / #296 |
| SEM-226 D: augmentation is governed exposure | resolved authorization source layer, transformation, visibility basis, backend-support ref, evidence/provenance, and limitations | authorization resolver, deny-first item exposure selector, and context-view validation | augmentation records source, authorized transformation, disclosure basis, and limits | scaffold guidance or augmentation metadata enters through caller-owned gate booleans | I3, I13, I17 / #296 |
| SEM-226 E: exposure changes are cut-anchored | exact state cut, policy-decision ref, immutable exposure-policy version/digest, derivation anchor, and authorization evidence | exact-cut policy/authorization resolution at derivation plus fresh delivery-cut authority | revocation prevents later delivery without retroactively erasing an earlier delivery | decision epoch or a later policy revision is used as authorization order | I2, I8, I9 / #296, #909 |
| SEM-226 F: delivery is not inferred from projection or disclosure | `ParticipantDecisionSurfaceDeliveryV2Model` and delivered lifecycle state | delivery resolver at transition and again at admission, bound to participant-view digest | trusted emission-is-delivery or transport occurrence makes the exact view actionable | projection, policy selection, or an unrelated observation is treated as delivery | I11, I13, I15 / #296, #909 |

### Adversarial counterexamples

The matrix includes the required negative cases; these examples make the
cross-requirement failure shapes explicit:

1. A shell is globally installed and supported, but participant `p` has no
   authored affordance binding. It is not available to `p`.
2. An affordance is authored and visible, but its target lies outside `p`'s
   authority. It remains visible and is rejected at admission.
3. An affordance is authored and eligible, but the selected implementation
   declares no realization support. Planning fails or records it as unsupported;
   it does not silently substitute another tool.
4. Candidate actions are computed from hidden evaluator state. The surface is
   invalid even when every action contract would otherwise be well formed.
5. A candidate is derived from a disclosure whose effective order is later than
   the surface order. Future visibility does not repair the earlier leak.
6. Open-ended generation emits a backend command without resolving a governed
   action contract. The proposal is rejected before admission.
7. A constrained form drops a parameter or supplies a hidden default that
   changes action meaning. The mapping is invalid without explicit disclosure.
8. A private answer reference, canary, adjudication record, scaffold hint, or
   augmentation payload enters the wrong participant's context view. Audience
   and hidden-truth boundaries reject it.
9. An exposure policy selects a tool-affordance ref, but runtime history contains
   no corresponding exposure evidence. Selection is not proof of realization.
10. A final aggregate surface is used to claim what the participant saw earlier.
    The claim is invalid without the order-indexed surface/history sequence.

The obligations above refine existing I1-I17 invariants. They add no new
`### I*` heading and therefore do not expand the abstract invariant oracle in
this design issue. Issues #294-#296 own concrete typed bindings and negative
fixtures that specialize the existing oracle.

## SEM-230 - Participant Information-Flow And Control Semantics

SEM-230 is defined in
[`information-flow-control.md`](information-flow-control.md). The focused
authority defines the revisioned crossing relation, participant/audience/policy
and order-relative label projection, independent control and information-flow
operations, dynamic purge and declassification semantics, and the exact
baseline `policy-noninterference` obligation.

The relation is bound through current taxonomy revision `rev8` rather than a local
registry. Its current assurance is definition-complete and bounded-tested but
deliberately unproved. The test-local model can falsify finite cases; it is not
runtime mediation, backend realization, or a universal information-flow proof.

## SEM-231 - Participant-Relative Predicate Opacity Semantics

SEM-231 is defined in
[`participant-predicate-opacity.md`](participant-predicate-opacity.md). The
focused authority defines a one-sided possibilistic predicate-opacity kernel
over participant information cells, mandatory revisioned opacity profiles,
active-strategy quantification, supervisor visibility, release and retained
memory, explicit time/order/probability boundaries, and exact distinctions
from SEM-230 noninterference, projected-history equality, epistemic
indistinguishability, trace equivalence, and bisimulation.

Taxonomy revision `rev5` introduced the relation and bounded-test assurance.
Revision `rev7` added the closed baseline profile and deterministic bounded
checker. Current revision `rev8` adds deterministic exact finite-state model
checking for the baseline fixture profile. It claims no mathematical proof,
runtime enforcement, backend declaration, backend realization, or backend
conformance. Issues #963 through #965 own those remaining independent lanes.

## SEM-232 - Proof-Bearing Participant-Crossing Bisimulation

SEM-232 is defined in
[`participant-crossing-bisimulation.md`](participant-crossing-bisimulation.md).
The design selects
`divergence-preserving-branching-bisimulation` between the complete finite
abstract SEM-230 crossing operation and an independently formalized
API-423/RUN-319 crossing kernel under
`participant-crossing-dpbb-finite-v1@rev1`.

Taxonomy revision `rev6` defines the exact relation and claim surface. Issue
#811 supplies the closed carrier, label projection, relation clauses, witness
family, mapping boundary, proof-tool contract, counterexample design, DRAFT
SEM-232 authority, and child program. It does not run the model check. Issues
#971 through #976 own independent model construction, live-runtime mapping,
negative mutations, finite equivalence checking, independent reproduction,
and reproduction-gated scientific documentation.

## SEM-233 and ASR-536 - Adversarial Participant Flow Control

SEM-233 and ASR-536 are defined in
[`adversarial-flow-control.md`](adversarial-flow-control.md).

SEM-233 adds a revisioned participant-neutral explicit-flow profile with
independent confidentiality and integrity coordinates, conservative
propagation, distinct declassification and integrity endorsement, and
deny-first final-sink decisions immediately before external action or
disclosure. Handoff, participant change, and episode reset do not erase labels
or provenance.

ASR-536 adds a separate control-evaluation profile for honest and attack
modes, main and side objectives, policy and monitor knowledge, adaptive
strategies, collusion and correlated failure, audit and intervention
protocols, memory/replay, and separate safety, usefulness, cost, uncertainty,
limitation, and nonclaim measures.

Issue #812 supplies the design authority and child program. Issue #1001
publishes the SEM-233 revision-1 algebra, and #1002 publishes its exact
profile plus portable relation contract with resolver-backed context
validation. SEM-233 and ASR-536 remain DRAFT; #1003, #1004, #1007, and #1008
retain the runtime, apparatus/backend, evaluation, and documentation work.

## Required Future Verification

The complete participant surface is `FM3`.

Delivered executable assurance artifact:

- `implementations/python/tests/test_participant_semantics_invariant_oracle.py`
  provides the FM-2 invariant oracle for `I1` through `I18`, including
  property-based valid episode/action/observation/outcome progressions and
  invariant-specific rejecting mutations.

Future implementation PRs should still include:

- child UID invariant refinements that specialize the abstract `I1` through
  `I18` oracle for concrete runtime slices;
- typed IR or published contracts for actions, observations, visibility,
  attribution, temporal clauses, and outcomes;
- runtime-integrated abstract state-machine coverage for
  episode/action/observation/outcome progression;
- machine-checkable action, observation, visibility, failure, temporal,
  attribution, and outcome semantics; prose-only definitions are insufficient
  for conformance;
- property-based or differential tests for visibility, interaction, ordering,
  failure, and outcome interpretation;
- mapping-loss fixtures for ATT&CK, OCSF, CACAO, STIX, OpenC2, Cyber DEM, CVE,
  exploit-module, and benchmark-milestone bindings;
- observation-apparatus fixtures covering capture basis, sampling/loss,
  redaction, delayed disclosure, and observer-effect disclosures;
- hidden-answer, canary, holdout-variant, and starter-file leakage tests;
- run/study provenance fixtures covering reset strategy, seeds, backend and
  participant versions, scaffold disclosure, and content/action-contract
  versions;
- authoring-profile examples and ambiguity/usability review artifacts for the
  concrete syntax chosen by child implementation issues, coordinated with the
  DSL language-evaluation evidence gate in issue #346;
- cross-stage agreement tests spanning authoring, validation, instantiation,
  compilation, planning, execution, and observation;
- backend conformance fixtures demonstrating both supported and explicitly
  unsupported participant-semantic guarantees.

## Deliberate Non-Adoptions

- Do not adopt Gym/PettingZoo as the RAES runtime protocol. Use their concepts,
  not their API shape, as lineage.
- Do not treat CybORG action YAML as the RAES action contract. It is precedent
  for action/observation discipline and sim-to-emulation disclosure.
- Do not treat ATT&CK technique IDs as action semantics. They are behavior
  labels, not precondition/effect/failure contracts.
- Do not treat OCSF events as participant observations without an explicit view
  relation.
- Do not treat CACAO agents/targets as participant semantics. They are useful
  workflow and command-lineage objects.
- Do not treat Cyber DEM as the RAES scenario model. It is an exchange model for
  cyber simulation objects/events.
- Do not treat timestamp order as causal attribution.
- Do not treat CTF flag capture, subtask completion, or benchmark milestone
  progress as complete participant outcome semantics.
- Do not treat Docker/container reproducibility as run or study reproducibility
  without reset, seed, version, backend, scaffold, and hidden-asset provenance.
- Do not treat external CTI, CVE, exploit-module, or command names as portable
  behavior without an RAES action contract and loss-labeled mappings.

## References

- ADR-022: Participant Behavior and Interaction Semantics
- ADR-083: Participant Tool, Decision-Surface, and Exposure Semantics
- ADR-085: Participant Information-Flow And Control
- ADR-090: Shared Time-Domain, Clock, And Progression Authority
- ADR-091: Portable Time Capability, Control, And Provenance Contracts
- ADR-092: Autonomous Benign Participants Under Shared Time
- ADR-007: Lightweight Formal Methods Policy for Semantic Systems
- ADR-013: Participant Episode Lifecycle Boundaries
- ADR-016: Semantic Layer Scope and Coverage Model
- ADR-020: Declarative Participant Framing Boundaries
- [OpenAI Gym](https://arxiv.org/abs/1606.01540)
- [Gymnasium](https://arxiv.org/abs/2407.17032)
- [PettingZoo](https://papers.nips.cc/paper/2021/hash/7ed2d3454c5eea71148b11d0c25104ff-Abstract.html)
- [OpenSpiel](https://arxiv.org/abs/1908.09453)
- [Planning and Acting in Partially Observable Stochastic Domains](https://people.smp.uq.edu.au/YoniNazarathy/Control4406_2014/resources/KaelblingLittmanCassandra1998.pdf)
- [Bernstein, Givan, Immerman, Zilberstein — The Complexity of Decentralized Control of Markov Decision Processes (Mathematics of Operations Research 27(4), 2002)](https://doi.org/10.1287/moor.27.4.819.297)
- [Oliehoek and Amato — A Concise Introduction to Decentralized POMDPs (Springer, 2016)](https://doi.org/10.1007/978-3-319-28929-8)
- [Kuhn — Extensive Games and the Problem of Information (Contributions to the Theory of Games II, 1953)](https://doi.org/10.1515/9781400881970-012)
- [Goguen and Meseguer — Security Policies and Security Models (1982)](https://doi.org/10.1109/SP.1982.10014)
- [Sabelfeld and Sands — Declassification: Dimensions and Principles (2009)](https://doi.org/10.3233/JCS-2009-0352)
- [Fagin, Halpern, Moses, Vardi — Reasoning About Knowledge (MIT Press, 1995)](https://mitpress.mit.edu/9780262562003/reasoning-about-knowledge/)
- [van Ditmarsch, van der Hoek, Kooi — Dynamic Epistemic Logic (Springer, 2007)](https://doi.org/10.1007/978-1-4020-5839-4)
- [Goguen and Meseguer — Security Policies and Security Models (IEEE S&P, 1982)](https://doi.org/10.1109/SP.1982.10014)
- [Sabelfeld and Sands — Declassification: Dimensions and Principles (Journal of Computer Security 17(5), 2009)](https://doi.org/10.3233/JCS-2009-0352)
- [Huang, Caines, Malhamé — Large Population Stochastic Dynamic Games (Communications in Information and Systems 6(3), 2006)](https://doi.org/10.4310/CIS.2006.v6.n3.a5)
- [Lasry and Lions — Mean Field Games (Japanese Journal of Mathematics 2, 2007)](https://doi.org/10.1007/s11537-007-0657-8)
- [Yang et al. — Mean Field Multi-Agent Reinforcement Learning (ICML, 2018)](https://arxiv.org/abs/1802.05438)
- [Fikes and Nilsson — STRIPS (Artificial Intelligence 2, 1971)](https://doi.org/10.1016/0004-3702(71)90010-5)
- [Haslum, Lipovetzky, Magazzeni, Muise — An Introduction to the Planning Domain Definition Language (Morgan & Claypool, 2019)](https://doi.org/10.2200/S00900ED2V01Y201902AIM042)
- [Fox and Long — PDDL2.1: An Extension to PDDL for Expressing Temporal Planning Domains (JAIR 20, 2003)](https://doi.org/10.1613/jair.1129)
- [Younes, Littman, Weissman, Asmuth — The First Probabilistic Track of the International Planning Competition (JAIR 24, 2005)](https://doi.org/10.1613/jair.1880)
- [Sanner — Relational Dynamic Influence Diagram Language (RDDL): Language Description (2010)](https://users.cecs.anu.edu.au/~ssanner/IPPC_2011/RDDL.pdf)
- [CybORG](https://arxiv.org/abs/2108.09118)
- [CyGIL: A Cyber Gym for Training Autonomous Agents over Emulated Network Systems](https://arxiv.org/abs/2109.03331)
- [Unified Emulation-Simulation Training Environment for Autonomous Cyber Agents](https://arxiv.org/abs/2304.01244)
- [CyberBattleSim](https://www.microsoft.com/en-us/research/project/cyberbattlesim/)
- [Cybench](https://arxiv.org/abs/2408.08926)
- [AutoPenBench](https://arxiv.org/abs/2410.03225)
- [CAIBench](https://arxiv.org/abs/2510.24317)
- [AI Agents That Matter](https://arxiv.org/abs/2407.01502)
- [Benchmarking Practices in LLM-driven Offensive Security](https://arxiv.org/abs/2504.10112)
- [VSDL](https://arxiv.org/abs/2001.06681)
- [CyRIS](https://www.jaist.ac.jp/~razvan/publications/cyris_facilitating_training.pdf)
- [Automated Cyber Range Design](https://arxiv.org/abs/2307.04416)
- [Open Cyber Range SDL](https://documentation.opencyberrange.ee/docs/sdl/)
- [Russo, Costa, Armando — Building Next Generation Cyber Ranges with CRACK (Computers & Security 95, 2020)](https://doi.org/10.1016/j.cose.2020.101837)
- [CACAO Security Playbooks v2.0](https://docs.oasis-open.org/cacao/security-playbooks/v2.0/security-playbooks-v2.0.pdf)
- [OCSF](https://ocsf.io/)
- [MITRE ATT&CK Design and Philosophy](https://www.mitre.org/news-insights/publication/mitre-attck-design-and-philosophy)
- [CALDERA planning and acting with unknowns](https://www.mitre.org/sites/default/files/2021-11/prs-18-0944-1-automated-adversary-emulation-planning-acting.pdf)
- [Halpern and Pearl, structural-model causality](https://arxiv.org/abs/cs/0011012)
- [Chockler and Halpern — Responsibility and Blame: A Structural-Model Approach (JAIR 22, 2004)](https://doi.org/10.1613/jair.1391)
- [Lamport, Time, Clocks, and the Ordering of Events](https://systems.cs.columbia.edu/ds2-class/papers/lamport-time.pdf)
- [Fidge — Timestamps in Message-Passing Systems That Preserve the Partial Ordering (Australian Computer Science Communications 10(1), 1988)](https://fileadmin.cs.lth.se/cs/Personal/Amr_Ergawy/dist-algos-papers/4.pdf)
- [Mattern — Virtual Time and Global States of Distributed Systems (Parallel and Distributed Algorithms, 1989)](https://www.vs.inf.ethz.ch/publ/papers/VirtTimeGlobStates.pdf)
- [Schwarz and Mattern — Detecting Causal Relationships in Distributed Computations: In Search of the Holy Grail (Distributed Computing 7(3), 1994)](https://doi.org/10.1007/BF02277859)
- [Winskel — Event Structures (Advances in Petri Nets, 1986)](https://doi.org/10.1007/3-540-17906-2_31)
- [Mazurkiewicz — Trace Theory (Advances in Petri Nets, 1986)](https://doi.org/10.1007/3-540-17906-2_30)
- [Allen — Maintaining Knowledge about Temporal Intervals (CACM 26(11), 1983)](https://doi.org/10.1145/182.358434)
- [Koymans — Specifying Real-Time Properties with Metric Temporal Logic (Real-Time Systems 2, 1990)](https://doi.org/10.1007/BF01995674)
- [Alur and Dill — A Theory of Timed Automata (Theoretical Computer Science 126, 1994)](https://doi.org/10.1016/0304-3975(94)90010-8)
- [IEEE Std 1516-2010 — High Level Architecture: Framework and Rules](https://standards.ieee.org/ieee/1516/3744/)
- [SISO Cyber DEM](https://cdn.ymaws.com/www.sisostandards.org/resource/resmgr/standards_products/siso-std-025-2023_cyberdem.pdf)
- [Do Software Languages Engineers Evaluate their Languages?](https://arxiv.org/abs/1109.6794)
