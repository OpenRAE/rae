---
id: EXP-733
title: "Participant Implementation And Exposure Provenance"
status: ACTIVE
type: FUNCTIONAL
priority: MUST
created_at: 2026-04-05T02:10:21.745292Z
updated_at: 2026-05-29T01:20:49.639885Z
---

# EXP-733 — Participant Implementation And Exposure Provenance

## Statement

The ecosystem shall preserve, as part of run and apparatus provenance, the participant implementations used in a run together with their selected manifests, configurations, and decision-surface exposure policies, distinct from authored participant intent, processor provenance, backend provenance, and derived results.

## Rationale

Current state: identified gap. If the same scenario can be driven by different participant implementations, the run record must preserve which implementation actually ran and what participant-visible surface it received.

## Traceability

- TESTS → TEST `implementations/python/tests/test_participant_implementation_manifest.py` (Participant implementation provenance validation tests)
- TESTS → TEST `implementations/python/tests/test_runtime_contracts.py` (Participant provenance schema bundle tests)
- DOCUMENTS → ADR `ADR-041` (Participant Implementation Manifest and Provenance Surface)
- IMPLEMENTS → SPEC `contracts/schemas/participant-implementation-provenance/participant-implementation-provenance-v1.json` (Participant implementation provenance v1 JSON Schema)
- IMPLEMENTS → SPEC `contracts/schemas/participant-implementation-configuration/participant-configuration-result-v1.json` (participant-configuration-result-v1 published schema)
