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

The raes codebase shall keep a one-way dependency between the SDL and processor layers: no `raes` module shall import `raes_processor`. No non-test, non-generated source file under `implementations/python/packages/` shall have more than 1,000 lines. An allowlist that can only shrink shall record the files over this line cap. The repository policy gate shall also fail on these new findings:

- an import cycle between sibling modules;
- an import of a private name from another module;
- a class with more than seven ancestors from the packages.

Each of these checks shall compare its findings with a baseline that can only shrink. The repository policy gate shall enforce all these invariants in CI, so that review judgment is not the only control.

The Go code shall meet the architecture model in `implementations/architecture.json` (ADR-122):

- The model shall classify each Go package in a layer and list the permitted dependencies of each package and layer.
- CI shall fail on an unclassified package, on a dependency that the model does not permit, and on an ADR-122 rule without a check.
- Each failure shall name the rule and the location, and state how to fix it.
- Each change shall declare its packages and dependencies in the model and pass the design check before its Go code is written.
- The Go checks shall have no baseline.

## Rationale

Layering and size invariants across the codebase prevent the architectural drift that makes modules tightly coupled and too large. One initiative-level requirement is the governance anchor for the cycle break, the structural CI gates, the foundational ADR, and the 14 file-split PRs that followed. An earlier audit in the scoping comment of issue #3 found 14 source files with more than 600 lines. It also found a `raes` ↔ `raes_processor` cycle, because `raes/validator.py` imported `raes_processor.semantics.{objectives,workflow}`. The cycle break and the CI gates are foundational. Sibling children of #3 track the file splits.

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
- IMPLEMENTS → ADR `docs/decisions/adrs/adr-122-go-architecture-model.md` (ADR-122: Go Architecture Model)
- IMPLEMENTS → GITHUB_ISSUE `1775` (Go port 02: Define the architecture model and check code and designs against it)
- CONSTRAINS → CONFIG `implementations/architecture.json` (Go architecture model)
- IMPLEMENTS → CODE_FILE `implementations/tooling/go/arch/model.go` (Architecture model and design checks)
- IMPLEMENTS → CODE_FILE `implementations/tooling/go/arch/code.go` (Code loading and code checks)
- IMPLEMENTS → CODE_FILE `implementations/tooling/go/arch/rules.go` (ADR-122 rule table check)
- IMPLEMENTS → CODE_FILE `implementations/tooling/go/cmd/archcheck/main.go` (Architecture check command)
- TESTS → TEST `implementations/tooling/go/arch/model_test.go` (Design check tests)
- TESTS → TEST `implementations/tooling/go/arch/code_test.go` (Code check tests)
- TESTS → TEST `implementations/tooling/go/arch/rules_test.go` (Rule table and rule coverage tests)
- TESTS → TEST `implementations/tooling/go/cmd/archcheck/main_test.go` (Architecture check command tests)
