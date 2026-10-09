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
  role, action, observation, outcome-rule and authority refs. Parser:
  `raes/parser.py` builds `ParticipantBehaviorSpecification`
  (`raes/participant_behavior_specification.py`) in the `raes/scenario.py`
  section. Schema: `$defs.ParticipantBehaviorSpecification` in
  `contracts/schemas/sdl/sdl-authoring-input-v1.json` admits the declaration
  and requires `semantic_version`. Validator:
  `raes/semantics/participant_behavior/_behavior_spec.py` and
  `raes/validator/_content_objectives.py` reject dangling, ambiguous and
  ungoverned refs. Composition: `raes/_module_symbols.py` lists
  `behavior_specifications` as an exportable, namespaced section. Compiler:
  `raes_processor/compiler/participant_behaviors.py` emits
  `participant.behavior-specification.<name>` records with resolved addresses.
- Scenario-local declarations: a declaration in the importing scenario binds
  imported participants by role, and imported action contracts, observation
  boundaries, outcome rules and authority scopes by qualified name. Parser:
  `raes/parser.py` reports an empty `semantic_version` or an unknown
  `lifecycle_state` as an `sdl.model.invalid` diagnostic at the declaration
  field. Schema: the same definition admits the scenario-local form.
  Validator: `_behavior_spec.py` rejects bare names of an imported unit and
  unknown roles, and `_content_objectives.py` rejects bare authority scopes.
  Composition: `raes/composition/_expand.py` merges the namespaced imports the
  declaration refers to, and `raes/_module_symbols.py` keeps unexported
  declarations private to their import. Compiler: `participant_behaviors.py`
  resolves the role and qualified refs to the addresses of both imports.
- Reusable definitions: one unit that is also a valid standalone scenario,
  imported twice under distinct namespaces, yields two declarations whose
  participant, action, observation, outcome-rule and authority refs resolve
  only inside their own namespace through composition and compilation. Parser:
  `raes/parser.py` parses the unit on its own and expands imports through
  `raes/composition`. Schema: the unit validates against the authoring schema
  on its own. Validator: a broken ref inside the unit is reported once per
  import, under the namespaced declaration name. Composition:
  `raes/composition/_expand.py` namespaces each import and rejects a second
  unit that declares the same behavior name in one namespace,
  `raes/composition/_behavior.py` rewrites the declaration's refs into its
  namespace, and `raes/module_registry/resolution.py` enforces the pinned and
  ranged import versions. Compiler: `participant_behaviors.py` emits one record
  per namespace.

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
`SDLParseError` diagnostic. These two gaps need no language decision: import
resolution in `raes/module_registry/resolution.py` validates the imported
scenario without the parser's diagnostic wrapping, and
`raes/module_registry/_digests.py` builds the version `SpecifierSet` without a
guard. Closing them is a package source change, which this verification does
not make.

## Traceability

- IMPLEMENTS → GITHUB_ISSUE `206` (First-Class Participant Behavior Specifications (ACT-606))
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/parser.py` (SDL parse entry point and model-diagnostic wrapping)
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
