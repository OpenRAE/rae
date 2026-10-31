---
id: ACT-617
title: "Mixed-Control Participant Operation"
status: ACTIVE
type: FUNCTIONAL
priority: SHOULD
wave: 3
created_at: 2026-04-03T06:15:08.540051Z
updated_at: 2026-09-22T01:33:58.710054Z
---

# ACT-617 — Mixed-Control Participant Operation

## Statement

The ecosystem shall support participants whose behavior combines autonomous operation with external direction, approval or denial, intervention, handoff, override, or cancellation through explicit controller and authority state and ordered transitions distinct from action admission, execution, and observation.

Authored policy shall distinguish reusable permitted transitions from their
applications. Each application shall bind fresh occurrence and applicable
proposal/target identity, exact prior/resulting state revisions, admitted order,
evaluated validity and evidence. The same edge shall permit repeated cycles in
one episode without weakening exact-state checks. An explicitly finite script
shall constrain applications through the same relation and retain its finite
extent. Source-controller authority and handoff-only controller transfer in the
revised form shall follow MC-01–MC-06 of the canonical amendment below.

## Rationale

Issue #794 found the original mixed-control requirement sound but underspecified: portable behavior needs explicit controller identity, authority basis, validity, ordering, conflict, provenance, and handoff semantics rather than behavior modes or ad hoc overrides.

Issue #1351 identifies fixed traversal revisions/order and proposal references
in the authored graph as a finite-script limitation. Permission must remain
reusable while each occurrence is independently precise and authorized.

## Semantic amendment and evidence boundary

[ADR-110](../../decisions/adrs/adr-110-reusable-mixed-control-policies-and-occurrences.md)
and [MC-01–MC-09](../../../specs/formal/participant-semantics/reusable-mixed-control.md)
define the #1351 amendment. ACTIVE records the accepted contract, not proof
that every amended clause is implemented. Existing code/schema links evidence
the legacy fixed-coordinate form; the new bounded tests evidence a design
projection. Executable adoption and historical readers must meet the
[migration contract](../../migration/reusable-mixed-control.md).

Issue #1363 adds the rev1 authoring form with its validation, composition,
compiled children and an explicit finite-script conversion. Planning and
runtime admission refuse that form, so no executable adoption is claimed.

## Traceability

- IMPLEMENTS → SPEC `specs/formal/participant-semantics/reusable-mixed-control.md` (Reusable permission/application semantic amendment; not runtime conformance)
- IMPLEMENTS → GITHUB_ISSUE `1351` (Semantic decision and canonical requirement amendment)
- DOCUMENTS → DOCUMENTATION `docs/decisions/adrs/adr-110-reusable-mixed-control-policies-and-occurrences.md` (Accepted-on-merge policy/occurrence decision)
- DOCUMENTS → DOCUMENTATION `docs/migration/reusable-mixed-control.md` (Producer/reader and historical-meaning rules)
- DOCUMENTS → DOCUMENTATION `docs/research/reusable-mixed-control/cases.md` (Worked cycles and bounded evidence claims)
- TESTS → TEST `implementations/python/tests/test_issue_1351_mixed_control_design.py` (Bounded abstract-model falsification; not production realization)

- TESTS → TEST `implementations/python/tests/test_issue_1004_apparatus_backend_capabilities.py` (ACT-617 processing-role-trust controller/authority declaration tests)
- DOCUMENTS → GITHUB_ISSUE `794` (Assess and design formal participant I/O control with information-flow and bisimulation semantics)
- DOCUMENTS → DOCUMENTATION `docs/research/participant-io-control/requirement-disposition.md` (Issue #794 participant information-flow/control requirement disposition)
- TESTS → TEST `implementations/python/tests/test_act_617_mixed_control.py` (ACT-617 mixed-control authoring, validation, composition, compiler, and fixture tests)
- DOCUMENTS → DOCUMENTATION `docs/explain/sdl/lineage.md#act-617` (ACT-617 lineage mapping, evidence, status, and non-claims)
- IMPLEMENTS → SPEC `contracts/schemas/sdl/sdl-authoring-input-v1.json` (SDL authoring input mixed-control schema)
- IMPLEMENTS → SPEC `contracts/schemas/sdl/instantiated-scenario-v1.json` (Instantiated scenario mixed-control schema)
- IMPLEMENTS → SPEC `contracts/schemas/sdl/instantiated-scenario-snapshot-v1.json` (Instantiated scenario snapshot mixed-control schema)
- IMPLEMENTS → SPEC `specs/formal/participant-behavior-model/README.md` (ACT-617 mixed-control participant formal semantics)
- IMPLEMENTS → GITHUB_ISSUE `251` (Mixed-Control Participant Operation (ACT-617))

- IMPLEMENTS → GITHUB_ISSUE `1363` (Reusable mixed-control authoring; executable adoption not claimed)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/participant_mixed_control_policy.py` (Rev1 reusable-policy and finite-script authoring models)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/participant_mixed_control_vocabulary.py` (Mixed-control vocabulary shared by both forms)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/validator/_mixed_control_policy.py` (Rev1 semantic validation)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/compiler/_mixed_control_policy.py` (Rev1 compiled children and occurrence-policy projection)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/models/mixed_control_resources.py` (Compiled rev1 policy children)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/mixed_control_migration.py` (Explicit finite-script conversion)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/planner/mixed_control_admission.py` (Backend-agnostic rev1 planning refusal)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/mixed_control_admission.py` (Reference-runtime rev1 admission and construction refusal)
- DOCUMENTS → DOCUMENTATION `docs/migration/mixed-control-finite-script-conversion.md` (Finite-script conversion record)
- TESTS → TEST `implementations/python/tests/test_issue_1363_mixed_control_authoring.py` (Rev1 authoring, validation, composition and compiler tests)
- TESTS → TEST `implementations/python/tests/test_issue_1363_schema_parity.py` (Python and published-schema parity for the rev1 shapes)
- TESTS → TEST `implementations/python/tests/test_issue_1363_mixed_control_migration.py` (Finite-script conversion and bounded legacy differential)
- TESTS → TEST `implementations/python/tests/test_issue_1363_delivery_and_admission.py` (Rev1 planning, admission and construction refusals)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/_language_metadata.py` (Shared mixed-control reference domains for completion and navigation)
- TESTS → TEST `implementations/python/tests/test_issue_1363_identity_integration.py` (Canonical identity integration across control forms and editor references)
- TESTS → TEST `implementations/python/tests/test_issue_1363_projection_integration.py` (Canonical semantic-only and runtime authority anchors in both rev1 forms)
