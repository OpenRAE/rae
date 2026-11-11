# Workflow semantics

This directory holds the repo-native formal artifacts for SDL workflow control semantics.

## Scope

- workflow step kinds and their observable state contracts
- legal transitions for `objective`, `decision`, `switch`, `parallel`, `join`, `retry`, `call`, and `end`
- branch interleaving and parallel barrier release
- join ownership and legal join entry
- step-state visibility before predicate evaluation
- portable workflow result envelopes
- explicit compensation / rollback registration and observation semantics
- scripted, objective, and scaffolded realization semantics

## Invariants

- every `join` has exactly one owning `parallel`
- only the owning parallel's branch closure may enter its `join`
- every explicit branch path converges on the declared `join`
- only observable step kinds may be referenced in step-state predicates
- step-state predicates may only ask for outcomes legal for the referenced step kind
- post-join visibility contains only step state guaranteed on every path to the join
- compensation executes only for successfully completed compensable steps
- compensation order is reverse completion order
- compensation workflows remain acyclic relative to normal `call` edges
- goal-oriented success requires evidence-bearing assertion truth and cannot be
  established by participant self-report

## Implementation mapping

- shared rules: `implementations/python/packages/raes_contracts/workflow/semantics.py`
- join convergence and guaranteed branch state: `workflow_join_states()` in the shared rules
- general graph mechanics: `implementations/python/packages/raes_contracts/graphs.py`, through Python `graphlib`
- validator enforcement: `implementations/python/packages/raes/validator/`
- compiled contracts: `implementations/python/packages/raes_processor/compiler/`
- typed runtime results and contract checks:
  - `implementations/python/packages/raes_processor/models/`
  - `implementations/python/packages/raes_runtime/manager.py`
- smoke/regression coverage:
  - `implementations/python/tests/test_sdl_validator.py`
  - `implementations/python/tests/test_runtime_models.py`
  - `implementations/python/tests/test_runtime_manager.py`
  - `implementations/python/tests/test_runtime_control_plane_api.py`
  - `implementations/python/tests/test_sce_004_goal_oriented_steps.py`
  - `implementations/python/tests/test_workflow_join_analysis.py`

See also [goal-oriented-steps.md](goal-oriented-steps.md) for SCE-004 mode,
admission, provenance, and success invariants.

## Notes

This first wave uses Markdown as the abstract model format. TLA+ or Alloy can be added later for especially risky changes without changing the code-facing contract described here.
