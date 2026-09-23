# SEM-233 And ASR-536 Adversarial Participant Flow Control

Issue #1354 and ADR-114 publish [IFC profile variability and publication](ifc-profile-variability.md).
The amendment separates authored requirements, exact profile expressibility
and evidenced realization, preserving this document's original revision and
implementation boundary. It adds no registered owner-aware profile or runtime
support; its migration contract governs future adoption.

Status: SEM-233 definition and portable-contract authority are published;
runtime, backend, and ASR-536 evaluation obligations remain DRAFT.

Requirements: `SEM-233`, `ASR-536`.

SEM-233 authority revision: `sem-233/rev1`.

Flow-policy profile: `participant-boundary-flow-policy-v1@rev1`.

Portable contracts: `participant-boundary-flow-policy-v1` and
`participant-flow-control-relation-v1`.

Decision authority:
[ADR-101](../../../docs/decisions/adrs/adr-101-adversarial-participant-flow-control.md).

## Scope

This specification adds two revisioned profiles over the existing SEM-230,
ACT-617, API-409, API-423, RUN-310, RUN-319, API-407, experiment, and ASR-535
carriers:

1. `participant-boundary-flow-policy-v1@rev1`, which defines independent
   confidentiality and integrity coordinates, conservative explicit-flow
   derivation, release operations, and final-sink decisions; and
2. `intentional-subversion-control-evaluation-v1@rev1`, which defines the
   experimental variables and evidence boundary for honest and intentionally
   subverting participant policies.

The profiles apply to human, scripted, reinforcement-learning,
large-language-model, and external-service participants. They do not expose or
govern chain-of-thought, private model state, credentials, or undeclared
internal apparatus flows.

## State and identities

For participant `p`, episode `e`, memory scope `m`, exact state cut `c`,
flow-policy profile `phi`, source or derived value `x`, and sink `s`, the
governed state reuses:

- the SEM-230 participant/audience projection, policy decision, memory,
  adaptive-strategy, release, order, and provenance coordinates;
- ACT-617 controller and authority state;
- API-409 control occurrences;
- API-423 crossing request, decision, transformation, delivery, observation,
  and audit occurrences;
- runtime-fact source, derivation, audience, scope, freshness, and sink
  declarations;
- participant proposal, action-admission, attempt, result, and output facts;
- the RUN-310/RUN-319 append-only histories and exact expected heads;
- API-407 declared and effective capability support; and
- experiment task, protocol, study, run, apparatus, evidence, measure, and
  traceability records.

Every derived identity is fresh and binds the source identities, derivation
kind, profile and revision, exact policy/state cut, authority, destination or
sink, and safe evidence refs. No release operation mutates a prior fact.

## Exact Revision-1 Flow Algebra

For revision 1, profile `phi` declares two independent, closed, finite
universes:

```text
C_phi = confidentiality-obligation tokens admitted by phi
I_phi = integrity-obligation tokens admitted by phi
```

A confidentiality token is one revisioned policy clause, such as an
owner-relative audience, destination, or sink restriction. An integrity token
is one unresolved possible-influence obligation. The source-label resolver
maps a possible writer or influence to the applicable integrity tokens; the
immutable influence refs remain in provenance even if a later endorsement
discharges an obligation. Tokens are stable typed refs, not raw values or open
metadata keys.

The effective label domain is the product powerset:

```text
Label_phi(x,c) = (Conf_phi(x,c), Int_phi(x,c))
Conf_phi(x,c) in P(C_phi)
Int_phi(x,c)  in P(I_phi)
```

Normalization validates every token against the named profile revision,
removes duplicates, and orders the canonical serialization lexically. An
unknown token, unresolved profile/revision, or cross-profile comparison is
unsupported; it is never silently discarded or coerced.

For labels `l1 = (C1, I1)` and `l2 = (C2, I2)`, revision 1 defines:

```text
l1 <=_phi l2   iff C1 subset-of C2 and I1 subset-of I2
l1 join_phi l2 = (C1 union C2, I1 union I2)
bottom_phi      = (empty-set, empty-set)
top_phi         = (C_phi, I_phi)
```

Upward means at least as restrictive: more confidentiality clauses must be
satisfied and more possible-influence obligations must be admitted or
explicitly endorsed. Owner-relative clauses make labels for mutually
distrustful principals or audiences incomparable when neither obligation set
contains the other. Neither coordinate is a global classification or trust
ladder.

The join is closed, associative, commutative, idempotent, and monotone in each
argument. Its componentwise union makes it independent of traversal order.
Adding a possible input cannot remove an obligation, and a successful decision
for `l2` cannot imply success for a strictly more restrictive label unless the
sink satisfies the added obligations.

For sink policy `S` at the exact cut, let `SatC_phi(S)` and `SatI_phi(S)` be the
closed sets of confidentiality and integrity obligations that its resolved
audience, destination, sink class, and release authorities satisfy:

```text
ConfidentialityObligationsSatisfied_phi(l,S) iff Conf_phi(l) subset-of SatC_phi(S)
IntegrityObligationsSatisfied_phi(l,S)       iff Int_phi(l)  subset-of SatI_phi(S)
```

The predicates are independent. A sink may satisfy one and fail the other.
Authentication, signatures, hashes, markings, sensitivity, confidence, roles,
and monitor scores may contribute evidence to a revisioned resolver, but none
is a label coordinate or satisfies both predicates.

### Source defaults

`SourceLabel_phi(src,c)` resolves through the revisioned source authority. A
known source returns a normalized member of `P(C_phi) x P(I_phi)`. When the
source, profile, revision, label, or authority cannot be resolved, the result
is either typed `unsupported` or the deny-equivalent `top_phi` accompanied by
an unresolved status. A sink decision rejects unresolved status even if its
ordinary obligation sets would otherwise cover `top_phi`. Empty input is not
evidence for `bottom_phi`, public, or trusted.

### Conservative composition

For a derivation `d` whose complete possible-input set is `Inputs(d)`:

```text
Conf_phi(d,c) = union { Conf_phi(x,c) | x in Inputs(d) }
Int_phi(d,c)  = union { Int_phi(x,c)  | x in Inputs(d) }
```

`Inputs(d)` includes participant context, retained memory, shared/joint state,
tool and destination arguments, error branches, and each participant, tool,
service, transformation, monitor, or apparatus source that may influence the
result. An opaque model, script, summary, copy, redaction, edit, parse, or
transformation retains all inputs. A typed transformation may exclude an
influence only through a closed, revisioned non-influence relation and safe
evidence; omission from caller-supplied provenance is not such evidence.

### Cross-participant and cross-episode carriage

API-409 handoff, API-423 crossing, controller change, participant change,
shared state, joint state, or episode reset never clears labels, unresolved
status, provenance, influence refs, or release history. A receiving
participant inherits the effective upstream state through the governed
crossing.

Cross-episode replay binds the original source, profile, revision, policy
decisions, release events, SEM-230 memory scope, and expected history heads.
Replay under a later cut receives a fresh final-sink decision; the later policy
does not reinterpret the historical label or release.

## Typed Carrier And Derivation Mapping

The mapping is semantic and reference-based. Issue #1001 does not change the
incumbent contracts.

| Flow stage | Existing typed owner | Required SEM-233 refs and possible inputs |
| --- | --- | --- |
| observation, retrieval, tool result, runtime fact | participant observation envelope and runtime-fact declaration/version/binding/sink models | source-label decision, profile/revision, source/provenance refs, and every source or apparatus that may affect the value; sensitivity is resolver evidence only |
| participant context, information state, retained memory, shared/joint state | SEM-230 participant view/history/memory and episode carriers | effective label, unresolved status, derivation/release history, and all retained upstream source/influence refs |
| proposal, participant output, action and destination/tool arguments | participant decision surfaces, action definitions, and `ParticipantActionAdmissionRequest` | join of context, memory, observations, participant process, transformation apparatus, and every argument source; structural/action admission remains a separate gate |
| controller change and handoff | ACT-617 and API-409 control occurrences/context validation | unchanged flow label and history plus fresh controller/authority occurrence refs; handoff is not declassification, endorsement, or admission |
| crossing, projection, redaction, transformation, disclosure | API-423 typed subjects, predecessor stages, exact policy/cut refs, and contextual validator | source/result identities, transformation relation, full input label join, immutable provenance/influence refs, and any coordinate-specific release ref |
| participant/external output, delivery, stream, callback, persistent write, and error | API-423 disclosure/delivery/observation stages and participant-facing views | a fresh final-sink decision for every serialization/effect; disclosure, delivery, and observation remain distinct; each stream chunk is independently governed or derived from one governed complete value |
| snapshot, retry, replay, and cross-episode reuse | RUN-310/RUN-319 snapshot/history/idempotency/expected-head carriers | original profile/policy/cut, label, unresolved status, provenance/influence/release histories, new exact cut, and fresh sink decision |

An open `taint`, `security_labels`, `context`, `metadata`, prompt, diagnostic,
header, query parameter, environment variable, or backend-options bag is not a
typed carrier for this mapping.

## Distinct operations

The following operations are semantically distinct:

| Operation | Effect |
| --- | --- |
| authentication | establishes principal identity and credential validity |
| authorization | permits an operation for an identity and authority |
| admission | accepts a fact, proposal, action, transition, or evidence record |
| approval | records a supervisory control decision |
| declassification | relaxes confidentiality for an exact result and sink |
| integrity endorsement | changes the admitted origin-trust coordinate for an exact result and sink |
| redaction | derives a new representation and retains influence unless a governed rule states otherwise |
| transformation | derives a new identity under a typed relation |
| trusted editing | derives a fresh proposal that re-enters normal gates |
| handoff | changes controller or authority state |
| deferral | transfers a decision obligation without authorizing the effect |
| interruption or shutdown | changes lifecycle and future enabledness |
| advice | supplies evidence or recommendation without authority |
| execution or delivery | realizes an already permitted effect or disclosure |

Declassification removes only named members of `Conf_phi`; endorsement removes
only named members of `Int_phi`. Both require the obligation to exist in the
source label and require explicit authority for the exact removal. Endorsement
does not delete the possible-writer/influence refs that caused the obligation.

Declassification and endorsement each bind:

- source and fresh result identity;
- exact changed coordinate and unchanged coordinate;
- destination, audience, or sink;
- authorizing principal and authority basis;
- profile, revision, policy decision, and state cut;
- predecessor and order refs; and
- safe evidence and limitation refs.

Approval, authentication, admission, monitor output, or trusted role does not
imply either release operation.

## Final-sink decision

For effective label `l`, exact cut `c`, sink `s`, authority `a`, destination
`d`, participant `p`, and effective capability posture `k`:

```text
MayFlowAtSink_phi(p,l,s,d,a,c,k)
  = ConfidentialityObligationsSatisfied_phi(l,s,d,c)
    and IntegrityObligationsSatisfied_phi(l,s,d,c)
    and AuthenticatedIdentityBinding(a,p,s,d,c)
    and Authorized(a,p,s,d,c)
    and Admitted(p,s,c)
    and EffectiveCapability(k,phi,s)
    and ExistingMayCrossAndTransformationGates(p,l,s,d,c)
    and FreshHeads(c)
```

Every conjunct is deny-first. Heuristic monitor output is not a conjunct that
can turn denial into permission. A profile may require monitor evidence as a
precondition, but only deterministic policy interprets that evidence.

The downstream runtime obligation owned by issue #1003 is to evaluate
`MayFlowAtSink`:

- after the last label, provenance, policy, authority, destination,
  participant, audience, capability, and state-cut resolution;
- immediately before `RuntimeTarget` or a backend performs an external
  mutation, tool action, callback, or persistent write; and
- immediately before participant-facing or external serialization, streaming,
  delivery, error output, or other disclosure.

That future runtime must commit the decision and all predecessor/history
changes atomically before effect. A denial, unsupported result, missing label
or provenance, ambiguous join, stale cut, history-head conflict, or failed
commit causes no external call and no disclosure. This definition and its
test-local finite model do not implement that boundary.

Each streaming chunk is either governed before release or derived from a
complete materialized value whose entire release is governed by the profile.

## Deterministic policy and heuristic monitors

Deterministic policy decides authorization, flow, capability, admission, and
release. A heuristic monitor emits a bounded observation, suspicion result, or
recommendation with identity, revision, visibility, provenance, confidence,
limitations, and safe evidence.

```text
MonitorResult != Authorization
MonitorFailure does not widen MayFlowAtSink
```

Monitor roles are apparatus and experiment declarations. A profile states:

- trusted, untrusted, or composed role;
- inputs and participant-visible outputs;
- policy, threshold, and audit knowledge;
- model or implementation identity where relevant;
- topology and shared inputs;
- independence, correlation, and collusion assumptions; and
- failure and fallback behavior.

Different monitor or model ids do not establish independence.

Human or trusted-system intervention names each authority effect. If an
intervention edits a proposal, it creates a fresh proposal with inherited
provenance and effective labels and re-enters validation, policy, capability,
and admission.

## Intentional-subversion evaluation profile

An admitted ASR-536 evaluation profile closes:

```text
Eval =
  (mode,
   main_objective,
   side_objective,
   participant_capabilities,
   apparatus,
   policy_knowledge,
   monitor_knowledge,
   audit_budget_knowledge,
   prior_outcome_visibility,
   adaptive_strategy_class,
   collusion,
   monitor_topology,
   monitor_correlation,
   audit_budget,
   audit_selection,
   intervention_protocol,
   memory_scope,
   replay_scope,
   policy_revision_scope,
   measures,
   limitations,
   nonclaims)
```

`mode` is `honest` or `attack`. Honest-but-fallible behavior and an attack
policy optimizing a side objective are separate populations.

The adaptive strategy is quantified over the facts actually visible to the
participant under SEM-230 and ADR-099. Possible feedback includes approvals,
denials, edits, deferrals, audits, handoffs, interruptions, outputs, order, and
declared timing facts. Hidden policy, threshold, audit, monitor, or objective
details do not enter the participant view unless the profile declares them
visible.

An audit budget is an evaluation-protocol coordinate unless the runtime
actually enforces it as a participant resource. Audit selection, trusted
editing, approval, defer-to-trusted, interruption, and shutdown are closed
protocol operations with explicit authority and evidence effects.

Measures report safety, usefulness, attack success, false positives, audit
cost, intervention cost, uncertainty, limitations, and nonclaims separately.
A weighted aggregate cannot erase the components.

Replay evidence is a digest-bound graph of existing episode, behavior,
control, crossing, action/result, experiment, and evidence refs. Hidden
objectives, credentials, private prompts, chain-of-thought, raw secrets, and
private model state remain outside portable evidence.

## Boundary-faithful required cases

### Injection

An untrusted observation or tool result influences a structurally valid
proposal and action argument. The integrity influence reaches the final sink.
The sink denies unless the exact policy admits it or a governed endorsement
creates a fresh result.

### Confidential exfiltration

A confidential fact influences a valid tool argument, participant output,
error, or colluding participant. Confidentiality reaches every explicit sink.
The unauthorized destination receives no output without exact declassification
authority.

### Adaptive monitor evasion

An attack participant adapts to declared prior outcomes, monitor visibility,
threshold or budget knowledge, and correlated monitors. Monitor success cannot
bypass deterministic policy. Safety and usefulness are reported across the
declared strategy class.

### Control-handoff manipulation

Tainted context or external direction crosses a valid API-409 handoff and
induces a receiver proposal. Controller, authority, provenance, effective
labels, receiver admission, API-423 crossing, and final sink are checked at one
exact cut. Handoff grants neither trust nor action admission.

Every denied case records zero prohibited `RuntimeTarget` calls and zero
participant/external disclosure. Tests also inspect append-only histories,
safe audit/error evidence, and replay.

## Bounded Executable Evidence

`implementations/python/tests/sem233_boundary_flow_model.py` is a test-local
finite interpretation of the revision-1 powerset algebra. Its companion
`test_sem_233_adversarial_boundary_flow.py` exercises closure, associativity,
commutativity, idempotence, monotonicity, traversal-order independence,
coordinate independence, conservative derivation, unknown/missing labels,
cross-profile joins, laundering attempts, coordinate-specific rewrites,
release-operation conflation, handoff, cross-episode replay, stale cuts, sink
obligations, and every deny-first final predicate conjunct.

Those cases are bounded falsification evidence over synthetic refs. The model
is not a portable contract, runtime implementation, backend realization,
complete instrumentation claim, model check, proof, universal
noninterference result, or intentional-subversion evaluation.

## Security and evidence boundary

- Closed DTOs and request-size guards apply to portable bodies. Touched path,
  query, and header values are separately bounded.
- Strict identity, target, role, participant, controller, audience, and
  destination binding precedes semantic fact creation.
- Existing runtime-fact, action, API-409, API-423, snapshot, and transition
  validators remain the owners of their relations.
- API-407 declared and effective support is deny-first.
- Expected failures use stable bounded diagnostics. Unexpected failures use
  the redacted error envelope.
- Logs, diagnostics, audit, and evidence contain safe refs, digests,
  classifications, counts, and bounded summaries, never raw confidential data,
  prompts, credentials, private state, monitor internals, or hidden objectives.
- Portable semantics add no required environment variable, CLI flag,
  subprocess, socket, daemon, sidecar, or host path.

## Requirement allocation

| Requirement | Ownership |
| --- | --- |
| SEM-233 | explicit-flow labels, derivation, release operations, sinks, and final decision |
| ASR-536 | intentional-subversion profile, protocol, measures, and evidence claims |
| SEM-230 | participant-relative projection, exact-cut policy, memory, strategies, and noninterference boundary |
| ACT-617 / API-409 | control authority and typed control occurrences |
| API-423 | portable crossing occurrences and order/context relation |
| RUN-310 / RUN-319 | authenticated mediation, persistence, replay, and reference-runtime enforcement |
| API-407 | declared/effective backend support, realization, downgrade, and conformance |
| ASR-535 | bounded flow falsification and evidence/claim discipline |

SEM-233 and ASR-536 remain DRAFT until their remaining downstream positive
obligations are satisfied. Issue #812 supplies design authority and the
implementation program; #1001 publishes the SEM-233 revision-1 algebra, and
#1002 publishes its profile and relation contracts. Neither delivery claims
runtime enforcement, backend realization, or ASR-536 evaluation evidence.

## Nonclaims

- No model-alignment or safe-internal-reasoning result.
- No chain-of-thought, prompt, private model state, or credential carriage.
- No automatic trust in a human, model, monitor, gateway, or backend.
- No protection for undeclared timing, storage, resource, steganographic, or
  other covert channels.
- No universal noninterference, shielding, runtime, backend, or
  intentional-subversion robustness result.
- No LLM-specific participant semantics, general taint framework, policy
  engine, gateway, monitor service, trajectory store, or agent framework.

## Implementation program

The dependency-ordered implementation program and canonical issue ids are in
[`implementation-program.json`](../../../docs/research/adversarial-participant-control/implementation-program.json).
