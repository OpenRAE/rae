---
id: SEM-220
title: "Participant Decision-Surface Semantics"
status: ACTIVE
type: FUNCTIONAL
priority: MUST
created_at: 2026-04-05T01:24:26.972019Z
updated_at: 2026-07-20T05:43:01.387740Z
---

# SEM-220 — Participant Decision-Surface Semantics

## Statement

The ecosystem shall define explicit semantics for participant decision surfaces, including open-ended action generation, constrained action forms, candidate-action sets, and their selection meaning.

## Rationale

Primary-source refresh shows that participant decision surfaces vary materially across ecosystems and require explicit semantics to remain portable.

## Traceability

- DOCUMENTS → ADR `docs/decisions/adrs/adr-083-participant-tool-decision-surface-and-exposure-semantics.md` (ADR-083 participant tool, decision-surface, and exposure semantics)
- DOCUMENTS → SPEC `specs/formal/participant-semantics/README.md` (Formal SEM-219/SEM-220/SEM-226 participant semantics)
- DOCUMENTS → DOCUMENTATION `docs/decisions/issue-119-sem-219-220-226-participant-decision-surface-preflight.md` (Issue 119 participant decision-surface architecture preflight)
- DOCUMENTS → DOCUMENTATION `docs/explain/reference/shared-semantic-integrity.md` (Shared semantic integrity mapping for SEM-219/SEM-220/SEM-226)
- DOCUMENTS → GITHUB_ISSUE `794` (Assess and design formal participant I/O control with information-flow and bisimulation semantics)
- DOCUMENTS → DOCUMENTATION `docs/research/participant-io-control/requirement-disposition.md` (Issue #794 participant information-flow/control requirement disposition)
- IMPLEMENTS → SPEC `contracts/schemas/control-plane/participant-decision-surface-v1.json` (Participant decision-surface v1 published schema)
- TESTS → TEST `implementations/python/tests/test_sem_220_participant_decision_surface.py` (SEM-220 participant decision-surface verification suite)
- DOCUMENTS → DOCUMENTATION `docs/explain/sdl/lineage.md` (SEM-220 participant decision-surface lineage and nonclaims)
- IMPLEMENTS → GITHUB_ISSUE `295` (Participant Decision-Surface Semantics (SEM-220))
- IMPLEMENTS → SPEC `contracts/schemas/control-plane/participant-decision-surface-v2.json` (participant-decision-surface-v2 published schema)
