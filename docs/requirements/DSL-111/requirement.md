---
id: DSL-111
title: "Entity And Exercise Timeline Modeling"
status: ACTIVE
type: FUNCTIONAL
priority: MUST
wave: 1
created_at: 2026-04-03T05:55:58.251562Z
updated_at: 2026-09-22T05:55:00Z
---

# DSL-111 — Entity And Exercise Timeline Modeling

## Statement

The language shall model entities, injects, events, scripts, and stories for exercise organization and timeline structure.

Authorized external requests shall instantiate authored injects as independently
identified occurrences bound to an admitted plan/source, target/run, concrete
realization bindings, bounded input contract, applicable preconditions and
trusted order/time. Retry keys, occurrence identities and scheduled slots shall
prevent duplicate logical execution while preserving permitted fresh repeats.
Admission, dispatch, backend refusal, effect absence, application, partial
application and indeterminate outcomes shall retain distinct evidence. No
participant declaration shall be required unless participant-specific semantics
are selected. Portable invocation/outcome semantics shall remain distinct from
concrete backend realization, preserving legacy authoring and historical meaning.

## Rationale

Requirement inventory phase. Status audit deferred until the full canonical graph is complete.

Issue #1353 defines the connection between authored orchestration and external
world-effect execution. Plan installation and participant status delivery do
not establish that an inject occurred in the world.

## Semantic amendment and evidence boundary

[ADR-111](../../decisions/adrs/adr-111-external-inject-triggering-and-execution.md)
and [EI-01–EI-06](../../../specs/sdl/external-injects.md) define the amendment.
ACTIVE records the accepted contract; it does not certify executable adoption.
Existing model/compiler evidence covers legacy narrative authoring. The new
bounded tests exercise a design projection, with production adoption governed
by the [compatibility contract](../../explain/sdl/external-inject-compatibility.md).

## Traceability

- IMPLEMENTS → SPEC `specs/sdl/external-injects.md` (External occurrence semantic amendment; not runtime conformance)
- IMPLEMENTS → GITHUB_ISSUE `1353` (Accepted external-trigger design and canonical requirement amendment)
- DOCUMENTS → DOCUMENTATION `docs/decisions/adrs/adr-111-external-inject-triggering-and-execution.md` (Accepted-on-merge execution decision)
- DOCUMENTS → DOCUMENTATION `docs/explain/sdl/external-inject-compatibility.md` (Producer, reader and evidence compatibility)
- DOCUMENTS → DOCUMENTATION `docs/explain/sdl/external-inject-cases.md` (Worked occurrences, outcomes and bounded claims)
- TESTS → TEST `implementations/python/tests/test_issue_1353_external_inject_design.py` (Bounded claim/lifecycle model and actual no-participant compiler witness; not backend execution)

- DOCUMENTS → DOCUMENTATION `docs/explain/sdl/sections.md` (SDL sections reference for entities, injects, events, scripts, and stories)
- DOCUMENTS → DOCUMENTATION `docs/explain/sdl/validation.md` (Validation rules for entity references and orchestration timeline integrity)
- DOCUMENTS → DOCUMENTATION `docs/explain/sdl/parser.md` (Parser normalization for timeline fields such as start-time and end-time)
- DOCUMENTS → DOCUMENTATION `docs/explain/sdl/runtime-architecture.md` (Runtime architecture for orchestrated inject, event, script, and story execution)
- CONSTRAINS → ADR `docs/decisions/adrs/adr-001-scenario-description-language.md` (ADR-001: entities and timeline orchestration are first-class SDL sections)
- CONSTRAINS → SPEC `contracts/schemas/sdl/sdl-authoring-input-v1.json` (SDL authoring schema for entities and orchestration sections)
- CONSTRAINS → SPEC `contracts/schemas/sdl/instantiated-scenario-v1.json` (Instantiated SDL schema carrying normalized entities and timeline structures)
- TESTS → TEST `implementations/python/tests/test_sdl_models.py` (Model tests for entity nesting, duration parsing, injects, scripts, and stories)
- TESTS → TEST `implementations/python/tests/test_sdl_validator.py` (Validator tests for entity, inject, event, script, and story reference checks)
- TESTS → TEST `implementations/python/tests/test_runtime_models.py` (Runtime model tests for inject bindings and orchestration window resolution)
- TESTS → TEST `implementations/python/tests/test_runtime_planner.py` (Planner tests for inject, event, script, and story scheduling behavior)
- TESTS → TEST `implementations/python/tests/test_sdl_realworld.py` (Real-world scenarios exercising nested entities and timeline orchestration together)
