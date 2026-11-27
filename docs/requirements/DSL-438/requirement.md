---
id: DSL-438
title: "Target-Node CPU Architecture Semantics"
status: ACTIVE
type: FUNCTIONAL
priority: MUST
wave: 1
created_at: 2026-08-02T14:43:12.079794Z
updated_at: 2026-10-21T00:00:00Z
---

# DSL-438 — Target-Node CPU Architecture Semantics

## Statement

The language shall represent a target-node CPU architecture requirement as a first-class, optional VM-node attribute drawn from a governed canonical vocabulary with authoring aliases, case-insensitive normalization, and a governed extension form for custom values, kept distinct from runtime-package artifact architecture and from backend host architecture; shall define deterministic, fail-closed compatibility between a target node and each architecture-constrained runtime package, including that a node without a target architecture may not carry an architecture-constrained package; shall give absence explicit no-requirement semantics that never infer the controller, host, runner, image, or emulator default architecture; and shall expose the requirement to backend realization-support disclosure so a conformant backend can report whether it can realize the target architecture without the processor selecting a runner.

## Rationale

Issue #674: the SDL Node model had no CPU architecture attribute — Resources carried only RAM and CPU count, and the runtime-package architecture field describes a package artifact, not the architecture the target node or guest requires. Without a first-class, governed target-node architecture, an authored environment cannot express a realization-relevant node constraint and cross-backend equivalence is ambiguous. RAES owns the controlled architecture value, schema placement, normalization, and target/package compatibility; env-packs, adapters, and backends retain physical host capability, selection, negotiation, and realization evidence.

## Traceability

- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/architectures.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/nodes.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/runtime_configuration.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/validator/_nodes_infra_network.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/phase_contracts.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/instantiate.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes/scenario.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/semantics/realization_concerns.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/models/resources.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/models/runtime_model.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/compiler/provisioning.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/planner/capability_domains.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/planner/manifest_validation.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/satisfiability/_translation.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_backend_protocols/provisioner_capabilities.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_backend_protocols/provisioner_manifest.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_backend_stubs/manifest.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/capabilities.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/base.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/realization_envelope.py`
- TESTS → TEST `implementations/python/tests/test_node_architecture.py`
- TESTS → TEST `implementations/python/tests/test_sdl_models.py`
- TESTS → TEST `implementations/python/tests/test_controlled_vocabularies.py`
- TESTS → TEST `implementations/python/tests/test_backend_manifest.py`
- TESTS → TEST `implementations/python/tests/test_sem_218_realization_designation.py`
- IMPLEMENTS → GITHUB_ISSUE `674` (Add target-node CPU architecture semantics to SDL)
- IMPLEMENTS → DOCUMENTATION `docs/decisions/issue-674-target-node-cpu-architecture-preflight.md` (Issue #674 target-node CPU architecture preflight decision note (defines vocabulary, normalization, compatibility rules, absence semantics))
- IMPLEMENTS → CONFIG `contracts/concept-authority/controlled-vocabularies-v1.json` (Concept-authority controlled vocabularies — provisioner-node-architectures governed vocabulary)
