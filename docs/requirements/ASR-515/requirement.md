---
id: ASR-515
title: "Validation Strength Disclosure"
status: ACTIVE
type: FUNCTIONAL
priority: MUST
wave: 3
created_at: 2026-04-03T07:17:05.349707Z
updated_at: 2026-07-05T03:35:08.628598Z
---

# ASR-515 — Validation Strength Disclosure

## Statement

The ecosystem shall preserve and expose the strength, profile, and limitations of the validation or admission basis used for scenarios, tasks, runs, and studies.

## Rationale

Requirement inventory expansion. Consumers need explicit disclosure of what validation basis supports a given claim.

## Traceability

- IMPLEMENTS → ADR `docs/decisions/adrs/adr-072-validation-and-admission-profiles.md` (ADR-072 validation and admission profiles)
- IMPLEMENTS → SPEC `specs/formal/validation-admission-profiles/README.md` (Validation and admission profiles formal specification)
- IMPLEMENTS → SPEC `specs/formal/assurance-fulfillment.yaml` (Assurance fulfillment mapping for validation-admission profiles)
- IMPLEMENTS → SPEC `contracts/schemas/profiles/validation-basis-disclosure-v1.json` (validation-basis-disclosure-v1 published schema)
