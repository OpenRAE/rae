---
id: API-412
title: "Processor Identity, Capability, And Compatibility Manifest"
status: ACTIVE
type: FUNCTIONAL
priority: MUST
wave: 1
created_at: 2026-04-04T22:58:16.942288Z
updated_at: 2026-04-12T03:13:40.484438Z
---

# API-412 — Processor Identity, Capability, And Compatibility Manifest

## Statement

The ecosystem shall define a processor manifest by which a processor declares its identity, supported language and contract versions, supported processing features, compatibility surface, and declared constraints, independent of any one task's authored specificity or realized form.

## Rationale

Current state: implemented. Processor manifests now publish a processor-specific v2 surface only: identity, supported SDL and contract versions, governed processing features, backend-only compatibility, and concept bindings validated against the shared concept and manifest authority stack. The old processor-manifest/v1 compatibility surface has been removed.

## Traceability

- IMPLEMENTS → CODE_FILE `tools/generate_contract_schemas.py` (Schema generation routing for processor manifest)
- TESTS → TEST `implementations/python/tests/test_processor_manifest.py` (Processor manifest unit tests)
- TESTS → TEST `implementations/python/tests/test_runtime_contracts.py` (Contract schema bundle and closed-world tests)
- DOCUMENTS → DOCUMENTATION `contracts/schemas/README.md` (Published Contract Schemas Overview)
- DOCUMENTS → DOCUMENTATION `docs/explain/sdl/runtime-architecture.md` (SDL Runtime Architecture)
- CONSTRAINS → SPEC `contracts/schemas/processor-manifest/processor-manifest-v2.json` (Processor Manifest Schema v2)
- IMPLEMENTS → SPEC `contracts/schemas/processor-manifest/processor-manifest-v2.json` (processor-manifest-v2 published schema)
