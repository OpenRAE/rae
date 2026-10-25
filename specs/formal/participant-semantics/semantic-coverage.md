# Participant Semantic Coverage Matrix

Issue #219 and ASR-506. This matrix is a coverage index, not a focused
specification. It adds no semantics. The normative text stays in the
[participant-semantics design](README.md) and its focused specifications, the
[participant behavior model](../participant-behavior-model/README.md), and the
[participant runtime design](../participant-runtime/README.md).

For each row the matrix records the requirement, the normative location, the
contract, the implementation, the tests, the class of that evidence, the
resulting coverage, and, for every row that is not `covered`, the open issue
that owns the gap and the test that would close it. When an owner lands, its PR
updates the row. ADR-022's "Cross-Issue Boundaries And Evidence Ownership"
owner table is acceptance-time text pinned under ADR-059 §1 (any edit needs an
ADR-059 §3 amendment record), so it keeps the owners named at acceptance. This
matrix, not that table, records the current open owner of each gap.

## Parts

This file holds the rules. The 89 rows are in five files, each small enough to
review on its own:

| Part | Rows | Clauses |
| --- | --- | --- |
| [design-commitments-sem-208-to-211.md](semantic-coverage/design-commitments-sem-208-to-211.md) | 20 | SEM-208.C1 to SEM-211.C3 |
| [design-commitments-sem-212-to-215.md](semantic-coverage/design-commitments-sem-212-to-215.md) | 23 | SEM-212.C1 to SEM-215.C8 |
| [invariants-i1-to-i18.md](semantic-coverage/invariants-i1-to-i18.md) | 18 | I1 to I18 |
| [behavior-model-and-runtime.md](semantic-coverage/behavior-model-and-runtime.md) | 15 | PBM-01 to PBM-12, PRT-07, PRT-09, PRT-10 |
| [family-rows.md](semantic-coverage/family-rows.md) | 13 | SEM-214.F to DSL-437.F |

`implementations/python/tests/test_issue_219_participant_semantic_coverage.py`
reads every part and checks the matrix against the tree in both directions:
every clause has a row, every row resolves to a clause, and every cited path,
test function, requirement, and relation exists. It also checks that this
file lists each part with its row count and that the open-row table below
matches the parts. Whether a cited test exercises the whole clause is a review
judgment.

## Scope

- **Clause rows.** The "Design commitments" bullets of SEM-208, SEM-209,
  SEM-210, SEM-212, SEM-213, and SEM-215; the SEM-211 precondition, effect, and
  failure groups; invariants I1 to I18; and the behavior-model cross-clause
  invariants PBM-01 to PBM-12. Clause IDs such as `SEM-208.C1` exist only here
  and follow bullet order. The normative bullets are not renumbered.
- **Family rows** (`.F`). One row for each `## SEM-…` README section without
  clause rows, and one for each focused-specification requirement family with
  no README section (SEM-234, SEM-235, ACT-617, ACT-618, and DSL-437), for 13
  rows. SEM-219, SEM-220, and SEM-226 share one joint row, which points to
  the README's ADR-083 §7 "Source-to-contract-to-test matrix" instead of
  restating it, so no clause has two clause matrices. Rows follow requirement
  families, not files. Every focused specification (every top-level `*.md` in
  this directory other than `README.md` and this index) is named in the
  normative location of at least one family row, and one row can name several:
  `SEM-232.F` names three, `SEM-235.F` names three, and
  `ifc-profile-variability.md` appears in both `SEM-233-ASR-536.F` and
  `SEM-235.F`. Every UID in the README's declared scope list appears in at
  least one row's requirement cell.
- **Participant-runtime rows.** PRT-07, PRT-09, and PRT-10 of the runtime
  design's "V1 Traceability Criteria Matrix" (visibility, shared state, and
  concurrency/time), with that design's declared scope as requirements.

Requirement cells come from existing sources only: a README heading's own UIDs,
each focused specification's own requirement line or requirement headings, the
invariant oracle's slice references for I-rows, the "Primary clauses" cell for
PBM rows, and the runtime design's scope list for PRT rows.

## Columns and conventions

Facet is one of `behavior`, `interaction`, `visibility`, `timing`,
`causality`, or `outcomes` (the ASR-506 and #219 facets). Excerpts are verbatim
prefixes of the clause text with Markdown code marks removed. Normative
location and contract paths are repository-relative. Implementation paths are
relative to `implementations/python/packages/`. Test references are
`<file>::<function>` (or `<file>::<Class>::<function>`) relative to
`implementations/python/tests/`, grouped by evidence class; a `proof` entry is a
repository-relative path. A dash means none.

## Evidence classes

The class set is closed. A class is a property of the cited evidence, never
derived from a catalog status, and no class promotes another (ADR-081
Decision 4).

- `executable-invariant`: a predicate executed over a test-local or abstract
  model, including named finite cases that do not drive shipped package code
  (for example the I1-I18 oracle).
- `bounded-model-check`: a pinned finite model exhaustively explored within
  declared bounds. This is the ADR-081 model-check axis only; named finite cases
  never get this class.
- `runtime-test`: a finite test that drives shipped code (parser, validator,
  compiler, contracts, processor checkers, runtime, or backend). ADR-081
  runtime-enforcement and backend-conformance evidence is always this class.
- `proof`: an independently checked proof (ADR-081 proof axis), such as the
  SEM-231 Isabelle theory pinned in `participant-opacity-proof-evidence.json`.

Finite runtime evidence does not establish a universal relation or a
hyperproperty (ADR-081 Decision 5). A row is an **unproved claim** exactly when
its evidence class cell contains no `proof`. Being unproved is not being
uncovered, so unproved rows need no owner.

Crosswalk to the ADR-081 axes in `specs/formal/behavioral-relations/README.md`:
"bounded model checks" are the model-check axis ("Was a pinned finite model
exhaustively explored within declared bounds?"); "runtime tests" are the
runtime-enforcement and backend-conformance axes ("Does the reference runtime
mediate every declared observation channel?", "Did the named realization pass
bounded adversarial cases?") plus any other test of shipped code; "unproved
claims" are rows without `proof` evidence (the proof axis, "Is a universal
obligation independently proved?", answered per row). Checker and bounded-test
evidence is finite executable evidence whose class depends on the code it
drives. Relation-bound family rows name the catalog relation and restate no
axis status: `contracts/concept-authority/behavioral-relations-v1.json` remains
the only record of those axes.

## Coverage rule

- `covered`: a contract, an implementation, and at least one `runtime-test`
  whose assertions exercise the whole clause.
- `partial`: some evidence is cited but `covered` fails (only
  `executable-invariant`, `bounded-model-check`, or `proof` evidence, only
  schema or authoring acceptance, evidence for part of the clause, or an open
  in-scope defect).
- `uncovered`: no contract, implementation, or test is cited.

Family rows apply the same rule to the family's own claims, read from the
focused specification's verification record plus the #219 audit. Every
`partial` or `uncovered` row names an open owner issue and a target acceptance
test with the behavior it must assert; that test need not exist yet.

A `partial` or `uncovered` row counts against every
[family status row](../../../docs/explain/reference/shared-semantic-integrity.md)
whose owning requirements include one of its requirements, unless the README
itself assigns the missing part to another owner (the "Cross-Issue Coverage And
Deferrals" table outside its duty cell, or a section's own deferral sentence).
Such a row says "deferred" and quotes the assignment.

## Open rows

Of the 89 rows, 61 are `covered` and 28 are `partial`; none is `uncovered`.
This table lists the owners of the 28 open rows; the part file holds each
row's evidence, any quoted README deferral, and the acceptance test.

| Clause | Part | Owner(s) |
| --- | --- | --- |
| `SEM-208.C6` | design-commitments-sem-208-to-211.md | #257 |
| `SEM-209.C4` | design-commitments-sem-208-to-211.md | #222 |
| `SEM-209.C5` | design-commitments-sem-208-to-211.md | #1555 |
| `SEM-213.C2` | design-commitments-sem-212-to-215.md | #254 |
| `I1` | invariants-i1-to-i18.md | #257 |
| `I3` | invariants-i1-to-i18.md | #1595 |
| `I11` | invariants-i1-to-i18.md | #222 |
| `I12` | invariants-i1-to-i18.md | #222 |
| `I13` | invariants-i1-to-i18.md | #1595 |
| `I15` | invariants-i1-to-i18.md | #106 |
| `I16` | invariants-i1-to-i18.md | #328, #106 |
| `I17` | invariants-i1-to-i18.md | #106, #328 |
| `I18` | invariants-i1-to-i18.md | #221 |
| `PBM-06` | behavior-model-and-runtime.md | #222 |
| `PBM-07` | behavior-model-and-runtime.md | #220 |
| `PBM-08` | behavior-model-and-runtime.md | #222 |
| `PRT-07` | behavior-model-and-runtime.md | #220 |
| `PRT-09` | behavior-model-and-runtime.md | #1512 |
| `SEM-214.F` | family-rows.md | #1512 |
| `SEM-219-220-226.F` | family-rows.md | #1570, #1571, #1572 |
| `SEM-230.F` | family-rows.md | #972 |
| `SEM-231.F` | family-rows.md | #1374 |
| `SEM-232.F` | family-rows.md | #974, #972, #973, #975, #976 |
| `SEM-233-ASR-536.F` | family-rows.md | #1007, #1008 |
| `SEM-234.F` | family-rows.md | #1017, #1018 |
| `SEM-235.F` | family-rows.md | #1071 |
| `ACT-617.F` | family-rows.md | #1583, #1369 |
| `DSL-437.F` | family-rows.md | #1439 |
