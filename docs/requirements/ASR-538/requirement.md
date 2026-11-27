---
id: ASR-538
title: "Modular Participant-Control Realization Conformance"
status: ACTIVE
type: NON_FUNCTIONAL
priority: MUST
wave: 4
created_at: 2026-09-06T00:00:00Z
updated_at: 2026-10-28T00:00:00Z
---

# Modular participant-control realization conformance

## Statement

RAES shall publish bounded conformance tests that run on their own.
They shall exercise exact participant-control profiles, mechanism compositions, provider protocols, and governed effects.
They shall use the real final participant and world crossings.

Evidence shall pin the backend and apparatus.
It shall pin each mechanism, profile, implementation, and configuration.
It shall also pin authority, policy, memory, cut, effect, and limitation identities.
Each result shall keep these claims distinct:

- Published semantics.
- Valid contracts.
- Shared runtime orchestration.
- Executable providers.
- Declared backend support.
- Realized effects.
- Bounded conformance.
- Experimental claims.

Positive and negative probes shall cover permissive influence observation.
They shall cover strict denial with zero prohibited effect.
They shall exercise triggered injects and each other supported effect.
They shall test non-IFC composition, absence, unsupported support, and weakened support.
They shall test conflicts, stale cuts, failure, bounded triggers, and supported recovery.

Independent backends may conform to different declared subsets.
A subset shall imply no mechanism parity or behavioral equivalence.
It shall imply no universal assurance.
An out-of-world integrity failure shall invalidate realization.
It shall not become an in-world attack occurrence.

## Rationale

ASR-535 owns bounded flow assurance.
ASR-536 owns intentional-subversion evaluation.
Neither replaces independent modular provider/effect conformance.
ASR-537 owns mixed-backend realization and transfer claims.

## Fulfillment boundary

ACTIVE covers the reusable bounded corpus and runner published by #1071.
It follows #1070, #1072, #1069 and their completed runtime prerequisites.
LilRAE #22 and Shifter #1969 own their real installed backend evidence.
A fixture provider establishes no such native evidence.

## Traceability

- DOCUMENTS → GITHUB_ISSUE `https://github.com/OpenRAE/rae/issues/1068`
- IMPLEMENTS → GITHUB_ISSUE `https://github.com/OpenRAE/rae/issues/1071`
- DOCUMENTS → GITHUB_ISSUE `https://github.com/OpenRAE/lilrae/issues/22`
- DOCUMENTS → GITHUB_ISSUE `https://github.com/Brad-Edwards/shifter/issues/1969`
- DOCUMENTS → ADR `docs/decisions/adrs/adr-108-modular-participant-control-and-governed-effects.md`
- DOCUMENTS → DOCUMENTATION `docs/research/modular-participant-control/delivery.md`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_conformance/conformance/modular_control.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_conformance/conformance/modular_control_types.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_conformance/conformance/modular_control_execution.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_conformance/conformance/modular_control_checks.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_conformance/conformance/modular_control_policy.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_conformance/conformance/modular_control_report.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_conformance/conformance/modular_control_observation.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_conformance/conformance/modular_control_refusals.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_conformance/conformance/modular_control_replay.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_conformance/conformance/report.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_conformance/conformance/target.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_conformance/conformance/__init__.py`
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/control_plane.py`
- IMPLEMENTS → DOCUMENTATION `docs/explain/reference/modular-control-conformance.md`
- IMPLEMENTS → DOCUMENTATION `docs/decisions/issue-1071-modular-control-conformance-design.md`
- TESTS → TEST `implementations/python/tests/test_issue_1071_modular_conformance.py`
- TESTS → TEST `implementations/python/tests/test_issue_1071_probe_matrix.py`
- TESTS → TEST `implementations/python/tests/test_issue_1071_review_regressions.py`
- TESTS → TEST `implementations/python/tests/test_issue_1071_effect_conformance.py`
- TESTS → TEST `implementations/python/tests/test_corpus_packaging.py`
- TESTS → TEST `implementations/python/tests/test_conformance_facade_parity.py`
