---
id: DSL-116
title: "Participant Behavior Specification Surface"
status: DRAFT
type: FUNCTIONAL
priority: MUST
created_at: 2026-04-05T01:24:06.394920Z
updated_at: 2026-04-05T01:24:06.394920Z
---

# DSL-116 — Participant Behavior Specification Surface

## Statement

The language shall support first-class specification of participant behavior beyond static participant framing, including reusable behavior definitions and scenario-local behavior declarations.

## Rationale

Primary-source refresh from OpenRange, Open Trajectory Gym, and OpenThoughts-Agent shows that participant behavior needs an explicit authoring surface rather than being inferred from runtime or benchmark conventions.

## Clause verification

- First-class specification beyond static framing: `behavior_specifications`
  entries are named, versioned, lifecycle-governed aggregates over participant,
  role, action, observation, outcome-rule and authority refs. The published
  authoring schema admits them, semantic validation rejects dangling, ambiguous
  and ungoverned refs, and the compiler emits
  `participant.behavior-specification.<name>` records with resolved addresses.
- Scenario-local declarations: a declaration in the importing scenario binds
  imported participants by role, and imported action contracts, observation
  boundaries, outcome rules and authority scopes by qualified name. Bare names
  of an imported unit, unexported declarations, unknown roles, and an empty
  version or unknown lifecycle state fail closed with diagnostics.
- Reusable definitions: one unit that is also a valid standalone scenario,
  imported twice under distinct namespaces, yields two declarations whose
  participant, action, observation, outcome-rule and authority refs resolve
  only inside their own namespace through composition and compilation. A broken
  ref inside the unit is reported once per import, and a second unit that
  declares the same behavior name in one namespace is rejected as a collision.

## Fulfillment boundary

DRAFT. #297 verified the #206 surface without changing it and found residual
gaps for reusable definitions. `participant_role_refs` in an imported
declaration select every participant with that role in the composed scenario,
including participants of another import, so a unit that pairs role refs with
tool affordances validates when imported once and fails when imported twice.
Scoping role selection to the declaring unit would change the meaning of
existing compositions and needs a language decision. A structurally invalid
imported declaration raises a pydantic `ValidationError`, and a malformed
import version range raises a `packaging` `InvalidSpecifier`, instead of an
`SDLParseError` diagnostic.

## Traceability

- IMPLEMENTS → GITHUB_ISSUE `206` (First-Class Participant Behavior Specifications (ACT-606))
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/participant_behavior_specification.py` (Authored behavior specification model and structural validation)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/scenario.py` (Scenario-level behavior_specifications section)
- IMPLEMENTS → SPEC `contracts/schemas/sdl/sdl-authoring-input-v1.json` (Published authoring schema for behavior specifications)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/semantics/participant_behavior/_behavior_spec.py` (Participant, role, action, observation and outcome-rule reference validation)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/validator/_content_objectives.py` (Authority-scope reference validation and behavior diagnostics)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/composition/_behavior.py` (Namespaced reference rewriting for imported behavior specifications)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/composition/_expand.py` (Import namespacing and declaration collision rejection)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/_module_symbols.py` (Export-restricted symbols that keep unexported declarations private to an import)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/module_registry/resolution.py` (Import version constraint enforcement)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/compiler/participant_behaviors.py` (Compiled behavior specification records)
- DOCUMENTS → DOCUMENTATION `docs/explain/sdl/sections.md` (Behavior specification authoring reference)
- DOCUMENTS → SPEC `specs/formal/participant-behavior-model/README.md` (ACT-606 behavior specification aggregate)
- DOCUMENTS → GITHUB_ISSUE `297` (Verify reusable and scenario-local behavior authoring)
- TESTS → TEST `implementations/python/tests/test_issue_297_behavior_authoring.py` (Standalone, twice-imported and scenario-local declarations through composition and compilation, with fail-closed diagnostics)
- TESTS → TEST `implementations/python/tests/fixtures/behavior-authoring/scan-behavior.sdl.yaml` (Reusable behavior unit that is also a valid standalone scenario)
- TESTS → TEST `implementations/python/tests/fixtures/behavior-authoring/twice-imported.sdl.yaml` (Scenario-local declaration over two namespaced imports of one unit)
- TESTS → TEST `implementations/python/tests/test_sem_208_participant_behavior.py` (Single-file declarations, single-namespace import, governed vocabularies and dangling-reference rejection)
- TESTS → TEST `implementations/python/tests/test_sdl_parser.py` (Import version mismatch and namespace collision rejection)
