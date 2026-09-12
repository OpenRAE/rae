---
id: SEM-217
title: "Semantics Of External Knowledge Bindings"
status: ACTIVE
type: FUNCTIONAL
priority: SHOULD
wave: 3
created_at: 2026-04-03T07:17:04.690343Z
updated_at: 2026-06-23T06:18:46.988350Z
---

# SEM-217 — Semantics Of External Knowledge Bindings

## Statement

The ecosystem shall define the semantic effect of external knowledge bindings, including when they annotate, constrain, refine, or align native meaning.

## Rationale

Requirement inventory expansion. External knowledge bindings need explicit semantics so they do not distort native meaning.

## Traceability

- TESTS → TEST `implementations/python/tests/test_classification_migration.py` (Externalized assertions preserve native runtime and require ordinary content disclosure)

- IMPLEMENTS → SPEC `specs/formal/participant-semantics/README.md` (SEM-217 external knowledge binding effect semantics)
- IMPLEMENTS → DOCUMENTATION `docs/explain/reference/shared-concept-model.md` (SEM-217 shared concept model binding-effect guidance)
- TESTS → TEST `implementations/python/tests/test_sem_217_knowledge_bindings.py` (SEM-217 external knowledge binding effect tests)
- DOCUMENTS → DOCUMENTATION `docs/explain/reference/shared-semantic-integrity.md` (Shared semantic integrity SEM-217 coverage row)
