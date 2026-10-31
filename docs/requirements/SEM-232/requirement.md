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

- DOCUMENTS → CODE_FILE `implementations/formal/participant_crossing/runtime_mapping.py` (Issue #972 bounded public-execution mapping; no equivalence or complete runtime-realization result)
- DOCUMENTS → CODE_FILE `implementations/formal/participant_crossing/runtime_mapping_integrity.py` (Independent operation-record preservation, audit-prefix and authorized-outcome checks)
- DOCUMENTS → CODE_FILE `implementations/formal/participant_crossing/runtime_mapping_export.py` (Mapping source, profile, model and observed-case digests with drift rejection)
- DOCUMENTS → SPEC `specs/formal/participant-semantics/participant-crossing-runtime-mapping.md` (State/transition mapping, data flows, security boundary and reproduction)
- DOCUMENTS → DOCUMENTATION `specs/formal/participant-semantics/runtime-mapping/rev1/manifest.json` (Bounded mapping evidence; incompatible and incomplete observations remain explicit)
- TESTS → TEST `implementations/python/tests/test_issue_972_runtime_mapping.py` (Public ingress, v2 context, effect dispatch, final egress, refusal, retry, corruption and projection checks)
- TESTS → TEST `implementations/python/tests/test_issue_972_mapping_export.py` (Reproduction, source and artifact drift, retained model integrity and bounded publication)
- TESTS → TEST `implementations/python/tests/test_issue_972_mapping_ownership.py` (Formal mapping ownership remains separate from runtime implementation ownership)
- TESTS → TEST `implementations/python/tests/crossing_runtime_cases.py` (Synthetic policy inputs driving real public entry points)
- TESTS → TEST `implementations/python/tests/crossing_runtime_observer.py` (Read-only phase and transaction witnesses from unmodified runtime orchestration)

- DOCUMENTS → CODE_FILE `implementations/formal/participant_crossing/multi_export.py` (Issue #1395 complete two-operation construction and source drift evidence; equivalence and realization remain unestablished)
- DOCUMENTS → SPEC `specs/formal/participant-semantics/participant-crossing-multi-operation-models.md` (Separate finite profile, projection and failure boundary)
- DOCUMENTS → DOCUMENTATION `docs/research/participant-bisimulation/multi-operation-construction.md` (Independent construction and historical-source preservation)
- TESTS → TEST `implementations/python/tests/test_issue_1395_crossing_models.py` (Complete closure, independent history/policy, retry and bounded failure cases)
- TESTS → TEST `implementations/python/tests/test_issue_1395_crossing_export.py` (Deterministic counts, source pins, drift and no partial publication)
- TESTS → TEST `implementations/python/tests/test_issue_1395_crossing_profile.py` (Closed profile, schema and carrier joins)

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

- DOCUMENTS → CODE_FILE `implementations/formal/participant_crossing/counterexample_corpus.py` (Bounded negative evidence; no positive relation or runtime realization)
- DOCUMENTS → CODE_FILE `implementations/formal/participant_crossing/counterexample_mutations.py` (Bounded negative evidence; no positive relation or runtime realization)
- DOCUMENTS → CODE_FILE `implementations/formal/participant_crossing/counterexample_witnesses.py` (Bounded negative evidence; no positive relation or runtime realization)
- DOCUMENTS → SPEC `specs/formal/participant-semantics/participant-crossing-counterexamples.md` (Exact carrier, relation and trust boundaries)
- DOCUMENTS → DOCUMENTATION `specs/formal/participant-semantics/counterexamples/pin.json` (Separately retained corpus and mutation review subject pins)
- TESTS → TEST `implementations/python/tests/test_issue_973_crossing_corpus.py` (Safe mutation and checked evidence regressions)
- TESTS → TEST `implementations/python/tests/test_issue_973_crossing_mutations.py` (Safe mutation and checked evidence regressions)
- TESTS → TEST `implementations/python/tests/test_issue_973_crossing_witnesses.py` (Safe mutation and checked evidence regressions)

- DOCUMENTS → CODE_FILE `implementations/formal/participant_crossing/machine_check.py` (Issue 974 exact finite model-check evidence; no runtime-realization claim)
- DOCUMENTS → CODE_FILE `implementations/formal/participant_crossing/machine_check_evidence.py` (Complete carrier, model, projection, source and model-check claim joins)
- DOCUMENTS → SPEC `specs/formal/participant-semantics/participant-crossing-machine-check.md` (Finite relation boundary, security and data flows)
- TESTS → TEST `implementations/python/tests/test_issue_974_machine_check.py` (Incomplete carriers, source drift, mutation false acceptance and claim promotion are refused)
- DOCUMENTS → CODE_FILE `implementations/formal/participant_crossing/machine_check_publication.py` (Qualified hosted provenance and admitted artifact inventory)
- TESTS → TEST `implementations/python/tests/test_issue_974_machine_check_publication.py` (Offline verification and refusal of unadmitted publication)
- DOCUMENTS → CODE_FILE `tools/tooling_policy_gate.py` (Shared validation-source inventory and offline installed-validator boundary)
- DOCUMENTS → CODE_FILE `tools/mcrl2_tool.py` (Pinned native checker refuses a missing tooling environment without acquisition fallback)
