# ADR-105: Recursive Partial Description Semantics

## Status

proposed

## Date

2026-09-05

## Classification

Classification: FM3
Required artifacts: decision record, typed finite reference model, algebraic
checks, explicit abstract transition system, counterexamples, acceptance matrix.
Waivers: The #1201 design deliverable published no production schema, parser,
compiler, backend or capture migration. Issue #1203 subsequently publishes the
draft recursive constraint contract described below; public SDL syntax and
backend migration remain unselected.

## Context

Issue [#1201](https://github.com/OpenRAE/rae/issues/1201), under SEM-218, asks
for a compositional semantic contract before implementation migrations.
Its 2026-09-05 governing intent is the binding design criterion: authors
constrain what matters, backends choose permitted realizations, and requested
reports describe the result at an honest depth and basis. Extensible catalogs
alone do not correct compulsory installation detail or unconditional evidence.

Existing SEM-218, SEM-219, ADR-012/033/034/064/066/070 and artifact/profile
contracts provide the owners. Current aggregate explicitness, specimen guards,
open-demand subsumption and descriptor-derived corroboration do not yet meet
all the new examples. Existing accepted specifications retain their meaning.

## Decision

Propose the [review-1 semantic contract](../../research/partial-description/semantics.md)
and its [executable evidence](../../research/partial-description/verification.md).
The rules there are normative **within this candidate design**, including the
governing intent; they are not assertions about current SDL behavior. Acceptance
of this ADR and migration of production contracts are distinct events.

1. Separate presence, constraints, knowledge, default selection, delegation,
   closure and lifecycle authority. Undefined contributes no local statement;
   unknown and redacted information grant no realization permission.
2. Apply an open scope recursively to unspecified descendants. Conjoin explicit
   constraints; a precise child never closes a sibling or loses its force.
   Optional presence is conditional satisfaction, not unconstrained presence.
3. Name the universe of every closed record or collection. Stable semantic
   identity governs matching; positional inventory order does not.
4. Reuse `runtime.software_components` as the owner of software presence and
   version refinement, retaining `runtime.packages` for explicit package
   coordinates. Acquisition and final repository state are separate refinements.
5. Preserve universal `subsumes(B, R)` as `R ⊆ B`. Delegated admission requires
   selection **and delivery** of a permitted supported witness under execution
   policy. One witness cannot establish a universal capability claim.
6. Let complete abstract transition/interaction models execute at their declared
   level. Do not require an invented concrete-machine description.
7. Keep realization reports, observation demand, collection, retention, export
   and operational inputs separate through ADR-064/066 owners. Apply prohibitions
   before collection, not only at the response boundary.
8. Introduce these changed meanings only at an explicitly negotiated revision.
   Review the compact model before selecting public syntax or migrating consumers.

### Incremental adoption record

Issue #1203 publishes `recursive-realization-constraint-v1` as the first
versioned production contract for the shared normal form. The normative
[recursive realization constraint specification](../../../specs/sdl/recursive-realization-constraints.md)
defines its boundary. The contract and pure relations live in
`raes_contracts.realization_structure`; the earlier exact/open/record/collection
plan structure remains a losslessly checked compatibility subset. This adoption
does not select new SDL authoring syntax, change ADR-070 universal subsumption,
authorize a backend witness, or create observation, retention, or export demand.
Those migrations retain their separately assigned issues.

Issue #1212 publishes `observation-demand-v1` as the separate, versioned
demand normal form anticipated by decision 7. Its scope addresses reuse the
recursive semantic hierarchy, but its purpose, mode, selector, collection,
retention, export, prohibition, redaction, integrity, and reporting-basis axes
do not inherit meaning from realization posture or closure. Normalized demand
is carried through runtime and published execution plans. Realization concern
descriptors no longer impose observation strength, and backend substrate
readback occurs only when explicit effective collection demand selects that
operational observation. Component selectors are validated in the authored
declaration domain and compiled to canonical runtime addresses before
execution. More-specific policy partitions a broader selector instead of
allowing the broader rule to bypass a restrictive descendant: the normalized
selector carries excluded descendant scopes so an adapter can still collect
the permitted sibling remainder. Runtime adapters advertise stable
selector-family patterns rather than scenario-specific selector keys, then
bind each compiled selector to one unambiguous most-specific capability during
admission. A composite execution plan names one observation-owning phase (the
last actionable backend phase, falling back to provisioning), so its shared
demand executes once; an independently submitted phase plan remains its own
single execution boundary.

Normalization preserves separate selector/authority obligations and clips
inherited selectors to child partitions. Mandatory retention for one selector
does not make unrelated optional selectors mandatory or retained; overlapping
prohibitions still constrain all uses of the affected data.

Protected explicitly retained values become durable in the same atomic commit
as terminal operation state. This is not backend resource atomicity. The current
runtime rejects mandatory observation combined with mutation before backend
apply, pending a real compensating execution owner. It also rejects requested
export until a governed delivery owner exists. Live capture/export integration
remains with #1112/#1209, not an unconsumed outbox or an archival policy carrier.

Realization-description values project to the canonical experiment realized-form
disclosure contract. Nonretained descriptions exist only in the immediate manager
result; control-plane recovery requires explicit retention. Native substrate
readback is selected before driver observation and remains transient operational
validation input outside persisted snapshots. Built-in backends can report their
bound compute-substrate selection without probing or fabricating evidence.

## Alternatives Considered

- A larger product enum or extensible installation catalog still forces detail
  the author did not select and cannot satisfy the abstraction examples.
- Making every field optional loses required presence, conditional optional
  constraints and admission diagnostics.
- Replacing subsumption with overlap silently weakens universal claims.
- Collecting complete state and filtering reports violates collection prohibitions.
- A wholesale CUE migration is unnecessary. CUE's constraint lattice and local
  closure are useful precedents; RAE still owns authority and observation policy.
- An independent finite Python oracle makes the quantifier and composition
  examples inspectable without publishing another production relation engine.

## Consequences

The common authoring path can remain sparse while detailed refinements stay
binding. Private mechanisms need author profiles only when constrained or
exchanged with semantic claims. Existing owners avoid a third software inventory
or a new evidence plane.

The cost is explicit revision negotiation and preservation of recursive
constraints across compiler, admission and observation boundaries. A finite
oracle checks only its declared worlds and transitions; passing it cannot prove
production integration, backend capability, independent observation or general
solver completeness. The acceptance matrix states these limits.

The PR review is the review record for the proposal and executable evidence.
This ADR stays proposed until maintainer ratification; no accepted ADR pin or
published schema is changed by merely adding it.
