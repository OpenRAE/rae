---
id: MOD-001
title: "Codebase Modularity And Layering"
status: ACTIVE
type: NON_FUNCTIONAL
priority: SHOULD
wave: 3
created_at: 2026-05-09T19:09:48.679Z
updated_at: 2026-10-31T00:00:00Z
---

# MOD-001 — Codebase Modularity And Layering

## Statement

The raes codebase shall keep a one-way dependency between the SDL and processor layers: no `raes` module shall import `raes_processor`. No `raes_contracts` module shall import another first-party package. No non-test, non-generated source file under `implementations/python/packages/` shall have more than 1,000 lines. An allowlist that can only shrink shall record the files over this line cap. The repository policy gate shall also fail on these new findings:

- an import cycle between sibling modules;
- an import of a private name from another module;
- a class with more than seven ancestors from the packages;
- an access to a private member of another object;
- a first-party import inside a function;
- a dynamic first-party import that does not name its target.

Each of these checks shall compare its findings with a baseline that can only shrink. The repository policy gate shall enforce all these invariants in CI, so that review judgment is not the only control.

## Rationale

Cross-cutting layering and size invariants prevent the architectural drift that produces tightly-coupled, oversized modules. Captured as a single initiative-level requirement so the cycle break, the structural CI gates, the foundational ADR, and the 14 follow-up file-split PRs share one governance anchor. Pre-existing audit (issue #3 scoping comment) found 14 source files >600 lines and a hard `raes` ↔ `raes_processor` cycle via `raes/validator.py` importing `raes_processor.semantics.{objectives,workflow}`. The cycle break and CI gates are foundational; the file splits are tracked under sibling children of #3.

## Traceability

- IMPLEMENTS → ADR `docs/decisions/adrs/adr-015-sdl-processor-layering-and-source-file-size-cap.md` (ADR-015: SDL/Processor Layering And Source-File Size Cap)
- IMPLEMENTS → GITHUB_ISSUE `410` (Re-architect SDL, processor, authoring suite, and runtime module boundaries)
- CONSTRAINS → POLICY `tools/policy/repo_policy.py` (Repository policy module-boundary checker)
- CONSTRAINS → CONFIG `tools/policy/adr_policy.yaml` (ADR policy module-boundary configuration)
- TESTS → TEST `implementations/python/tests/test_repo_policy_tools.py` (Repository policy module-boundary tests)
- IMPLEMENTS → PULL_REQUEST `412` (Implement runtime module boundaries)
- DOCUMENTS → ADR `docs/decisions/adrs/adr-036-sdl-processor-runtime-module-boundaries.md` (ADR-036: SDL, Processor, Runtime Module Boundaries)
- IMPLEMENTS → PULL_REQUEST `759` (refactor: clear PR 753 Sonar findings)
- IMPLEMENTS → ADR `docs/decisions/adrs/adr-117-ratcheted-structural-checks.md` (ADR-117: Ratcheted Structural Checks for Package Modules)
- IMPLEMENTS → GITHUB_ISSUE `1734` (Quality refactor 00: Add structural checks and a ratchet before the refactor starts)
- IMPLEMENTS → POLICY `tools/policy/structural_ratchet.py` (ADR-117 structural ratchet)
- IMPLEMENTS → POLICY `tools/policy/private_imports.py` (ADR-117 private-import check)
- IMPLEMENTS → POLICY `tools/policy/class_ancestry.py` (ADR-117 class-ancestry check)
- IMPLEMENTS → POLICY `tools/policy/import_cycles.py` (ADR-117 cyclic components and layer agreement)
- IMPLEMENTS → POLICY `tools/policy/import_graph.py` (ADR-117 grimp and import-linter bridge)
- IMPLEMENTS → POLICY `tools/policy/structural_baseline.py` (ADR-117 baselines and base-revision comparison)
- IMPLEMENTS → POLICY `tools/policy/source_index.py` (ADR-117 static source index)
- CONSTRAINS → CONFIG `tools/policy/import_contracts.toml` (Import contracts and import debt)
- CONSTRAINS → CONFIG `tools/policy/structural_baseline.json` (Structural baseline)
- TESTS → TEST `implementations/python/tests/test_issue_1734_private_imports.py` (Private-import check tests)
- TESTS → TEST `implementations/python/tests/test_issue_1734_class_ancestry.py` (Class-ancestry check tests)
- TESTS → TEST `implementations/python/tests/test_issue_1734_import_cycles.py` (Cyclic component and layer agreement tests)
- TESTS → TEST `implementations/python/tests/test_issue_1734_structural_ratchet.py` (Structural ratchet tests)
- TESTS → TEST `implementations/python/tests/test_issue_1734_import_graph.py` (grimp and import-linter bridge tests)
- TESTS → TEST `implementations/python/tests/test_issue_1734_structural_integration.py` (Structural checks with Git and the tooling analyzers)
- IMPLEMENTS → ADR `docs/decisions/adrs/adr-121-strict-package-layers.md` (ADR-121: Strict Package Layers and a Schema Composition Root)
- IMPLEMENTS → GITHUB_ISSUE `1711` (Quality refactor 02: Remove the import cycle between raes_contracts and raes)
- IMPLEMENTS → POLICY `tools/policy/private_members.py` (ADR-117 private-member check)
- IMPLEMENTS → POLICY `tools/policy/function_imports.py` (ADR-117 check of imports inside functions)
- IMPLEMENTS → POLICY `tools/policy/hidden_imports.py` (ADR-117 hidden-import check)
- IMPLEMENTS → POLICY `tools/policy/import_boundaries.py` (Module-boundary decision for static and dynamic imports)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_schemas/bundle.py` (Schema composition root above the package layers)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/published_schemas.py` (Published schemas read as data below the SDL layer)
- DOCUMENTS → DOCUMENTATION `docs/decisions/issue-1711-strict-layers-design.md` (Issue 1711 strict package layers design)
- TESTS → TEST `implementations/python/tests/test_issue_1711_layer_direction.py` (No raes_contracts module imports a first-party package)
- TESTS → TEST `implementations/python/tests/test_issue_1711_structural_checks.py` (Private-member, inside-function and hidden-import checks)
