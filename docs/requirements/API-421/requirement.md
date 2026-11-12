---
id: API-421
title: "Time Model And Clock Declaration Contracts"
status: DRAFT
type: INTERFACE
priority: MUST
created_at: 2026-04-05T03:33:03.424812Z
updated_at: 2026-04-05T03:33:03.424812Z
---

# API-421 — Time Model And Clock Declaration Contracts

## Statement

The ecosystem shall define portable contracts and capability declarations for supported time domains, clock surfaces, pacing and synchronization modes, and temporal guarantees.

## Rationale

Independent processors and backends need explicit external declarations for how time is handled, not just implicit behavior behind a runtime boundary.

## Traceability

- DOCUMENTS → SPEC `https://fmi-standard.org/docs/3.0.2/` (FMI 3.0.2 Specification)
- IMPLEMENTS → SPEC `contracts/schemas/time/realized-time-model-v1.json` (realized-time-model-v1 published schema)
- IMPLEMENTS → SPEC `contracts/schemas/time/time-model-v1.json` (time-model-v1 published schema)
- IMPLEMENTS → SPEC `contracts/schemas/time/time-runtime-state-v1.json` (time-runtime-state-v1 published schema)
