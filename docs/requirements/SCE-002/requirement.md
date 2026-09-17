---
id: SCE-002
title: "Scenario Composition, Parameterization, and Randomization"
status: ACTIVE
type: FUNCTIONAL
priority: SHOULD
wave: 2
created_at: 2026-07-15T03:17:25.688429Z
updated_at: 2026-07-20T02:07:08.261022Z
---

# SCE-002 — Scenario Composition, Parameterization, and Randomization

## Statement

Scenarios shall support composition (combining atomic scenarios into larger campaigns), parameterization (variables for IPs, credentials, paths), and randomization (varying attack order, target selection, timing) to increase exercise variety and prevent rote memorization.

## Rationale

Static scenarios become predictable after one run. CALDERA's fact-based variable substitution and Atomic Red Team's input_arguments demonstrate that parameterization is standard practice.

## Traceability

- DOCUMENTS → GITHUB_ISSUE `OpenRAE/rae#1013` (Compose the existing SCE-002 authority in SEM-234 without changing its runtime contract)
- DOCUMENTS → SPEC `specs/formal/participant-semantics/cross-backend-participant-control.md` (Revisioned mixed-composition compatibility boundary)
- TESTS → TEST `implementations/python/tests/test_sem_234_mixed_composition.py` (Bounded composition with incumbent SCE-002 authority)
- DOCUMENTS → GITHUB_ISSUE `788` (SCE-002: publish the admitted experiment trial-plan contract)
- DOCUMENTS → GITHUB_ISSUE `652` (Design: scenario variation and deterministic trial realization (SCE-002))
- DOCUMENTS → ADR `docs/decisions/adrs/adr-084-scenario-variation-and-deterministic-trial-realization.md` (ADR-084: Scenario Variation and Deterministic Trial Realization)
- DOCUMENTS → DOCUMENTATION `docs/explain/reference/scenario-variation-and-trial-realization.md` (Scenario Variation and Trial Realization Reference Architecture)
- DOCUMENTS → DOCUMENTATION `docs/research/scenario-variation-trial-realization/prior-art-and-design-criteria.md` (Scenario Variation and Trial Realization Prior Art and Design Criteria)
- DOCUMENTS → SPEC `specs/formal/scenario-variation-trial-realization/README.md` (Scenario Variation and Trial Realization Formal Obligations)
- IMPLEMENTS → SPEC `specs/sdl/variation-points.md` (SDL Variation Points Specification)
- TESTS → TEST `implementations/python/tests/test_sdl_variation_points.py` (SDL variation points test suite)
- IMPLEMENTS → GITHUB_ISSUE `786` (SCE-002: implement bounded SDL scenario-family variation points)
- IMPLEMENTS → SPEC `contracts/schemas/sdl/sdl-authoring-input-v1.json` (Published SDL authoring schema with bounded variation points)
- IMPLEMENTS → SPEC `contracts/schemas/participant-runtime/runtime-fact-binding-plane-v1.json` (Published runtime fact binding plane contract)
- IMPLEMENTS → GITHUB_ISSUE `791` (SCE-002/SCE-004: implement typed runtime fact bindings)
- TESTS → TEST `implementations/python/tests/test_runtime_fact_bindings.py` (Runtime fact binding contract, security, and conformance tests)
- IMPLEMENTS → GITHUB_ISSUE `787` (SCE-002: add experiment variation-selection policies and allocation bindings)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/experiment_selection.py` (Closed experiment variation-selection policy contracts)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/experiment_selection.py` (Trusted SDL-family selection admission)
- IMPLEMENTS → SPEC `contracts/schemas/experiment-core/experiment-authoring-input-v1.json` (Published experiment authoring selection schema)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/experiment_spec.py` (Bounded and redacted experiment authoring ingress)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_mcp/tools/experiment_authoring.py` (MCP experiment selection validation and scaffolding)
- TESTS → TEST `implementations/python/tests/test_experiment_authoring.py` (Experiment authoring ingress and MCP validation tests)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/variation.py` (Bounded SDL scenario-family variation declarations)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/runtime_fact_dispatch.py` (Trusted one-shot runtime fact dispatch boundary)
- TESTS → TEST `implementations/python/tests/test_experiment_selection.py` (Experiment variation-selection contract and family-admission tests)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/validator/_variation.py` (SDL variation semantic admission)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/runtime_facts.py` (Closed runtime fact binding contract models and invariants)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/runtime_fact_binding_policy.py` (Runtime fact scope, authority, freshness, and projection policy)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/runtime_fact_bindings.py` (Append-only runtime fact plane and trusted binding orchestration)
- IMPLEMENTS → SPEC `contracts/schemas/plans/admitted-trial-plan-v1.json` (Published admitted trial-plan contract schema)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/admitted_trial_plan.py` (Admitted trial-plan entry/plan models, integrity chain, and plan-local validation)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/admitted_trial_plan_components.py` (Admitted trial-plan leaf component contracts (profiles, input refs, entry records, admission))
- TESTS → TEST `implementations/python/tests/test_sce_002_admitted_trial_plan.py` (Admitted trial-plan contract and validator failure-branch tests)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/trial_compilation.py` (Typed trial compilation limits and execution-cleanup authority)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/selected_scenario.py` (SDL-owned complete selection construction and semantic admission)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/trial_compiler/models.py` (Deterministic trial compiler request and atomic result boundary)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/trial_compiler/profiles.py` (Trial coordinate and identity profile implementation)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/trial_compiler/domains.py` (Canonical finite variation-domain enumeration)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/trial_compiler/policies.py` (Deterministic selection policy graph compilation)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/trial_compiler/compiler.py` (Atomic deterministic admitted trial-plan compiler)
- TESTS → TEST `implementations/python/tests/test_sce_002_selected_scenario.py` (Selected scenario target, constraint, and semantic admission tests)
- TESTS → TEST `implementations/python/tests/test_sce_002_trial_compiler.py` (Trial compiler determinism, policy, property, security, and admission tests)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/canonical.py` (Public RFC 8785 canonical byte and digest helpers)
- VERIFIES → SPEC `contracts/fixtures/plans/trial-compiler-v1/identity-vectors.json` (Trial compiler v1 coordinate and identity conformance vectors)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/trial_compiler/apparatus.py` (Digest-bound concrete apparatus manifest and capability admission)
- IMPLEMENTS → GITHUB_ISSUE `789` (SCE-002: implement deterministic trial-set compilation and admission)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/trial_compiler/inputs.py` (Bounded compilation input validation and canonical coordinate planning)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/trial_realization.py` (Realize one sealed admitted trial entry through SDL and processor planning.)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/trial_provenance.py` (Bind archival runs to admitted entries, snapshots, processor artifacts, and attempts.)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/trial_analysis.py` (Reconcile admitted trial plans, cleanup receipts, archival runs, and study allocation.)
- TESTS → TEST `implementations/python/tests/test_sce_002_trial_realization.py` (Verify admitted-entry realization, substitution rejection, provenance, retries, and reconciliation.)
- IMPLEMENTS → DOCUMENTATION `docs/decisions/issue-790-sce-002-trial-realization-provenance-preflight.md` (Define the authoritative trial-realization and provenance integration boundary.)
- IMPLEMENTS → GITHUB_ISSUE `790` (SCE-002: integrate trial realization with SDL instantiation and run provenance)
