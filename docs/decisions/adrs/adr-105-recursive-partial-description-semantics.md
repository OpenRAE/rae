# ADR-105: Recursive Partial Description Semantics

## Status

accepted

Ratification is carried by the reviewed #1204 delivery change and becomes
authoritative when that change merges. This acceptance is incremental; it does
not declare every candidate-design example implemented.

## Amendments

| Date | Commit/PR | Summary |
| --- | --- | --- |
| 2026-09-12 | #1204 | Proposed acceptance with bounded compiler/runtime adoption, opt-in joint preparation, prepared portable membership, and the authenticated plan-level profile host. Ratification takes effect on merge. |

## Date

2026-09-05

## Classification

Classification: FM3
Required artifacts: decision record, typed finite reference model, algebraic
checks, explicit abstract transition system, counterexamples, acceptance matrix.
Waivers: The finite reference model is a design oracle, not a proof of arbitrary
backend behavior. The production adoption below selects no new SDL profile
syntax, software-acquisition authoring contract, or global version migration.

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

Accept the design principles in the
[review-1 semantic contract](../../research/partial-description/semantics.md)
and its [executable evidence](../../research/partial-description/verification.md),
with production applicability limited to the explicit adoption records below.
The candidate notation and finite-model behavior are not public SDL syntax.

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

Issue #1204 adopts the recursive contract at the existing compiler, planner,
authenticated provisioning handoff, realization comparison, and safe snapshot
publication boundaries. The carrier retains source-bound leaf domains, local
closure, conditional presence, defaults and author/processor origins. Scalar
defaults do not acquire author authority. Exact siblings remain binding under
open aggregates. Core concerns and admitted standard/private extension values
use the same bounded relation.

Specialized collection profiles retain their native identities: mount target,
published host endpoint, forwarding/listener IDs, and canonical process-limit
selector identity. Capability and mount-option sets use comparison-only scalar
records; finite scalar choices carry explicit collision-free aliases with the
actual value kept separate from its matching identity. These aliases cannot
rename plan-owned resources or permit ambiguous matching. Ordered sequences
remain ordered. Publication uses existing native redaction and payload shapes,
not the comparison-only identities.

`backend-realization-preparation-v1` is the explicit change from full-envelope
coverage admission to admission of one supported completion. An opted-in backend
selects read-only, then the runtime validates the entire proposal before apply
and verifies delivery of those selections afterward. Legacy backends retain
their universal-envelope contract; ADR-070 `subsumes` is unchanged. Additional
portable nodes must be declared in preparation under authenticated, plan-owned
collection authority, with native identity, dependency, semantic, capability,
artifact and observation admission. Internal backend choices are not implicitly
portable resources.

`plan-realization-profiles-v1` is an optional authenticated plan-level host for
pinned definitions and recursive binding constraints. Backend support is pinned
independently and requires installed semantic validation. No new SDL attachment
syntax, executable handler loading from profile data, or opaque execution
fallback is selected.

ASR-532 admission is part of this same execution boundary: resource identity,
domain ownership, submitted operation/target scope, complete transition
accounting, typed carrier histories, and preservation of the immediate trusted
predecessor on rejected successful claims. Credential egress uses the admitted
completion and remains value-free. This does not certify backend honesty,
contain hostile code, roll back infrastructure or authorize execution replay.

The normative contracts are
[preparation](../../../specs/sdl/backend-realization-preparation.md),
[profile carriage](../../../specs/sdl/plan-realization-profiles.md), and
[runtime result admission](../../../specs/formal/runtime-contracts/backend-result-admission.md).
Selection does not create observation, retention or export demand; #1212 and
#1112 continue to own selected demand and required-capture admission. #1205 owns
software acquisition semantics, and #1210 owns program-wide version migration.

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

The #1204 PR review and merge are the ratification record for this adoption.
The earlier design PR remains the record for the finite proposal and evidence.
