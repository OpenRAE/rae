---
id: ACT-609
title: "Offensive Behavior Vocabularies"
status: ACTIVE
type: FUNCTIONAL
priority: SHOULD
wave: 2
created_at: 2026-04-03T06:14:53.030734Z
updated_at: 2026-07-03T02:19:52.591583Z
---

# ACT-609 — Offensive Behavior Vocabularies

## Statement

The ecosystem shall support offensive behavior vocabularies for expressing attack-oriented participant tasks, goals, or activities.

## Rationale

Requirement inventory expansion. Offensive behavior must be expressible as a first-class participant concern rather than as ad hoc backend behavior.

## Traceability

- IMPLEMENTS → SPEC `contracts/concept-authority/attack-enterprise-tactics-source-v1.json` (Pinned MITRE ATT&CK Enterprise tactic source record)
- IMPLEMENTS → SPEC `contracts/concept-authority/atlas-tactics-source-v1.json` (Pinned MITRE ATLAS tactic source record)
- IMPLEMENTS → SPEC `contracts/concept-authority/controlled-vocabularies-v1.json` (Controlled vocabulary authority artifact for offensive behavior references)
- IMPLEMENTS → SPEC `contracts/schemas/concept-authority/controlled-vocabularies-v1.json` (Controlled vocabulary schema for offensive behavior references)
- IMPLEMENTS → SPEC `contracts/schemas/concept-authority/external-concept-bindings-v1.json` (Generic authored behavior classifications with explicit source coordinates)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/external_concept_bindings.py` (Neutral ATT&CK and ATLAS source snapshot adapters)
- IMPLEMENTS → SPEC `specs/concept-authority/controlled-vocabularies.md` (Controlled vocabulary lineage and conformance specification)
- IMPLEMENTS → SPEC `specs/formal/participant-behavior-model/README.md` (Participant behavior model specification for offensive behavior references)
- IMPLEMENTS → DOCUMENTATION `docs/explain/sdl/sections.md` (SDL authoring documentation for offensive behavior references)
- IMPLEMENTS → DOCUMENTATION `docs/decisions/issue-209-act-609-offensive-behavior-vocabularies-preflight.md` (Issue 209 vocabulary lineage and architectural preflight record)
- TESTS → TEST `implementations/python/tests/test_controlled_vocabularies.py` (Controlled vocabulary authority, source lineage, and conformance tests)
- TESTS → TEST `implementations/python/tests/test_classification_migration.py` (Generic behavior binding migration and native runtime noninterference tests)
- TESTS → TEST `tools/check_attack_tactic_vocabulary.py` (Pinned MITRE ATT&CK Enterprise tactic vocabulary conformance guard)
- TESTS → TEST `tools/check_atlas_tactic_vocabulary.py` (Pinned MITRE ATLAS tactic vocabulary conformance guard)
- TESTS → CONFIG `noxfile.py` (Standard verify gate invokes ATT&CK and ATLAS vocabulary conformance checks)
- IMPLEMENTS → SPEC `contracts/schemas/concept-authority/attack-enterprise-tactics-source-v1.json` (Schema for pinned MITRE ATT&CK Enterprise tactic source records)
- IMPLEMENTS → SPEC `contracts/schemas/concept-authority/atlas-tactics-source-v1.json` (Schema for pinned MITRE ATLAS tactic source records)
- IMPLEMENTS → CONFIG `contracts/schema-publication-manifest.json` (Schema publication manifest entries for offensive behavior vocabulary authority schemas)
