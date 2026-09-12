---
id: SEM-235
title: "Modular Participant Control and Extensible Dynamic IFC Semantics"
status: DRAFT
type: FUNCTIONAL
priority: MUST
wave: 4
created_at: 2026-09-06T00:00:00Z
updated_at: 2026-09-06T00:00:00Z
---

# SEM-235 — Modular Participant Control and Extensible Dynamic IFC Semantics

## Statement

RAES shall define revisioned participant-control profile and mechanism
composition semantics over the declared participant/world boundary, including
extensible dynamic information-flow-control domains with closed carriers,
orders, conservative joins, source/default and propagation rules, policy
resolution, memory scope and explicit release authority. Profiles shall select
finite exact mechanism sets with mandatory/advisory roles, acyclic dependencies,
deterministic conjunction and conflict rules, explicit absence, unsupported,
stale, weakened and failure behavior, and independently authorized typed effect
requests. Triggered transformations and injects shall preserve exact state cuts,
fresh identity, provenance, participant visibility, ordinary downstream
admission, idempotency and finite causal budgets. SEM-233's published security
domain and historical meaning shall remain intact; backend integrity outside
the declared world shall remain a realization responsibility.

## Rationale

SEM-230 supplies participant-relative flow and SEM-233 supplies its security
profile. Neither owns arbitrary non-security domains or composition with
non-IFC mechanisms. ADR-108 establishes that missing scope without requiring
identical backend mechanisms or an executable policy language in RAES.

## Fulfillment boundary

The requirement remains DRAFT through #1068. #1070 must publish revisioned
formal clauses, concept-authority placement, lineage, worked examples and
bounded falsification evidence. Downstream contracts, runtime and realization
have separate owners; acceptance of this design is not their implementation.

## Traceability

- DOCUMENTS → GITHUB_ISSUE `https://github.com/OpenRAE/rae/issues/1068` (Modular participant-control architecture)
- DOCUMENTS → GITHUB_ISSUE `https://github.com/OpenRAE/rae/issues/1070` (Semantic publication)
- DOCUMENTS → ADR `docs/decisions/adrs/adr-108-modular-participant-control-and-governed-effects.md` (ADR-108)
- DOCUMENTS → DOCUMENTATION `docs/research/modular-participant-control/composition.md` (Architectural composition contract PC-01 through PC-15)
- DOCUMENTS → DOCUMENTATION `docs/research/modular-participant-control/cases.md` (Worked examples and counterexamples)
- TESTS → TEST `docs/research/modular-participant-control/check_design.py` (Bounded abstract-design falsification only)
