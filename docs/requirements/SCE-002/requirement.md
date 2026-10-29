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

# Scenario composition, parameterization, and randomization

`SCE-002`

## Statement

Scenarios shall support the following to increase exercise variety and prevent rote memorization:

- Composition: combine atomic scenarios into larger campaigns.
- Parameterization: use variables for IPs, credentials, and paths.
- Randomization: vary attack order, target selection, and timing.

## Rationale

Static scenarios become predictable after one run.
CALDERA uses fact-based variable substitution.
Atomic Red Team uses input_arguments.
These show that the use of parameters is standard practice.

## Traceability

- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/trial_compiler/control_admission.py` (Reject a complete trial plan when a selected backend cannot support entry controls.)
- TESTS → TEST `implementations/python/tests/test_issue_1628_trial_control_admission.py` (Test selected-backend isolation and deterministic whole-plan refusal.)

- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/variation_structure.py` (Define closed choices for node presence. Keep runtime inventory scoped to its owner.)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/selected_structure.py` (Resolve explicit node and inventory choices. Apply those choices.)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/_selection_provenance.py` (Keep selected inventory constraints and derivation evidence. Use stable IDs to retain them.)
- TESTS → TEST `implementations/python/tests/test_issue_1625_structural_variation.py` (Test structural choices and composition. Test identity, provenance, schema, and atomic trial admission.)

- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/trial_compiler/bindings.py` (Admit canonical descriptors. This code is extracted from the trial compiler.)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/trial_compiler/replacement.py` (Admit explicit replacements within bounds. Use the existing compiler.)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/trial_compiler/replacement_inputs.py` (Define replacement coordinate intervals. Keep allocation identity stable.)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/trial_replacement.py` (Define closed replacement policy and lineage. The experiment owns them.)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/trial_replacement_analysis.py` (Trace lineage across plans. Account for the original slot in analysis.)
- TESTS → TEST `implementations/python/tests/test_issue_1396_trial_replacement.py` (Test fresh identity and cleanup refusal. Test bounds and duplicate decisions. Count each trial once in analysis.)
- VERIFIES → SPEC `contracts/fixtures/plans/trial-compiler-replacement-v1/identity-vectors.json` (Check that replacement compiler identity conforms.)

- IMPLEMENTS → GITHUB_ISSUE `OpenRAE/rae#1014` (Bring selected scenario authority into the portable mixed-composition profile.)
- IMPLEMENTS → SPEC `contracts/schemas/plans/mixed-participant-composition-profile-v1.json` (Carry the scenario snapshot pinned by digest. Carry the compiled allocation.)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/mixed_composition.py` (Define the composition profile. Reuse existing selection and compiled-address authority.)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/mixed_composition_validation.py` (Check closed allocation for each phase. Check canonical providers.)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/mixed_composition_resolution.py` (Join the exact selected scenario and compiled targets. Use their context.)
- TESTS → TEST `implementations/python/tests/test_issue_1014_mixed_composition_contracts.py` (Test composition modes. Keep selected scenario identity without selecting again.)
- DOCUMENTS → GITHUB_ISSUE `OpenRAE/rae#1013` (Compose existing SCE-002 authority in SEM-234. Keep its runtime contract unchanged.)
- DOCUMENTS → SPEC `specs/formal/participant-semantics/cross-backend-participant-control.md` (Define the mixed-composition compatibility boundary. Give it a revision.)
- TESTS → TEST `implementations/python/tests/test_sem_234_mixed_composition.py` (Test composition within bounds. Use existing SCE-002 authority.)
- DOCUMENTS → GITHUB_ISSUE `788` (Publish the admitted experiment trial-plan contract for SCE-002.)
- DOCUMENTS → GITHUB_ISSUE `652` (Design scenario variation and deterministic trial realization for SCE-002.)
- DOCUMENTS → ADR `docs/decisions/adrs/adr-084-scenario-variation-and-deterministic-trial-realization.md` (Record ADR-084. Define scenario variation and deterministic trial realization.)
- DOCUMENTS → DOCUMENTATION `docs/explain/reference/scenario-variation-and-trial-realization.md` (Describe the reference architecture for scenario variation and trial realization.)
- DOCUMENTS → DOCUMENTATION `docs/research/scenario-variation-trial-realization/prior-art-and-design-criteria.md` (Review prior art for scenario variation and trial realization. State the design criteria.)
- DOCUMENTS → SPEC `specs/formal/scenario-variation-trial-realization/README.md` (State formal obligations for scenario variation and trial realization.)
- IMPLEMENTS → SPEC `specs/sdl/variation-points.md` (Specify SDL variation points.)
- TESTS → TEST `implementations/python/tests/test_sdl_variation_points.py` (Test SDL variation points.)
- IMPLEMENTS → GITHUB_ISSUE `786` (Implement the bounded variation points of an SDL scenario family for SCE-002.)
- IMPLEMENTS → SPEC `contracts/schemas/sdl/sdl-authoring-input-v1.json` (Publish the SDL authoring schema. Include bounded variation points.)
- IMPLEMENTS → SPEC `contracts/schemas/participant-runtime/runtime-fact-binding-plane-v1.json` (Publish the runtime fact binding plane contract.)
- IMPLEMENTS → GITHUB_ISSUE `791` (Implement typed runtime fact bindings for SCE-002 and SCE-004.)
- TESTS → TEST `implementations/python/tests/test_runtime_fact_bindings.py` (Test the runtime fact binding contract. Test security and conformance.)
- IMPLEMENTS → GITHUB_ISSUE `787` (Add policies for how an experiment selects variation for SCE-002. Add allocation bindings.)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/experiment_selection.py` (Define closed contracts for how the experiment selects variation.)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/experiment_selection.py` (Admit selections from a trusted SDL family.)
- IMPLEMENTS → SPEC `contracts/schemas/experiment-core/experiment-authoring-input-v1.json` (Publish the schema for how authors select values in an experiment.)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/experiment_spec.py` (Admit experiment authoring input. Apply bounds and redaction.)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_mcp/tools/experiment_authoring.py` (Check experiment selections through MCP. Provide scaffolding.)
- TESTS → TEST `implementations/python/tests/test_experiment_authoring.py` (Test experiment authoring input. Test MCP validation.)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/variation.py` (Declare the bounded variation of an SDL scenario family.)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/runtime_fact_dispatch.py` (Set the trusted runtime fact dispatch boundary. Dispatch once.)
- TESTS → TEST `implementations/python/tests/test_experiment_selection.py` (Test the contracts for how an experiment selects variation. Test family admission.)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/validator/_variation.py` (Admit SDL variation through semantic checks.)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/runtime_facts.py` (Define closed runtime fact binding contract models. State their invariants.)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/runtime_fact_binding_policy.py` (Set runtime fact scope and authority. Set freshness and projection policy.)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/runtime_fact_bindings.py` (Provide an append-only runtime fact plane. Manage the trusted binding of facts.)
- IMPLEMENTS → SPEC `contracts/schemas/plans/admitted-trial-plan-v1.json` (Publish the admitted trial-plan contract schema.)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/admitted_trial_plan.py` (Model admitted trial-plan entries and plans. Keep the integrity chain. Check each plan.)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/admitted_trial_plan_components.py` (Define trial-plan leaf contracts. Cover profiles, input refs, entry records, and admission.)
- TESTS → TEST `implementations/python/tests/test_sce_002_admitted_trial_plan.py` (Test the admitted trial-plan contract. Test failure branches in its validator.)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/trial_compilation.py` (Define typed limits on how trials are compiled. Define who has authority to clean up execution.)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/selected_scenario.py` (Build complete selections under SDL authority. Admit them through semantic checks.)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/trial_compiler/models.py` (Define requests for the deterministic trial compiler. Return each result as one atomic unit.)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/trial_compiler/profiles.py` (Implement the profiles for trial coordinates and identity.)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/trial_compiler/domains.py` (Enumerate finite variation domains in canonical form.)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/trial_compiler/policies.py` (Compile selection policy graphs. Keep each result deterministic.)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/trial_compiler/compiler.py` (Compile admitted trial plans. Keep compilation atomic and deterministic.)
- TESTS → TEST `implementations/python/tests/test_sce_002_selected_scenario.py` (Test selected scenario targets and constraints. Test semantic admission.)
- TESTS → TEST `implementations/python/tests/test_sce_002_trial_compiler.py` (Test that the trial compiler is deterministic. Test its policy and properties. Test security and admission.)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/canonical.py` (Provide public helpers for canonical bytes and digests. Use RFC 8785.)
- VERIFIES → SPEC `contracts/fixtures/plans/trial-compiler-v1/identity-vectors.json` (Check trial compiler v1 coordinates and identity. Use conformance vectors.)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/trial_compiler/apparatus.py` (Admit concrete apparatus manifests and capabilities. Bind them by digest.)
- IMPLEMENTS → GITHUB_ISSUE `789` (Compile and admit trial sets for SCE-002. Keep this process deterministic.)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/trial_compiler/inputs.py` (Check compilation input within bounds. Plan canonical coordinates.)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/trial_realization.py` (Realize one sealed, admitted trial entry. Use SDL and processor planning.)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/trial_provenance.py` (Bind archival runs to admitted entries and snapshots. Bind them to processor artifacts and attempts.)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/trial_analysis.py` (Reconcile admitted trial plans and cleanup receipts. Reconcile archival runs and study allocation.)
- TESTS → TEST `implementations/python/tests/test_sce_002_trial_realization.py` (Test admitted-entry realization and substitution rejection. Test provenance, retries, and reconciliation.)
- IMPLEMENTS → DOCUMENTATION `docs/decisions/issue-790-sce-002-trial-realization-provenance-preflight.md` (Define the authoritative boundary for trial realization and provenance integration.)
- IMPLEMENTS → GITHUB_ISSUE `790` (Integrate trial realization with SDL instantiation for SCE-002. Include run provenance.)
- IMPLEMENTS → GITHUB_ISSUE `OpenRAE/rae#1015` (Admit exact mixed and staged realization assignments. Scope them to each trial coordinate.)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/admitted_trial_plan.py` (Support mixed entries in the existing admitted-plan lifecycle.)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/admitted_trial_plan_components.py` (Pin profile inputs. Keep exact source-plan lineage.)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/trial_compilation.py` (Bound mixed-profile work in aggregate. Bound work that uses context.)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/trial_compiler/models.py` (Keep inputs immutable while realization assignments are compiled.)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/trial_compiler/inputs.py` (Assign every coordinate. Resolve exact profiles. Keep plan intent canonical.)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/trial_compiler/compiler.py` (Compile mixed and staged trials. Keep compilation deterministic and atomic.)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/trial_compiler/realization_admission.py` (Admit exact selected scenarios and source plans. Admit context, resources, and apparatus.)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/trial_compiler/profiles.py` (Define mixed plan, entry, and run IDs. Keep their domains separate.)
- IMPLEMENTS → DOCUMENTATION `docs/explain/reference/scenario-variation-and-trial-realization.md` (Describe mixed and staged admission. State the runtime nonclaim.)
- VERIFIES → SPEC `contracts/fixtures/plans/trial-compiler-mixed-composition-v1/identity-vectors.json` (Check mixed compiler identity with conformance vectors.)
- TESTS → TEST `implementations/python/tests/test_issue_1015_mixed_staged_trial_admission.py` (Test pure compatibility. Test that mixed and staged compilation is deterministic. Test bounds and lineage.)

- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/runtime_experiment_records.py` (Keep selected treatments and admitted run identities in records.)
- TESTS → TEST `implementations/python/tests/test_issue_1630_run_records.py` (Test factorial condition evidence and replacement history.)
