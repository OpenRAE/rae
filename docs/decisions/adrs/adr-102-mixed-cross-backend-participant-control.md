# ADR-102: Mixed Cross-Backend Participant Control

## Status

accepted

## Date

2026-07-31

## Classification

Classification: FM3

Required artifacts: edition-pinned primary-source assessment, revisioned
mixed-composition and trial-schedule profiles, formal invariants, explicit
authority and trust boundaries, a demonstration protocol, DRAFT Ground
Control ownership, and dependency-ordered implementation work.

Waivers: issue #813 is design authority. It does not publish portable schemas,
change trial compilation or runtime behavior, declare or realize a backend
capability, execute the demonstration, or establish interoperability,
transfer, IFC/noninterference, trace inclusion, bisimulation, or backend
equivalence.

## Context

RAES already has participant-neutral authorities for:

- backend-neutral scenario meaning and deterministic scenario-family
  composition;
- experiment selection, apparatus constraints, trial admission, immutable
  plan/run identity, cleanup, and evidence;
- participant identity, one acting controller, scoped authority, action
  admission, handoff, and append-only history;
- participant/audience projection, crossings, delivery, observation,
  declassification, and exact state cuts;
- shared clocks, time progression, order, realization evidence, and
  conformance; and
- backend capability strength, constraints, downgrade, realization, and
  evidence.

Those authorities support realizing the same scenario on different backends
and comparing bounded evidence. They do not define one trial containing
simulated and emulated/operational participant components at the same time.
The admitted trial entry pins one realization envelope. The apparatus context
can report multiple components after the fact but does not authorize a mixed
topology.

The issue #600 corpus is deliberately a pair of separate backend runs. CybORG
also selects simulation or emulation for a run. Neither is evidence of an
AND-composition.

Other precedents expose the missing dimensions:

- HLA standardizes federation services, scoped object/attribute ownership,
  interest management, directed interactions, and logical-time coordination.
- NIST integrated federations expose bridge topology, independent clocks,
  information-hiding limits, translation, and shared-resource effects.
- UCEF, ACTING/EDL-FG, LVC systems, FMI, and HELICS explicitly mix simulation,
  emulation, hardware, or differently scheduled components.
- CybORG and CyGIL show that a common interface and successful training do not
  eliminate observation, action, model, or transfer mismatch.
- digital-twin composition distinguishes integrated, unified, and federated
  composition and makes synchronization/fidelity material.

RAES needs both OR and AND semantics without making backend selection part of
portable scenario meaning or conflating multiple realization providers with
multiple controllers.

The supporting
[research record](../../research/cross-backend-participant-control/) contains
the complete source disposition, current-state analysis, composition design,
demonstration protocol, DRAFT requirement disposition, and child program.

## Decision

### 1. Add two DRAFT owners

SEM-234, **Mixed Cross-Backend Participant-Control Composition**, owns the
portable semantic profile. ASR-537, **Cross-Backend Participant-Control
Realization and Transfer Evidence**, owns the demonstration and evidence
profile.

Both remain DRAFT. Issue #813 defines their boundaries and implementation
program. It does not satisfy their positive implementation or evaluation
clauses.

### 2. Support alternative and simultaneous mixed realization

The first composition profile supports:

- **alternative realization**: the same authored scenario and participant
  policy are admitted for simulation or for emulation/operation; and
- **simultaneous mixed realization**: two or more admitted apparatus
  components with different realization forms participate in one trial.

Realization forms include simulation, emulation/operation, hardware/native,
and federated composition. Labels describe admitted, evidenced realization;
they are not inferred from backend names, adapter classes, infrastructure, or
marketing terms.

### 3. Keep SDL backend-neutral

Portable SDL continues to author participants, controlled scopes, action
families, observation boundaries, crossings, injects, time intent, and world
meaning. It does not select a backend, adapter, federation, or digital-twin
mode.

Realization allocation belongs to admitted experiment/trial intent and
references stable compiled identities. Revision 1 can allocate:

- a participant runtime;
- a controlled scope;
- an action family;
- an observation source; and
- a crossing boundary.

An allocation must be closed, bounded, non-overlapping or governed by an
explicit arbitration rule, and complete for every required effect and
observation. Runtime and schedulers cannot choose outside it. Missing
allocation is rejection, not backend fallback.

### 4. Make composition topology and boundaries explicit

The profile names single-component, integrated, unified, federated/bridged,
and nested topologies.

Every directed composition edge binds:

- source and destination component refs;
- adapter or bridge identity and version;
- authority and allocation scope;
- action or observation mapping;
- participant/audience policy and release basis;
- time-domain and order mapping;
- required API-407 support strength;
- transformation and mapping loss;
- failure, retry, and partial-delivery behavior; and
- evidence and provenance refs.

A shared bus, FOM, API, broker, gateway, or package does not fill these fields
by implication.

### 5. Preserve one acting controller in revision 1

The authority path is:

```text
participant
  -> acting controller
  -> authority basis and controlled scope
  -> action admission
  -> selected realization provider
  -> adapter or bridge responsibility
  -> backend effect
```

Backend responsibility is not action authority. HLA object/attribute ownership
is responsibility for updating simulated object state; it is not participant
identity, acting control, approval, handoff, or disclosure authority. Directed
delivery is addressing; it is not observation or authorization.

Revision 1 retains exactly one acting controller per participant and episode.
It does not support:

- simultaneous controllers for different scopes;
- lease claims based only on validity windows; or
- joint/fused control represented by a synthetic identity or controller list.

A later profile may add these only with exact scope and controller identities,
lease renewal/expiry/fencing or quorum/priority/arbitration/unanimity,
revision-fenced atomic transitions, clock/order semantics, oscillation and
livelock handling, failure behavior, and evidence.

### 6. Use explicit transfer states

HLA ownership services are adopted as a transition-protocol precedent, not an
authority model. A future backend realization may expose requested, offered,
pending, committed, failed, expired, cancelled, and stale acquisition or
divestiture states.

Pull and push initiation retain different provenance. They converge only
after a RUN-310 revision-fenced atomic commit. Until commit, the prior acting
controller and authority remain effective. Alternating valid transfers are not
proof of progress; oscillation needs a bounded retry/cooldown or explicit
livelock disposition.

### 7. Separate routing from policy

Declaration, publish/subscribe, DDM, directed interactions, bridge filters,
encryption, and transport authorization are realization mechanisms. They
cannot grant participant visibility, marking authorization,
declassification, IFC, or noninterference.

SEM-230 and API-423 authorize the exact participant/audience projection before
it reaches the edge. Filtering may narrow an authorized projection. It cannot
widen one.

Leakage analysis includes membership, subscriptions, classes, regions,
destinations, sizes, timing, synchronization, ownership changes, retractions,
and differential failures. Audit retention uses an evidence audience and does
not disclose to a participant.

### 8. Require admitted time and order mappings

Each component declares its clock, time domain, role, progression service,
lookahead if applicable, delivery order, serialization basis, and readback.
Every cross-clock edge supplies an admitted mapping or records the relation as
partial/unknown.

A timestamp-only backend is `disclosed_weak`. It cannot claim governed logical
order. A `backend_serialized` claim requires the serialization service, clock,
runtime readback, and conformance evidence.

Staleness binds controller, authority, capability, policy revision, state
revision, history head, and governed order. Wall-clock recency is not enough.
Rollback, replay, concealment, and retraction append facts and never erase a
delivery or participant knowledge.

### 9. Preserve trial identity while supporting staged realization

An inter-trial realization change creates a new admitted plan entry and run id
linked to its source. It supports simulation-to-emulation training/evaluation,
emulation-to-simulation model regeneration, and alternating or parallel
calibration without pretending the runs are one world.

Revision 1 also permits a finite within-run phase schedule when:

- every possible component and manifest is pinned before execution;
- each activation/deactivation edge, mapping, authority, clock, policy, and
  failure behavior is admitted;
- the schedule is finite and schedule-independent;
- a phase transition commits before new effects; and
- transition and failure evidence is append-only.

An unadmitted late join, discovered backend, runtime fallback, or phase rewrite
is rejected.

### 10. Keep three open/closed axes independent

The profile separates:

- **control loop**: open-loop observation/replay versus closed-loop
  intervention/actuation;
- **world assumption**: closed-world versus bounded-open-world treatment of
  unknown entities, actions, observations, and mappings; and
- **federation membership**: fixed versus finite pre-admitted dynamic
  membership.

Closed-loop posture grants no action authority. A bounded-open-world profile
does not widen a closed vocabulary or admit an unknown mapping. Dynamic
membership does not bypass trial admission.

### 11. Require a claim-separated demonstration

ASR-537 requires:

- pure simulation;
- pure emulation/operation;
- simultaneous mixed composition;
- linked inter-trial change;
- pre-admitted within-run phase change;
- open-loop and closed-loop cases; and
- adversarial mismatch and zero-effect cases.

Every result binds scenario/policy digests, plan/run identity, apparatus,
adapters, allocation, topology, clocks/order, capability, conformance,
mappings, model/data/seed provenance, losses, limitations, and reproduction
evidence.

Bounded conformance, interoperability readiness, empirical transfer, trace
inclusion, bisimulation, IFC/noninterference, and backend equivalence remain
distinct. No result is promoted between them silently.

### 12. Allocate dependency-ordered work

- #1013 publishes SEM-234 semantic authority.
- #1014 publishes portable composition contracts after #1013.
- #1015 implements deterministic trial admission after #1014.
- #1016 implements fail-closed runtime coordination after #1014 and #1015.
- #1017 implements generic backend capability and conformance after #1014 and
  #1016, in the Backend Contract & Conformance milestone.
- #1018 executes ASR-537 after #1015, #1016, and #1017.
- #1019 reconciles claims after #1016, #1017, and #1018.

### 13. Executable mapping and time amendment (#1355, 2026-09-24)

The DRAFT statuses in section 1 record the original #813 decision; SEM-234 is
now ACTIVE. The published `sem-234/rev1` profile remains a sealed statement of
intent. Its edge, time, loss, and evidence references are not executable
services. An admitted mixed action now requires an installed, revision-pinned
`MixedEdgeExecutionBinding` for its exact directed edge. The binding joins the
admitted route and time mapping to one source action subject, one destination
subject, an executable mapper, a time service, and a bridge. The current
reference runtime requires both compiled action addresses to equal the
governed request and the destination provider's admitted action allocation.
The bridge may translate its pinned backend-native subject internally, but
the mapper cannot alter the portable request's participant identity, action,
authority, audience, terminal-outcome demand, or other governed fields. A
missing or mismatched binding refuses before a provider call.

The control plane retains operation ownership and commits the RUN-310/API-423
decision and exact provider attempt before the bridge runs. The bridge receives
the owning operation id and may call the selected provider once. The installed
time service reads the admitted two-clock state, provides a correlated order
grant, and reads back after execution. Mapping and timing evidence must satisfy
the admitted edge obligations. The current executable profile admits a proved
comparison within one clock segment; an incomparable or unproved relation
refuses. This uses shared time semantics and does not imply a common physical
clock, hard real-time synchronization, or physical-OT timing guarantees.

Backend execution, destination delivery, and participant observation remain
separate facts. A correlated bridge execution report requires backend readback;
delivery additionally requires a destination receipt read through its own
installed service; observation additionally requires exact participant and
audience readback. The bridge result, a timestamp, an evidence reference, or
`ApplyResult.success` alone cannot create either later fact. An authorized
declared mapping loss appears only with the correlated execution report. A
known partial result or unresolved delivery is `INDETERMINATE` under the shared
operation lifecycle, retaining known evidence and blocking dependent work
until explicit resolution. Idempotent replay returns the original operation;
it never invokes the bridge again.

A staged membership change requires an installed handoff binding with exact
source and destination native owners. Its admitted clock mapping receives a
correlated order grant and typed readback before transfer. A committed native
transfer must be followed by destination-owner and time readback at the
expected phase revision before the new phase and handoff fact commit. Failed
or stale transfer with old-owner readback keeps the prior phase; pending or
uncertain transfer is `INDETERMINATE` and blocks dependent effects. The store
claims phase transitions and other mixed effects under one run-scoped
conflict boundary before external calls. Native ownership remains distinct
from the RUN-310 acting controller and disclosure authority.

Compatibility is fail closed. Existing `sem-234/rev1` plans and historical
reference-only records remain readable with their original meaning; their
mapping refs, success booleans, and timestamps are not reinterpreted as
executed delivery, observation, or handoff. Pure paths continue under their
existing operation contract, but also make no unsupported delivery or
observation claim. This amendment does not change a published schema; the
executable services are trusted runtime bindings to the already admitted
profile. Another bridge implementation can use the same binding seam after
provider-local capability and conformance admission. It receives no authority
from its name, installation, or manifest claim alone.

## Consequences

RAES can represent both backend substitution and mixed composition without
putting apparatus choice in SDL or weakening participant authority. The same
profile also supports bounded trial-stage variation and preserves exact losses
and evidence.

The cost is a cross-cutting contract and runtime program. Trial admission must
pin more than one apparatus component and validate a graph of mappings.
Runtime coordination must resolve and commit a larger exact cut. Backend
conformance must probe services rather than interfaces. Evaluation must retain
negative and mismatch evidence.

Revision 1 deliberately rejects multi-controller and lease semantics. That
keeps mixed realization independent of the harder authority-composition
problem and leaves a versioned seam for later work.

## Non-goals

- HLA, FMI, HELICS, EDL-FG, CybORG, CyGIL, CyberBattleSim, or digital-twin
  wire compatibility.
- A universal federation, co-simulation, agent, gateway, or digital-twin
  framework.
- Backend selection in portable SDL.
- Distributed, leased, simultaneous scoped-owner, or joint/fused control in
  revision 1.
- Treating routing, filtering, encryption, ownership, or membership as
  participant authorization or IFC.
- Runtime implementation, backend realization, demonstration, transfer,
  interoperability, trace inclusion, bisimulation, IFC/noninterference, or
  equivalence from this ADR alone.

## References

- [Architecture preflight](../issue-813-cross-backend-participant-control-preflight.md)
- [Research and implementation program](../../research/cross-backend-participant-control/)
- [SEM-234 and ASR-537 formal design](../../../specs/formal/participant-semantics/cross-backend-participant-control.md)

## Amendments

| Date | Commit/PR | Summary |
| --- | --- | --- |
| 2026-09-24 | #1355 | Required executable mixed mappings, bridge and time coordination, independent stage readback, and native staged handoff while preserving historical reference-only meaning. |
