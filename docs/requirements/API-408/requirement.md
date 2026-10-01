---
id: API-408
title: "Participant Observation And Retrieval Contracts"
status: ACTIVE
type: INTERFACE
priority: SHOULD
wave: 2
created_at: 2026-04-03T06:16:04.481738Z
updated_at: 2026-09-21T00:00:00Z
---

# API-408 — Participant Observation And Retrieval Contracts

## Statement

The control-plane contract shall provide portable retrieval surfaces for participant status, derived context views, and histories.

## Rationale

Requirement inventory expansion. Participant execution must be observable through portable contracts, not only through backend-local inspection.

## Traceability

- DOCUMENTS → ADR `docs/decisions/adrs/adr-060-participant-backend-facing-contract-surface.md` (ADR-060 participant backend-facing contract surface)
- DOCUMENTS → SPEC `specs/formal/runtime-contracts/participant-backend-contracts.md` (Participant backend-facing contracts formal design (API-408 retrieval projections))
- DOCUMENTS → SPEC `contracts/schemas/control-plane/participant-status-view-v1.json` (Generated participant status view schema)
- DOCUMENTS → SPEC `contracts/schemas/control-plane/participant-history-view-v1.json` (Generated participant history view schema)
- DOCUMENTS → SPEC `contracts/schemas/control-plane/participant-context-view-v1.json` (Generated participant context view schema)
- TESTS → TEST `implementations/python/tests/test_participant_backend_contracts.py` (Participant retrieval-view fixture and schema tests)
- TESTS → TEST `implementations/python/tests/test_runtime_control_plane.py` (Runtime participant retrieval projection tests)
- TESTS → TEST `implementations/python/tests/test_runtime_control_plane_api.py` (HTTP participant retrieval route tests)
- TESTS → TEST `implementations/python/tests/test_act_614_temporal_durability.py` (Temporal assessments through history retrieval and durable readback)
