# Objective window consistency

## Window reference model

Objective windows can constrain visibility using normalized references to:

- stories
- scripts
- events
- workflows
- workflow steps using `<workflow>.<step>`

All objective-window references are resolved into a single normalized internal
shape before compiler/planner semantics run. Each resolved reference carries:

- raw author-facing text
- canonical name
- reference kind
- dependency role set
- optional workflow and step identity
- a namespace-extensible path slot reserved for future module/import work

## Consistency rules

- `window.steps` must use `<workflow>.<step>` syntax
- `window.steps` require at least one referenced workflow
- each workflow ref must resolve to a declared workflow
- each workflow step ref must resolve to:
  - a declared workflow
  - a declared step within that workflow
- if `window.workflows` is present, every `window.steps` workflow name must be
  a member of that set
- if `window.stories` is present, every explicit `window.scripts` entry must be
  included by at least one referenced story
- if explicit or reachable scripts are known, every `window.events` entry must
  be included by at least one referenced script

## Reachability and refresh semantics

- referenced stories derive reachable scripts
- explicit scripts override story-derived reachability for event membership
  checks
- explicit or reachable scripts derive reachable events
- `window.workflows` contributes orchestration workflow refresh dependencies
- `window.steps` contributes:
  - the stable step reference string
  - the owning workflow address for refresh propagation
- objective refresh dependencies are therefore derived from one shared
  objective-window analysis rather than separate validator/compiler logic

## Fail-closed cases

- malformed workflow-step syntax
- undefined story/script/event/workflow names
- undefined step names
- script refs outside the declared story window
- event refs outside the explicit/reachable script window
- step refs outside the declared workflow window

## Composition-ready invariants

- normalized references are independent of source-file layout
- future module/import expansion must occur before this analysis runs
- namespacing may extend the reference identity, but must not change:
  - reference kinds
  - dependency role semantics
  - workflow-step ownership semantics

## Implementation mapping

- shared semantic source of truth: `implementations/python/packages/raes/semantics/objectives.py`
- validator checks: `implementations/python/packages/raes/validator/`
- compiled runtime references and refresh derivation:
  - `implementations/python/packages/raes_processor/compiler/`
  - `implementations/python/packages/raes_processor/models/`
- differential and property tests:
  - `implementations/python/tests/test_semantics_objectives.py`
    (`test_window_invariant_story_refs_must_resolve`,
    `test_window_invariant_script_refs_must_resolve`,
    `test_window_invariant_event_refs_must_resolve`,
    `test_window_invariant_steps_must_use_workflow_step_syntax`,
    `test_window_invariant_steps_require_workflow_window`,
    `test_window_invariant_workflow_refs_must_resolve`,
    `test_window_invariant_step_workflow_must_resolve`,
    `test_window_invariant_step_name_must_resolve_within_workflow`,
    `test_window_invariant_step_workflow_must_be_inside_workflow_window`,
    `test_window_invariant_explicit_scripts_must_be_inside_story_window`,
    `test_window_invariant_events_must_be_inside_reachable_script_window`,
    `test_composition_ready_invariant_imported_window_analysis_uses_expanded_canonical_identities`,
    `test_composition_ready_invariant_namespace_extends_window_identity_without_changing_kind_roles_or_ownership`)
  - `implementations/python/tests/test_fm2_semantics.py`
