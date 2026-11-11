---
id: API-411
title: "Participant Outcome Reporting Contracts"
status: DRAFT
type: INTERFACE
priority: SHOULD
wave: 2
created_at: 2026-04-03T06:16:04.805451Z
updated_at: 2026-04-03T06:16:04.805451Z
---

# API-411 — Participant Outcome Reporting Contracts

## Statement

The ecosystem shall define plain-data contracts for participant-local outcomes and their relationship to scenario and workflow state.

## Rationale

Requirement inventory expansion. Participant-local outcomes need portable external reporting semantics.

## Traceability

- DOCUMENTS → ADR `docs/decisions/adrs/adr-060-participant-backend-facing-contract-surface.md` (ADR-060 participant backend-facing contract surface)
- DOCUMENTS → SPEC `specs/formal/runtime-contracts/participant-backend-contracts.md` (Participant backend-facing contracts formal design (API-411 outcome reports))
- DOCUMENTS → SPEC `contracts/schemas/participant-runtime/participant-outcome-report-v1.json` (Generated participant outcome report schema)
- TESTS → TEST `implementations/python/tests/test_participant_backend_contracts.py` (Participant outcome-report fixture and schema tests)
- IMPLEMENTS → SPEC `contracts/schemas/participant-runtime/participant-outcome-report-v1.json` (participant-outcome-report-v1 published schema)
