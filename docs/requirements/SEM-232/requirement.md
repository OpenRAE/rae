---
id: SEM-232
title: "Proof-Bearing Participant-Crossing Bisimulation"
status: ACTIVE
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
- IMPLEMENTS → GITHUB_ISSUE `OpenRAE/rae#976` (Publish reproduced participant-crossing bisimulation documentation)
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
- TESTS → TEST `implementations/python/tests/test_issue_973_model_check_workflow.py` (Canonical finite-check publication remains mandatory, offline and isolated)
- TESTS → TEST `implementations/python/tests/test_repo_policy_tools.py` (Public finite-check nox session inventory and helper dependency graph)

- DOCUMENTS → CODE_FILE `implementations/formal/participant_crossing/reproduction.py` (Issue 975 fresh measurement; independent acceptance requires a separate attributable review)
- DOCUMENTS → CODE_FILE `implementations/formal/participant_crossing/reproduction_sandbox.py` (Issue 975 fresh measurement; independent acceptance requires a separate attributable review)
- DOCUMENTS → SPEC `specs/formal/participant-semantics/participant-crossing-reproduction.md` (Isolation, exact subject and separate reviewer authority)
- TESTS → TEST `implementations/python/tests/test_issue_975_reproduction.py` (Exact comparison, isolated execution and refusal of self-approved measurement)
- TESTS → TEST `implementations/python/tests/test_issue_975_reproduction_sandbox.py` (Exact comparison, isolated execution and refusal of self-approved measurement)
- TESTS → TEST `implementations/python/tests/test_issue_975_reproduction_workflow.py` (Exact comparison, isolated execution and refusal of self-approved measurement)
- DOCUMENTS → CODE_FILE `implementations/formal/participant_crossing/reproduction_checks.py` (Fixed independent comparison driver within the complete rootless worker boundary)
- TESTS → TEST `implementations/python/tests/test_issue_975_reproduction_checks.py` (Complete comparison inventory, exact original bytes and always-accept rejection)
- TESTS → TEST `implementations/python/tests/test_issue_975_reproduction_record.py` (Retained qualified evidence, exact artifact joins and attributable agent acceptance)
- DOCUMENTS → DOCUMENTATION `specs/formal/participant-semantics/reproduction/pin.json` (Immutable qualified reproduction and separate acceptance record)

- IMPLEMENTS → CODE_FILE `implementations/formal/participant_crossing/machine_check.py` (Finite DPBB decision production and admission for participant-crossing-dpbb-finite-v1@rev2)
- IMPLEMENTS → CODE_FILE `implementations/formal/participant_crossing/machine_check_evidence.py` (Closed result, claim, and subject-source manifest)
- IMPLEMENTS → CODE_FILE `implementations/formal/participant_crossing/export.py` (Independent model construction and model subject sources)
- IMPLEMENTS → CODE_FILE `implementations/formal/participant_crossing/counterexample_corpus.py` (Mandatory mutation replay and corpus subject sources)
- IMPLEMENTS → CODE_FILE `implementations/formal/participant_crossing/reproduction.py` (Fresh isolated measurement bound to reproducer subject sources)
- IMPLEMENTS → CODE_FILE `implementations/formal/participant_crossing/reproduction_record.py` (Retained reproduction admission with separate reviewer validation)
- IMPLEMENTS → CODE_FILE `implementations/formal/participant_crossing/publication.py` (Published facts composed from the two admitted records)
- IMPLEMENTS → CONFIG `contracts/concept-authority/behavioral-relations-v1.json` (Catalog rev14 records the finite model-check axis only)
- IMPLEMENTS → DOCUMENTATION `specs/formal/participant-semantics/machine-check/pin.json` (Selected finite model-check capture)
- IMPLEMENTS → DOCUMENTATION `specs/formal/participant-semantics/counterexamples/pin.json` (Selected mutation corpus capture)
- IMPLEMENTS → DOCUMENTATION `docs/public/participant-control.md` (Reader-facing finite result, claim binding, publication facts, and nonclaims)
- DOCUMENTS → DOCUMENTATION `docs/decisions/issue-976-crossing-evidence-identity-design.md` (Subject identity, execution provenance, admission, and publication)
- TESTS → TEST `implementations/python/tests/test_issue_976_evidence_identity.py` (Apparatus changes keep records admissible; subject changes refuse them)
- TESTS → TEST `implementations/python/tests/test_issue_976_reproduction_record.py` (Self-approved, detached, and stale reproduction records are refused)
- TESTS → TEST `implementations/python/tests/test_issue_976_crossing_publication.py` (Published claim and facts equal the admitted records)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/behavioral_relations.py` (Retained rev13 catalog registry behind the rev14 finite model-check axis)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/scientific_completeness.py` (Reviewed selection of the 2026-10-31 assessment that cites the reproduced result)
- IMPLEMENTS → SPEC `contracts/profiles/scientific-completeness/delivery-assessment-2026-10-31.json` (Behavioral-relation evidence for the reproduced finite result without profile promotion)
- TESTS → TEST `implementations/python/tests/test_issue_811_participant_bisimulation_design.py` (Exact relation, bounded claim surface, and program dependencies)
- TESTS → TEST `implementations/python/tests/test_behavioral_relations.py` (Catalog rev14 and retained revision validation)
- TESTS → TEST `implementations/python/tests/test_scientific_scenario_completeness.py` (Current assessment selection and profile outcomes)
- TESTS → TEST `implementations/python/tests/test_sem_230_information_flow_control.py` (Catalog rev14 keeps the policy-noninterference entry unchanged)
- TESTS → TEST `implementations/python/tests/test_sem_231_participant_predicate_opacity.py` (Catalog rev14 keeps the opacity entry unchanged)
- TESTS → TEST `implementations/python/tests/test_sem_233_adversarial_boundary_flow.py` (Catalog rev14 keeps the SEM-233 relation evidence unchanged)
- TESTS → TEST `implementations/python/tests/test_issue_963_participant_opacity_proof.py` (Catalog rev14 keeps the opacity proof axis unchanged)
- TESTS → TEST `implementations/python/tests/test_issue_964_participant_opacity_runtime.py` (Catalog rev14 keeps the opacity runtime axis unchanged)
- IMPLEMENTS → CODE_FILE `implementations/formal/participant_crossing/reproduction_attestation.py` (Retain-time binding of review references to GitHub comment, run, job, artifact, and commit records)
- IMPLEMENTS → ADR `docs/decisions/adrs/adr-100-participant-crossing-bisimulation.md` (ADR-100 amendment records the completed #971-#976 work and the ACTIVE transition)
- IMPLEMENTS → CODE_FILE `implementations/formal/participant_crossing/runtime_mapping_export.py` (Mapping capture inventory binds the mapping test drivers and stays within the repository file-size limit)
