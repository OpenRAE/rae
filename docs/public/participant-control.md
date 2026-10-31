# Control participant input and output

For task/effect attainment independent of evaluation and reward, see
[participant-local outcome reporting](https://github.com/OpenRAE/rae/blob/dev/docs/explain/reference/participant-local-outcomes.md).

Use participant control to set three things. Set what may cross a participant
boundary. Set who may direct the participant. Set what proof a run retains.
This guide explains the shipped RAES model. It serves five reader roles. It
does not define participant-control semantics.

Read
[ADR-085](https://github.com/OpenRAE/rae/blob/main/docs/decisions/adrs/adr-085-participant-information-flow-and-control.md),
[ADR-095](https://github.com/OpenRAE/rae/blob/main/docs/decisions/adrs/adr-095-participant-decision-epoch-state-cut-and-delivery-semantics.md),
[SEM-230 information-flow specification](https://github.com/OpenRAE/rae/blob/main/specs/formal/participant-semantics/information-flow-control.md),
and the
[API-423 crossing schema](https://github.com/OpenRAE/rae/blob/main/contracts/schemas/participant-runtime/participant-crossing-occurrence-v1.json).
They own the rules. Follow them if this guide seems to differ.

## Keep four planes separate

For backend authors, the
[modular provider contract reference](https://github.com/OpenRAE/rae/blob/dev/docs/explain/reference/modular-participant-control-contracts.md)
describes closed profile selections, typed results and requested effects, and
how the reference runtime orchestrates them. Publishing these contracts does
not install a provider or execute its requests. The runtime invokes only
providers an operator constructed and bound to the admitted selection. It
commits the composed decision before any backend effect or delivery. It
dispatches an admitted effect only through the RAES operation that already owns
it. An effect acts for the principal whose operation admitted it, never for the
caller that later requests its dispatch.

API-424 now also publishes v2 selection/evaluation contracts and
`ParticipantControlProviderV2` for per-crossing applicability and typed
dependency inputs. Those contracts keep the complete admitted apparatus
separate from the slots applicable at one state cut, require profile-owned
coverage and explicit input support, and separate parent decisions from
effect prerequisites. They require exact protocol/schema negotiation and a
trusted operator resolver. The reference runtime can explicitly admit a v2
binding and evaluate its applicable slots in dependency order. Required inputs
and support must be satisfied; optional failure is recorded without blocking
an otherwise permitted crossing. Scoped state and the evaluation join the
existing atomic crossing commit. Retained v1 records keep their original
interpretation. V2 admits only effects with an installed, exactly bound owner.
Its drain supports fresh world injects, compiled handoffs and evidenced
cancellation of execution attempts. Parent denial applies before execution;
independent consequences need their own authority. Evaluation eligibility
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

The crossing history keeps each API-423 stage apart. The stages are request,
decision, change, release, delivery attempt, delivery, observation, and audit.
Each stage refers to an existing carrier. It does not copy the carrier payload
into a generic participant message.

## Mixed simulation and emulation semantics

Issue #813 and ADR-102 define the design boundary for using the same
participant-control intent in:

- simulation or emulation/operation as alternative realizations; and
- simulation and emulation/operation together in one admitted trial.

Issue #1013 publishes SEM-234's revisioned semantic definition and finite admission examples.
The installed runtime now executes simultaneous mixed arrangements and staged handoffs.
The [mixed-control demonstration](https://github.com/OpenRAE/rae/blob/dev/docs/explain/reference/mixed-control-demonstration.md)
checks these paths with controlled test providers.
It establishes no native backend qualification or simulation-to-operation transfer.
The broader ASR-537 research requirement remains DRAFT.

Portable SDL stays backend-neutral. Admitted trial intent allocates
stable participant-runtime, controlled-scope, action-family,
observation-source, and crossing refs to exact apparatus components. Every
component edge must state its adapter, authority, action/observation mapping,
participant/audience policy, clock/order mapping, support strength, loss,
failure behavior, and evidence.

These are admitted apparatus obligations. They do not require authors to
specify internal installation recipes. Open materialization scopes retain
their delegated choices, exact constraints stay binding, and abstract models
can be complete. Reporting, experimental collection, retention and export are
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

An inter-trial realization change creates a new linked plan entry and run. A
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

## Choose the route for your role

### Scenario author

Start with the participant and behavior specification. Then select an
observation boundary. Reuse the action, control, or inject carrier.

- Use an explicit `mixed-control` behavior declaration when control can move
  between the participant and another controller. Declare controller states.
  Declare authority, scope, moves, and proof. Keep approval and intervention
  apart. Keep handoff, override, and cancellation apart. Action admission,
  execution, and observation also stay apart.
- Use `participant_inject_deliveries` when an existing orchestration inject is
  addressed to a participant. Retain its inject identity. Retain its
  event/script/story identity. Bind an observation boundary. Name each needed
  delivery, order, evidence, or control reference. A temporal constraint bound
  to the delivery compiles to that delivery's `participant.*` address; it
  constrains the authored occurrence and does not prove dispatch, delivery, or
  observation.
- Do not infer a participant addressee from an environment inject. Do not put
  policy text, hidden answers, credentials, or raw evidence in a participant
  carrier.

The
[mixed-control fixture](https://github.com/OpenRAE/rae/blob/main/contracts/fixtures/sdl/mixed-control-v1/valid/mixed-control-participant.yaml)
and
[participant-directed inject fixture](https://github.com/OpenRAE/rae/blob/main/contracts/fixtures/sdl/participant-inject-delivery-v1/valid/participant-directed.yaml)
show the governed authoring shapes. They show SDL checks. They do not show
runtime delivery.

### Participant-implementation author

Consume only the carrier sent through the participant interface. It may be an
admitted action or control input. It may be a projected status, context,
history, observation, or inject view. Keep its source ID. Keep its exposed
order data.

Do not request or consume administrative `participant_crossing_history`,
hidden policy inputs, or operator audit records. Do not consume another
participant's view or raw world state. The participant-facing carrier is the
data plane. API-423 crossing facts form the assurance plane.

Treat these outcomes independently:

1. accepted by a parser or contract model;
2. authorized at the exact participant policy state cut;
3. admitted by the owning action or control semantics;
4. supported by the selected backend;
5. dispatched, delivered, or observed; and
6. retained as evidence.

A missing delivery record is not success. A missing observation record is not
success. Neither one proves a policy denial. Check the allowed operation and
evidence surfaces.

### Runtime operator

Select participant control by backend profile and feature strength. Governed
operation requires:

- a trusted participant crossing policy resolver;
- authenticated caller and exact runtime-target binding;
- a participant/controller binding for ingress or one participant/audience
  binding for egress;
- exact policy-decision and state-cut evidence;
- the applicable API-407 feature, strength, required contracts, limitations,
  and evidence;
- a compatible append-only store; and
- the shared RUN-319 crossing mediator.

Missing policy meaning fails closed. So does a missing identity or evidence.
Missing contracts or backend support also fail closed. Each check fails at its
own gate. Only the API-407 policy path can allow a downgrade. Record its real
strength. Record its limits, release, and source. Missing support is not a
downgrade.

Legacy API-408 status, context, and history retrieval remains available when
no crossing resolver is set. That legacy mode is not governed egress. With a
resolver, the HTTP adapter binds the audience before lookup. It resolves
trusted evidence. It commits crossing facts before it writes the view.
If the final flow-sink check refuses release, retrieval returns no view and
the same atomic write records a failed operation and denied audit. Earlier
crossing decisions remain in history as evidence of work performed; they do
not mean the view was delivered. Retrying the same request returns the denied
outcome, including after the local store is reopened.

Use the
[participant-control migration guide](https://github.com/OpenRAE/rae/blob/dev/docs/migration/participant-information-flow-control.md)
for legacy, opt-in, required, rollout, and rollback steps. After the first
governed write, keep a resolver-aware reader. Keep the crossing history,
operation, idempotency, and audit write set. Never delete crossing facts. Do
not rebuild them from policy, time stamps, logs, or empty defaults.

### Build a backend

Declare each participant-policy feature on its own. Use the API-407 backend
manifest. A positive entry needs an exact support strength. It also needs the
required contracts, limits, release, and proof. A method or valid schema does
not show runtime support.

Run the participant-policy conformance harness only against behavior the
target may test. Keep the target and profile in the report. Keep the probe-set
digest and case IDs. Keep the finite scope, errors, and real support. A feature
without an allowed probe result is `unsupported`. It is not conformant.

The stub test double declares all six participant-policy features
`unsupported`. Some tests use stronger manifests. Those tests do not make the
stub a native implementation. RAES ships no concrete backend. Start with the
[backend guide](backends.md). Then read the
[feature-admission implementation](https://github.com/OpenRAE/rae/blob/main/implementations/python/packages/raes_backend_protocols/participant_feature_admission.py),
and
[finite participant-policy probes](https://github.com/OpenRAE/rae/blob/dev/implementations/python/packages/raes_conformance/conformance/participant_policy_probes.py).

### Researcher

Name the question first. Then select a relation. Record the subject and
carriers. Record the direction and projection revision. Name all quantifiers.
State the scheduler, setting, and order assumptions. State the evidence bound,
status, limits, and nonclaims.

Finite examples can find faults in their stated bounds. So can conformance
probes. They do not prove a broad property. Keep each failed case as a
counterexample. Do not average it away. Do not give a finite report a stronger
relation.

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
| Do two finite crossing models match in both directions with explicit hidden steps and divergence? | `divergence-preserving-branching-bisimulation` | Closed relation-parameter profile, complete finite carrier, both initial states, projection, hidden-label set, tool provenance, mutations, and a separately reviewed reproduction |

Two equal sampled histories support a bounded comparison. They do not show
participant-policy noninterference. A successful trace sample does not show
trace inclusion. A matching finite example does not show simulation or
refinement. It also does not show strong or weak bisimulation. The finite
participant-opacity model check covers only its exact digest-bound model and
profile; it does not establish runtime enforcement, backend realization, or an
unbounded theorem.

The following existing claim-binding contract reports only the seven named
examples in this guide:

<!-- participant-control-claim:start -->
```json
{
  "taxonomy_id": "raes-behavioral-relations",
  "taxonomy_revision": "rev8",
  "relation_id": "bounded-probe-success",
  "subject": "Seven named participant-policy examples for one declared target and profile",
  "left_carrier_ref": "backend-conformance-report:participant-policy-example",
  "right_carrier_ref": null,
  "observation_projection_ref": "participant-policy-probe-projection",
  "observation_projection_revision": "rev1",
  "quantifier_scope": "finite-cases",
  "evidence_scope": "finite",
  "evidence_boundary": "Only denial, withholding, redaction, governed declassification, transformation, participant-directed inject delivery, and unsupported-capability cases named by this guide for the disclosed target and profile",
  "assurance_status": "tested",
  "evidence_refs": [
    "implementations/python/tests/test_asr_535_participant_flow_assurance.py"
  ],
  "limitations": [
    "The stub test double declares all participant-policy features unsupported; positive paths use explicit test manifests."
  ],
  "explicit_non_claims": [
    "Does not establish universal participant-policy noninterference or participant-projected history equivalence.",
    "Does not establish trace inclusion, simulation, refinement, strong or weak bisimulation, native-backend realization, model checking, or proof."
  ]
}
```
<!-- participant-control-claim:end -->

The public documentation test loads this JSON through
`BehavioralClaimBindingModel` and resolves its relation against the canonical
catalog. A stronger claim needs the full governed binding. It also needs the
right proof. A prose change is not enough.

## Read the finite participant-crossing result

RAES has one reproduced finite result for the
`divergence-preserving-branching-bisimulation` relation.
The result compares two formal models of one participant crossing.
The abstract model follows SEM-230.
The concrete model follows the API-423 and RUN-319 crossing kernel.
Separate transition authorities construct the two models.
Both models are complete for profile `participant-crossing-dpbb-finite-v1@rev2`.
The profile has one participant, audience, controller, episode, and request.
It has the exact policy cuts `p0` and `p1`.
Projection `participant-crossing-projection@rev1` hides only five mediation classes.
Denial, unsupported outcomes, delivery, observation, replay rejection, and cut advance stay visible.
Deadlock, termination, and divergence stay explicit.

The pinned mCRL2 `202607.0` `dpbranching-bisim` decision relates the declared initial states.
Every mandatory mutation fails the relation.
A fresh isolated run in the qualified CI environment reproduced every result byte.
A separate implementation-agent reviewer accepted that reproduction.
No human review is claimed.
Both records are unsigned.

This is a finite model-check result.
It is not an unbounded proof, a proof certificate, or a checked relation witness.
It does not establish live-runtime realization or backend conformance.
It does not establish policy noninterference or predicate opacity.
It makes no timed, probabilistic, concurrent, fair, partial-order, handoff, or multi-operation claim.
The separate multi-operation profile has no result.

The original claim binding follows.
It keeps its `independent-reproduction` nonclaim, because the claim predates the review.

<!-- participant-crossing-claim:start -->
```json
{
  "assurance_axis": "model-check",
  "assurance_status": "model-checked",
  "evidence_boundary": "Only the complete reachable carrier of participant-crossing-dpbb-finite-v1@rev2.",
  "evidence_refs": [
    "sha256:5891bbc5b3da53c7345f383da7f935ee9f8f0e4dd56b50c6edc132bbbd33964b",
    "sha256:8d8ca9681c2893abf048a0988aa5efc76c22e1fe148c4c75be78780e9be09b39",
    "sha256:8cfd29f2e46e18f145dc56981cb62232ad13c1a1708efd4c1c3549300091e525"
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

The publication facts follow.
A repository test compares each value with the admitted machine-check and reproduction records.

<!-- participant-crossing-evidence:start -->
```json
{
  "schema": "participant-crossing-publication/v1",
  "relation": "divergence-preserving-branching-bisimulation",
  "taxonomy": "raes-behavioral-relations@rev8",
  "profile": "participant-crossing-dpbb-finite-v1@rev2",
  "profile_digest": "sha256:4439d8ece4d8977f2d991b9ef6b5a73a98951ace513adf80ea4496923985dbb4",
  "projection": "participant-crossing-projection@rev1",
  "complete_reachable_fixed_point": true,
  "equivalent": true,
  "domain_counts": {
    "audience": 1,
    "controller": 1,
    "decision": 6,
    "delivery": 4,
    "episode": 1,
    "history_head": 4,
    "input_class": 5,
    "participant": 1,
    "policy_cut": 2,
    "replay": 3,
    "request_id": 1
  },
  "models": {
    "abstract": {
      "model_id": "sem-230-participant-crossing-abstract",
      "model_revision": "rev2",
      "initial": 0,
      "states": 88,
      "semantic_transitions": 107,
      "aut_transitions": 107,
      "input_digest": "sha256:5891bbc5b3da53c7345f383da7f935ee9f8f0e4dd56b50c6edc132bbbd33964b",
      "sidecar_digest": "sha256:8a5804e83b674b2099206b113101e2a45e60d7f08996af099dfe685e494173e3"
    },
    "concrete": {
      "model_id": "api-423-run-319-crossing-kernel",
      "model_revision": "rev2",
      "initial": 0,
      "states": 178,
      "semantic_transitions": 197,
      "aut_transitions": 197,
      "input_digest": "sha256:8d8ca9681c2893abf048a0988aa5efc76c22e1fe148c4c75be78780e9be09b39",
      "sidecar_digest": "sha256:108384d53dadb8aff695d9591c6fa8908af753bee14d56ed37d4c5c382203691"
    }
  },
  "tool": {
    "artifact_id": "mcrl2",
    "version": "202607.0",
    "archive_sha256": "00cb4c347638b3a418fb67c9d67b8d2bf2245e10d4affa4cd993b1c357bde969",
    "executable_sha256": "b34a7ba73939222886fe6e35c2a1009fd78056369fa06d0b3c48ebfe87ec4d21",
    "installed_tree_sha256": "c0d7d21471aff63c991d53a8c9bea8a16218ecb5ab583271396e8587c2655590"
  },
  "verification": {
    "mode": "dpbranching-bisim",
    "tau": [
      "internal"
    ],
    "ordered_inputs": [
      "abstract.aut",
      "concrete.aut"
    ]
  },
  "mutation_cases": {
    "hidden-denial": false,
    "hidden-divergence": false,
    "hidden-observation": false,
    "later-cut-replay": false,
    "removed-delivery": false
  },
  "machine_check": {
    "manifest_digest": "sha256:3240d46536489d8468d9a8c3dd8f23f2be3b92d40c02b81a4d60228aef8d3110",
    "result_digest": "sha256:5b42b0f114c33842d3c9ae950c99a5783f5b950b0654913cf602e97b050fea7f",
    "claim_digest": "sha256:578d67009eef8791e98c859024124c6a72b14cd73d245a93eed2e6f02f82ae54",
    "corpus_manifest_digest": "sha256:5de4ae658bfe8265b83cf72eb46bf9cf72f3a69f69263da78f756c16e8285f8b",
    "mutation_review_subject_digest": "sha256:92803733e9aa6afc765af5e8f9d5b33c98c5824dbf62afd0b86a24a79ec29e95",
    "authenticity": "unsigned",
    "claim_non_claims": [
      "unbounded-proof",
      "proof-certificate",
      "independent-reproduction",
      "runtime-realization",
      "backend-conformance",
      "noninterference",
      "opacity",
      "other-profiles-carriers-orders-times-probabilities-concurrency-controllers-policy-cuts-backends"
    ],
    "limitations": [
      "One fresh operation with retries, sequential total order, untimed and nonprobabilistic.",
      "Singleton participant, audience, controller, episode and request; exact policy cuts p0 and p1.",
      "Native finite decision with no positive certificate or checked relation witness."
    ]
  },
  "reproduction": {
    "manifest_digest": "sha256:35bef4e0fdbea4ea57fbde9166c9f2d2e5d9171a86a6bc9c2a28aa040d183cf0",
    "measurement_digest": "sha256:cb71cb45b064ec3fca09b2407a36d5358bf73e3933b3bc6c993df7448a0a4f5f",
    "execution_digest": "sha256:093be5249d8b40de3779202785525d42a71503e6204e72c1554abea303f153d9",
    "review_digest": "sha256:0571524c26b72c620a3f63c64fc1017306c8a052acc76d9091a09e0ef0185768",
    "decision": "accepted-bounded-reproduction",
    "reviewer_role": "implementation-agent",
    "producer_ref": "https://github.com/OpenRAE/rae/issues/976#issuecomment-6544932861",
    "reviewer_ref": "https://github.com/OpenRAE/rae/issues/976#issuecomment-6547519444",
    "acceptance_record_ref": "https://github.com/OpenRAE/rae/issues/976#issuecomment-6547521916",
    "qualified_run": "https://github.com/OpenRAE/rae/actions/runs/41229565420",
    "qualified_artifact_digest": "sha256:551f763ca1ed1c7dd7a31187368ccea713ceb585787134756253b12f9d238df8",
    "source_revision": "71e2a1389349c0a2a5ac9775fd710631af60652a",
    "authenticity": "unsigned",
    "nonclaims": [
      "runtime-realization",
      "backend-conformance",
      "noninterference",
      "opacity",
      "unbounded-proof",
      "wider-profile"
    ]
  }
}
```
<!-- participant-crossing-evidence:end -->

The [machine-check specification](https://github.com/OpenRAE/rae/blob/dev/specs/formal/participant-semantics/participant-crossing-machine-check.md)
and the [reproduction specification](https://github.com/OpenRAE/rae/blob/dev/specs/formal/participant-semantics/participant-crossing-reproduction.md)
give the complete boundary.

## Diagnose failures without leaking data

Keep expected failures on the existing safe surfaces. These include
diagnostic, operation, and HTTP results. An HTTP authorization failure is a
generic `403 forbidden`. An ambiguity or state conflict uses a bounded `409`
detail. An unexpected fault stays `{"detail":"internal server error"}`.

Do not expose rejected payloads or policy bodies. Do not expose hidden state
or participant existence. Keep credentials and bearer tokens out. Keep
backend objects, exception strings, and tracebacks out. The same rule covers
environment values, host paths, and raw proof. Do not place these values in
responses, logs, fixtures, screenshots, or docs.

For current delivery status, evidence, and known limits, use the
[participant-control adoption index](https://github.com/OpenRAE/rae/tree/main/docs/research/participant-io-control)
and [current project limitations](limitations.md).

## Treat adversarial participants as a boundary problem

Issue #812 and ADR-101
define a DRAFT participant-neutral design for intentionally subverting
participants and untrusted content.

The design keeps two coordinates separate:

- confidentiality restricts audiences, destinations, and sink classes; and
- integrity records the origins that may have influenced a value and the trust
  a sink requires.

Labels and provenance follow observations, tool results, retained memory,
proposals, action arguments, handoffs, crossings, outputs, and errors.
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

An operator must admit the exact profile and supported implementation, coverage
and guarantees before use. Unsupported owner distinctions are rejected; losing
an admitted guarantee blocks the affected operation. The original security
profile keeps its existing meaning. Selecting a profile does not install a
provider or establish that an external release operation has occurred.
