# Participant semantic consistency design

Issue #219 reconciles existing participant semantic artifacts for ASR-506.
The consistency map describes coverage. It grants no new runtime authority.

## Architecture and ownership

Normative meaning remains in `specs/`. Published exchange shapes remain in `contracts/`.
Closed SDL models, semantic validators, compiler records, and runtime consumers retain their existing responsibilities.
The participant behavior specification aggregates those surfaces through references.
External classifications use the separate `external-concept-bindings/v1` contract.
They do not become native behavior fields or action authority.

The existing participant semantic coverage matrix connects normative clauses, published contracts, implementation files, and executable tests.
The shared semantic integrity reference links that matrix under ADR-016.
The resumed PR already supplies this index and its five clause tables.
Current reconciliation extends those records instead of creating another coverage registry.
Each incomplete guarantee names its existing requirement owner and a concrete acceptance case.
The map separates abstract invariant oracles, bounded models, runtime tests, and claims without proof.
It does not create a second conformance corpus or migration guide.
Issue #220 owns the corpus. Issue #1342 owns author-facing identity and migration guidance.

The ACT-606 field inventory describes the current closed authoring model.
The existing structural test compares that inventory with the model's actual fields.
It detects both omitted additions and obsolete fields.
The map uses repository links to existing evidence rather than copied test results.
Existing coverage and ADR policy tools check the unchanged authority boundaries.
New semantic slices extend the map without adding another participant model or registry.

## Data flow and trust boundaries

```text
Author --> untrusted SDL declarations --> Parser and semantic validation
Pinned local scheme snapshots --> exact classification context --> Binding admission
Parser and semantic validation --> admitted declarations --> Compiler
Compiler --> typed contracts and references --> Runtime admission
Trusted policy and episode stores --> exact-cut authority --> Runtime admission
Runtime admission --> admitted action --> Installed backend
Installed backend --> validated result --> Runtime evidence store
Runtime evidence store --> authorized projection --> Exposure and delivery gates
Exposure and delivery gates --> participant view --> Participant
Runtime evidence store --> assurance records --> Authorized assurance reader
Normative specs and contracts --> clause references --> Consistency map
Implementation and tests --> bounded coverage references --> Consistency map
```

The parser boundary rejects unknown fields and unresolved references.
Binding admission uses explicit local snapshots without locator dereferencing.
The backend boundary validates results before storing portable evidence.
The participant boundary separates assurance, projection, disclosure, delivery, observation, selection, and action admission.
The map reads these authorities. It does not change their data flows.
This diagram supplies the component and data-flow views needed for this documentation boundary.
Deployment and runtime state machines remain in their existing specifications.

## Systems security

| Asset and threat | Existing boundary and control | Verification |
| --- | --- | --- |
| Scenario authority; external labels grant execution | Closed native model and exact external subject binding | Classification rejection and offline binding tests |
| Hidden truth; assurance metadata enters a participant view | Exact-cut exposure policy and separate v2 trust planes | Decision-surface v2 projection, digest, and delivery tests |
| Historical evidence; v1 fields acquire v2 meaning | Separate versioned schemas and admission readers | Historical v1 and actionable v2 tests |
| Assurance integrity; finite checks become universal claims | Explicit evidence categories and limitation statements | Invariant oracle, bounded-model tests, and map review |
| Decision history; accepted decisions change silently | ADR-059 amendment records and acceptance-content pins | Existing ADR immutability check |

The residual risk is incomplete backend realization or proof evidence.
Coverage links establish neither backend qualification nor universal security.
The map retains concrete owners and acceptance cases for these limits.
No credentials, private instruction bytes, source uploads, or external processing are introduced.

## Policy, architecture checks, and decisions

Existing file-local policy, requirement governance, ADR pins, and documentation checks apply.
The field inventory and evidence-link tests check consistency against existing architecture artifacts.
No wire schema, publication manifest, concept vocabulary, or runtime policy changes are needed.
The existing closed models already reject the obsolete fields.
No new ADR is needed because this change applies existing accepted decisions.
ADR-067 and ADR-083 retain proposed status.
ADR-095 remains the accepted executable decision-surface amendment.
ADR-108 through ADR-114 retain their accepted decisions and recorded implementation limits.
Their current runtime support is described separately by the revised-control reference.
Accepted ADR content and acceptance pins remain unchanged.
The matrix's decision crosswalk resolves these statuses from the live ADR files.
Its guard uses the existing ADR parser and test-reference resolver.
The current merge adds control-context authoring, PBM-13, and a runtime-mapping specification.
Existing field, clause, and focused-specification parity tests detect their missing coverage.
The original scope manifest supplies ASR-506 authority on the resumed PR branch.

## Source-bound runtime mapping evidence

The runtime-mapping exporter pins test source as well as shipped code.
The coverage guard changes that source identity.
Fresh public crossing observations therefore supply a new immutable mapping capture.
The existing exporter selects its content-addressed path and rejects historical overwrite.
The capture retains bounded cases, explicit incompatibilities, and the original nonclaims.
No runtime-mapping model, source inventory, schema, or historical capture changes are needed.

## Reference and writing review

- [Pydantic models](https://docs.pydantic.dev/latest/concepts/models/), version 2.12.5, extra data and model fields: compare the closed native field inventory.
- [NIST SP 800-160 Volume 1 Revision 1](https://csrc.nist.gov/pubs/sp/800/160/v1/r1/final), November 2022, security architecture and assurance: separate assets, trust boundaries, controls, and evidence.
- [ASD-STE100 Issue 9](https://www.asd-ste100.org/assets/files/ASD-STE100_ISSUE9.pdf), January 2025, sections 1, 4, 5, 6, and 9: terminology and writing review.

The official STE text was read from the available local copy after its website refused access.
The review checks technical names, approved word use, short sentences, and one topic per paragraph.
Architecture describes ownership. The reference describes coverage. The issue plan contains implementation tasks.
