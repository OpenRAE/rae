---
id: ACT-610
title: "Defensive Behavior Vocabularies"
status: ACTIVE
type: FUNCTIONAL
priority: SHOULD
wave: 2
created_at: 2026-04-03T06:14:53.132970Z
updated_at: 2026-07-20T00:36:18.206356Z
---

# ACT-610 — Defensive Behavior Vocabularies

## Statement

The ecosystem shall support defensive behavior vocabularies for expressing detection, investigation, response, containment, and recovery-oriented participant tasks, goals, or activities.

## Rationale

Requirement inventory expansion. Defensive behavior needs its own expressible vocabulary rather than being reduced to post-hoc evaluation only.

## Traceability

- IMPLEMENTS → GITHUB_ISSUE `210` (Defensive Behavior Vocabularies (ACT-610))
- IMPLEMENTS → CONFIG `contracts/concept-authority/controlled-vocabularies-v1.json` (Governed participant defensive behavior vocabulary)
- IMPLEMENTS → CONFIG `contracts/schemas/concept-authority/nist-csf-defensive-categories-source-v1.json` (NIST CSF defensive category source schema)
- IMPLEMENTS → CONFIG `contracts/concept-authority/nist-csf-defensive-categories-source-v1.json` (Pinned NIST CSF 2.0 defensive category source)
- IMPLEMENTS → SPEC `contracts/schemas/concept-authority/external-concept-bindings-v1.json` (Generic authored defensive behavior classification contract)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/external_concept_bindings.py` (Neutral NIST CSF source snapshot adapter)
- IMPLEMENTS → SPEC `specs/formal/participant-behavior-model/README.md` (Formal defensive behavior reference contract)
- IMPLEMENTS → SPEC `specs/concept-authority/controlled-vocabularies.md` (Defensive vocabulary authority and lineage specification)
- TESTS → TEST `implementations/python/tests/test_controlled_vocabularies.py` (Defensive vocabulary authority and source validation tests)
- TESTS → TEST `implementations/python/tests/test_classification_migration.py` (Generic defensive behavior migration and native runtime noninterference tests)
- TESTS → TEST `tools/check_nist_csf_defensive_vocabulary.py` (NIST CSF defensive vocabulary conformance checker)
