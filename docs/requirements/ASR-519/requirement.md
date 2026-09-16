---
id: ASR-519
title: "Realization Honesty And Disclosure Conformance"
status: ACTIVE
type: FUNCTIONAL
priority: MUST
wave: 3
created_at: 2026-04-05T00:55:45.357920Z
updated_at: 2026-08-11T00:00:00Z
---

# ASR-519 — Realization Honesty And Disclosure Conformance

## Statement

The ecosystem shall provide validation and conformance artifacts that detect silent relaxation of binding declarations and missing disclosure of processor or backend realizations for underspecified concerns.

## Rationale

Current state: identified gap. Honest portability needs executable checks against silent approximation and undisclosed gap-filling, not just documentation.

## Traceability

- IMPLEMENTS → GITHUB_ISSUE `1237` (Exact observation-source conformance repair)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_conformance/_realization_validation.py` (Canonical exact-source honesty checks)

- DOCUMENTS → GITHUB_ISSUE `490` (Issue #490 contributes the first ASR-519 conformance artifact (planner realization-support gate))
- TESTS → TEST `implementations/python/tests/test_sem_218_runtime_realization.py` (SEM-218 runtime gate + provenance tests)
- IMPLEMENTS → GITHUB_ISSUE `491` (SEM-218 realization enforcement 3/3 (issue #491))
- DOCUMENTS → GITHUB_ISSUE `715` (03: Add guest-observed libvirt realization probes (ASR-519))
- DOCUMENTS → GITHUB_ISSUE `717` (05: Certify the libvirt reference scenario with honest evidence (ASR-519))
- IMPLEMENTS → GITHUB_ISSUE `100` (01: Publish configuration-specific libvirt realization envelopes (ASR-519))
- IMPLEMENTS → SPEC `contracts/schemas/realization-envelope/realization-envelope-v1.json` (Published realization-envelope-v1 schema)
- IMPLEMENTS → CONFIG `contracts/realization-envelopes/libvirt-qemu/generic-v1.json` (Generic libvirt realization envelope)
- IMPLEMENTS → ADR `docs/decisions/adrs/adr-070-realization-envelope-semantics.md` (ADR-070 realization-envelope semantics)
- IMPLEMENTS → CONFIG `contracts/realization-envelopes/libvirt-qemu/techvault-appliance-v1.json` (TechVault appliance realization envelope)
- IMPLEMENTS → SPEC `specs/formal/realization/envelope-semantics.md` (Formal realization-envelope semantics)
- IMPLEMENTS → SPEC `specs/authority/authority-boundary.yaml` (Realization-envelope normative authority registration)
- TESTS → TEST `implementations/python/tests/test_realization_envelope_contract.py` (Realization-envelope schema and semantic invariant tests)
- TESTS → TEST `implementations/python/tests/test_libvirt_backend_envelopes.py` (Libvirt envelope disclosure and capability-boundary tests)
- TESTS → TEST `implementations/python/tests/test_libvirt_backend_provisioner.py` (Fail-closed libvirt envelope enforcement tests)
- TESTS → TEST `implementations/python/tests/test_libvirt_backend_manifest_publication.py` (Published libvirt manifest envelope tests)
- TESTS → TEST `implementations/python/tests/test_libvirt_backend_manifest.py` (Configuration-specific libvirt manifest tests)
- TESTS → TEST `implementations/python/tests/test_runtime_conformance.py` (Runtime conformance envelope preservation tests)
- TESTS → TEST `implementations/python/tests/test_backend_manifest.py` (Backend envelope contract validation tests)
- TESTS → TEST `implementations/python/tests/test_authority_boundary.py` (Realization-envelope authority-boundary tests)
- IMPLEMENTS → CODE_FILE `examples/scenarios/techvault-bounded-native.sdl.yaml` (ASR-519 implementation artifact)
- TESTS → TEST `implementations/python/tests/test_libvirt_backend_cli.py` (ASR-519 conformance test)
- TESTS → TEST `implementations/python/tests/test_libvirt_backend_techvault_honesty.py` (ASR-519 conformance test)
- TESTS → TEST `implementations/python/tests/test_libvirt_backend_techvault_real_libvirt.py` (ASR-519 conformance test)
- TESTS → TEST `implementations/python/tests/test_libvirt_backend_techvault_native.py` (ASR-519 conformance test)
- IMPLEMENTS → GITHUB_ISSUE `714` (02: Enforce honest TechVault appliance realization disclosure (ASR-519))
- IMPLEMENTS → SPEC `contracts/realization-envelopes/libvirt-qemu/guest-certified-appliance-v1.json` (Guest-certified realization envelope (guest-observed disclosures))
- TESTS → TEST `implementations/python/tests/test_libvirt_backend_guest_certified.py` (Hermetic guest-observation orchestration + falsification + evidence tests)
- TESTS → TEST `implementations/python/tests/test_libvirt_backend_guest_certified_real_libvirt.py` (Opt-in real-daemon guest-certification (native-proof gate))
- TESTS → TEST `implementations/python/tests/test_authored_domain_topology.py` (Planner rejection of unrealized domain topology and SPN requests)
- TESTS → TEST `implementations/python/tests/test_reference_backend_manifest.py` (Reference manifest capability-honesty regression test)
- IMPLEMENTS → GITHUB_ISSUE `776` (Issue #776: correct unrealized domain and SPN capability claims)
- IMPLEMENTS → GITHUB_ISSUE `716` (04: Add ASR-519 realization honesty conformance (ASR-519))
- IMPLEMENTS → DOCUMENTATION `docs/decisions/issue-716-asr-519-realization-honesty-conformance-preflight.md` (ASR-519 realization honesty conformance design)
- IMPLEMENTS → DOCUMENTATION `docs/conformance/libvirt-qemu.provisioning-only.report.json` (ASR-519 machine-readable libvirt conformance report)
- IMPLEMENTS → DOCUMENTATION `docs/explain/reference/backend-conformance.md` (ASR-519 backend conformance contract)
- TESTS → TEST `implementations/python/tests/test_realization_honesty_conformance.py` (ASR-519 dishonest-backend conformance tests)
- TESTS → TEST `implementations/python/tests/test_libvirt_conformance.py` (ASR-519 libvirt conformance mode tests)
- TESTS → TEST `implementations/python/tests/test_libvirt_participant_runtime.py` (ASR-519 libvirt realization observation tests)
- TESTS → TEST `implementations/python/tests/test_realization_envelope_relation.py` (ASR-519 envelope probe relation tests)
- IMPLEMENTS → GITHUB_ISSUE `1116` (Root-run libvirt init-script interface validation)
- IMPLEMENTS → GITHUB_ISSUE `1094` (Deterministic, preflighted, content-identified boot artifacts)
- IMPLEMENTS → GITHUB_ISSUE `1095` (Fresh operation-bound guest facts and exact memory evidence)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_backend_libvirt/guest_certified_driver.py` (Per-operation freshness lifecycle)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_backend_libvirt/guest_observation.py` (Exact memory observation and explicit tolerance appraisal)
- IMPLEMENTS → DOCUMENTATION `docs/decisions/issue-1094-libvirt-boot-artifact-reliability.md` (Boot-artifact evidence reliability)
- IMPLEMENTS → DOCUMENTATION `docs/decisions/issue-1095-libvirt-guest-evidence-freshness.md` (Freshness and memory evidence architecture)
- TESTS → TEST `implementations/python/tests/test_libvirt_boot_artifacts.py` (Artifact identity and preflight falsification)
- TESTS → TEST `implementations/python/tests/test_libvirt_backend_guest_certified.py` (Freshness, stale-fact, exact-memory, and evidence-binding falsification)
- TESTS → TEST `implementations/python/tests/test_libvirt_guest_appliance_init_script.py` (Shared root-run interface injection regressions)
- DOCUMENTS → GITHUB_ISSUE `1105` (Guest service protocol honesty defect)
- DOCUMENTS → DOCUMENTATION `docs/decisions/issue-1105-libvirt-guest-service-protocol.md` (Protocol evidence boundary)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_backend_libvirt/guest_observation.py` (Protocol-bound expected and observed service evidence)
- TESTS → TEST `implementations/python/tests/test_libvirt_backend_guest_certified.py` (Wrong-protocol evidence rejection)
