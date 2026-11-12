---
id: DSL-116
title: "Participant Behavior Specification Surface"
status: ACTIVE
type: FUNCTIONAL
priority: MUST
created_at: 2026-04-05T01:24:06.394920Z
updated_at: 2026-10-11T18:30:00Z
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
  and requires a nonblank `semantic_version` string. Validator:
  `raes/semantics/participant_behavior/_behavior_spec.py` rejects dangling and
  ungoverned refs, and `raes/validator/_content_objectives.py` passes each
  authority scope to `_validate_named_ref` in `raes/validator/_core.py`, which
  rejects dangling and ambiguous scopes. Composition: `raes/_module_symbols.py`
  lists `behavior_specifications` as an exportable, namespaced section. Compiler:
  `raes_processor/compiler/participant_behaviors.py` emits
  `participant.behavior-specification.<name>` records with resolved addresses.
- Scenario-local declarations: a declaration in the importing scenario binds
  imported participants by role, and imported action contracts, observation
  boundaries, outcome rules and authority scopes by qualified name. Parser:
  `raes/parser.py` reports an empty `semantic_version` or an unknown
  `lifecycle_state` as an `sdl.model.invalid` diagnostic at the declaration
  field. Schema: the same definition admits the scenario-local form.
  Validator: `_behavior_spec.py` rejects bare names of an imported unit and
  unknown roles, and `_content_objectives.py` rejects bare authority scopes
  through `_core.py`. Composition: `raes/composition/_expand.py` merges the
  namespaced imports the declaration refers to, and `raes/_module_symbols.py`
  renames unexported declarations into the import's generated
  `<namespace>.__private` segment, so they are not reachable under their
  exported name. Compiler: `participant_behaviors.py` resolves the role and
  qualified refs to the addresses of both imports.
- Reusable definitions: one unit that is also a valid standalone scenario,
  imported twice under distinct namespaces, yields two declarations whose
  participant, action, observation, outcome-rule and authority refs resolve
  only inside their own namespace through composition and compilation. Parser:
  `raes/parser.py` parses the unit on its own and expands imports through
  `raes/composition`. Schema: the unit validates against the authoring schema
  on its own. Validator: a ref inside the unit that names nothing the unit
  declares is reported once per import, under the namespaced declaration name,
  when the composed scenario declares nothing of that name; otherwise it binds
  that declaration. An ambiguous ref inside the unit is reported once per
  import. Composition: `raes/composition/_expand.py` namespaces each import and
  rejects a second unit that declares the same behavior name in one namespace,
  `raes/composition/_behavior.py` rewrites the declaration's refs to the unit's
  own declarations into its namespace, and
  `raes/module_registry/resolution.py` enforces the pinned and ranged import
  versions. Compiler: `participant_behaviors.py` emits one record per
  namespace.

## Fulfillment boundary

ACTIVE records the DSL authoring contract and its delivery in #297. The
[composition decision](../../decisions/issue-297-behavior-authoring.md) settles
role and reference scope consistently with ADR-053: roles select matching
participants across the composed scenario, while explicit participant refs
retain their namespaced bindings. Cross-fragment refs may resolve root
declarations; unresolved and ambiguous refs fail against the complete symbol
table. Module exports govern authored name access, not role membership or
runtime permission.

Authored private behavior refs fail before composition, including on direct
`Scenario` construction. Generated private refs remain valid inside imported
units. Imported typed-model failures and malformed import constraints produce
source-anchored `SDLParseError` diagnostics. Published behavior version schemas
reject empty and whitespace-only labels, matching parser validation.

The tests cover reusable local bindings and intentional scenario-wide role
selection, including rejection when selected participants lack a declared tool
binding. These are executable authoring/compiler claims. They do not establish
backend execution or the repeatable control occurrences owned by #1363/#1364
under ADR-110. No issue-297 authoring acceptance criterion is deferred to those
runtime deliveries. Evidence becomes delivered when PR #1426 merges; CI must
verify its current head before merge.

## Traceability

- IMPLEMENTS → GITHUB_ISSUE `206` (First-Class Participant Behavior Specifications (ACT-606))
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/parser.py` (SDL parse entry point and model-diagnostic wrapping)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/participant_behavior_specification.py` (Authored behavior specification model and structural validation)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/scenario.py` (Scenario-level behavior_specifications section)
- IMPLEMENTS → SPEC `contracts/schemas/sdl/sdl-authoring-input-v1.json` (Published authoring schema for behavior specifications)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/semantics/participant_behavior/_behavior_spec.py` (Participant, role, action, observation and outcome-rule reference validation)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/validator/_content_objectives.py` (Authority-scope reference validation and behavior diagnostics)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/validator/_core.py` (Named-reference resolution behind the dangling and ambiguous authority-scope diagnostics)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/composition/_behavior.py` (Namespaced reference rewriting for imported behavior specifications)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/composition/_expand.py` (Import namespacing and declaration collision rejection)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/_module_symbols.py` (Export-restricted symbols: unexported declarations are renamed under the generated `__private` segment)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/module_registry/resolution.py` (Import version constraint enforcement)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/compiler/participant_behaviors.py` (Compiled behavior specification records)
- DOCUMENTS → DOCUMENTATION `docs/explain/sdl/sections.md` (Behavior specification authoring reference)
- DOCUMENTS → SPEC `specs/formal/participant-behavior-model/README.md` (ACT-606 behavior specification aggregate)
- IMPLEMENTS → GITHUB_ISSUE `297` (Verify reusable and scenario-local behavior authoring)
- TESTS → TEST `implementations/python/tests/test_issue_297_behavior_authoring.py` (Standalone, twice-imported and scenario-local declarations through composition and compilation, with fail-closed diagnostics, authored-private rejection and explicit global role/reference semantics)
- TESTS → TEST `implementations/python/tests/fixtures/behavior-authoring/scan-behavior.sdl.yaml` (Reusable behavior unit that is also a valid standalone scenario)
- TESTS → TEST `implementations/python/tests/fixtures/behavior-authoring/twice-imported.sdl.yaml` (Scenario-local declaration over two namespaced imports of one unit)
- TESTS → TEST `implementations/python/tests/test_sem_208_participant_behavior.py` (Single-file declarations, single-namespace import, governed vocabularies and dangling-reference rejection)
- TESTS → TEST `implementations/python/tests/test_sdl_parser.py` (Import version mismatch and namespace collision rejection)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/_behavior_authoring.py` (Pre-expansion authored reference boundary)
- DOCUMENTS → DOCUMENTATION `docs/decisions/issue-297-behavior-authoring.md` (Composition design, compatibility and runtime-refactor alignment)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/instantiate.py` (Prevent parameters from introducing private behavior refs)
- TESTS → TEST `implementations/python/tests/test_formal_semantic_validation.py` (Current source-bound formal evidence release selection)
- TESTS → TEST `implementations/python/tests/test_specification_coverage.py` (Current source-bound coverage evidence release selection)
- TESTS → TEST `implementations/python/tests/test_issue_989_versioned_evidence.py` (Explicit current release selection and rejection of stale evidence)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/_module_declarations.py` (Typed module and import metadata with version-constraint validation)
