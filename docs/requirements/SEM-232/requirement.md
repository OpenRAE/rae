---
id: SEM-232
title: "Proof-Bearing Participant-Crossing Bisimulation"
status: DRAFT
type: FUNCTIONAL
priority: MUST
wave: 4
created_at: 2026-07-29T16:10:45.780882Z
updated_at: 2026-07-29T16:10:45.780882Z
---

# SEM-232 — Proof-Bearing Participant-Crossing Bisimulation

## Statement

The RAES ecosystem SHALL define a revision-pinned participant/audience projection and independently derived abstract SEM-230 participant-crossing and concrete API-423/RUN-319 crossing-kernel labelled transition systems; for each governed profile that claims equivalence, it SHALL establish divergence-preserving branching bisimulation (the governed `divergence-preserving-branching-bisimulation` relation) between the declared initial states over the complete quantified carrier after hiding only the profile-declared finite mediation labels, and SHALL publish independently reproducible machine-check evidence binding the exact model, projection, mapping, source, tool, domain, witness or safe counterexample, and artifact digests. Formal equivalence, live-runtime realization, backend conformance, policy noninterference, and predicate opacity SHALL remain separate assurance claims, and no result SHALL be generalized beyond the named profile, carrier, order, time, probability, concurrency, controller, policy-cut, or backend boundary.

## Rationale

SEM-230 defines participant information-flow labels and projection, API-423 and RUN-319 define crossing contracts and mediation, and ASR-535 defines assurance discipline, but no existing requirement owns an exact bisimulation target, its independently constructed model pair, or a machine-checkable and independently reproduced result.

## Traceability

- DOCUMENTS → GITHUB_ISSUE `OpenRAE/rae#1395` (Model multiple operations and interleaved retries)

- TESTS → TEST `implementations/python/tests/test_issue_971_crossing_profile.py` (Closed carrier and binary profile validation tests)

- TESTS → TEST `implementations/python/tests/test_issue_971_crossing_export.py` (Complete export, drift and safe publication tests)

- DOCUMENTS → CODE_FILE `implementations/python/packages/raes_contracts/_participant_crossing_profile.py` (Closed construction profile; theorem remains unestablished)

- DOCUMENTS → DOCUMENTATION `docs/research/participant-bisimulation/model-construction.md` (Construction boundary and source derivation)

- TESTS → TEST `implementations/python/tests/test_issue_971_crossing_models.py` (Complete single-operation transition, retry and atomicity construction tests)

- DOCUMENTS → CODE_FILE `implementations/formal/participant_crossing/export.py` (Issue #971 single-operation formal model construction only; no equivalence or runtime-realization result)

- DOCUMENTS → GITHUB_ISSUE `OpenRAE/rae#971` (Implement independent participant-crossing proof models)
- DOCUMENTS → GITHUB_ISSUE `OpenRAE/rae#972` (Map the reference runtime to the participant-crossing proof model)
- DOCUMENTS → GITHUB_ISSUE `OpenRAE/rae#973` (Build the participant-crossing bisimulation counterexample corpus)
- DOCUMENTS → GITHUB_ISSUE `OpenRAE/rae#974` (Machine-check finite participant-crossing bisimulation)
- DOCUMENTS → GITHUB_ISSUE `OpenRAE/rae#975` (Independently reproduce participant-crossing bisimulation)
- DOCUMENTS → GITHUB_ISSUE `OpenRAE/rae#976` (Publish reproduced participant-crossing bisimulation documentation)
- DOCUMENTS → GITHUB_ISSUE `OpenRAE/rae#811` (Design a proof-bearing participant-control bisimulation result)
- DOCUMENTS → ADR `docs/decisions/adrs/adr-100-participant-crossing-bisimulation.md` (ADR-100: Proof-Bearing Participant-Crossing Bisimulation)
- DOCUMENTS → SPEC `specs/formal/participant-semantics/participant-crossing-bisimulation.md` (Participant-Crossing Bisimulation)
- DOCUMENTS → DOCUMENTATION `docs/research/participant-bisimulation/implementation-program.md` (Participant-Crossing Bisimulation Implementation Program)
- DOCUMENTS → CONFIG `contracts/concept-authority/behavioral-relations-v1.json` (Behavioral relation catalog revision rev6)
