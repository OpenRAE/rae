# Control participant input and output

Select a task that sets what may cross a participant boundary and retains the right evidence.
These routes describe RAES 11.0.2. Each route needs the exact compiled policy and installed owners.
A manifest declaration alone does not install enforcement.

## Before you start

Keep world state, governed participant views, participant-visible history, and protected evidence separate.
Use only the caller identity and scope admitted by your host.
Never expose a P2 token, raw snapshot, or store to a participant.
Read the [participant crossing specification](https://github.com/OpenRAE/rae/blob/main/specs/formal/participant-semantics/information-flow-control.md)
before changing policy. It retains normative authority.

## Choose the route for your role


### Scenario author

Outcome: a validated declaration with explicit participant, control, and disclosure intent.
Use [SDL validation](sdl/validate-compile-plan.md) after editing the source.
This changes the authored file only; it does not dispatch a runtime action.

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
- Use an `episode_policy` on the behavior specification to declare how a
  participant's episodes start, take turns, end, and reset. Each end condition
  names one terminal reason and its evidence. The policy declares intent only.
  It does not start, reset, or end an episode.
  Read the [episode structure guide](https://github.com/OpenRAE/rae/blob/dev/docs/explain/sdl/participant-episode-structure.md) for the authoring and runtime boundaries.
- Do not infer a participant addressee from an environment inject. Do not put
  policy text, hidden answers, credentials, or raw evidence in a participant
  carrier.

The
[mixed-control fixture](https://github.com/OpenRAE/rae/blob/main/contracts/fixtures/sdl/mixed-control-v1/valid/mixed-control-participant.yaml),
[participant-directed inject fixture](https://github.com/OpenRAE/rae/blob/main/contracts/fixtures/sdl/participant-inject-delivery-v1/valid/participant-directed.yaml),
and
[episode policy fixture](https://github.com/OpenRAE/rae/blob/main/contracts/fixtures/sdl/participant-episode-policy-v1/valid/analyst-shift-episode.yaml)
show the governed authoring shapes. They show SDL checks. They do not show
runtime delivery or episode execution.

### Participant-implementation author

Outcome: your implementation consumes only the carrier admitted for its participant and audience.
Keep its participant, episode, projection revision, and order coordinates.
If delivery or observation evidence is absent, retain that uncertainty.

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

Outcome: the installed mediator authorizes a crossing at the exact state cut before release or dispatch.
This task changes runtime state and can release data or authorize native effects.
Use the [private control-plane setup](guides/control-plane.md#before-you-start) and its original runtime owner.

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
own gate.

Only the API-407 policy path can allow a downgrade. Record its real
strength. Record its limits, release, and source. Missing support is not a
downgrade.

Legacy API-408 status, context, and history retrieval remains available when
no crossing resolver is set. That legacy mode is not governed egress. With a
resolver, the HTTP adapter binds the audience before lookup. It resolves
trusted evidence. It commits crossing facts before it writes the view.
If the final flow-sink check refuses release, retrieval returns no view and
the same atomic write records a failed operation and denied audit.

Earlier crossing decisions remain in history as evidence of work performed; they do
not mean the view was delivered. Retrying the same request returns the denied
outcome, including after the local store is reopened.

Use the
[participant-control migration guide](https://github.com/OpenRAE/rae/blob/dev/docs/migration/participant-information-flow-control.md)
for legacy, opt-in, required, rollout, and rollback steps. After the first
governed write, keep a resolver-aware reader. Keep the crossing history,
operation, idempotency, and audit write set. Never delete crossing facts. Do
not rebuild them from policy, time stamps, logs, or empty defaults.

### Build a backend

Outcome: a finite support report for the exact installed target and profile.
Use [fixture checking](backends.md#run-the-portable-fixture-check) before live qualification.
Live target probes need resource permissions, readback, and verified native cleanup.

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

Outcome: an explicitly bounded claim with the correct relation and evidence.
Use [the relation catalogue](participant-control-explanation.md#select-a-behavioral-claim) before recording a claim.

Name the question first. Then select a relation. Record the subject and
carriers. Record the direction and projection revision.

Name all quantifiers.
State the scheduler, setting, and order assumptions. State the evidence bound,
status, limits, and nonclaims.

Finite examples can find faults in their stated bounds. So can conformance
probes. They do not prove a broad property. Keep each failed case as a
counterexample. Do not average it away. Do not give a finite report a stronger
relation.

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

## Select a behavioral claim

For the seven existing finite examples, retain the following claim without strengthening its relation or quantifiers.
The [crossing examples](participant-control-explanation.md#read-the-crossing-examples)
explain what each case establishes. This is a bounded evidence example, not a live-backend certificate.

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

The existing documentation test validates this JSON through `BehavioralClaimBindingModel` and the canonical relation catalogue.
A stronger claim needs its own governed binding and supporting evidence.

## Finish

Keep the crossing decision, release, delivery, observation, and cleanup outcomes separately.
A permitted crossing does not prove a native effect or participant observation.
For uncertain effects, preserve reservations and use the original runtime's reconciliation path.
Use the backend owner's verified cleanup procedure before resource reuse.

Native enforcement remains unverified without the exact backend release, installed resolver, authorized crossing, readback, and cleanup evidence.
Read the [runtime API reference](api/runtime.rst) and [participant-control explanation](participant-control-explanation.md).

## Keep four planes separate

Read [keep four planes separate](participant-control-explanation.md#keep-four-planes-separate) in the explanation.

## Mixed simulation and emulation semantics

Read [mixed simulation and emulation semantics](participant-control-explanation.md#mixed-simulation-and-emulation-semantics) in the explanation.

## Read the crossing examples

Read [read the crossing examples](participant-control-explanation.md#read-the-crossing-examples) in the explanation.

### Denial

Read [denial](participant-control-explanation.md#denial).

### Withholding

Read [withholding](participant-control-explanation.md#withholding).

### Redaction

Read [redaction](participant-control-explanation.md#redaction).

### Governed declassification

Read [governed declassification](participant-control-explanation.md#governed-declassification).

### Intervention and transformation

Read [intervention and transformation](participant-control-explanation.md#intervention-and-transformation).

### Participant-directed inject delivery

Read [participant-directed inject delivery](participant-control-explanation.md#participant-directed-inject-delivery).

### Unsupported capability

Read [unsupported capability](participant-control-explanation.md#unsupported-capability).

## Read the finite participant-crossing result

Read [read the finite participant-crossing result](participant-control-explanation.md#read-the-finite-participant-crossing-result) in the explanation.

## Treat adversarial participants as a boundary problem

Read [treat adversarial participants as a boundary problem](participant-control-explanation.md#treat-adversarial-participants-as-a-boundary-problem) in the explanation.

## Finite owner-qualified information flow profiles

Read [finite owner-qualified information flow profiles](participant-control-explanation.md#finite-owner-qualified-information-flow-profiles) in the explanation.

```{toctree}
:hidden:

participant-control-explanation
```
