# Understand participant-control boundaries

This explanation describes the Python implementation in RAES 11.0.2.
For a task, use [control participant input and output](participant-control.md).
The cited specifications and decisions retain normative authority.

## Keep four planes separate

For backend authors, the
[modular provider contract reference](https://github.com/OpenRAE/rae/blob/dev/docs/explain/reference/modular-participant-control-contracts.md)
describes closed profile selections, typed results and requested effects, and
how the reference runtime orchestrates them. Publishing these contracts does not install a provider.
It does not execute the provider's requests. The runtime invokes only
providers an operator constructed and bound to the admitted selection. It
commits the composed decision before any backend effect or delivery. It
dispatches an admitted effect only through the RAES operation that already owns
it. An effect acts for the principal whose operation admitted it.
The caller that later requests dispatch does not replace that principal.

API-424 now also publishes v2 selection/evaluation contracts and
`ParticipantControlProviderV2` for per-crossing applicability and typed
dependency inputs. The admitted apparatus stays complete.
Applicable slots form a separate set at one state cut.
They require profile-owned coverage and explicit input support.
They keep parent decisions separate from effect prerequisites. They require exact protocol/schema negotiation and a
trusted operator resolver. The reference runtime can explicitly admit a v2 binding.
It evaluates applicable slots in dependency order. Required inputs must be satisfied.
Required support must be satisfied too.
Optional failure is recorded without blocking an otherwise permitted crossing. Scoped state and the evaluation join the
existing atomic crossing commit. Retained v1 records keep their original
interpretation. V2 admits only effects with an installed, exactly bound owner.
Its drain supports fresh world injects, compiled handoffs and evidenced
cancellation of execution attempts. Parent denial applies before execution.
Independent consequences need their own authority. Evaluation eligibility
supplies no effect permission. See the
[migration rules](https://github.com/OpenRAE/rae/blob/dev/docs/migration/control-applicability-and-evaluation.md).

| Plane | What it contains | What it does not imply |
| --- | --- | --- |
| World truth | Backend or environment state under its owning semantics | Participant visibility |
| Participant view | A projection authorized for one participant and audience at an exact policy state cut | Complete world truth or future delivery |
| Participant-visible history | The append-only actions, controls, views, deliveries, and observations exposed to that participant | Administrative crossing history |
| Archival evidence | Crossing decisions, operations, audit, provenance, and conformance records retained for authorized review | Participant disclosure |

Projection, disclosure, delivery, and observation are different facts. A
permitted projection can still fail before delivery. A delivered value may
never be observed. Audit retention does not put a value in the participant
view.

The crossing history keeps each API-423 stage apart. The first stages are request, decision, change, and release.
The remaining stages are delivery attempt, delivery, observation, and audit.
Each stage refers to an existing carrier. It does not copy the carrier payload
into a generic participant message.

## Mixed simulation and emulation semantics

Issue #813 and ADR-102 define the design boundary for using the same
participant-control intent in:

- simulation or emulation/operation as alternative realizations; and
- simulation and emulation/operation together in one admitted trial.

Issue #1013 publishes SEM-234's revisioned semantic definition and finite admission examples.
The installed runtime executes simultaneous mixed arrangements.
It also executes staged handoffs.
The [mixed-control demonstration](https://github.com/OpenRAE/rae/blob/dev/docs/explain/reference/mixed-control-demonstration.md)
checks these paths with controlled test providers.
It establishes no native backend qualification or simulation-to-operation transfer.
The broader ASR-537 research requirement remains DRAFT.

Portable SDL stays backend-neutral. Admitted trial intent allocates
stable participant-runtime, controlled-scope, action-family,
observation-source, and crossing refs to exact apparatus components. Each component edge must state its adapter, authority, and action/observation mapping.
It must state participant/audience policy and clock/order mapping.
It must also state support strength, loss, failure behavior, and evidence.

These are admitted apparatus obligations. They do not require authors to
specify internal installation recipes. Open materialization scopes retain their delegated choices.
Exact constraints stay binding. Abstract models can be complete. Reporting, experimental collection, retention and export are
independently requested; precise scenario detail does not imply telemetry.

Keep these separate:

- participant identity;
- the one acting controller in revision 1;
- authority basis and controlled scope;
- action admission;
- the provider responsible for realizing an action or observation;
- HLA-style object/attribute ownership;
- delivery routing; and
- participant disclosure authority.

Multiple providers are not multiple controllers. Revision 1 does not support
leases, simultaneous scoped controllers, or joint/fused control.

The design also separates three meanings of open/closed:

1. open-loop observation versus closed-loop actuation;
2. closed-world versus bounded-open-world assumptions; and
3. fixed versus finite pre-admitted dynamic membership.

Closed-loop does not grant action authority. Bounded-open-world does not allow
unknown commands or mappings. Dynamic membership does not allow an unadmitted
backend to join.

An inter-trial realization change creates a new linked plan entry.
It creates a new run too. A
within-run change is permitted only as a finite schedule whose components,
mappings, policy, clocks, and failure behavior were admitted before execution.
Neither kind erases prior delivery or participant knowledge.

Do not treat a shared adapter, passing conformance probe, paired backend run,
or successful transfer trial as backend equivalence. The contract, runtime and
evidence have separate owners and limits. Reusable control combined with mixed runtime remains refused.
Distributed dispatch combined with local portable mixed services also remains refused.
See the [current support reference](https://github.com/OpenRAE/rae/blob/dev/docs/explain/reference/revised-control-semantics.md),
[migration checklist](https://github.com/OpenRAE/rae/blob/dev/docs/migration/revised-control.md),
and [executable examples](https://github.com/OpenRAE/rae/blob/dev/docs/examples/revised-control.md).

## Read the crossing examples

The examples below use synthetic identifiers and summarize existing evidence.
They are explanatory illustrations, not new API payloads.

### Denial

An egress request names participant `red-1`. It also names audience
`red-primary`. A policy or audience gate returns deny at the exact state cut.
The runtime records the request. It also records the deny result. It releases
no value and makes no backend call. Safe audit proof may retain the refusal.
It does not reveal the rejected value or a hidden participant.

The ASR-535 `denial` case checks the refusal and those side-effect boundaries
through the shipped runtime. It is one named finite case. It is not a broad
information-flow result.

### Withholding

Withholding is a choice not to release an available item. It is not packet
loss. It is not a backend fault or missing record. API-423 can record a
`withhold` result. It can keep safe proof of why the crossing stopped.

The current RUN-319 decision mapper does not emit `withhold`. Its finite
ASR-535 probe accepts a deny as refusal proof. The probe tests nonrelease. It
does not show that the runtime made a distinct withholding fact.

### Redaction

For an allowed status projection, policy can select redaction. It can also
select a governed change before release. The result keeps a typed subject. It
records the source and result link. It records loss, markings, the policy
result, and proof. Only the new carrier may be written to the view.

Redaction does not allow a crossing. It does not declassify the source. An
ingress change creates a new typed subject. That subject needs fresh checks
and full action admission. The ASR-535 `redaction` case gives bounded runtime
proof of this split.

### Governed declassification

Declassification needs an exact authority basis. It needs the policy result,
state cut, source mark, allowed release, order, and proof. Authority at one cut
does not change the past. It does not survive an unrelated policy revision.
The result is still not delivery or observation.

The finite ASR-535 governed-declassification case drives a status projection.
It does not request a separate declassification operation. It does not prove
support for the `participant_declassification` backend feature.

### Intervention and transformation

Each external control event remains an API-409 control occurrence. This
includes a proposal, approval, intervention, handoff, override, or
cancellation. The event stays bound to the authored mixed-control state
machine. Participant ingress adds the needed API-423 crossing facts. Approval
does not admit or run an action. An intervention does not replace the control
move.

If mediation transforms the proposed ingress, the transformed subject gets a
new identity. It gets a fresh semantic check and action-admission result. The
ASR-535 `transformation` case is bounded refusal proof. It is not a general
refinement or simulation result.

### Participant-directed inject delivery

The authoring model binds one participant to one inject occurrence. It binds
the observation boundary, order, and proof needs. It may also bind a matching
mixed-control move. Environment-only injects stay as orchestration events.
Normal participant projection must allow them.

The shipped runtime probe records delivery of an already projected status view
under the `participant-inject-delivery` interaction kind. It keeps delivery
apart from observation. It does not bind the compiled DSL-142 delivery to the
original DSL-111 inject identity. It also does not bind the full
event/script/story identity end to end.

### Unsupported capability

The selected target may omit a needed feature. It may omit a contract, proof,
resolver, or minimum strength. In each case, selection or crossing fails
closed. This happens before backend dispatch or view output. The report keeps
the stated level and a safe reason. It makes no positive support claim.

The ASR-535 `unsupported-capability` case and the no-harness path demonstrate
this bounded behavior. A manifest entry alone is not runtime support. It is
not conformance.

All seven finite cases are exercised and bounded in
[the ASR-535 assurance tests](https://github.com/OpenRAE/rae/blob/dev/implementations/python/tests/test_asr_535_participant_flow_assurance.py).

## Select a behavioral claim

Read the current
[behavioral-relation catalog](https://github.com/OpenRAE/rae/blob/main/contracts/concept-authority/behavioral-relations-v1.json)
instead of defining relation meaning in a report.

| Question | Catalog relation | Required boundary |
| --- | --- | --- |
| Did named finite fixtures or probes produce their expected results? | `bounded-probe-success` | Exact target, profile, cases, assumptions, failures, and finite bound |
| Are two histories equal for one participant under one projection revision? | `participant-projected-history-equivalence` | Both carriers, participant, projection, order, and compared bound |
| Are unauthorized high variations invisible under the full participant policy? | `policy-noninterference` | Adaptive strategies, memory, exact policy cuts, purge and declassification schedule, scheduler, environment, order, and support-set quantifiers |
| Does every actual secret point retain a nonsecret alternative in the same observer information cell? | `participant-predicate-opacity` | Exact revisioned opacity profile; a model-check claim additionally binds the complete finite transition model, assumptions, tool, explored coverage, and result |
| Does every projected implementation trace belong to an abstract trace set? | `trace-inclusion` | Left-to-right direction, labels, hiding, projection, assumptions, and the universal obligation |
| Can implementation and abstract steps be matched in one direction? | `forward-simulation` or `backward-simulation` | State relation, initiality, direction, and step obligations |
| Do concrete states and operations preserve an abstract data model? | `data-refinement` | Retrieve relation plus initialization and operation obligations |
| Do two branching systems match in both directions? | `strong-bisimulation` or `weak-bisimulation` | Symmetry; weak matching also names the governed hidden-action set, closure, stuttering, and divergence treatment |
| Do two finite crossing models match in both directions with explicit hidden steps and divergence? | `divergence-preserving-branching-bisimulation` | Closed relation-parameter profile, complete finite carrier, both initial states, projection, hidden-label set, tool provenance, and mutations, checked again on every commit |

Two equal sampled histories support a bounded comparison. They do not show
participant-policy noninterference. A successful trace sample does not show
trace inclusion. A matching finite example does not show simulation or
refinement. It also does not show strong or weak bisimulation. The finite
participant-opacity model check covers only its exact digest-bound model and
profile; it does not establish runtime enforcement, backend realization, or an
unbounded theorem.

The [bounded example claim](participant-control.md#select-a-behavioral-claim)
retains the seven-case binding and its explicit nonclaims.


## Read the finite participant-crossing result

RAES has one reproduced finite result for the
`divergence-preserving-branching-bisimulation` relation.
The result compares two formal models.
Both describe one participant crossing.
The abstract model follows SEM-230.
The concrete model follows the API-423 and RUN-319 crossing kernel.
Separate transition authorities construct the two models.
Both models are complete for profile `participant-crossing-dpbb-finite-v1@rev2`.
The profile has one participant and one audience.
It has one controller, one episode, and one request.
It has the exact policy cuts `p0` and `p1`.
Projection `participant-crossing-projection@rev1` hides only five mediation classes.
Denial, unsupported outcomes, delivery, observation, replay rejection, and cut advance stay visible.
Deadlock, termination, and divergence stay explicit.

The mCRL2 `202607.0` `dpbranching-bisim` decision relates the declared initial states.
Every mandatory mutation fails the relation.
CI builds the models and the mutation corpus from the current sources and repeats the decision on every commit.
No retained result record exists.
No reviewer reproduction record exists.

This is a finite model-check result.
It is not an unbounded proof, a proof certificate, or a checked relation witness.
It does not establish live-runtime realization.
It does not establish backend conformance.
It does not establish policy noninterference or predicate opacity.
It makes no timed, probabilistic, concurrent, fair, partial-order, handoff, or multi-operation claim.
The separate multi-operation profile has no result.

The claim binding follows.

<!-- participant-crossing-claim:start -->
```json
{
  "assurance_axis": "model-check",
  "assurance_status": "model-checked",
  "evidence_boundary": "Only the complete reachable carrier of participant-crossing-dpbb-finite-v1@rev2.",
  "evidence_refs": [
    "sha256:5891bbc5b3da53c7345f383da7f935ee9f8f0e4dd56b50c6edc132bbbd33964b",
    "sha256:8d8ca9681c2893abf048a0988aa5efc76c22e1fe148c4c75be78780e9be09b39",
    "sha256:40fbc2a4cce132b4214741d25fed3345bf79c5ab02048711010eba5511d6d2e6"
  ],
  "evidence_scope": "model-check",
  "explicit_non_claims": [
    "unbounded-proof",
    "proof-certificate",
    "independent-reproduction",
    "runtime-realization",
    "backend-conformance",
    "noninterference",
    "opacity",
    "other-profiles-carriers-orders-times-probabilities-concurrency-controllers-policy-cuts-backends"
  ],
  "left_carrier_ref": "sem-230-participant-crossing-abstract",
  "limitations": [
    "One fresh operation with retries, sequential total order, untimed and nonprobabilistic.",
    "Singleton participant, audience, controller, episode and request; exact policy cuts p0 and p1.",
    "Native finite decision with no positive certificate or checked relation witness."
  ],
  "observation_projection_ref": "participant-crossing-projection",
  "observation_projection_revision": "rev1",
  "quantifier_scope": "all-admitted-inputs",
  "relation_id": "divergence-preserving-branching-bisimulation",
  "relation_parameter_profile_ref": "participant-crossing-dpbb-finite-v1",
  "relation_parameter_profile_revision": "rev2",
  "right_carrier_ref": "api-423-run-319-crossing-kernel",
  "subject": "Declared initial states of the complete single-operation rev2 finite carrier",
  "taxonomy_id": "raes-behavioral-relations",
  "taxonomy_revision": "rev8"
}
```
<!-- participant-crossing-claim:end -->

The [machine-check specification](https://github.com/OpenRAE/rae/blob/dev/specs/formal/participant-semantics/participant-crossing-machine-check.md)
gives the complete boundary.

## Treat adversarial participants as a boundary problem

Issue #812 and ADR-101
define a DRAFT participant-neutral design for intentionally subverting
participants and untrusted content.

The design keeps two coordinates separate:

- confidentiality restricts audiences, destinations, and sink classes; and
- integrity records the origins that may have influenced a value and the trust
  a sink requires.

Labels and provenance follow observations, tool results, and retained memory.
They also follow proposals, action arguments, handoffs, crossings, outputs, and errors.
Authentication, approval, action admission, authorization, declassification,
integrity endorsement, editing, and execution remain distinct.

The reference enforcement point is immediately before `RuntimeTarget` performs
an external effect or before participant-facing or external data is
serialized or delivered. A monitor score is evidence or advice, never
authorization. Missing labels, provenance, profile support, or a stable state
cut fail closed.

The companion evaluation profile distinguishes honest and attack modes
and makes objectives, policy/monitor knowledge, adaptation, collusion, audit
budgets, monitor correlation, interventions, memory, safety, usefulness, cost,
uncertainty, and limitations explicit.

RAE now has a backend-neutral harness for seven finite cases.
It exercises an honest baseline, permitted injection, a correlation negative control,
exfiltration denial, adaptive denial with replay, handoff denial, and apparatus invalidation.
A permitted attack can succeed without violating the selected policy.
Apparatus invalidation is not a successful safety observation.

The [evaluation evidence guide](https://github.com/OpenRAE/rae/blob/dev/docs/explain/reference/adversarial-control-evaluation.md)
records exact source and configuration bindings, separate measures, reproduction, and unsupported conditions.
RAE evaluation does not require a concrete backend implementation.
Concrete backend claims still require their own exact realization evidence.
These finite results establish no universal robustness, monitor honesty, model alignment,
private-reasoning safety, opacity, bisimulation, or undeclared-channel control.

## Finite owner-qualified information flow profiles

The governed `participant-owner-flow-policy-v1@rev1` profile preserves two
independent owners' confidentiality and integrity clauses. Each owner can release
only its own obligations through independently resolved authority. Combined
information retains both owners' restrictions and its source provenance.

Before use, an operator must admit the exact profile.
That admission must cover the supported implementation, coverage, and guarantees. Unsupported owner distinctions are rejected; losing
an admitted guarantee blocks the affected operation. The original security
profile keeps its existing meaning. Selecting a profile does not install a provider.
It does not establish that an external release operation occurred.

## Reference and next task

Read the [crossing contract](https://github.com/OpenRAE/rae/blob/main/contracts/schemas/participant-runtime/participant-crossing-occurrence-v1.json)
for exact data fields. Use the [control-plane guide](guides/control-plane.md)
to configure the administrative host boundary.
