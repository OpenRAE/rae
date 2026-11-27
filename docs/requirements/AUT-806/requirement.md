---
id: AUT-806
title: "Examples, Templates, And Pattern Libraries"
status: ACTIVE
type: FUNCTIONAL
priority: MUST
wave: 2
created_at: 2026-04-03T07:15:30.275877Z
updated_at: 2026-05-24T05:36:11.479760Z
---

# AUT-806 — Examples, Templates, And Pattern Libraries

## Statement

The ecosystem shall maintain worked examples, templates, and reusable pattern libraries for scenarios, workflows, participant behavior, tasks, runs, and studies.

## Rationale

Requirement inventory expansion. Mature ecosystems need reusable examples and patterns, not just validation fixtures.

## Traceability

- IMPLEMENTS → CODE_FILE `examples/scenarios/cloud-resources/cloud-secret-cross-project.sdl.yaml` (Cross-project identity and secret-service example)

- IMPLEMENTS → CODE_FILE `examples/library/catalog.yaml` (AUT-806 example template and pattern library catalog)
- IMPLEMENTS → POLICY `tools/check_example_library.py` (AUT-806 example library policy checker)
- TESTS → TEST `implementations/python/tests/test_example_library_policy.py` (AUT-806 example library policy tests)
- DOCUMENTS → DOCUMENTATION `README.md` (Agentic Cyber Environment System README)
- DOCUMENTS → DOCUMENTATION `docs/explain/reference/canonical-reference-map.md` (Canonical Reference Map)
