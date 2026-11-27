---
id: RUN-311
title: "Participant Episode Lifecycle And Reset"
status: ACTIVE
type: FUNCTIONAL
priority: MUST
created_at: 2026-04-05T01:39:33.701478Z
updated_at: 2026-04-12T06:35:41.845947Z
---

# RUN-311 — Participant Episode Lifecycle And Reset

## Statement

The runtime shall support episodic participant execution with explicit initialization, reset, completion, timeout, truncation, interruption, and restart handling.

## Rationale

Primary-source refresh shows that participant-supporting runtimes commonly depend on explicit episode lifecycle and reset handling rather than one long-lived undifferentiated run loop.

## Traceability

- IMPLEMENTS → ADR `docs/decisions/adrs/adr-013-participant-episode-lifecycle-boundaries.md` (ADR-013 Participant Episode Lifecycle Boundaries)
- TESTS → TEST `implementations/python/tests/test_run_311_participant_episode_lifecycle.py` (RUN-311 participant episode lifecycle integrity tests)
- TESTS → TEST `implementations/python/tests/test_runtime_conformance.py` (Conformance fixture suite and semantic diagnostics coverage for RUN-311)
- TESTS → TEST `implementations/python/tests/test_runtime_control_plane.py` (TestParticipantEpisodeControlPlane lifecycle and rejection paths)
- TESTS → TEST `implementations/python/tests/test_runtime_control_plane_api.py` (TestParticipantEpisodeHttpRoutes HTTP surface coverage)
- TESTS → TEST `implementations/python/tests/test_runtime_manager.py` (Manager apply path coverage extended for participant runtime kwarg)
- TESTS → TEST `implementations/python/tests/test_runtime_registry.py` (Registry shape validation for participant_runtime field)
- IMPLEMENTS → GITHUB_ISSUE `599` (Issue 599 participant implementation action admission binding)
- IMPLEMENTS → PULL_REQUEST `617` (PR 617 participant implementation action admission binding)
- IMPLEMENTS → SPEC `contracts/schemas/control-plane/participant-episode-history-event-stream-v1.json` (participant-episode-history-event-stream-v1 published schema)
- IMPLEMENTS → SPEC `contracts/schemas/control-plane/participant-episode-state-envelope-v1.json` (participant-episode-state-envelope-v1 published schema)
