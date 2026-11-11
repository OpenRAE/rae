# Planner graph semantics

This directory holds the formal artifacts for dependency ordering and
reconciliation semantics.

## Scope

- typed dependency-edge semantics (`ordering` vs `refresh`)
- ordering dependency normalization
- cycle detection
- stable topological order for create/start
- reverse topological order for delete/teardown
- transitive refresh propagation
- reconciliation action semantics over desired resources vs snapshot state
- composition-ready identity invariants for future module/import expansion

## Implementation mapping

- shared graph helpers: `implementations/python/packages/raes_processor/semantics/planner.py`
- planner use sites:
  - `implementations/python/packages/raes_processor/planner/`
  - `implementations/python/packages/raes_runtime/manager.py`

## Tests

- `implementations/python/tests/test_semantics_planner.py`
- `implementations/python/tests/test_fm2_semantics.py`
- `implementations/python/tests/test_runtime_planner.py`
- `implementations/python/tests/test_runtime_manager.py`
