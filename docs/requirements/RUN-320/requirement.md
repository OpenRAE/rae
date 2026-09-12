---
id: RUN-320
title: "Modular Participant-Control Orchestration and Governed Trigger Execution"
status: DRAFT
type: FUNCTIONAL
priority: MUST
wave: 4
created_at: 2026-09-06T00:00:00Z
updated_at: 2026-09-06T00:00:00Z
---

# RUN-320 — Modular Participant-Control Orchestration and Governed Trigger Execution

## Statement

The RAES runtime shall invoke admitted participant-control providers through
the public protocol, compose their exact-cut results under SEM-235, and admit
and commit every effective decision and typed effect intent through existing
crossing/control and operation-store authority before backend effect or
participant disclosure. It shall preserve append-only contribution, provider
state, causal and realization evidence; fresh derived identities; stable
logical effect keys; finite root/depth/firing/retry budgets; predecessor and
subsequent effect distinctions; and ordinary downstream admission. Missing
mandatory support, unaccepted weakening, stale state, conflict, exhausted
required triggers and failed commit shall cause no prohibited dispatch.
Recovery shall distinguish intent, dispatch, observed application and external
uncertainty without blind duplicate execution or unsupported exactly-once
claims. Runtime orchestration shall not select or load scenario-designated
code, implement backend-specific mechanism branches, or take ownership of
out-of-world provider integrity.

## Rationale

RUN-319 and RUN-310 supply crossing/control enforcement and ADR-104 supplies
operation durability. The new owner adds mechanism-neutral composition and
bounded triggered execution while retaining those boundaries.

## Fulfillment boundary

DRAFT through #1068. #1069 follows semantic and contract publication and tests
real final sinks, concurrency, both supported stores, crash/replay limits,
IFC-triggered injects and at least one other effect. Synthetic providers are
runtime/contract evidence only; downstream providers own real instrumentation.

## Traceability

- DOCUMENTS → GITHUB_ISSUE `https://github.com/OpenRAE/rae/issues/1068` (Architecture)
- DOCUMENTS → GITHUB_ISSUE `https://github.com/OpenRAE/rae/issues/1069` (Runtime orchestration)
- DOCUMENTS → ADR `docs/decisions/adrs/adr-108-modular-participant-control-and-governed-effects.md` (ADR-108)
- DOCUMENTS → DOCUMENTATION `docs/research/modular-participant-control/composition.md` (PC-05 through PC-12 and PC-15)
- TESTS → TEST `docs/research/modular-participant-control/check_design.py` (Bounded abstract transition counterexamples only)
