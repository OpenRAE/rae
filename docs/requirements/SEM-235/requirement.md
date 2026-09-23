---
id: SEM-235
title: "Modular Participant Control and Extensible Dynamic IFC Semantics"
status: ACTIVE
type: FUNCTIONAL
priority: MUST
wave: 4
created_at: 2026-09-06T00:00:00Z
updated_at: 2026-09-23T00:00:00Z
---

# SEM-235 — Modular Participant Control and Extensible Dynamic IFC Semantics

## Statement

RAES shall define revisioned participant-control profile and mechanism
composition semantics over the declared participant/world boundary, including
extensible dynamic information-flow-control domains with closed carriers,
orders, conservative joins, source/default and propagation rules, policy
resolution, memory scope and explicit release authority. Profiles shall select
finite exact mechanism sets with mandatory/advisory roles, acyclic dependencies,
deterministic conjunction and conflict rules, explicit absence, unsupported,
stale, weakened and failure behavior, and independently authorized typed effect
requests. Triggered transformations and injects shall preserve exact state cuts,
fresh identity, provenance, participant visibility, ordinary downstream
admission, idempotency and finite causal budgets. SEM-233's published security
domain and historical meaning shall remain intact; backend integrity outside
the declared world shall remain a realization responsibility.

Composition shall distinguish the admitted apparatus from profile obligations,
exact-cut applicable invocations, proven inapplicability and unresolved
coverage. It shall evaluate a finite typed dependency graph with immutable
predecessor results, explicit shared-state scope and atomic state/decision/
intent commit. Mandatory input closure shall be satisfied without granting
advisory content veto authority. Optional failure shall remain isolated, and
bounded support shall satisfy the admitted requirement's coverage and
constraints. Parent deny/withhold shall retain the same meaning in every phase;
prerequisites and independent or success-dependent consequences shall have
separate target, authority, outcome and ordering relations under CA-01–CA-09.

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

SEM-230 supplies participant-relative flow and SEM-233 supplies its security
profile. Neither owns arbitrary non-security domains or composition with
non-IFC mechanisms. ADR-108 establishes that missing scope without requiring
identical backend mechanisms or an executable policy language in RAES.

## Fulfillment boundary

#1070 publishes sem-235/rev1 formal clauses, concept-authority placement,
lineage, worked examples and bounded falsification evidence. ACTIVE denotes
this semantic fulfillment, authoritative when the delivery PR merges.
Downstream contracts, runtime, conformance and realization have separate
owners; semantic publication is not their implementation.

## Semantic amendment and evidence boundary

[ADR-111](../../decisions/adrs/adr-111-control-applicability-and-effect-decisions.md)
and [CA-01–CA-09](../../../specs/formal/participant-semantics/control-applicability-and-evaluation.md)
define the #1352 amendment, `participant-control-applicability/rev1`.
ACTIVE records the accepted semantic contract, authoritative on merge; it
does not assert executable adoption of the amendment. Existing implementation
and evidence links retain their original revision-1 scope. The new finite
model supplies bounded design evidence. Producers and historical readers must
satisfy the [migration contract](../../migration/control-applicability-and-evaluation.md)
before claiming the amended semantics.

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

- IMPLEMENTS → GITHUB_ISSUE `1352` (Applicability, dependency and effect semantic amendment)
- IMPLEMENTS → SPEC `specs/formal/participant-semantics/control-applicability-and-evaluation.md` (CA-01–CA-09 semantic contract; not runtime adoption)
- IMPLEMENTS → DOCUMENTATION `docs/decisions/adrs/adr-111-control-applicability-and-effect-decisions.md` (Accepted-on-merge decision)
- DOCUMENTS → DOCUMENTATION `docs/decisions/issue-1352-control-applicability-preflight.md` (Architecture guardrails)
- DOCUMENTS → DOCUMENTATION `docs/research/control-applicability/cases.md` (Worked cases, clause map and evidence limits)
- DOCUMENTS → DOCUMENTATION `docs/migration/control-applicability-and-evaluation.md` (Historical interpretation and adoption obligations)
- TESTS → TEST `implementations/python/tests/control_applicability_model.py` (Finite applicability/evaluation oracle, reusing revision-1 typed satisfaction)
- TESTS → TEST `implementations/python/tests/test_issue_1352_control_applicability.py` (Bounded semantic counterexamples)
- TESTS → TEST `implementations/python/tests/test_issue_1352_governance.py` (Real ownership and requirement-scope consumer)

- DOCUMENTS → GITHUB_ISSUE `1072` (API-424 consumes the existing semantic publication without changing its fulfillment boundary)
- DOCUMENTS → DOCUMENTATION `docs/explain/reference/modular-participant-control-contracts.md` (Published contract correspondence and nonclaims)

- DOCUMENTS → GITHUB_ISSUE `https://github.com/OpenRAE/rae/issues/1068` (Modular participant-control architecture)
- DOCUMENTS → GITHUB_ISSUE `https://github.com/OpenRAE/rae/issues/1070` (Semantic publication)
- DOCUMENTS → ADR `docs/decisions/adrs/adr-108-modular-participant-control-and-governed-effects.md` (ADR-108)
- DOCUMENTS → DOCUMENTATION `docs/decisions/issue-1070-sem-235-architecture-preflight.md` (Issue #1070 semantic publication guardrails)
- DOCUMENTS → DOCUMENTATION `docs/research/modular-participant-control/composition.md` (Architectural composition contract PC-01 through PC-15)
- DOCUMENTS → DOCUMENTATION `docs/research/modular-participant-control/cases.md` (Worked examples and counterexamples)
- TESTS → TEST `docs/research/modular-participant-control/check_design.py` (Bounded abstract-design falsification only)

- IMPLEMENTS → GITHUB_ISSUE `1070` (Modular participant-control semantic publication)
- IMPLEMENTS → SPEC `specs/formal/participant-semantics/modular-participant-control.md` (sem-235/rev1 formal semantic publication)
- IMPLEMENTS → SPEC `specs/concept-authority/participant-control.md` (Revisioned placement in incumbent concept families)
- IMPLEMENTS → CONFIG `contracts/provenance/sdl-lineage-ledger-v2.json` (Exact SEM-235 semantic lineage)
- IMPLEMENTS → DOCUMENTATION `docs/explain/sdl/lineage.md` (Source derivation and nonclaims)
- IMPLEMENTS → CONFIG `tools/policy/requirement_order.yaml` (Bounded semantic-publication ownership)
- TESTS → TEST `implementations/python/tests/sem235_modular_control_model.py` (Finite semantic oracle, not runtime realization)
- TESTS → TEST `implementations/python/tests/test_sem_235_modular_control.py` (Domain, composition, effect and causal witnesses)
- TESTS → TEST `implementations/python/tests/test_sem_235_governance.py` (Real publication ownership evaluator)
- DOCUMENTS → DOCUMENTATION `docs/research/modular-participant-control/semantic-verification.md` (Clause mapping, cases and bounded evidence)
