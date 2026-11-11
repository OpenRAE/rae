---
id: ASR-537
title: "Cross-Backend Participant-Control Realization and Transfer Evidence"
status: DRAFT
type: NON_FUNCTIONAL
priority: MUST
wave: 4
created_at: 2026-07-31T02:14:06.940076Z
updated_at: 2026-07-31T02:14:14.753798Z
---

# ASR-537 — Cross-Backend Participant-Control Realization and Transfer Evidence

## Statement

RAES SHALL define and execute a revision-pinned cross-backend participant-control evidence protocol that: (1) evaluates the same authored participant-control policy in pure simulation, pure emulation/operation, simultaneous mixed composition, and linked or pre-admitted staged realization cases; (2) binds every result to scenario/policy digests, trial/run identity, apparatus and adapter identities, capability and conformance results, realization allocation/topology, clock/order mappings, data/model/seed provenance, losses, limitations, and reproduction evidence; (3) includes stale handoff, concurrent intervention, unsupported or falsely declared capability, timestamp-only or unmapped ordering, simulation-only observation, unrealizable action, directed-delivery failure, prior-delivery retraction, and bridge-metadata leakage cases; (4) requires rejection or zero prohibited effects where authority, policy, mapping, admission, or commit fails; and (5) reports bounded conformance, interoperability readiness, empirical sim-to-em transfer, trace inclusion, bisimulation, IFC/noninterference, and backend equivalence as distinct claims with no silent promotion.

## Rationale

Shared action/observation interfaces and paired backend runs do not establish simultaneous mixed realization, semantic equivalence, or transfer. Current cyber-range evidence shows material sim/em mismatch, while DSEEP, SIRL, HLA, co-simulation, and digital-twin precedents require purpose-bound apparatus, topology, time, provenance, uncertainty, and reproducibility evidence.

## Traceability

- DOCUMENTS → DOCUMENTATION `docs/explain/reference/revised-control-semantics.md` (Current supported arrangements and bounded evidence; no requirement promotion)
- DOCUMENTS → GITHUB_ISSUE `OpenRAE/rae#1017` (Conform mixed-composition backend capabilities)
- DOCUMENTS → GITHUB_ISSUE `OpenRAE/rae#1018` (Demonstrate mixed cross-backend participant control)
- DOCUMENTS → GITHUB_ISSUE `OpenRAE/rae#1019` (Reconcile mixed participant-control claims)
- DOCUMENTS → DOCUMENTATION `docs/research/cross-backend-participant-control/demonstration-protocol.md` (ASR-537 cross-backend participant-control demonstration protocol)
- DOCUMENTS → DOCUMENTATION `docs/research/cross-backend-participant-control/implementation-program.json` (Issue 813 machine-readable implementation program)
- TESTS → TEST `implementations/python/tests/test_issue_813_cross_backend_participant_control_design.py` (Issue 813 structural acceptance gate)
- DOCUMENTS → GITHUB_ISSUE `OpenRAE/rae#813` (Design cross-backend participant control against simulation and cyber-range precedents)

## Current evidence boundary

The #1018 demonstration executes RAE through controlled test providers.
It includes simultaneous mixed execution, staged handoff, and separate reusable-control and governed-effect paths.
Its retained record binds the apparatus, source, observations, and fresh-process comparison.
The [demonstration guide](../../explain/reference/mixed-control-demonstration.md) states its limits.
This evidence does not complete the broader realization and transfer protocol above.
It establishes no native qualification, backend equivalence, independent-party reproduction, or simulation-to-operation transfer.
The requirement remains DRAFT.
