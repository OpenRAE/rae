---
id: API-424
title: "Participant-Control Provider, Composition and Effect Contracts"
status: DRAFT
type: INTERFACE
priority: MUST
wave: 4
created_at: 2026-09-06T00:00:00Z
updated_at: 2026-09-06T00:00:00Z
---

# API-424 — Participant-Control Provider, Composition and Effect Contracts

## Statement

RAES shall publish closed, versioned portable contracts and a public
participant-control provider protocol for exact profile/mechanism selection,
resolved facts, deterministic decisions, advisory results, composition and
typed effect requests. The contracts shall bind apparatus, implementation,
configuration, authority, provenance, limitations, participant/episode,
crossing/sink, state cut, expected history, provider state and causal identities;
preserve every contributing result and explicit unsupported, abstain, conflict,
stale, failed, weakened and realization dispositions; and reuse existing action,
crossing, inject, intervention, lifecycle and evidence carriers. Executable code
selection, open label/effect/metadata maps and backend-private state shall not
be portable request authority. Backend declarations and effective support shall
remain distinct from installed providers and realized effects.

## Rationale

API-409/423 own incumbent operations and API-407/420 own capability/manifests.
They need closed composition and provider bindings, including typed review,
delay and lifecycle effect targets, before the runtime replaces its implicit
SEM-233 resolver hook. This is a protocol boundary, not a plugin host.

## Fulfillment boundary

DRAFT through #1068. #1072 follows #1070 and must publish schemas, publication
ledger records, protocol compatibility, valid/invalid fixtures and contextual
validators. No current schema or importable provider protocol is changed by
this requirement record.

## Traceability

- DOCUMENTS → GITHUB_ISSUE `https://github.com/OpenRAE/rae/issues/1068` (Architecture)
- DOCUMENTS → GITHUB_ISSUE `https://github.com/OpenRAE/rae/issues/1072` (Contract publication)
- DOCUMENTS → ADR `docs/decisions/adrs/adr-108-modular-participant-control-and-governed-effects.md` (ADR-108)
- DOCUMENTS → DOCUMENTATION `docs/research/modular-participant-control/composition.md` (PC-01 through PC-03 and PC-07 through PC-15)
