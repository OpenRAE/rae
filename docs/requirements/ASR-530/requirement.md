---
id: ASR-530
title: "Claim Falsification And Evidence Gate"
status: ACTIVE
type: NON_FUNCTIONAL
priority: MUST
wave: 2
created_at: 2026-05-18T02:22:07.827366Z
updated_at: 2026-07-15T05:47:36.193973Z
---

# ASR-530 — Claim Falsification And Evidence Gate

## Statement

The ecosystem shall treat major architecture and maturity claims as unproven until each claim has an explicit falsification protocol, objective pass/fail criteria, named evidence artifacts, and a recorded evidence status that distinguishes demonstrated, partially demonstrated, untested, and refuted claims.

## Rationale

Agent-assisted development can produce internally coherent code and documentation that still overstates real ecosystem maturity. RAES needs a ruthless credibility gate so claims such as backend agnosticism, independent backend implementability, conformance honesty, backend substitution, provenance separation, and processor artifact portability are evaluated through pre-registered tests and evidence rather than architectural confidence or reference-code self-consistency.

## Traceability

- IMPLEMENTS → GITHUB_ISSUE `989` (Versioned current replay and immutable historical evidence)
- IMPLEMENTS → CODE_FILE `tools/research_evidence.py` (Exact source-state provenance and coherent release selection)
- IMPLEMENTS → CODE_FILE `tools/formal_semantic_validation/_releases.py` (Version-specific historical and current validation)
- IMPLEMENTS → CODE_FILE `tools/formal_semantic_validation/_production.py` (Strict stored, direct, CLI, and replay joins)
- IMPLEMENTS → CODE_FILE `tools/check_specification_coverage.py` (Current coverage replay and historical integrity dispatch)
- IMPLEMENTS → CODE_FILE `tools/specification_coverage/_artifacts.py` (Exact current source pins and bounded historical archives)
- IMPLEMENTS → PROOF `docs/research/formal-semantic-validation/bundles/retest-v3.json` (Atomic current retest release 4.0.0)
- IMPLEMENTS → PROOF `docs/research/specification-coverage/bundles/raes-standardized-specification-coverage-issue-989-v2.json` (Atomic current coverage release 2.0.0)
- TESTS → TEST `implementations/python/tests/test_issue_989_versioned_evidence.py` (Replay bypass, provenance, selection, and archive-integrity regressions)
- TESTS → TEST `implementations/python/tests/test_specification_coverage.py` (Current coverage and frozen historical evidence checks)
- DOCUMENTS → DOCUMENTATION `docs/explain/sdl/lineage.md` (SDL lineage and prior work)
- DOCUMENTS → DOCUMENTATION `docs/explain/sdl/precedents.md` (SDL design precedents for participant semantics and language adequacy)
- DOCUMENTS → ADR `docs/decisions/adrs/adr-021-falsification-first-claim-evidence-gate.md` (ADR-021: Falsification-First Claim Evidence Gate)
- DOCUMENTS → DOCUMENTATION `docs/decisions/issue-346-dsl-language-evaluation-preflight.md` (Issue 346 DSL evaluation architecture preflight)
- DOCUMENTS → DOCUMENTATION `docs/research/dsl-language-evaluation/analysis-v1.json` (DSL language-evaluation claim analysis record)
- DOCUMENTS → DOCUMENTATION `docs/research/dsl-language-evaluation/bundle-manifest.json` (DSL language-evaluation evidence bundle manifest)
- DOCUMENTS → DOCUMENTATION `docs/research/dsl-language-evaluation/execution-snapshot-v1.json` (DSL language-evaluation execution snapshot)
- DOCUMENTS → DOCUMENTATION `docs/research/dsl-language-evaluation/protocol-v1.json` (DSL language-evaluation falsification protocol)
- DOCUMENTS → DOCUMENTATION `docs/research/dsl-language-evaluation/index.md` (DSL language-evaluation protocol documentation)
- IMPLEMENTS → CODE_FILE `tools/check_dsl_language_evaluation.py` (Offline DSL language-evaluation evidence integrity gate)
- TESTS → TEST `implementations/python/tests/test_dsl_language_evaluation.py` (DSL language-evaluation evidence gate regression tests)
- IMPLEMENTS → GITHUB_ISSUE `346` (Test protocol: DSL language-evaluation and adequacy evidence)
- IMPLEMENTS → DOCUMENTATION `docs/research/dsl-language-evaluation/protocol-v2.json` (Researcher accessibility falsification protocol)
- IMPLEMENTS → DOCUMENTATION `docs/research/dsl-language-evaluation/analysis-accessibility-v1.json` (Researcher accessibility claim analysis and evidence status)
- IMPLEMENTS → GITHUB_ISSUE `178` (Test protocol: accessibility for non-infrastructure-expert researchers)
- IMPLEMENTS → CONFIG `docs/research/dsl-language-evaluation/bundle-manifest.json` (DSL evaluation evidence bundle manifest)
- IMPLEMENTS → DOCUMENTATION `docs/research/dsl-language-evaluation/execution-snapshot-accessibility-v1.json` (Researcher accessibility execution evidence snapshot)
- IMPLEMENTS → CODE_FILE `tools/check_formal_semantic_validation.py` (Formal semantic validation evidence gate)
- IMPLEMENTS → CONFIG `noxfile.py` (Formal semantic validation nox session)
- IMPLEMENTS → PROOF `docs/research/formal-semantic-validation/analysis-v1.json` (Formal semantic validation recorded evidence status v1)
- IMPLEMENTS → SPEC `docs/research/formal-semantic-validation/protocol-v1.json` (Formal semantic validation falsification protocol v1)
- IMPLEMENTS → PROOF `docs/research/formal-semantic-validation/execution-snapshot-v1.json` (Formal semantic validation execution snapshot v1)
- IMPLEMENTS → PROOF `docs/research/formal-semantic-validation/bundle-manifest.json` (Formal semantic validation evidence bundle manifest)
- IMPLEMENTS → DOCUMENTATION `docs/research/formal-semantic-validation/index.md` (Formal semantic validation evidence bundle documentation)
- TESTS → TEST `implementations/python/tests/test_formal_semantic_validation.py` (Formal semantic validation automated tests)
- IMPLEMENTS → GITHUB_ISSUE `168` (Issue #168: Formal semantic validation gate)
- IMPLEMENTS → SPEC `specs/formal/scenario-satisfiability/README.md` (Governed whole-scenario satisfiability specification)
- IMPLEMENTS → PROOF `docs/research/formal-semantic-validation/satisfiability-analysis-v1.json` (Whole-scenario satisfiability recorded evidence status)
- TESTS → TEST `implementations/python/tests/test_scenario_satisfiability.py` (Scenario satisfiability analysis and evidence tests)
- TESTS → TEST `implementations/python/tests/test_satisfiability_cli.py` (Governed satisfiability CLI tests)
- IMPLEMENTS → GITHUB_ISSUE `826` (Governed whole-scenario constraint satisfiability and solver evidence)
- IMPLEMENTS → GITHUB_ISSUE `1114` (Fail-closed incomplete solver checks and defensive solver-boundary validation)
- DOCUMENTS → DOCUMENTATION `docs/decisions/issue-1114-solver-operational-safety-remediation.md` (Incomplete-check operational-safety remediation)
- DOCUMENTS → GITHUB_ISSUE `1108` (Complete-operation satisfiability deadline)
- DOCUMENTS → DOCUMENTATION `docs/decisions/issue-1108-asr-530-operation-bounded-solver.md` (Incremental solver and monotonic deadline decision)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/satisfiability/_solver.py` (Single-session solver and operation-wide deadline)
- TESTS → TEST `implementations/python/tests/test_scenario_satisfiability.py` (Differential, timeout, and construction-count regressions)
- IMPLEMENTS → PROOF `docs/research/formal-semantic-validation/bundles/retest-v2.json` (Formal semantic validation atomic retest evidence release v2)
- IMPLEMENTS → GITHUB_ISSUE `828` (Re-test formal semantic validation, satisfiability, and exploit-path claims)
