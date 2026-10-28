---
id: API-414
title: "Participant Tool And Affordance Declarations"
status: ACTIVE
type: INTERFACE
priority: MUST
created_at: 2026-04-05T01:24:46.721391Z
updated_at: 2026-10-27T18:11:19.852151Z
---

# API-414 — Participant Tool And Affordance Declarations

## Statement

Processor and backend manifests shall declare supported participant tool and affordance surfaces together with relevant constraints and limitations.

## Rationale

Primary-source refresh shows that participant behavior claims need explicit external declarations of the available tool and affordance surface.

## Traceability

- IMPLEMENTS → GITHUB_ISSUE `304` (Declare and check participant tool-profile support)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_backend_protocols/manifest.py` (Tool-profile declaration and admission boundary)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_backend_protocols/participant_capabilities.py` (Tool-profile declaration and admission boundary)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_conformance/conformance/target.py` (Tool-profile declaration and admission boundary)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/manifests.py` (Tool-profile declaration and admission boundary)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/participant_tool_support.py` (Tool-profile declaration and admission boundary)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/processor_capabilities.py` (Tool-profile declaration and admission boundary)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/manifest_authority.py` (Tool-profile declaration and admission boundary)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/capabilities.py` (Tool-profile declaration and admission boundary)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/manifest.py` (Tool-profile declaration and admission boundary)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/participant_tool_support.py` (Tool-profile declaration and admission boundary)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/planner/__init__.py` (Tool-profile declaration and admission boundary)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/planner/core.py` (Tool-profile declaration and admission boundary)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/reference.py` (Tool-profile declaration and admission boundary)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/trial_compiler/compiler.py` (Tool-profile declaration and admission boundary)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/trial_compiler/tool_support.py` (Tool-profile declaration and admission boundary)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/trial_realization.py` (Tool-profile declaration and admission boundary)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/manager_plan_admission.py` (Tool-profile declaration and admission boundary)
- TESTS → TEST `implementations/python/tests/test_issue_304_tool_support.py` (Declared support, capacity, rejection, and evidence separation)
- TESTS → TEST `implementations/python/tests/test_issue_1660_review_regressions.py` (Selected processor retained during refresh and rechecked before effects)
- TESTS → TEST `implementations/python/tests/test_runtime_conformance.py` (Declared support, capacity, rejection, and evidence separation)
- IMPLEMENTS → SPEC `contracts/schemas/processor-manifest/processor-manifest-v2.json` (Portable tool-profile support declaration)
- IMPLEMENTS → SPEC `contracts/schemas/backend-manifest/backend-manifest-v2.json` (Portable tool-profile support declaration)
- DOCUMENTS → DOCUMENTATION `docs/decisions/issue-304-participant-tool-support.md` (Tool-profile support and compatibility)
- DOCUMENTS → DOCUMENTATION `docs/migration/participant-tool-support.md` (Tool-profile support and compatibility)
- DOCUMENTS → DOCUMENTATION `docs/explain/reference/backend-conformance.md` (Tool-profile support and compatibility)
- DOCUMENTS → DOCUMENTATION `docs/research/specification-coverage/captures/capture-6490c7fc0e9f0d9587f7e65bb5cc812594ad74ec66d362667e2433a858b8a548/manifest.json` (Current-source bounded evidence capture)
- DOCUMENTS → DOCUMENTATION `docs/research/formal-semantic-validation/captures/capture-d0248897f207f37e8f538ee2b9648dc10bbfd086bf49725ff19843ee8737463b/manifest.json` (Current-source bounded evidence capture)
- TESTS → TEST `implementations/python/tests/test_issue_1628_trial_control_admission.py` (Manifest omission and normalized-digest preservation)
- TESTS → TEST `implementations/python/tests/test_issue_1396_trial_replacement.py` (Manifest-bound trial identity and parent references)
- DOCUMENTS → DOCUMENTATION `docs/research/specification-coverage/captures/capture-f028e3196a4b3e8ff7b7621f6b7f8d3b54b43dc96646cc6eab5ce7607c217eb5/manifest.json` (Refactored-source bounded evidence capture)
- DOCUMENTS → DOCUMENTATION `docs/research/formal-semantic-validation/captures/capture-832b5183f66e7bde6a973833145eae377dc93eae938579d3d0eb4bbada7b47a3/manifest.json` (Refactored-source bounded evidence capture)
- DOCUMENTS → DOCUMENTATION `docs/research/specification-coverage/captures/capture-41a130a76cc3f34762cb4d93a7cbd80b29fc6ab688d4215dda55670783a17e6f/manifest.json` (Combined-source bounded evidence capture)
- DOCUMENTS → DOCUMENTATION `docs/research/formal-semantic-validation/captures/capture-7e5a5f0094de3729c27ed9cd5ba21caf99ca276e55822b0ea2de44f57c141d2a/manifest.json` (Combined-source bounded evidence capture)
