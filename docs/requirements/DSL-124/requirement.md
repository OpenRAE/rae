---
id: DSL-124
title: "Authored Data And Evidence Requirements"
status: ACTIVE
type: FUNCTIONAL
priority: MUST
created_at: 2026-04-05T01:59:50.260561Z
updated_at: 2026-06-24T17:56:30.201348Z
---

# DSL-124 — Authored Data And Evidence Requirements

## Statement

The language shall support authored requirements for data, evidence, and output capture from declared sources, scopes, windows, or comparable boundaries, independent of participant objectives and distinct from scenario-native observability systems.

## Rationale

Scenario authors may need to require that particular data be captured from particular sources even when they do not dictate how a processor or backend satisfies that requirement.

## Traceability

- DOCUMENTS → GITHUB_ISSUE `347` (Issue #347 — Multi-Organizational Authority And Governance Contracts)
- DOCUMENTS → ADR `docs/decisions/adrs/adr-066-observability-evidence-plane-separation.md` (ADR-066 Observability evidence plane separation)
- DOCUMENTS → SPEC `specs/formal/observability-evidence-plane.md` (Formal observability/evidence plane specification)
- DOCUMENTS → DOCUMENTATION `specs/sdl/observability-and-evidence.md` (SDL observability and evidence authoring catalog)
- IMPLEMENTS → SPEC `contracts/schemas/sdl/sdl-authoring-input-v1.json` (Published SDL authoring schema for evidence requirements)
- IMPLEMENTS → SPEC `contracts/schemas/sdl/instantiated-scenario-v1.json` (Published instantiated scenario schema for evidence requirements)
- IMPLEMENTS → CONFIG `contracts/schema-publication-manifest.json` (Schema publication manifest update for evidence requirements)
- IMPLEMENTS → SPEC `specs/sdl/sections.md` (SDL section registry for evidence_requirements)
- IMPLEMENTS → SPEC `specs/sdl/references.md` (SDL reference semantics for authored evidence requirements)
- IMPLEMENTS → SPEC `specs/sdl/observability-and-evidence.md` (SDL authored evidence requirement specification)
- IMPLEMENTS → SPEC `specs/formal/observability-evidence-plane.md` (Formal observability/evidence plane coverage for DSL-124)
- TESTS → TEST `implementations/python/tests/test_dsl_124_authored_evidence_requirements.py` (DSL-124 authored evidence requirement tests)
- IMPLEMENTS → GITHUB_ISSUE `337` (Issue 337: Authored Data And Evidence Requirements)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_processor/capture_admission.py` (Compiled authored evidence demand and backend admission)
- TESTS → TEST `implementations/python/tests/test_issue_1112_capture_admission.py` (Authored evidence demand admission and non-demand boundaries)
