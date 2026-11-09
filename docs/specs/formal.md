# Formal specifications

Use this reference to find formal domains and their assurance requirements.

The specifications live under `specs/formal/<domain>/`.
A specification alone does not prove that its properties hold in a running system.
Each domain records its own evidence and limits.
Use the [formal domain index](../../specs/formal/README.md) for current domain introductions.
Use the [research entry](../research/index.md) for recorded results and source revisions.
See
[ADR-007](../decisions/adrs/adr-007-lightweight-formal-methods-policy.md) and the
[coding standards](../explain/reference/coding-standards.md) for the policy on when
formal artifacts are warranted.

## Domains

- **Workflows** (`specs/formal/workflows/`) -- Workflow state machine properties
- **Objectives** (`specs/formal/objectives/`) -- Objective/window consistency
- **Planner** (`specs/formal/planner/`) -- Dependency ordering and reachability
- **Runtime Contracts** (`specs/formal/runtime-contracts/`) -- Result/evaluation contracts
- **Participant Semantics** (`specs/formal/participant-semantics/`) -- Participant
  action, observation, interaction, visibility, causality, temporal behavior,
  derived context-view, and outcome-interpretation semantics
- **Participant Runtime** (`specs/formal/participant-runtime/`) -- Participant
  runtime state/history, observable action lifecycle, shared operational state,
  and concurrent execution semantics
- **Shared Time Model** (`specs/formal/time-model/`) -- Exact time domains,
  clocks, mappings, progression, temporal constraints, and lifecycle control
- **Experiment Core** (`specs/formal/experiment-core/`) -- Task, run,
  apparatus-context, study/collection, capture specification, raw evidence,
  derived measure, backend observation capability, and archival provenance
  contracts
- **Scenario Variation And Trial Realization**
  (`specs/formal/scenario-variation-trial-realization/`) -- Scenario-family
  identity, bounded selection, schedule-independent random streams, admitted
  plans, explicit instantiation, late binding, and archival linkage
- **Realization** (`specs/formal/realization/`) -- Exact/constrained/open
  realization boundaries, backend realization support, and proposed
  realization-envelope membership, subsumption, witness, and negative
  conformance semantics
- **Exploit-Path Analysis** (`specs/formal/exploit-path-analysis/`) -- Typed
  attack-state graph, transition, query, witness, and failure-evidence
  semantics with explicit nonclaims for weaker reachability and vulnerability
  evidence
- **Behavioral Relations** (`specs/formal/behavioral-relations/`) -- Revisioned
  validity, conformance, trace, simulation, refinement, bisimulation,
  participant-projection, strategic, probabilistic, statistical, and empirical
  claim semantics with explicit evidence and assurance boundaries

<a id="fm-classification"></a>

## Assurance classification

The canonical mapping is
[`specs/formal/assurance-policy.yaml`](../../specs/formal/assurance-policy.yaml)
(see [ADR-018](../decisions/adrs/adr-018-classification-based-assurance-policy.md)),
which gives the structural classification and is checked in CI by
`tools/check_assurance_policy.py`.

Artifact fulfillment is recorded per subsystem in
[`specs/formal/assurance-fulfillment.yaml`](../../specs/formal/assurance-fulfillment.yaml)
and checked by the same tool.
A waiver needs an ISO date and tracking reference.
Use these two files for exact classification and fulfillment facts.

| Level | Scope | Required artifacts |
|-------|-------|--------------------|
| FM0 | Structural (parsing, schema, local validation) | Unit tests |
| FM1 | Static Semantic (cross-references, ambiguity, fail-closed) | Invariants + unit tests |
| FM2 | Semantic Graph / Constraint (reachability, dependencies, portability) | FM1 + typed IR/contract coverage + targeted property-based or differential tests |
| FM3 | Stateful / Control Semantics (state machines, branching, lifecycle) | FM2 + abstract state-machine model |
