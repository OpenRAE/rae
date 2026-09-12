---
id: ASR-536
title: "Intentional-Subversion Participant Control Evaluation"
status: DRAFT
type: NON_FUNCTIONAL
priority: MUST
wave: 4
created_at: 2026-07-30T18:36:58.392300Z
updated_at: 2026-09-06T00:00:00Z
---

# ASR-536 — Intentional-Subversion Participant Control Evaluation

## Statement

The ecosystem shall define revisioned participant-control evaluation profiles that distinguish honest from intentionally subverting behavior and bind main and side objectives, participant capabilities, policy and monitor knowledge, adaptive strategies, collusion and correlated monitor failure, audit budgets and selection rules, trusted editing, approval, deferral, interruption and shutdown protocols, cross-participant and cross-episode memory, replayable evidence, and separate safety, usefulness, intervention-cost, audit-cost, uncertainty, limitation, and nonclaim measures.

Evaluations shall consume exact realized participant-control compositions,
pinning mechanism, profile, provider/implementation, configuration, trigger/effect
rules and backend evidence under SEM-235 and ASR-538. Known adversarial inputs
inside the admitted world may intentionally be delivered and tracked; their
expected disposition is determined by the selected policy. Out-of-world
provider or backend interference shall invalidate realization rather than be
classified as an in-world attack. At least one real conformant backend is
required for realization-based results, and every additional backend claim
requires its own evidence without presumed mechanism parity or equivalence.

## Rationale

ASR-535 provides bounded participant-flow assurance discipline, but ordinary negative tests and monitor accuracy do not establish robustness against a participant that knows and adapts to the control protocol. Issue #812 adds an explicit experimental authority for intentional subversion without treating a monitor score as authorization or importing apparatus-specific LLM internals into portable records.

## Traceability

- DOCUMENTS → ADR `docs/decisions/adrs/adr-108-modular-participant-control-and-governed-effects.md` (Modular architecture and declared-world boundary)
- DOCUMENTS → DOCUMENTATION `docs/research/modular-participant-control/requirements.md` (Issue #1068 amendment disposition)

- TESTS → TEST `implementations/python/tests/test_issue_1004_apparatus_backend_capabilities.py` (ASR-536 honest/unsupported/weakened/overclaiming/colluding declaration fixtures)
- DOCUMENTS → GITHUB_ISSUE `https://github.com/OpenRAE/rae/issues/812` (Issue #812 adversarial participant control design)
- DOCUMENTS → ADR `docs/decisions/adrs/adr-101-adversarial-participant-flow-control.md` (ADR-101: Adversarial Participant Boundary Flow Control)
- DOCUMENTS → SPEC `specs/formal/participant-semantics/adversarial-flow-control.md` (SEM-233 and ASR-536 formal authority)
- DOCUMENTS → DOCUMENTATION `docs/research/adversarial-participant-control/implementation-program.json` (Adversarial participant control implementation program)
- DOCUMENTS → GITHUB_ISSUE `https://github.com/OpenRAE/rae/issues/1004` (Issue #1004 apparatus and backend support)
- DOCUMENTS → GITHUB_ISSUE `https://github.com/OpenRAE/rae/issues/1007` (Issue #1007 adversarial evaluation)
- DOCUMENTS → GITHUB_ISSUE `https://github.com/OpenRAE/rae/issues/1008` (Issue #1008 evidenced documentation)
- DOCUMENTS → GITHUB_ISSUE `812` (Issue #812 adversarial participant control design)
