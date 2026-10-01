# Control applicability: worked cases and evidence limits

Authority: [ADR-111](../../decisions/adrs/adr-111-control-applicability-and-effect-decisions.md)
and [CA-01–CA-09](../../../specs/formal/participant-semantics/control-applicability-and-evaluation.md).
These are semantic-design cases. They do not report deployed-provider behavior.

## Cases

**A — One apparatus, disjoint sinks.** B admits ingress provider A and egress
provider B. At ingress cut K0, the ingress obligation maps to A's fact slot and
the egress obligation has profile-owned inapplicability evidence. Invoke A,
retain both providers in B, and record the complete coverage. At egress K1,
resolve coverage again and invoke B. Filtering B and comparing the filtered
digest to the admitted digest fails this case; retaining B but requiring every
binding to match both sinks also fails it.

**B — Nothing returned versus nothing required.** A required profile applies
at K0 but maps to no slot: coverage is unresolved and the parent cannot release.
A resolver returning no request gives no contrary evidence. If the profile's
trusted relation proves it inapplicable at K0, no slot is needed. Even that
valid empty evaluation cannot override a failed incumbent authority gate.
K0's proof does not establish non-applicability at K1.

**C — A → B → A.** A resolves influence; B receives that exact fact and emits
an advisory assessment; A's rule receives that exact assessment and decides.
The rule's availability dependency makes B's valid input required. B's negative
opinion is not a veto: the admitted rule can permit. Missing B prevents the
rule from running successfully. Calling A and B once each with the same empty
predecessor request cannot produce this relation. Independent input order
changes no result, but dependencies still constrain invocation.

**D — Optional failure without permission.** An optional monitor outside M
times out, returns a wrong slot/cut/kind, raises a private error or has no
supported implementation. Record safe lost advice and omit its state/effects;
the mandatory plan is unchanged. If a mandatory rule needs its input, loss
blocks that rule. A malformed shared apparatus or forged global authority is
not an optional provider failure. Optional conflicting routes are omitted;
they cannot block a mandatory route through shared conflict accounting.

**E — Support against a requirement.** An evidenced one-unit loss satisfies a
compatible admitted bound of two units. It fails an exact zero-loss
requirement; two units fail a one-unit requirement. Missing evidence fails.
These numbers are one toy dimension, not API-407's general support ranking.
An authorization to change requirements cannot make the old requirement true.

**F — False trigger.** A mandatory teaching rule evaluates valid influence
but its condition is false. Its explicit not-triggered result satisfies rule
evaluation and requests no inject. An omitted rule result or an exception does
not establish a false trigger. Original teaching-domain propagation and memory
rules remain unchanged.

**G — Denial is not a later operation.** A mandatory parent denial is encoded
with predecessor, subsequent or independent phase in a legacy-shaped
counterexample. The conservative semantic projection is deny in every case;
the new live contract uses an unscheduled decision. Withhold likewise never
becomes permit. A prerequisite awaiting review must not downgrade deny to
withhold. This projection is a design witness, not a historical wire rewrite.

**H — Audit of denial.** A rule permits a bounded audit for a denied parent.
Commit the deny and separately admitted audit intent. Deny remains final for
that candidate. No audit dispatch is eligible without its own authority,
support, target and allowed-trigger disposition. Audit failure cannot promote
or reverse the parent. Subject-visible audit existence still needs projection.

**I — Review before release, consequence after application.** A parent that
otherwise permits requests required review and a post-application follow-up.
It is withheld while review is pending. Successful review permits a fresh
evaluation, never automatic release; a new denial still blocks. The follow-up
waits for the actual parent-application receipt, not merely the evaluation's
commit. If review itself waits for parent success, the combined graph cycles
and must be rejected. An optional follow-up failure does not undo application.

**J — State and commit.** Two participants have separate state cells despite
using one implementation. An admitted evaluation-state update may commit with
deny; a parent-release update may not. Competing unordered writes to one cell
conflict in either order. A stale expected head or failed commit publishes
none of the cells, decision or intents. Ordered tentative-state chains require
the explicit dependency extension; the bounded model deliberately exercises
the conservative conflict alternative only.

**K — Archive and adoption.** Retain a v1 evaluation and its original claims,
budget consumption and receipts. An amended reader selects its original
interpretation; it cannot infer missing coverage, produce a new denial record,
or release a formerly unapplied effect through a new reducer. A producer using
the amendment requires negotiated reader/protocol support. Unsupported or
unverifiable archives remain preserved and explicitly limited. This case is a
normative migration walkthrough; no new wire/store reader ships here.

## Verification map

The finite model reuses `sem235_modular_control_model.Result`, `Slot` and
`compose` for typed satisfaction. It adds a bounded invocation/coverage
projection and separate parent/effect and atomic-state relations. The new
module is `implementations/python/tests/control_applicability_model.py`; its
property cases are `test_issue_1352_control_applicability.py` in the same directory.

| Clause / acceptance | Artifact and evidence |
| --- | --- |
| #1352 AC1; SEM-235 applicability/coverage | CA-01; cases A/B; disjoint-sink and missing/unresolved-coverage tests. |
| #1352 AC2; SEM-235 dependency/state/commit; API-424 input contract | CA-02/05/08; cases C/F/J; permutation, immutable-input, false-trigger, graph and atomic-commit tests. |
| #1352 AC3; parent/effect meaning and phase | CA-06/07; cases G/H/I; six phase/decision combinations, independent-audit and combined-cycle tests. |
| #1352 AC4; mandatory closure, optional failure and support | CA-03/04; cases C/D/E; six optional-failure variants and five support-bound combinations. |
| #1352 AC5; canonical publication and migration | ADR-111, ADR-108 explicit amendment, both requirement records, CA-09 and the migration contract; case K is a specification walkthrough, not tested reader adoption. ADR pins and requirement-scope checks validate publication structure. |
| SEM-235 retained domains, orders, joins, propagation, memory, releases, provenance, freshness, budgets and world boundary | Original MPC-04/08–15 and `test_sem_235_modular_control.py`; the amendment explicitly preserves those clauses. |
| API-424 retained closed contracts, exact bindings, typed status/effects, no executable authority and separation of declaration/realization | Original reference contract and published v1 models; `test_api_424_composition_derivation.py` remains a bounded legacy consistency witness. Migration requires consumer-level evidence for amended fields and joins. |

The initial red run produced 24 failures and two passing boundary cases against
an empty model relation. The implemented relation passes all 26 cases.
The preserved SEM-235/API-424 baseline passed 47 tests. This records development
evidence, not a general proof or a claim that a production defect is repaired.

The model assumes trusted profile applicability, resolved complete K,
authorized projected input, scalar support evidence and exact owner receipts.
Immutable replacement assumes local atomicity. It bounds invocation graphs to
16 nodes and uses finite test inputs and permutations. It does not implement
wire parsing, real providers, concurrent stores, ordered shared-state chains,
optional effect-conflict selection, cross-store transactions or migration
readers. Those obligations remain normative and require the real-consumer
evidence specified by the migration contract before adoption is claimed.
