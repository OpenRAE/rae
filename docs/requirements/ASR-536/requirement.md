---
id: ASR-536
title: "Intentional-Subversion Participant Control Evaluation"
status: ACTIVE
type: NON_FUNCTIONAL
priority: MUST
wave: 4
created_at: 2026-07-30T18:36:58.392300Z
updated_at: 2026-10-29T00:00:00Z
---

# ASR-536 — Intentional-Subversion Participant Control Evaluation

## Statement

The ecosystem shall define revisioned participant-control evaluation profiles that distinguish honest from intentionally subverting behavior and bind main and side objectives, participant capabilities, policy and monitor knowledge, adaptive strategies, collusion and correlated monitor failure, audit budgets and selection rules, trusted editing, approval, deferral, interruption and shutdown protocols, cross-participant and cross-episode memory, replayable evidence, and separate safety, usefulness, intervention-cost, audit-cost, uncertainty, limitation, and nonclaim measures.

RAE evaluations shall use RAE-owned, backend-neutral harnesses over public
contracts and runtime seams. Each result shall pin the exact contract and
profile revisions, mechanism/provider fixture implementation, configuration,
policy, apparatus, attacker/monitor assignment, memory, trigger/effect rules,
source content, and execution evidence under SEM-235 and ASR-538.
Known adversarial inputs inside the admitted world may intentionally be delivered
and tracked. The selected policy determines their expected disposition.
Out-of-world provider or apparatus interference shall invalidate the affected
result rather than count as an in-world attack.

Concrete backend implementation or realization is not a prerequisite for RAE
harness evaluation or publication. A concrete backend claim requires its own
exact realization evidence. Harness results shall not imply backend qualification,
mechanism parity, or equivalence.

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
- IMPLEMENTS → GITHUB_ISSUE `1008` (Bounded backend-neutral RAE harness evaluation publication)
- DOCUMENTS → GITHUB_ISSUE `812` (Issue #812 adversarial participant control design)

- IMPLEMENTS → SPEC `specs/formal/participant-semantics/adversarial-flow-control.md` (Revisioned intentional-subversion profile and separate measures)
- IMPLEMENTS → DOCUMENTATION `docs/explain/reference/adversarial-control-evaluation.md` (Exact RAE harness results, reproduction, limitations and nonclaims)
- TESTS → TEST `implementations/python/tests/issue_1007_intentional_subversion_harness.py` (RAE-owned protocol, typed cases and executed runtime evidence)
- TESTS → TEST `implementations/python/tests/test_issue_1007_intentional_subversion_evaluation.py` (Intentional-subversion runtime, denial, adaptive replay and disclosure checks)
- TESTS → TEST `implementations/python/tests/test_issue_1008_evaluation_backed_claims.py` (Retained report joins, tamper rejection and fresh recollection)
- TESTS → TEST `docs/research/modular-participant-control/check_design.py` (RAE evaluation and publication have no concrete backend prerequisites)
- TESTS → TEST `implementations/python/tests/issue_1008_harness_publication.py` (Local source-bound publication, verification and recollection)
