---
id: DSL-142
title: "Participant-Directed Inject Binding And Delivery"
status: ACTIVE
type: FUNCTIONAL
priority: MUST
wave: 3
created_at: 2026-07-15T05:45:06.862070Z
updated_at: 2026-09-22T05:55:00Z
---

# DSL-142 — Participant-Directed Inject Binding And Delivery

## Statement

The language shall model participant-directed inject bindings and delivery policies distinctly from environment-directed injects while preserving orchestration identity, participant addressee, disclosure and observation basis, temporal and ordering semantics, intervention meaning when applicable, and required delivery evidence.

Reusable direction/intervention declarations shall constrain a permitted
control-policy edge; each actual delivery application shall bind an exact
accepted control occurrence identity/revision, participant/episode, typed target,
acting source controller, authority scope, evaluated validity and evidence.
Delivery and control policies shall retain independent identities/revisions,
and delivery shall revalidate disclosure/time/flow conditions at its own cut.
Each occurrence/binding pair shall authorize at most one logical delivery with
idempotent retries. Repetition shall not imply repeated narrative/environment
effects, renewed authority or proof of delivery/observation. General injects,
disclosure-only bindings and authenticated principals shall not thereby become
participant controllers. Legacy bindings retain their original interpretation.

When composed with an externally triggered world effect, participant delivery
shall join its exact occurrence and produced result, independently of world
admission and execution evidence. Delivery reservation and retries shall not
re-execute the effect or infer observation. An applied world effect shall remain
applied after delivery failure; required delivery shall withhold composed
success and dependent progress until independently evidenced. A schedule-free
external occurrence shall require an explicitly supported versioned delivery
join, without fabricating or relaxing legacy narrative anchors.

## Rationale

DSL-111 models orchestration injects and timelines but does not define participant addressees, governed disclosure, delivery receipts, or the boundary between environment effects and participant input.

Issue #1351 distinguishes a reusable permission from its repeated applications
and resolves controller, policy-revision, time and evidence joins without
promoting general orchestration into participant control.

## Semantic amendment and evidence boundary

[ADR-110](../../decisions/adrs/adr-110-reusable-mixed-control-policies-and-occurrences.md)
and [MC-01–MC-09](../../../specs/formal/participant-semantics/reusable-mixed-control.md)
define the #1351 amendment. ACTIVE records the accepted contract, not proof
that every amended clause is implemented. Existing code/schema links evidence
the legacy fixed-coordinate form; the new bounded tests evidence a design
projection. Executable adoption and historical readers must meet the
[migration contract](../../migration/reusable-mixed-control.md).

[ADR-112](../../decisions/adrs/adr-112-external-inject-triggering-and-execution.md)
and [EI-05](../../../specs/sdl/external-injects.md#ei-05--optional-participant-composition)
add #1353's world-effect/delivery composition boundary. They preserve ADR-110's
exact accepted-control join and independent policies. The
[external-inject compatibility contract](../../explain/sdl/external-inject-compatibility.md)
governs adoption; the amendment and its bounded witnesses do not certify live
backend execution, delivery or observation.

## Traceability

- IMPLEMENTS → SPEC `specs/sdl/external-injects.md` (Exact world-occurrence/result delivery join; not runtime conformance)
- IMPLEMENTS → GITHUB_ISSUE `1353` (External world-effect and participant-delivery semantic boundary)
- DOCUMENTS → DOCUMENTATION `docs/decisions/adrs/adr-112-external-inject-triggering-and-execution.md` (Accepted-on-merge execution decision)
- DOCUMENTS → DOCUMENTATION `docs/explain/sdl/external-inject-compatibility.md` (Versioned unscheduled joins and preserved historical meaning)
- DOCUMENTS → DOCUMENTATION `docs/explain/sdl/external-inject-cases.md` (Independent effect, delivery and observation outcomes)
- TESTS → TEST `implementations/python/tests/test_issue_1353_external_inject_design.py` (Bounded delivery reservation/composition projection; not delivery realization)
- TESTS → TEST `implementations/python/tests/test_issue_1313_workflow_policy.py` (Merged delivery finalizer permission boundary)
- TESTS → TEST `implementations/python/tests/test_release_workflows.py` (Merged delivery finalizer job token scope and event classification)

- IMPLEMENTS → SPEC `specs/formal/participant-semantics/reusable-mixed-control.md` (Exact control-application/delivery semantic amendment; not runtime conformance)
- IMPLEMENTS → GITHUB_ISSUE `1351` (Semantic decision and canonical requirement amendment)
- DOCUMENTS → DOCUMENTATION `docs/decisions/adrs/adr-110-reusable-mixed-control-policies-and-occurrences.md` (Accepted-on-merge policy/occurrence decision)
- DOCUMENTS → DOCUMENTATION `docs/migration/reusable-mixed-control.md` (Producer/reader and historical-meaning rules)
- DOCUMENTS → DOCUMENTATION `docs/research/reusable-mixed-control/cases.md` (Worked cycles and bounded evidence claims)
- TESTS → TEST `implementations/python/tests/test_issue_1351_mixed_control_design.py` (Bounded exact control/delivery-join projection; not delivery realization)

- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/composition/__init__.py` (DSL-142 composition reference rewriting)
- DOCUMENTS → GITHUB_ISSUE `794` (Assess and design formal participant I/O control with information-flow and bisimulation semantics)
- DOCUMENTS → DOCUMENTATION `docs/research/participant-io-control/requirement-disposition.md` (Issue #794 participant information-flow/control requirement disposition)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/participant_inject_delivery.py` (DSL-142 participant inject delivery authoring model)
- IMPLEMENTS → GITHUB_ISSUE `797` (DSL-142 — Participant-Directed Inject Binding And Delivery)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/participant_behavior_specification.py` (DSL-142 participant behavior delivery relation)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/compiler/participant_inject_deliveries.py` (DSL-142 typed participant delivery compiler metadata)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/validator/_participant_inject_deliveries.py` (DSL-142 semantic admission and fail-closed validation)
- IMPLEMENTS → SPEC `specs/sdl/sections.md` (DSL-142 normative SDL section contract)
- IMPLEMENTS → SPEC `specs/sdl/references.md` (DSL-142 normative delivery reference semantics)
- IMPLEMENTS → SPEC `contracts/schemas/sdl/sdl-authoring-input-v1.json` (DSL-142 governed authoring schema)
- TESTS → TEST `implementations/python/tests/test_dsl_142_participant_inject_delivery.py` (DSL-142 participant inject delivery tests)
- IMPLEMENTS → SPEC `contracts/schemas/sdl/instantiated-scenario-v1.json` (DSL-142 governed instantiated scenario schema)
- TESTS → TEST `implementations/python/tests/test_sdl_catalog_parity.py` (DSL-142 SDL catalog parity tests)
