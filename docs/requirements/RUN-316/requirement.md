---
id: RUN-316
title: "Operational Apparatus Observability"
status: ACTIVE
type: FUNCTIONAL
priority: MUST
created_at: 2026-04-05T01:59:50.614372Z
updated_at: 2026-10-21T00:00:00Z
---

# RUN-316 — Operational Apparatus Observability

## Statement

The processing layer shall support operational observability surfaces for processors and backends needed to realize, monitor, verify, and troubleshoot scenarios and experiments, distinct from scenario-native observability systems and captured experiment evidence.

## Rationale

Processors and backends require their own operational observability, but that concern must remain distinct from both in-world observability and the evidence captured for analysis.

## Traceability

- DOCUMENTS → GITHUB_ISSUE `347` (Issue #347 — Multi-Organizational Authority And Governance Contracts)
- IMPLEMENTS → GITHUB_ISSUE `128` (Issue #128 - Observability evidence conformance implementation)
- TESTS → TEST `implementations/python/tests/test_backend_manifest.py` (Backend manifest tests cover observation contract vocabulary and experiment-run-v1 support)
- TESTS → TEST `implementations/python/tests/test_runtime_control_plane_api.py` (Operational apparatus summary API tests)
- IMPLEMENTS → GITHUB_ISSUE `338` (Operational Apparatus Observability (RUN-316))
- IMPLEMENTS → GITHUB_ISSUE `1173` (Safe and complete libvirt failure observability)
- IMPLEMENTS → PULL_REQUEST `1163` (Bounded libvirt backend failure observability)
