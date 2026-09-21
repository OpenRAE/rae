# ADR-002: Declarative Experiment Objectives in the SDL

## Status

accepted

## Date

2026-03-29

## Context

[ADR-001](adr-001-scenario-description-language.md) established the SDL as a backend-agnostic specification language grounded in the Open Cyber Range (OCR) SDL and extended with additional sections adapted from other precedents.

The repository preserved OCR's scoring pipeline (`conditions -> metrics -> evaluations -> TLOs -> goals`) in the SDL, but objective intent still sat awkwardly between specification-time meaning and runtime concerns:

- experiment meaning
- backend-specific validation behavior
- execution behavior

That left an architectural gap: the SDL could describe topology, orchestration, agents, and scoring criteria, yet it lacked a first-class way to declare who was trying to do what, against which targets, during which exercise window, and by what success semantics.

Research and precedent review pointed in the same direction:

- **OCR** keeps assessment semantics in the specification layer, not only in runtime.
- **CACAO** keeps agent/target/workflow intent in the playbook specification while leaving execution adapters external.
- **CybORG** places agent-facing configuration such as actions, initial knowledge, and reward-calculator choice in scenario definitions.

At the same time, those precedents do not require the authored objective layer
to absorb every participant-implementation concern. Prompt modes, policy
selection, model/provider choice, human-control proxies, and similar concrete
participant apparatus remain separate from the authored objective contract.

The design question was therefore whether the SDL itself should carry declarative experiment semantics.

## Decision

Add a first-class `objectives` section to the SDL for declarative experiment semantics.

Each objective may declare:

- optional organizational `owner` and optional `assigned_participant`, with
  at least one required and both permitted (ADR-109)
- optional `actions` referencing declared action contracts; assigned objectives
  additionally constrain actions to their participant's declared action set
- optional `targets`
- required `success` criteria composing declared invariant or postcondition
  assertions over backend-neutral propositions (ADR-079)
- optional `window` constraints over `stories`, `scripts`, and `events`
- optional `depends_on` links forming an acyclic ordering relation between objectives

This section is intentionally declarative. It expresses:

- who owns the objective and which participant, if any, is assigned to pursue it
- what they are trying to affect
- when the objective matters
- how success should be interpreted

It does **not** encode backend-specific validation probes such as Wazuh queries,
command execution, file checks, polling loops, or session orchestration in
objective meaning. Legacy `conditions` carry probe implementation mechanics;
they are not propositions and cannot be referenced as objective success.

It also does **not** identify the concrete participant implementation that will
realize an authored participant role in a given run. Ownership without
assignment remains organizational intent, not runtime work. Neither relation
identifies the actor of an observed event, grants authority, or identifies a
beneficiary. Realization remains a separate apparatus and provenance concern.

### Relationship to ADR-001

This ADR refines ADR-001's SDL boundary by making declarative objectives part of the language itself while preserving ADR-001's backend-agnostic separation between specification and deployment/runtime mechanics.

## Consequences

### Positive

- The SDL now captures experiment meaning more completely, not just topology and scoring fragments.
- Agent definitions, orchestration, scoring, and objectives can be authored and reviewed together in one specification surface.
- The runtime boundary is cleaner: the SDL defines semantics, while runtime adapters define how those semantics are checked.
- Authored owner/assignment/target/success meaning remains distinct from concrete
  participant implementations and apparatus choices.
- Objective dependencies can be validated structurally as an acyclic ordering graph.

### Negative

- The SDL surface area grows, increasing documentation and test burden.
- The distinction between declarative objective semantics and runtime evaluation mechanics must remain explicit to avoid drift back into runtime-coupled schema design.
- Real-world stress scenarios need to keep pace so the section is exercised beyond unit tests.

### Risks

- If future runtimes need loops, switch/case routing, or exception branches, the current workflow model may need further expansion.
- Authors may infer stronger execution semantics than currently implemented unless `depends_on`, `window`, workflow, and success rules are documented precisely.
- Divergence from OCR/CACAO details remains possible if future changes borrow terminology without preserving the underlying conceptual boundary.
- Future agent-support work could accidentally collapse participant-exposure or
  participant-implementation concerns into objectives unless those boundaries
  remain explicit.

## Amendments

| Date | Commit/PR | Summary |
|------|-----------|---------|
| 2026-07-05 | #682 | Per [ADR-073](adr-073-scoring-reward-language-scope.md), narrowed the objective-success clause: `objectives.success` references observable state (`conditions`) only. The OCR scoring pipeline (`metrics` / `evaluations` / `tlos` / `goals`) this ADR preserved was removed from the SDL; graded scoring and reward now live in the experiment/evaluator plane (ADR-055/064/069). |
| 2026-07-12 | #725 | Per [ADR-079](adr-079-backend-neutral-proposition-and-truth-semantics.md), corrected the condition/proposition conflation: objective success now composes invariant or postcondition assertions over typed propositions; executable conditions are probe realizations only. |
| 2026-09-21 | #1338 | Per [ADR-109](adr-109-participant-identity-and-objective-assignment.md), replace exclusive actor binding with independent organizational ownership and participant assignment; require declared action contracts and preserve realized-attribution boundaries. |
