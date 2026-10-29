# Canonical Reference Map

This page identifies the current repository locations for Reproducible Agentic
Environments System (RAES) and RAES SDL reference material. RAES is the overall
system for agentic environments; SDL is its authored scenario language. This
page is an index, not a replacement for the linked artifacts.

## How To Use This Map

- Scenario authors: start with the SDL guide, section reference, parser
  behavior, validation rules, and limitations.
- Agentic-environment users: start with the glossary, getting-started guide,
  runtime architecture, realization semantics, and conformance notes to follow
  the path from authored scenario to realized environment and evidence.
- Backend implementers: start with the contract root, schema inventory,
  runtime architecture, and backend conformance notes.
- Researchers: start with lineage, design precedents, formal specifications,
  glossary, and current materialization notes.
- Reviewers: use the authority boundary, ADRs, and documentation style guide
  to distinguish normative claims from explanatory prose.

## RAES Lifecycle And Boundaries

| Surface | Current reference |
|---------|-------------------|
| RAES and agentic-environment terminology | [`glossary.md`](glossary.md) |
| Current system boundary and entrypoints | [`docs/public/index.md`](../../public/index.md) |
| Authored scenario language | [`docs/explain/sdl/index.md`](../sdl/index.md) |
| Instantiation, planning, and realization path | [`docs/explain/sdl/runtime-architecture.md`](../sdl/runtime-architecture.md) |
| Explicitness and realized-form semantics | [`explicitness-realization-semantics.md`](explicitness-realization-semantics.md), [`realization-envelopes.md`](realization-envelopes.md) |
| Variation and trial realization | [`scenario-variation-and-trial-realization.md`](scenario-variation-and-trial-realization.md) |
| Experiment binding contracts | [`experiment-binding-contracts.md`](experiment-binding-contracts.md), [ADR-094](../../decisions/adrs/adr-094-authoritative-cross-plane-experiment-bindings.md) |
| Backend conformance | [`backend-conformance.md`](backend-conformance.md) |
| Evidence-bounded claim guidance | [`docs/explain/sdl/agent-guidance.md`](../sdl/agent-guidance.md), [`docs/explain/sdl/scientific-scenario-completeness.md`](../sdl/scientific-scenario-completeness.md) |

## Repository Authority

| Surface | Current reference |
|---------|-------------------|
| Authority boundary | [`specs/authority/authority-boundary.yaml`](../../../specs/authority/authority-boundary.yaml), [ADR-009](../../decisions/adrs/adr-009-normative-artifact-authority-and-repository-structure.md), [ADR-019](../../decisions/adrs/adr-019-normative-authority-boundary-manifest.md) |
| Normative prose | `specs/` |
| Architecture decisions | [`docs/decisions/adrs/`](../../decisions/adrs/README.md) |
| Reference notes | [`docs/explain/reference/`](README.md) |
| Coding policy | [`coding-standards.md`](coding-standards.md) |
| Documentation policy | [`documentation-style-guide.md`](documentation-style-guide.md) |

## SDL And Experiments

| Surface | Current reference |
|---------|-------------------|
| Getting started | [`docs/public/quickstart.md`](../../public/quickstart.md) |
| Worked examples | `examples/README.md`, `examples/scenarios/*.sdl.yaml` |
| Template and pattern library | `examples/library/catalog.yaml`, `examples/library/templates/`, `examples/library/patterns/` |
| SDL guide | [`docs/explain/sdl/index.md`](../sdl/index.md) |
| SDL sections | [`docs/explain/sdl/sections.md`](../sdl/sections.md) |
| Parser behavior | [`docs/explain/sdl/parser.md`](../sdl/parser.md) |
| Semantic validation | [`docs/explain/sdl/validation.md`](../sdl/validation.md) |
| Current SDL limits | [`docs/explain/sdl/limitations.md`](../sdl/limitations.md) |
| Testing notes | [`docs/explain/sdl/testing.md`](../sdl/testing.md) |
| Design precedents | [`docs/explain/sdl/precedents.md`](../sdl/precedents.md) |
| Academic lineage | [`docs/explain/sdl/lineage.md`](../sdl/lineage.md) |
| Scenario variation and trial realization design | [`scenario-variation-and-trial-realization.md`](scenario-variation-and-trial-realization.md), [ADR-084](../../decisions/adrs/adr-084-scenario-variation-and-deterministic-trial-realization.md) |
| Cross-plane experiment binding and configuration | [`experiment-binding-contracts.md`](experiment-binding-contracts.md), [ADR-094](../../decisions/adrs/adr-094-authoritative-cross-plane-experiment-bindings.md) |

## Contracts And Processing

| Surface | Current reference |
|---------|-------------------|
| Contract root | `contracts/README.md` |
| Published schemas | `contracts/schemas/README.md` |
| Schema inventory | [`contracts/schema-publication-manifest.json`](../../../contracts/schema-publication-manifest.json) |
| Processor API | [`docs/public/api/processor.rst`](../../public/api/processor.rst) |
| Processor semantics API | [`docs/public/api/processor-semantics.rst`](../../public/api/processor-semantics.rst) |
| Runtime API | [`docs/public/api/runtime.rst`](../../public/api/runtime.rst) |
| Runtime architecture | [`docs/explain/sdl/runtime-architecture.md`](../sdl/runtime-architecture.md) |
| Backend conformance | [`backend-conformance.md`](backend-conformance.md) |

## Formal And Semantic Material

| Surface | Current reference |
|---------|-------------------|
| Formal specs index | [`docs/specs/formal.md`](../../specs/formal.md), `specs/formal/README.md` |
| Objective semantics | `specs/formal/objectives/`, [`objective-semantics.md`](objective-semantics.md) |
| Workflow semantics | `specs/formal/workflows/` |
| Runtime contracts | `specs/formal/runtime-contracts/` |
| Assessment semantics | `specs/formal/assessment/`, [`assessment-semantics.md`](assessment-semantics.md) |
| Participant semantics | `specs/formal/participant-semantics/README.md` |
| Shared time model | `specs/formal/time-model/README.md`, ADR-090 |
| Realization semantics | `specs/formal/realization/`, [`explicitness-realization-semantics.md`](explicitness-realization-semantics.md) |
| Scenario variation and trial realization invariants | `specs/formal/scenario-variation-trial-realization/` |
| Whole-scenario finite-domain satisfiability | `specs/formal/scenario-satisfiability/`, ADR-086 |
| Planner semantics | `specs/formal/planner/` |

## Current Materialization Notes

- SDL authoring, parsing, validation, instantiation, compilation, planning,
  runtime manager/control-plane APIs, published JSON schemas, and a
  non-normative template/pattern library are present in the repository.
- Participant-implementation manifests, evidence-capture contracts, and
  provenance contract surfaces are described at the architecture level and are
  not fully materialized as published schemas.
- Legacy `v1` backend and processor manifest schemas remain checked in as
  deprecated reference artifacts; current conformance material uses the shared
  `v2` apparatus manifest envelope.
