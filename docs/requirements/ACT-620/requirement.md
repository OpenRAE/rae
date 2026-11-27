---
id: ACT-620
title: "Participant Control Context Artifacts"
status: ACTIVE
type: FUNCTIONAL
priority: SHOULD
created_at: 2026-04-05T01:24:07.005101Z
updated_at: 2026-04-05T01:24:07.005101Z
---

# ACT-620 — Participant Control Context Artifacts

## Statement

The ecosystem shall support participant control-context artifacts, including directives, policies, instructions, and similar execution-guiding context, as first-class participant assets.

## Rationale

Primary-source refresh shows that participant execution is often shaped by explicit control context that should be modeled as a first-class ecosystem concern.

## Traceability

- IMPLEMENTS → GITHUB_ISSUE `302`
- IMPLEMENTS → SPEC `specs/supply-chain/participant-control-context-assets.md`
- IMPLEMENTS → SPEC `contracts/schemas/participant-runtime/participant-control-context-asset-v1.json`
- IMPLEMENTS → SPEC `contracts/schemas/participant-runtime/participant-control-context-change-v1.json`
- IMPLEMENTS → SPEC `contracts/schemas/participant-runtime/participant-control-context-record-v1.json`
- IMPLEMENTS → SPEC `contracts/schemas/control-plane/participant-context-view-v1.json`
- IMPLEMENTS → CODE `implementations/python/packages/raes_contracts/contracts/participant_control_context.py`
- IMPLEMENTS → CODE `implementations/python/packages/raes_contracts/participant_control_context.py`
- IMPLEMENTS → CODE `implementations/python/packages/raes_conformance/conformance/control_context_assets.py`
- TESTS → TEST `implementations/python/tests/test_act_620_control_context_assets.py`
- TESTS → TEST `implementations/python/tests/test_act_620_control_context_authority.py`
- TESTS → TEST `implementations/python/tests/test_act_620_control_context_publication.py`
