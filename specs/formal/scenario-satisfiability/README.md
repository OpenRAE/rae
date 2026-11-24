# Scenario satisfiability

This specification defines the normative v1 whole-scenario satisfiability
boundary adopted by ADR-086. The keywords MUST, MUST NOT, SHALL, and SHOULD are
normative.

## Profile identity and phase

The analysis profile `raes-finite-domain-satisfiability-v1` SHALL mean exactly:

```text
theory_profile      = raes-finite-domain-theory/v1
translation_profile = raes-sdl-authoring-translation/v1
solver_profile      = raes-z3-finite-domain/v1
```

The input SHALL be a composed authoring `Scenario` that parsed successfully
and passed semantic validation. Analysis SHALL occur before variable
instantiation, planning, and backend realization. The root source SHALL be read
with `SDLParserLimits` before UTF-8 decoding. The analyzer SHALL bind the exact
source bytes and the canonical authored semantics.

## Finite-domain model

Let `S` be a finite, canonically ordered set of symbols. Each symbol `s` has one
sort in `{string, integer, boolean}` and a finite domain `D(s)`.

Let `C` be a canonically ordered set of named clauses. Each clause is a tuple:

```text
(clause_id, kind, symbol_id, source_address, allowed_values)
```

where `kind` is `declared-domain` or `target-domain`, and
`allowed_values` is a subset of `D(s)`. A binding `b` satisfies the normalized
model iff:

```text
for every c in C: b(c.symbol_id) is in c.allowed_values
```

Empty target domains are valid clauses and make the model unsatisfiable.
Symbols, clauses, domains, and clause values MUST be unique and use canonical
RFC 8785 scalar order. Bounds are 128 symbols, 256 domain members per symbol,
and 512 clauses.

## Translation coverage

Required or referenced string and integer variables MUST declare finite
`allowed_values`. A Boolean variable MAY omit `allowed_values`, in which case
its domain is canonically `(false, true)`. Number variables are unsupported.

The translation SHALL recognize only whole-token occurrences `${name}` at:

| Authoring address | Required sort | Target membership |
|---|---|---|
| `/nodes/<id>/os` | string | normalized `OSFamily` values |
| `/infrastructure/<id>/acls/<n>/action` | string | normalized `ACLAction` values |
| `/infrastructure/<id>/count` | integer | values greater than or equal to one |
| `/infrastructure/<id>/properties/internal` | boolean | the declared Boolean domain |

The translator SHALL recursively inspect every other authored scenario field.
It excludes the variable declarations, import declarations, module marker, and
expansion-provenance carrier. The translator SHALL produce a stable
`unsupported` diagnostic for each of these conditions: an embedded occurrence,
an unsupported sort, an unbounded domain, an unrecognized address, a missing
symbol, or an exceeded resource bound. No occurrence may be silently dropped.

## Solver semantics

The v1 adapter SHALL use these settings:

- Z3 package `4.16.0.0` and engine `4.16.0`;
- logic `QF_LIA` and seed zero;
- operation timeout 5000 ms and one thread;
- automatic configuration disabled; and
- model and unsat-core production enabled.

Scalar domain members SHALL be encoded as integer indices. The published solver
configuration SHALL contain each of these settings and be digest-bound.

Every solver check MUST complete with `sat` or `unsat` before it contributes to
a completed outcome, a witness-selection claim, or a core-reduction claim. Empty
membership clauses MUST be explicitly asserted as false. The adapter MUST reject
duplicate clause ids before it constructs tracked assumptions. The normalized
model contract also forbids them, but this check is a defensive measure.

One analysis MUST construct one expression graph and query it incrementally.
The 5000 ms monotonic deadline covers expression construction, all repeated
checks, and deterministic witness or core selection. Each native check receives
at most the remaining operation time. A result that returns after the deadline
is an operational failure.

For symbols `S`, domains `D(s)`, and clauses `C`, one analysis has the derived
check budget:

```text
B = 1 + max(|C|, sum(|D(s)| for s in S))
```

The initial decision consumes one check. Then only witness selection or core
reduction runs. Witness selection consumes at most one check per domain member.
Core reduction consumes at most one check per clause. Exhausting this derived
budget is an operational failure. On its operational-error boundary, the
reference implementation SHALL preserve the phase, check count, check budget,
5000 ms operation timeout, and bounded solver reason. It SHALL NOT emit partial
evidence.

For a satisfiable model, the witness SHALL select the first feasible value for
each symbol in canonical symbol and domain order. It keeps the previous choices.
The resulting binding SHALL pass normal scenario instantiation and admission. It
SHALL be published as the canonical instantiated-scenario snapshot and digest.

For an unsatisfiable model, the adapter SHALL start from all canonical clause
ids. In sorted order, it SHALL remove each clause if the remainder stays
unsatisfiable. The final sorted set is subset-minimal under that deletion
procedure. It MUST be named an unsatisfiable core. It is not a proof certificate
or a globally minimum core.

Solver `unknown`, timeout, package/profile mismatch, and internal failure SHALL
be operational failures. They MUST NOT be labelled `unsupported`.

## Evidence and replay

The published `scenario-satisfiability-evidence-v1` contract SHALL bind:

1. portable source id and exact root-byte SHA-256;
2. canonical authored semantic digest and import provenance;
3. the normalized model and its RFC 8785 SHA-256;
4. the exact solver configuration and its RFC 8785 SHA-256;
5. exactly one of a witness, unsatisfiable core, or unsupported disclosure; and
6. stable, value-free diagnostics.

Replay SHALL verify the exact source-byte digest. Then it SHALL recompute the
full evidence envelope with the analysis profile of the evidence. Any mismatch
SHALL fail. Evidence models SHALL reject unknown fields and inconsistent
cross-object joins.

## Claims and nonclaims

The executable corpus contains satisfiable, unsatisfiable, and unsupported
controls. Passing replay demonstrates the implementation's result for this
finite profile and the pinned artifacts only.

It does not demonstrate these properties:

- satisfiability of arbitrary SDL;
- translation completeness outside the table;
- backend realizability or execution success;
- exploit-path validity or temporal properties;
- uniqueness or optimality;
- independent verification of Z3 proofs; or
- universal soundness or completeness.

A change to any of these items requires a new governed profile or version:
sorts, targets, theories, encodings, solver versions, witness orders, core
algorithms, or evidence meaning.

## Evidence v2

Evidence v2 corrects Python's workflow-field serialization. New service and CLI
results SHALL use `scenario-satisfiability-evidence/v2`. A satisfiable result
SHALL use witness profile `raes-satisfiability-witness/v2` and snapshot profile
`raes-sdl-instantiated-snapshot/v3`. The snapshot SHALL serialize public SDL
names, including `then`, `else` and `default`. Its digest SHALL bind that exact
serialized snapshot, including its profile.

The analysis, theory, translation, budgets and outcome meanings above remain
unchanged. The solver configuration SHALL select one complete published Python
v1 or Go v2 adapter identity. A mixed adapter identity is invalid.

The published schema is `scenario-satisfiability-evidence-v2`. The standalone
snapshot schema is `instantiated-scenario-snapshot-v2`. Existing v1 evidence
and snapshot contracts retain their historical meanings. Readers SHALL select
contracts by explicit version. Re-running an analysis creates new v2 evidence;
it does not rewrite stored v1 evidence or retain its digest.

See [the migration guide](../../../docs/decisions/issue-1789-evidence-v2-migration.md)
for the public identifiers and Python and Go type names.
