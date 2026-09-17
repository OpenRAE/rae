# Mixed Cross-Backend Participant-Control Composition

Requirements: SEM-234 and ASR-537.

Status: published SEM-234 semantic definition; ASR-537 realization evidence
remains DRAFT. Publication does not establish runtime support.

Authority revision: `sem-234/rev1`.

Composition profile: `mixed-cross-backend-participant-control-v1@rev1`.

Issues: #813 (design), #1013 (semantic publication).

This specification composes existing scenario-family, experiment/trial,
participant-control, crossing, time, backend-capability, and evidence
authorities. It defines no wire contract or positive runtime/backend claim.

Revision 1 retains MCB-001–045 identities and makes their admission and
transition relations precise below. It composes accepted ADR-102 with the
progressive-specification correction in
[ADR-105](../../../docs/decisions/adrs/adr-105-recursive-partial-description-semantics.md).
Profile revision, document status, wire version and realization evidence are
independent. Historical #813 research/program dispositions remain historical.

## 1. Domains

Let:

- \(S\) be an admitted backend-neutral instantiated scenario;
- \(P\) be its participants;
- \(E\) be participant episodes;
- \(U\) be stable compiled allocation units;
- \(C\) be admitted apparatus components;
- \(F\) be realization forms;
- \(A_\phi \subseteq U \times C\) be allocation in phase \(\phi\);
- \(T = (C,X)\) be a directed composition topology with edges \(X\);
- \(\Phi = [\phi_0,\dots,\phi_n]\) be an optional finite phase schedule;
- \(K\) be the exact participant-control and crossing state cut;
- \(M\) be admitted cross-clock/order mappings;
- \(Q\) be the participant/audience policy and projection state;
- \(B\) be API-407 effective backend support;
- \(L\) be explicit mapping losses and limitations; and
- \(V\) be evidence and provenance.

Realization forms are:

```text
simulation
emulation-or-operational
hardware-or-native
federated-composition
```

Composition modes are:

```text
alternative-realization
simultaneous-mixed-realization
```

Allocation units are:

```text
participant-runtime
controlled-scope
action-family
observation-source
crossing-boundary
```

No backend name, adapter type, host, worker, or schedule position is an
allocation-unit identity.

## 2. Authority decomposition

For participant \(p\), episode \(e\), and cut \(K\), define:

- \(\operatorname{controller}(p,e,K)\): one effective acting controller;
- \(\operatorname{authority}(p,e,K)\): authority basis and controlled scope;
- \(\operatorname{admit}(a,K)\): action-admission relation;
- \(\operatorname{provider}(u,\phi,K)\): admitted realization provider;
- \(\operatorname{owner}(o,\alpha,K)\): optional backend-native
  object/attribute responsibility;
- \(\operatorname{route}(x,K)\): delivery addressing/transport; and
- \(\operatorname{release}(v,p,q,K)\): participant/audience disclosure
  authority.

These relations are pairwise non-substitutable:

\[
\operatorname{owner} \not\Rightarrow \operatorname{controller}
\]

\[
\operatorname{provider} \not\Rightarrow \operatorname{admit}
\]

\[
\operatorname{route} \not\Rightarrow \operatorname{release}
\]

\[
\operatorname{controller} \not\Rightarrow \operatorname{owner}
\]

Revision 1 requires:

\[
|\operatorname{selectedController}(p,e,K)| = 1
\]

It defines no positive lease, simultaneous scoped-controller, joint, or fused
control relation. One selected identity does not imply active authority:
revoked, expired, stale or unresolved authority permits no action. Pending
handoff leaves the prior controller selected, subject to its own current
authority. Provider and native ownership changes do not change this selection.

## 3. Backend-neutral authoring

### MCB-001 — Portable scenario independence

Scenario identity and membership authority are independent of \(A_\phi\), \(T\), \(\Phi\),
component manifests, and backend availability.

### MCB-002 — Allocation authority

Allocation is experiment/trial intent compiled after deterministic scenario
composition and before runtime execution.

### MCB-003 — Stable allocation targets

Every \(u \in U\) resolves through the canonical compiled-address authority and
has the same meaning across admitted realizations.

### MCB-004 — No apparatus-created meaning

An apparatus component may realize or refuse \(u\). It cannot create a
participant, controlled scope, action family, observation source, or crossing
that is not permitted by \(S\). Here \(S\) includes the authored constraints
and their selected abstraction, not an exhaustive concrete inventory. A
delegated internal materialization choice does not become a portable allocation
unit. Additional portable membership, where allowed, must first pass the
owning prepared-membership authority and resolve stable compiled identities
before composition sealing; a backend report cannot grant it.

## 4. Allocation

### MCB-005 — Completeness

In every active phase, every required unit has an admitted active provider:

\[
\forall u \in U_{\mathrm{required}},\
\exists c \in C_\phi : (u,c) \in A_\phi
\]

### MCB-006 — Effective eligibility

\[
(u,c) \in A_\phi
\Rightarrow
B(c,u) \geq \operatorname{requiredStrength}(u)
\]

where \(B\) includes declared support, effective support, required contracts,
realization-envelope membership, limitations, downgrade, and conformance
evidence.

Effective support is scoped to the selected provider, effect, edge and phase;
it is not the union of other providers' capabilities. Under negotiated
`backend-realization-preparation-v1`, delegated admission selects a jointly
supported allowed witness and later validates delivery. It does not require
the backend to realize every allowed completion. Legacy universal-envelope
admission and ADR-070 `subsumes(B,R)` retain their stronger meaning. Neither
negotiation nor a nonempty intersection alone proves delivery.

### MCB-007 — Closed overlap

If two providers cover the same unit, an accepted revisioned arbitration or
failover profile must define selection and failure. Revision 1 supplies no such
profile, so unexplained overlap is invalid. This is phase-relative and checks
resolved effect coverage across allocation kinds: a participant-runtime scope
and an action-family scope cannot assign the same effect to different
providers. Repeated consistent coverage by the same provider is not competing
ownership. Disjointness requires the owning scope interpretation, not address
prefixes. Sequential providers in different phases are not simultaneous overlap.

### MCB-008 — No runtime fallback

A failed or unavailable provider does not authorize another component.
Fallback outside the current \(A_\phi\) is rejection. A pinned but inactive
provider cannot act.

### MCB-009 — Schedule independence

Allocation identity and sealed plan bytes do not depend on host, worker,
thread, queue, batching, completion order, retry count, wall time, or backend
availability.

## 5. Composition topology

Topology class is one of:

```text
single-component
integrated
unified
federated-or-bridged
nested
```

For every edge \(x \in X\), require:

```text
source component
destination component
adapter or bridge
allocated crossing scope
authority
action or observation mapping
participant/audience policy
release or declassification basis
source and destination clocks
time/order mapping
required support strength
mapping loss
failure behavior
evidence
```

### MCB-010 — Edge totality

An exchange across components is admissible only when its edge fields resolve
to revision/digest-matched authority.

These are admitted apparatus obligations, not compulsory author-written backend
recipes. Evidence fields bind the selected obligation, basis and authorized
references; they do not require an experimental inventory or raw telemetry.
An obligation may be inapplicable only under its owning policy. Required
operational/capability facts cannot be waived by an empty reference list.

### MCB-011 — Directionality

An edge \(c_i \to c_j\) does not imply \(c_j \to c_i\). Bidirectional
interaction uses two directed edges or a closed bidirectional profile.

### MCB-012 — Nested disclosure

A nested component exposes its external allocation, edge/time/policy
capabilities, digest, internal-evidence ref, and limitations. Its internal
composition is not inferred by the parent. Internal evidence is required only
to support a selected boundary claim or execution obligation; unrelated
implementation choices need no authored profile or universal export. Nested
profile resolution is bounded and acyclic. Interaction feedback edges are
different: they may be cyclic, but require explicit progress/failure semantics.

## 6. Control and responsibility transfer

Transfer states are:

```text
requested
offered
pending
committed
failed
expired
cancelled
stale
```

### MCB-013 — Commit establishes responsibility

Requested, offered, or pending transfer does not alter effective provider or
controller state. Only an atomic revision-fenced `committed` occurrence does.

### MCB-014 — Pull/push provenance

Acquisition initiated by the candidate and transfer initiated by the current
provider retain different initiator/negotiation evidence even when both
converge on the same commit relation.

### MCB-015 — Stale transition safety

A controller, authority, policy, capability, state-revision, history-head, or
order mismatch yields `stale` and zero prohibited effects.

### MCB-016 — No authority laundering

Provider/owner transfer never changes participant identity, acting controller,
action authority, or disclosure authority by implication.

### MCB-017 — Oscillation is not progress

Repeated valid transfers require a bounded cooldown/retry or explicit
livelock/cycle disposition before any progress guarantee may be claimed.
Revision 1 makes no such guarantee.

## 7. Information distribution

### MCB-018 — Authorization before routing

SEM-230/API-423 projection and release are resolved before publish/subscribe,
DDM, bridge filtering, directed delivery, or serialization.

### MCB-019 — Filtering may only narrow

For authorized projection \(R\) and bridge filter \(D\):

\[
D(R) \subseteq R
\]

An adapter cannot add participant-visible information.

### MCB-020 — Delivery stages remain distinct

Addressing, request, decision, delivery attempt, delivery, observation, and
audit remain distinct occurrences. No earlier stage implies a later stage.

### MCB-021 — Metadata projection

The observer profile dispositions:

```text
membership
subscription or class
region or destination
message size and cadence
synchronization
ownership/responsibility change
retraction
differential failure
```

Payload filtering does not establish metadata noninterference.

### MCB-022 — Audit is a separate audience

Authorized audit retention does not add a participant observation.

## 8. Time and order

Each component's admitted time profile resolves the applicable terms below.
An inapplicable service (for example rollback in an irreversible physical
component) is explicitly dispositioned by that profile, not invented or made
a universal authored field:

```text
clock identity and authority
time domain and unit
pacing or dilation
regulating or constrained role
advance request and grant behavior
lookahead
delivery order
serialization service
rollback or replay behavior
runtime readback
```

### MCB-023 — Cross-clock mapping

Every edge between different clock domains has an admitted mapping \(M_{ij}\).
Without one, the relation is unknown and cannot authorize an exchange that
requires it. An admitted partial-order mapping is different: it can support
only comparisons actually established by that mapping. Incomparable events
remain incomparable; timestamps, phase indices and arrival order do not add
causal edges. Identity mappings within one clock are still explicit.

### MCB-024 — Timestamp weakness

Timestamps without governed mapping/order/readback support only
`disclosed_weak`. They do not establish causality or exact order.

### MCB-025 — Backend serialization evidence

`backend_serialized` requires a named clock, serialization service, runtime
readback, and conformance evidence.

### MCB-026 — Staleness coordinates

Staleness is evaluated over:

```text
controller
authority
capability
policy revision
state revision
history heads
governed order
```

Wall-clock age can constrain but not replace those facts.

### MCB-027 — Knowledge is append-only

Rollback, replay, concealment, and retraction append occurrences. They do not
erase prior delivery or participant knowledge.

## 9. Trial and phase realization

### MCB-028 — Inter-trial change

A realization change between trials creates a new admitted plan entry and run
id with source lineage.

### MCB-029 — Derived model identity

An emulation-derived simulator records source dataset/traces, generator and
profile revisions, model digest, coverage, unknown transitions, and
limitations.

### MCB-030 — Finite within-run phases

\(\Phi\) is finite and sealed before execution. Every possible component,
allocation, edge, clock mapping, policy, authority expectation, transition,
progress bound, and failure behavior resolves before plan sealing.

### MCB-031 — Phase commit before effect

The transition from \(\phi_i\) to \(\phi_{i+1}\) commits its exact state cut
before the next phase can cause effects.

Revision 1 uses quiescent transition: pending effects/deliveries must be
resolved under their original owners before activation can commit. A timeout
or cancellation may stop progression but cannot turn pending work into
completion. The sealed transition names its trusted trigger evaluator, bounds
and failure disposition. Runtime facts do not themselves select apparatus.

### MCB-032 — Phase history

A transition appends prior/next phase, trigger/order, membership,
allocation, controller/authority/policy/time cuts, commit result, loss, and
evidence.

### MCB-033 — Identity preservation

A phase change does not rewrite plan id, plan-entry id, run id, prior control
or crossing histories, prior delivery, or participant knowledge.

### MCB-034 — Unadmitted join

A component absent from the sealed possible-membership set cannot join.

## 10. Open and closed axes

### MCB-035 — Control-loop posture

`open-loop` permits observation/replay without external actuation.
`closed-loop` permits a candidate action to reach ordinary control, admission,
policy, capability, time/order, commit, and effect boundaries. The posture
does not grant authority.

### MCB-036 — World assumption

`closed-world` rejects unknown entities/actions/observations/mappings.
`bounded-open-world` acknowledges possible unknowns but treats an unknown
required mapping as unsupported. This axis does not prohibit governed typed
extensions or close delegated materialization. Its closed terms describe
operational dispositions, not an exhaustive catalog of products, private
mechanisms or all possible worlds. Exact authored constraints remain binding
under either world assumption (ADR-105).

### MCB-037 — Federation membership

`fixed` keeps one active component set.
`pre-admitted-dynamic` follows \(\Phi\). No other dynamic membership is
admitted.

The three axes are independent.

## 11. Runtime effect boundary

### MCB-038 — Exact-cut resolution

Before any adapter call or disclosure, resolve:

```text
authenticated caller and target
participant, controller, and audience
authority and action admission
allocation and active phase
component and adapter manifests
effective capability
policy and release
clock/order mapping
state revision and history heads
mapping loss and evidence expectations
```

### MCB-039 — Commit before effect

The exact decision and predecessor histories commit atomically before the
effect or serialization.

This is an authority/store transaction, not a distributed transaction with
the apparatus. A crash after commit requires reconciliation. The decision,
attempt, successful delivery and observation remain different facts; an
accepted operation receipt or a record named `delivered` is not success by
itself. Replay may return the original result, never renew permission or
dispatch a second effect implicitly.

### MCB-040 — Zero prohibited effects

Denial, stale cut, missing/unsupported mapping, failed admission, unsupported
capability, invalid phase, or failed commit produces:

```text
zero prohibited backend calls
zero participant/external disclosures
unchanged prohibited effect state
append-only safe failure evidence when its authorized store is available
```

These zero-effect obligations apply to pre-effect refusals. Already-started
external effects are not undone by later denial, cancellation or store failure.
Retain their accountable state and limitations; do not restore an obsolete
snapshot or claim compensation, cleanup or exactly-once execution.

### MCB-041 — Adapter distrust

Backend output is revalidated and mapped through safe diagnostics. Adapter
success cannot synthesize a portable success after a failed RAES gate.

## 12. Evidence and claims

For the selected ASR-537 demonstration claim, evidence binds:

```text
scenario and policy digests
plan, entry, coordinate, run, and replicate
participant, controller, and authority
apparatus and adapter manifests
allocation, topology, edges, and phase schedule
clocks, mappings, and realized order
capability and conformance
models, datasets, generators, seeds, and random streams
transformations, loss, uncertainty, and limitations
raw evidence, derived measures, and reproduction
```

### MCB-042 — Pure and mixed cases

The protocol covers pure simulation, pure emulation/operation, simultaneous
mixed, inter-trial transition, and pre-admitted phase transition.

### MCB-043 — Open and closed loops

The protocol covers open-loop and closed-loop cases under the same profile
identities.

### MCB-044 — Mandatory mismatches

The protocol includes stale handoff, concurrent intervention, false/unsupported
capability, timestamp-only/unmapped order, simulation-only observation,
unrealizable action, directed-delivery failure, prior-delivery retraction, and
bridge-metadata leakage.

### MCB-045 — Claim separation

These claims remain distinct:

```text
bounded conformance
interoperability readiness
empirical sim-to-em transfer
trace inclusion
bisimulation
IFC or noninterference
backend equivalence
```

Evidence for one does not satisfy another without an explicit governed
relation and binding.

Neither this demonstration protocol nor component specificity is a universal
per-run evidence demand. Collection, reporting, retention, export and required
operational inputs retain the independent
[observation-demand owner](../../sdl/observability-and-evidence.md#scoped-observation-demand).
An exact image does not request telemetry; an abstract model can request
exhaustive traces within a finite named scope. A missing required observation
fails its selected gate; absent unrequested data is not a composition defect.

## 13. Nonclaims

This design does not establish:

- portable contract or runtime implementation;
- any backend-native realization;
- HLA, FMI, HELICS, EDL-FG, CybORG, CyGIL, CyberBattleSim, or digital-twin
  compatibility;
- distributed, leased, simultaneous scoped-owner, or joint/fused controller
  support;
- exact cross-clock order without admitted mappings;
- protection from undeclared covert channels;
- general interoperability;
- universal sim-to-em transfer;
- trace inclusion or bisimulation;
- IFC/noninterference; or
- cross-backend equivalence.

## 14. Revision-1 admission relation

Let `resolve(u,S)` return the finite set of semantic effect/observation atoms
covered by compiled unit `u`, under its owning address and scope interpretation.
This includes cross-kind overlap. It is not string-prefix matching. Let
`Required(S,D,O,phi)` contain portable obligations at the declared abstraction,
effective selected observation demand `D`, and operational obligations `O`.
It excludes unspecified internal mechanisms and unrequested experimental data.

```text
Providers(a,phi) = { c | (u,c) in A_phi and a in resolve(u,S) }
Complete(phi)    iff every required atom has exactly one effective provider
Consistent(phi)  iff every allocated atom has at most one effective provider
Eligible(phi)   iff each allocation resolves to an active admitted component
                    with effective support for all its resolved atoms
```

An edge is the directed relation `(source, destination, crossing-scope)` plus
the bindings in section 5. A declared required exchange needs exactly one
resolving edge. No reverse or transitive authority follows from another edge.
Multiple edges with conflicting interpretations of the same exchange refuse
admission. Endpoint clocks must match the named mapping's source/destination
domains. A common adapter identity does not supply a missing mapping. Mapping
loss must be explicit, compatible with exact constraints, and accepted by the
selected policy before sealing.

`ResolveGraph` requires unique component/phase identities, canonical scope
resolution, all selected revision/digest matches, closed possible membership,
and complete edge/trigger/reference resolution. Count, depth and work budgets
bound the entire resolution, including nested profiles. Missing references,
cyclic nested definitions or exhaustion reject the whole graph. Cyclic
interaction topology does not itself violate reference acyclicity, but makes
no progress/deadlock guarantee without its admitted coupling/failure rules.

```text
Admit(P,S,D,O) iff
  supported exact composition-profile revision
  and ResolveGraph(P)
  and all phases satisfy Complete, Consistent and Eligible
  and every required exchange has its admitted directed edge
  and all edge, time, loss, authority and selected evidence obligations resolve
  and all finite transitions, trigger owners and failure bounds resolve
  and the selected realization satisfies S jointly with all component/edge constraints
```

Alternative realization relates separately admitted plans holding instantiated
scenario and participant-policy identity fixed, with distinct plan-entry/run
identities and their own apparatus provenance. It is an OR choice, not a
concurrent fallback pool. Simultaneous mixed realization has at least one
active phase with two or more providers whose declared realized dimensions
include distinct forms. `federated-composition` describes a composition
boundary; its nested profile must disclose the relevant leaf forms. Several
same-form components, names or adapter classes alone do not establish mixed
simulation/emulation. Simulation realizes declared transition/interaction
semantics; emulation/operation realizes the selected operational behavior;
hardware/native names a physical/native realization dimension. These labels
are bounded declarations supported by the selected basis, not equivalence.

Admission does not imply current execution permission. For exchange `x` at
cut `K`, the semantic effect relation is:

```text
MayExchange(x,K) iff Admit(P,S,D,O)
  and x belongs to the current active phase
  and current authenticated participant/controller/scope authority is valid
  and the owning action/input-admission predicate accepts
  and SEM-230/API-423 policy, release and transformation predicates accept
  and any selected stronger SEM-233 final-sink obligations accept
  and current capability and required evidence remain sufficient
  and every required order comparison holds under the admitted clock mapping
  and expected revisions, policy/capability cuts and history heads equal K
```

The authorized projection includes declared metadata observations as well as
payload. `BridgeOutput(x,K)` must be a narrowing of that projection before
serialization. Metadata outside the modeled observer surface is an explicit
claim limitation, not proven absence of a channel. Audit uses its own audience.
An edge does not wrap every internal exchange in a participant carrier:
API-423 applies only at the participant boundary and keeps its existing typed
subjects, predecessor joins and stage dispositions.

Refusal versus weakening is precise. Missing/revoked/stale authority,
unresolved required mappings, unmet exact constraints and failed commit always
refuse the affected effect. A weaker *claim* can be admitted only where its
owning policy explicitly permits that strength and records the omitted relation,
loss and limitations. It does not satisfy an unchanged stronger obligation.
Timestamp-only disclosure cannot be promoted to causal or backend-serialized
order. Optional unsupported observation has an explicit unavailable outcome;
required unsupported observation refuses. Weakening never invents permission.

## 15. Abstract transition system and carrier compatibility

State is `(sealed P, active phi, K, histories H, attempts E, knowledge N,
outstanding W)`. The sealed plan includes scenario selection and experiment
random-stream coordinates. The following transitions do not edit it:

| Transition | Preconditions | Result |
| --- | --- | --- |
| refuse | a pre-effect obligation fails | unchanged effects/knowledge/active phase; append a bounded authorized refusal if storage is available |
| authorize and attempt | `MayExchange`, then successful atomic expected-cut commit | append decision and attempt; no implied delivery or observation |
| reconcile result | result joins its original committed attempt and owner | append successful, failed, partial or unknown result; only actual authorized delivery adds delivered information |
| advance phase | sealed next transition and trusted trigger, fresh valid cut, `W` empty, successful commit | activate next admitted allocation; preserve P, controller unless separately handed off, history prefixes and N |
| pending/failed transfer | transfer has not committed under its owner | no new provider/controller authority; preserve prior state subject to revocation/expiry |
| inter-trial link | new admitted entry/run and explicit source lineage | new trial identity; source histories remain immutable; SEM-230 memory scope owns any cross-trial memory treatment |

Phase activation cannot reselect a scenario, redraw an experimental factor,
reset participant memory, erase a delivered fact or prove cleanup. A failed
phase commit does not partially activate a subset. Retry/replay must revalidate
the exact current cut and preserve idempotency. A finite schedule bounds possible
transitions; it does not establish termination if a trigger never occurs.

The current API-423 successor validator requires strictly increasing scalar
order and stable participant/episode, audience, controller, authority, policy
and order coordinates. Its transformation graph has one result per source
identity in the validated history. RUN-310 uses total-effective-order and
order-then-revalidate. The partial-order relations above do not silently change
those carriers. A composition needing unsupported representation must refuse
that implementation until its versioned contract supplies the relation. Do not
restamp old records, discard history or synthesize source identities to fit it.

RUN-310 owns supervision, approval/denial, direction, intervention, handoff,
override and cancellation. An accepted denial is a valid supervisory outcome,
not action admission. A stale rejected request is not a new controller. A
handoff evidence reference does not establish a provider handshake. Cancellation
at proposal/decision can prevent future work; after admission/attempt it carries
the incumbent partial/too-late disposition, not proof of backend abort. Use the
composed control/crossing commit and existing history owners; no second protocol
or event stream is defined here.

## 16. Executable evidence and applicability

The [worked cases and clause matrix](../../../docs/explain/reference/mixed-participant-composition.md)
bind this definition to finite admission/transition tests and incumbent
compatibility tests. The oracle interprets trusted finite scope, support,
policy and order inputs. It is not a parser, solver for arbitrary backends,
authentication service, nested-profile resolver, coordinator or conformance
engine. Its symbolic attempts/results are not realization evidence.

MCB-001–045 are definitions; the matrix states the narrower clauses exercised
by executable witnesses. No portable schema, runtime enforcement, backend
realization, general model-checking result, proof or ASR-537 demonstration
is established. The profile keeps the edition-pinned prior-art dispositions
from [the #813 source assessment](../../../docs/research/cross-backend-participant-control/prior-art-and-design-criteria.md).
HLA ownership/time, co-simulation coupling and range transfer precedents remain
design lineage, not wire or behavioral compatibility claims.
