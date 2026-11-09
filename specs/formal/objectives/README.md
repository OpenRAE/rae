# Objective semantics

Find exact declarative-objective rules here.
`SEM-202` covers objective windows.
`SEM-207` covers ownership, assignment, targets, success, and dependencies.
The [objective reference](declarative-objective-semantics.md) gives the complete contract.
The [truth algebra](proposition-and-assertion-semantics.md) defines assertion outcomes.

## Scope

- ownership and assignment: `owner`, `assigned_participant`, or both, under
  [ADR-109](../../../docs/decisions/adrs/adr-109-participant-identity-and-objective-assignment.md).
  Ownership resolves to an entity; assignment resolves to an `agents` declaration.
  Each action resolves to a declared action contract, including for an unassigned objective.
- target resolution through the objective-subject purpose of the
  named-reference index (bare or
  section-qualified), fail-closed on missing/ambiguous references
- success interpretation: `mode` (`all_of` / `any_of` / `at_least`) over
  invariant or postcondition `assertions`, under
  [ADR-079](../../../docs/decisions/adrs/adr-079-backend-neutral-proposition-and-truth-semantics.md).
  `at_least` requires a threshold from one to the assertion count.
  Other modes forbid the threshold.
  The former `success.conditions` field is rejected.
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

## Implementation mapping

- shared name-level source of truth for whole-objective semantics:
  `implementations/python/packages/raes/semantics/objective_semantics/`
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
