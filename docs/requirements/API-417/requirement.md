---
id: API-417
title: "Participant Episode And Reset Contracts"
status: DRAFT
type: INTERFACE
priority: MUST
created_at: 2026-04-05T01:39:34.231481Z
updated_at: 2026-04-05T01:39:34.231481Z
---

# API-417 — Participant Episode And Reset Contracts

## Statement

The ecosystem shall define plain-data contracts for participant episode initialization, reset, completion, truncation, timeout, interruption, and restart observation.

## Rationale

Primary-source refresh shows that episode lifecycle handling needs portable external contracts rather than backend-local conventions.

## Traceability

- IMPLEMENTS → SPEC `contracts/schemas/control-plane/participant-episode-history-event-stream-v1.json` (participant-episode-history-event-stream-v1 published schema)
- IMPLEMENTS → SPEC `contracts/schemas/control-plane/participant-episode-state-envelope-v1.json` (participant-episode-state-envelope-v1 published schema)
