---
id: SEM-233
title: "Adversarial Participant Boundary Information-Flow Control"
status: ACTIVE
type: FUNCTIONAL
priority: MUST
wave: 4
created_at: 2026-07-30T18:36:51.139346Z
updated_at: 2026-09-23T00:00:00Z
---

# SEM-233 — Adversarial Participant Boundary Information-Flow Control

## Statement

The ecosystem shall define revisioned participant-neutral boundary information-flow semantics with independent confidentiality and integrity coordinates, conservative provenance-preserving propagation across observations, retained memory, proposals, transformations, action arguments, control handoffs, participant crossings, outputs, and sinks; it shall keep authentication, authorization, admission, approval, declassification, integrity endorsement, redaction, and transformation distinct, and require fail-closed exact-cut mediation immediately before every RAES-controlled external effect or disclosure, including cross-participant and cross-episode flows.

Profile support shall distinguish authored obligations and admitted guarantees
from published profile expressibility and backend realization. Independent
owner-qualified confidentiality and integrity requirements shall retain every
required propagation and selective-release distinction; trusted authority
shall cover each discharged obligation. Unsupported expression or realization
shall prevent the affected mandatory release, and unexpected loss of an
admitted guarantee shall not silently weaken the effective binding. Governed
finite publication and exact historical interpretation shall follow
`ifc-profile-variability/rev1`; new syntax or executable extensibility requires
separate justification and supported consumers.

## Rationale

SEM-230 and the current action, control, crossing, and runtime authorities define participant-relative mediation but do not yet carry independent confidentiality and source-integrity coordinates transitively to the final enforceable sink or distinguish intentionally adversarial influence from ordinary invalid behavior. Issue #812 adopts that missing boundary while preserving participant neutrality and explicit nonclaims for opaque internals and covert channels.

## IFC publication amendment and evidence boundary

[ADR-113](../../decisions/adrs/adr-113-ifc-profile-variability-and-publication.md)
and [IFC-01–IFC-07](../../../specs/formal/participant-semantics/ifc-profile-variability.md)
publish the #1354 semantic amendment, authoritative on merge. Existing ACTIVE
status and implementation/test links retain their original fulfillment scope.
The new finite witnesses are bounded design evidence, not new portable profile,
owner-aware runtime, installed backend or revised support-negotiation adoption.
The [migration obligations](../../migration/ifc-profile-variability.md) must be
met before claiming those meanings across contracts, live state or history.

## Traceability

- IMPLEMENTS → GITHUB_ISSUE `1354` (IFC variability semantic decision; no runtime adoption)
- IMPLEMENTS → SPEC `specs/formal/participant-semantics/ifc-profile-variability.md` (IFC-01–IFC-07 semantic publication)
- IMPLEMENTS → ADR `docs/decisions/adrs/adr-113-ifc-profile-variability-and-publication.md` (Accepted-on-merge publication decision)
- DOCUMENTS → DOCUMENTATION `docs/decisions/issue-1354-ifc-profile-variability-preflight.md` (Architecture constraints and current support limits)
- DOCUMENTS → DOCUMENTATION `docs/research/ifc-profile-variability/cases.md` (Worked cases and bounded evidence)
- IMPLEMENTS → DOCUMENTATION `docs/migration/ifc-profile-variability.md` (Interpretation, conversion and adoption obligations)
- TESTS → TEST `implementations/python/tests/ifc_profile_variability_model.py` (Finite design interpretation; not runtime enforcement)
- TESTS → TEST `implementations/python/tests/test_issue_1354_ifc_profile_variability.py` (Owner, support and publication witnesses)
- TESTS → TEST `implementations/python/tests/test_issue_1354_governance.py` (Real requirement ownership and scope evaluator)

- DOCUMENTS → ADR `docs/decisions/adrs/adr-108-modular-participant-control-and-governed-effects.md` (Preserves SEM-233 security semantics within modular control)
- DOCUMENTS → DOCUMENTATION `docs/research/modular-participant-control/requirements.md` (Issue #1068 reuse disposition; statement and ACTIVE status unchanged)

- TESTS → TEST `implementations/python/tests/test_sem_233_flow_control_contracts.py` (SEM-233 portable flow-control contract tests)
- IMPLEMENTS → GITHUB_ISSUE `1002` (Issue #1002 portable flow-control contracts)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/participant_flow_control.py` (SEM-233 portable flow-control relation contract)
- DOCUMENTS → DOCUMENTATION `docs/decisions/issue-1002-sem-233-portable-flow-control-contracts-preflight.md` (Issue #1002 SEM-233 architecture preflight)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_contracts/contracts/participant_flow_control_semantics.py` (SEM-233 participant boundary flow-policy semantics)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/participant_flow_sink.py` (SEM-233 final-sink permit resolution and enforcement in the reference runtime)
- IMPLEMENTS → CODE_FILE `implementations/python/packages/raes_runtime/control_plane.py` (SEM-233 fail-closed final-sink enforcement configuration gate)
- TESTS → TEST `implementations/python/tests/test_issue_1003_final_sink_flow_enforcement.py` (SEM-233 final-sink boundary enforcement tests)
- DOCUMENTS → DOCUMENTATION `docs/decisions/issue-1003-sem-233-final-runtime-sinks-preflight.md` (Issue #1003 SEM-233 final-sink enforcement architecture preflight)
- IMPLEMENTS → GITHUB_ISSUE `1003` (Issue #1003 enforce participant flow policy at final runtime sinks)
- TESTS → TEST `implementations/python/tests/test_issue_1004_apparatus_backend_capabilities.py` (SEM-233 boundary-flow-resolution and final-sink-mediation declaration tests)
- DOCUMENTS → GITHUB_ISSUE `https://github.com/OpenRAE/rae/issues/812` (Issue #812 adversarial participant control design)
- DOCUMENTS → ADR `docs/decisions/adrs/adr-101-adversarial-participant-flow-control.md` (ADR-101: Adversarial Participant Boundary Flow Control)
- DOCUMENTS → SPEC `specs/formal/participant-semantics/adversarial-flow-control.md` (SEM-233 and ASR-536 formal authority)
- DOCUMENTS → DOCUMENTATION `docs/research/adversarial-participant-control/implementation-program.json` (Adversarial participant control implementation program)
- DOCUMENTS → GITHUB_ISSUE `https://github.com/OpenRAE/rae/issues/1001` (Issue #1001 semantic authority)
- DOCUMENTS → GITHUB_ISSUE `https://github.com/OpenRAE/rae/issues/1002` (Issue #1002 portable contracts)
- DOCUMENTS → GITHUB_ISSUE `https://github.com/OpenRAE/rae/issues/1004` (Issue #1004 apparatus and backend support)
- DOCUMENTS → GITHUB_ISSUE `https://github.com/OpenRAE/rae/issues/1007` (Issue #1007 adversarial evaluation)
- DOCUMENTS → GITHUB_ISSUE `https://github.com/OpenRAE/rae/issues/1008` (Issue #1008 evidenced documentation)
- DOCUMENTS → GITHUB_ISSUE `812` (Issue #812 adversarial participant control design)

- IMPLEMENTS → GITHUB_ISSUE `1070` (Modular participant-control semantic publication)
- IMPLEMENTS → SPEC `specs/formal/participant-semantics/modular-participant-control.md` (Preserves incumbent security domain in modular composition)
- TESTS → TEST `implementations/python/tests/test_sem_235_modular_control.py` (Known adversarial exposure, retained influence and independent inject)
