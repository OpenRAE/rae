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

This file holds the rules. The 90 rows are in five files, each small enough to
review on its own:

| Part | Rows | Clauses |
| --- | --- | --- |
| [design-commitments-sem-208-to-211.md](semantic-coverage/design-commitments-sem-208-to-211.md) | 20 | SEM-208.C1 to SEM-211.C3 |
| [design-commitments-sem-212-to-215.md](semantic-coverage/design-commitments-sem-212-to-215.md) | 23 | SEM-212.C1 to SEM-215.C8 |
| [invariants-i1-to-i18.md](semantic-coverage/invariants-i1-to-i18.md) | 18 | I1 to I18 |
| [behavior-model-and-runtime.md](semantic-coverage/behavior-model-and-runtime.md) | 16 | PBM-01 to PBM-13, PRT-07, PRT-09, PRT-10 |
| [family-rows.md](semantic-coverage/family-rows.md) | 13 | SEM-214.F to DSL-437.F |

`implementations/python/tests/test_issue_219_participant_semantic_coverage.py`
reads every part. It checks the matrix against the tree in both directions:
every clause has a row, every row resolves to a clause, and every cited path,
test function, requirement, and relation exists. It also checks that this
file lists each part with its row count, and that the open-row table below
matches the parts. Whether a cited test exercises the whole clause is a review
judgment.

## Scope

- **Clause rows.** The "Design commitments" bullets of SEM-208, SEM-209,
  SEM-210, SEM-212, SEM-213, and SEM-215; the SEM-211 precondition, effect, and
  failure groups; invariants I1 to I18; and the behavior-model cross-clause
  invariants PBM-01 to PBM-13. Clause IDs such as `SEM-208.C1` exist only here
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
  `SEM-232.F` names seven, `SEM-235.F` names three, and
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

## Current decision and implementation crosswalk

This crosswalk records current decisions without changing accepted ADR content or pins.
ADR-067 and ADR-083 remain proposed. ADR-095 supplies the accepted executable decision-surface amendment.
The [revised-control reference](../../../docs/explain/reference/revised-control-semantics.md) describes current installed paths and refused combinations.
Its [support table](../../../docs/explain/reference/revised-control-semantics.md#supported-arrangements) is bounded RAE evidence through controlled providers.
Acceptance of a decision does not establish backend installation, native qualification, or universal equivalence.

ADR file and normative paths below are repository-relative.
Evidence names resolve to functions under `implementations/python/tests/`.
The evidence classes remain those defined above; a crosswalk reference adds no stronger assurance claim.

| Decision | ADR file | Status | Normative surface | Evidence |
| --- | --- | --- | --- | --- |
| `ADR-067` | `docs/decisions/adrs/adr-067-participant-behavior-model.md` | proposed | `specs/formal/participant-behavior-model/README.md`: ACT-606 aggregate, ACT-609/610 external classifications; current closed authoring fields | `test_sem_208_participant_behavior.py::test_behavior_classifications_require_external_binding_migration` |
| `ADR-083` | `docs/decisions/adrs/adr-083-participant-tool-decision-surface-and-exposure-semantics.md` | proposed | `specs/formal/participant-semantics/README.md`: SEM-219/220/226 design and joint clause matrix | `test_sem_220_participant_decision_surface.py::test_selection_must_be_a_candidate_member` |
| `ADR-095` | `docs/decisions/adrs/adr-095-participant-decision-epoch-state-cut-and-delivery-semantics.md` | accepted | `specs/formal/participant-semantics/README.md`: SEM-220 historical v1 versus actionable v2; distinct epoch, cut, digest and delivery facts | `test_sem_220_participant_decision_surface_v2_runtime.py::test_initial_epoch_projects_delivers_and_admits_only_the_exact_view` |
| `ADR-108` | `docs/decisions/adrs/adr-108-modular-participant-control-and-governed-effects.md` | accepted | `specs/formal/participant-semantics/modular-participant-control.md`: SEM-235 declared-world boundary, typed mechanisms and independent effect owners | `test_issue_1071_effect_conformance.py::test_missing_or_contradictory_owner_readback_fails` |
| `ADR-109` | `docs/decisions/adrs/adr-109-participant-identity-and-objective-assignment.md` | accepted | `specs/sdl/participant-identity.md`: PI-01–PI-09; participant identity, affiliation, effective role, owner and assignment remain separate | `test_issue_1338_participant_identity.py::test_shared_affiliation_does_not_merge_identity_or_assign_objectives` |
| `ADR-110` | `docs/decisions/adrs/adr-110-reusable-mixed-control-policies-and-occurrences.md` | accepted | `specs/formal/participant-semantics/reusable-mixed-control.md`: MC-01–MC-09; reusable permission versus immutable API-409 v2 occurrences, original-policy replay | `test_issue_1364_reusable_runtime.py::test_four_handoffs_reuse_two_edges_in_one_running_episode` |
| `ADR-111` | `docs/decisions/adrs/adr-111-control-applicability-and-effect-decisions.md` | accepted | `specs/formal/participant-semantics/control-applicability-and-evaluation.md`: CA-01–CA-09; complete coverage, required dependency closure, optional advice and commit before dispatch | `test_issue_1352_control_applicability.py::test_missing_and_unresolved_coverage_never_become_empty_success`, `test_issue_1071_modular_conformance.py::test_optional_failure_has_no_veto` |
| `ADR-112` | `docs/decisions/adrs/adr-112-external-inject-triggering-and-execution.md` | accepted | `specs/sdl/external-injects.md`: EI-01–EI-06; participant-free world effects, independent occurrence/result and optional delivery/observation | `test_issue_1353_external_inject_design.py::test_researcher_claim_needs_no_participant_or_control_occurrence`, `test_issue_1368_inject_delivery.py::test_public_delivery_requires_an_installed_owner_and_does_not_refire_world` |
| `ADR-113` | `docs/decisions/adrs/adr-113-reusable-execution-machinery.md` | accepted | `specs/sdl/execution-recovery.md`: reused machinery retains RAE admission, identity, effect ownership, recovery and time authority | `test_issue_1369_effect_recovery.py::test_owner_applied_before_outcome_commit_is_observed_without_redispatch` |
| `ADR-114` | `docs/decisions/adrs/adr-114-ifc-profile-variability-and-publication.md` | accepted | `specs/formal/participant-semantics/ifc-profile-variability.md`: IFC-01–IFC-07; authored guarantees, finite profile expressibility and evidenced realization | `test_issue_1354_ifc_profile_variability.py::test_finite_owner_encoding_admits_only_evidenced_coverage`, `test_issue_1370_ifc_runtime.py::test_live_owner_sink_allows_selective_sharing_and_blocks_other_owner_release` |
| `ADR-115` | `docs/decisions/adrs/adr-115-concrete-backends-owned-outside-raes.md` | accepted | `specs/formal/participant-semantics/participant-crossing-runtime-mapping.md`: portable runtime mapping with explicit producer/profile limits; concrete backend ownership remains external | `test_issue_1017_mixed_backend_conformance.py::test_a_backend_that_only_claims_the_capability_fails` |

API-409 occurrence v2, API-424 evaluation v2, and decision-surface v2 have independent reader and semantic lineages.
Historical records retain their original policy, identity, consumed budgets, provenance, and outcome.
V1 `observation_order` selects a supplied behavior-history occurrence. It is not a v2 decision epoch.
V2 admission requires trusted reprojection and the exact delivered view; renaming a field supplies neither.
Projection, disclosure, delivery, observation, selection, admission, execution, and outcome remain distinct facts.
The [v2 migration reference](../../../docs/explain/reference/participant-decision-surface-v2-migration.md) retains the reader and admission boundary.
Author-facing identity and migration guidance remains #1342's responsibility; the executable conformance corpus remains #220's.

## Open rows

Of the 90 rows, 66 are `covered` and 24 are `partial`; none is `uncovered`.
This table lists the owners of the 25 open rows. Each part records evidence and a concrete acceptance test.

| Clause | Part | Owner(s) |
| --- | --- | --- |
| `PBM-06` | behavior-model-and-runtime.md | #222 |
| `PBM-07` | behavior-model-and-runtime.md | #220 |
| `PBM-08` | behavior-model-and-runtime.md | #222 |
| `PRT-07` | behavior-model-and-runtime.md | #220 |
| `PRT-09` | behavior-model-and-runtime.md | #1512 |
| `SEM-208.C6` | design-commitments-sem-208-to-211.md | #257 |
| `SEM-209.C4` | design-commitments-sem-208-to-211.md | #222 |
| `SEM-209.C5` | design-commitments-sem-208-to-211.md | #1555 |
| `SEM-213.C2` | design-commitments-sem-212-to-215.md | #254 |
| `SEM-214.F` | family-rows.md | #1512 |
| `SEM-219-220-226.F` | family-rows.md | #1570, #1571, #1572 |
| `SEM-231.F` | family-rows.md | #222 |
| `SEM-232.F` | family-rows.md | #974, #973, #975, #976 |
| `SEM-234.F` | family-rows.md | #608, #222 |
| `ACT-617.F` | family-rows.md | #1583 |
| `I1` | invariants-i1-to-i18.md | #257 |
| `I3` | invariants-i1-to-i18.md | #1595 |
| `I11` | invariants-i1-to-i18.md | #222 |
| `I12` | invariants-i1-to-i18.md | #222 |
| `I13` | invariants-i1-to-i18.md | #1595 |
| `I15` | invariants-i1-to-i18.md | #106 |
| `I16` | invariants-i1-to-i18.md | #328, #106 |
| `I17` | invariants-i1-to-i18.md | #106, #328 |
| `I18` | invariants-i1-to-i18.md | #221 |
