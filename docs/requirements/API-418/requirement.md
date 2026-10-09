---
id: API-418
title: "Participant Budget And Usage Contracts"
status: DRAFT
type: INTERFACE
priority: MUST
created_at: 2026-04-05T01:39:34.343447Z
updated_at: 2026-04-05T01:39:34.343447Z
---

# API-418 — Participant Budget And Usage Contracts

## Statement

The ecosystem shall define plain-data contracts for participant budgets, quotas, usage accounting, and limit-triggered status or outcome reporting.

## Rationale

Primary-source refresh shows that participant budgets and quota consumption need portable reporting surfaces if runs and benchmarks are to remain comparable.

## Traceability

- IMPLEMENTS → SPEC `contracts/schemas/participant-runtime/participant-resource-budget-event-v1.json` (participant-resource-budget-event-v1 published schema)
- IMPLEMENTS → SPEC `contracts/schemas/participant-runtime/participant-resource-budget-policy-v1.json` (participant-resource-budget-policy-v1 published schema)
- IMPLEMENTS → SPEC `contracts/schemas/participant-runtime/participant-resource-budget-state-v1.json` (participant-resource-budget-state-v1 published schema)
- IMPLEMENTS → SPEC `contracts/schemas/participant-runtime/participant-resource-pool-capacity-v1.json` (participant-resource-pool-capacity-v1 published schema)
