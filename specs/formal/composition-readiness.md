# Composition readiness

This reference records the semantic invariants that module/import and namespace work must preserve.

## Phase boundary

The original FM2 design did **not** implement:

- module/import syntax
- reusable workflow subflows
- source-file-level namespace syntax

It defines the semantic preconditions those features must respect.
Module composition now exists under
[ADR-053](../../docs/decisions/adrs/adr-053-sdl-module-composition-for-inventory-backed-scenarios.md).
That delivery does not remove these invariants or establish every future composition feature.

## Required invariants

- module/import expansion must occur before full semantic validation and
  compile
- objective/window reference analysis must run on expanded canonical identities,
  not on author-facing module-local names
- planner dependency semantics must operate on resolved canonical resource
  identities, not on source-file boundaries
- future namespacing may extend canonical identity shape, but must not change:
  - objective-window reference kinds
  - dependency role meanings
  - planner `ordering` vs `refresh` edge semantics

## Current implementation hooks

- objective/window references already carry a namespace-extensible path slot in
  `implementations/python/packages/raes/semantics/objectives.py`
- planner identity handling is already defined in terms of canonical compiled
  addresses in `implementations/python/packages/raes_processor/semantics/planner.py`
- named regression tests pin the layout/namespace invariants:
  - former assessment pipeline: removed under ADR-073.
    `implementations/python/tests/test_semantics_assessment.py` checks the remaining assertion resource-kind tag.
    The former aggregation tests are not current evidence.
  - objective windows: `implementations/python/tests/test_semantics_objectives.py`
    (`test_composition_ready_invariant_imported_window_analysis_uses_expanded_canonical_identities`,
    `test_composition_ready_invariant_namespace_extends_window_identity_without_changing_kind_roles_or_ownership`)

These hooks keep source layout separate from FM2 semantics.
