# Objective Semantics

This directory holds the formal artifacts for declarative-objective semantics —
the objective-window slice (`SEM-202`) and the surrounding actor-binding,
target-resolution, success-interpretation, and dependency-ordering semantics
(`SEM-207`).

## Scope

- actor binding: an authored `agent` xor an authored `entity` owns the
  objective; agent-action checks reuse the declaring agent's `actions`
- target resolution through the objective-subject purpose of the
  named-reference index (bare or
  section-qualified), fail-closed on missing/ambiguous references
- success interpretation: `mode` (`all_of` / `any_of`) over referenced
  `conditions` (observable state only; the OCR scoring surfaces `metrics`,
  `evaluations`, `tlos`, and `goals` were removed by
  [ADR-073](../../../docs/decisions/adrs/adr-073-scoring-reward-language-scope.md))
- windows: normalized story/script/event/workflow/workflow-step reference
  resolution; consistency between `window.stories`, `window.scripts`,
  `window.events`, `window.workflows`, and `window.steps`; reachability
  derivation from story -> script -> event chains; refresh-dependency derivation
  from workflow and workflow-step refs
- dependency ordering: `depends_on` is an objective-to-objective ordering
  relation, acyclic and fail-closed
- dependency roles: success and `depends_on` edges both order and refresh;
  window edges only refresh; actor and target references are normalized for
  fail-closed validation but carry no runtime dependency role today (the
  compiler does not propagate ordering or refresh through actor/target identity,
  so the analyzer assigns them an empty role tuple — a future change that
  compiles them into runtime addresses lifts the role constants in lockstep)
- fail-closed behavior for invalid, dangling, ambiguous, or out-of-window
  references
- composition-ready invariants for later namespace/module expansion

## Implementation Mapping

- shared name-level source of truth for whole-objective semantics:
  `implementations/python/packages/raes/semantics/objective_semantics.py`
  (`analyze_objective_semantics`, `partition_objective_dependencies`,
  `OBJECTIVE_*_DEPENDENCY_ROLES`)
- shared objective-window helper:
  `implementations/python/packages/raes/semantics/objectives.py`
  (`analyze_objective_window`)
- authoring models: `implementations/python/packages/raes/objectives.py`
- semantic validation: `implementations/python/packages/raes/validator/`
  (`_verify_objectives`)
- compiled runtime objective resource, addresses, diagnostics, and
  ordering/refresh derivation:
  - `implementations/python/packages/raes_processor/compiler/`
  - `implementations/python/packages/raes_processor/models/`
- planner ordering/refresh reconciliation:
  - `implementations/python/packages/raes_processor/planner/`
  - `implementations/python/packages/raes_processor/semantics/planner.py`

## Tests

- `implementations/python/tests/test_semantics_objectives.py`
- `implementations/python/tests/test_fm2_semantics.py`
- `implementations/python/tests/test_sdl_validator.py`
- `implementations/python/tests/test_runtime_models.py`

## Notes

- `window-consistency.md` captures the objective-window reference model and
  consistency rules (`SEM-202`).
- `declarative-objective-semantics.md` captures the `SEM-207` semantic boundary
  for objective actor binding, target resolution, success interpretation,
  windows, and dependency ordering, plus its implementation/test mapping.
