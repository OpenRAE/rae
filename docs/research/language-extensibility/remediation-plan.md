# Issue 1198 remediation plan

Status: proposed implementation program following the
[design review](design-review.md). No language change is accepted by this plan.
The requested milestone is **Progressive Specification & Language Extensibility**.
The audit and planning deliverable [#1198](https://github.com/OpenRAE/rae/issues/1198)
is complete when its documentation PR is merged. Implementation and verification
remain owned by #1200–#1212 and milestone 70; closing the audit does not claim
that the language defects have been fixed.

Updated 2026-09-05 to make the [maintainer's clarified intent](design-intent.md)
an acceptance requirement: open scopes delegate materialization choices to the
backend; authors do not complete installation recipes; abstract models can be
complete; reporting and experimental observation are independently requested.
This deliberately corrects contrary design drift, not merely a closed catalog.
The current runtime/formal contracts are not silently reinterpreted by this plan.

## Work packages and dependency order

The identifiers below are planning labels, not new requirement UIDs. GitHub
issue links are recorded in the delivery table. L13 was added during the
2026-09-05 consistency pass because observation demand had no explicit owner.

| ID | Deliverable | Prerequisites | Findings |
|---|---|---|---|
| L1 | Preserve exact sibling constraints when another leaf is unknown or outside a vocabulary | None; focused correctness work | F2, F3 |
| L2 | Ratify partial-description, closure, refinement and lifecycle semantics | Review and concrete counterexamples | F1–F6 |
| L3 | Publish typed domain-extension identity, schema, support and offline-resolution contracts | L2 | F1, F2, F5, F6 |
| L4 | Implement recursive authoring constraints and stable collection semantics | L2 | F3 |
| L5 | Carry granular authority through compiler, admission and runtime comparison | L3, L4, L13; preserve L1 correction; integrate existing #1112 | F2, F3, F6 |
| L6 | Separate software requirements, acquisition constraints and final repository state | L2, L3, L4; acceptance uses L5 | F1 |
| L7 | Migrate runtime product/protocol/format vocabularies without sentinel identity loss | L3, L4; acceptance uses L5 | F2 |
| L8 | Move completeness and specimen-specific guards into selected profiles | L2, L4; acceptance uses L5 | F4 |
| L9 | Extend generated-artifact, materialization, enterprise/access and resource-profile seams | L3, L4; acceptance uses L5 | F5 |
| L10 | Preserve recursive partial descriptions in realization reports and environment captures | L3, L4, L5, L13 | F6 |
| L11 | Deliver migrations, formatting, composition and semantic-diff support | L3–L10, L13 and existing #989 | F1–F6 |
| L12 | Conform the integrated language, document authoring, and prevent catalog regression | L1–L11, L13; integrate #959 and #340–#342 | F1–F6 |
| L13 | Define scoped observation/reporting, collection, retention and export demand | L2, L3, L4; enforcement uses L5 and existing #1112 | F6 and clarified design intent |

L1 can land before the redesign. A conservative early fix may reject a mixed
case that cannot preserve exact constraints; it must not silently broaden or
invent intent. L2 must review a compact executable semantic prototype before
committing to the final public syntax. Domain work can progress against the
approved common contracts; do not invent separate extension systems in L6–L9.
L13 defines demand policy/carriage before L5/L10 integrated enforcement; it does
not depend on those downstream implementations or replace #1112.

### Enforced GitHub blocking relationships

Native GitHub `blocked by` links enforce the following immediate prerequisites.
The graph is transitively reduced: earlier design/contracts remain prerequisites
through the named blocker, without repeating every ancestor on every issue.
An issue is an implementation/completion unit; preliminary discussion can still
occur before its blockers close. Do not run the dependent implementation early.

| Issue | Immediate blockers |
|---|---|
| #1200 (L1), #1201 (L2) | None; these can proceed independently |
| #1202 (L3), #1203 (L4) | #1201 |
| #1212 (L13) | #1202, #1203 |
| #1204 (L5) | #1200, #1212, #1112 |
| #1205–#1209 (L6–L10) | #1204; these domain/lifecycle implementations can then proceed in parallel |
| #1210 (L11) | #1205, #1206, #1207, #1208, #1209, #989 |
| #1211 (L12) | #1210, #959, #340, #341, #342 |

#1112 is a hard integration prerequisite for actual required-capture admission;
#989 supplies the owned classification migration. #959 and #340–#342 are final
audit/evidence integration prerequisites, not reasons to serialize independent
domain implementation. Other coordination references are not automatically
blockers. The completed audit #1198 is not blocked by its implementation
follow-ups and does not block their already published design review.

## Required results for each work package

### L1 — correctness

Cover the compiler's weakest-child aggregation, sentinel classification, and
runtime evaluator. Reproduce the known-ID/other-engine case from `audit.py`;
mutating the ID must fail while a permitted choice in an open sibling succeeds.
Include unknown observations and a mixed exact/constrained collection. Treat
`other` identities with an explicit numeric extension code (DNS) as exact
where appropriate. Do not indiscriminately convert all unknowns to concrete
values or claim missing observation is satisfied. Review schema and legacy
behavior impact, and retain a negative control that demonstrates the test is
checking constraint preservation.
The temporary reject-safe option is not the final design: an open parent with
an exact nmap child must eventually be executable, with other packages open.

### L2 — reviewed semantic contract

Decide presence, unknown/undefined/redacted information, defaults, explicit
delegation, record closure, collection closure and refinement as independent
concepts. Specify precedence, composition, identity, conflicts, and finite
resource limits. Separate description validity from capability admission and
evidence strength. Include a sparse software requirement, a deep private
profile, mixed sibling constraints, partial capture, and a non-cyber domain.
Evaluate a CUE-backed prototype or independent small reference model as a
design check, without making a CUE migration a prerequisite.
Ratify inherited subtree delegation, complete abstract models, independent
observation demand, and the five-Linux/Kali acceptance examples. Separate
selection of one supported permitted realization from a universal capability
promise. Review ADR-070 and the open-demand subsumption call site without
silently weakening the existing universal relation. Apply the principle to
topology, data and participant behavior as well as runtime inventories.

### L3 — extensible typed profiles

Reuse concept authority, artifact identities, manifests and profile distribution.
Support private/offline pinned definitions, explicit namespace ownership,
schema/semantic version identity, nested data and contextual resolution. Define
which unknowns may be preserved and which require refusal of validation,
comparison or execution. Separate validators/interpreters from data; no implicit
network lookup or execution of downloaded code. Test collisions, missing
profiles, unsupported required vocabularies, and incompatible revisions.
Do not require a profile declaration or registry entry for an unmentioned
backend-internal acquisition/materialization choice. Extension typing is for
detail actually constrained, described or exchanged, not every possible choice.

### L4 — authoring and collections

Implement one normal form and recursive semantics for core and extension data.
Keep simple literals concise. Preserve absent/empty/null/unknown distinctions
and source/default provenance. Define membership requirements versus exhaustive
inventory, stable keyed collection matching, ordered sequences, duplicate IDs,
and graph reference cycles. Demonstrate nested open/closed/undefined scopes
without adding a manual concern registry entry for each leaf.
One open scope must cover unspecified descendants without per-field waivers.
An exact child must not close its parent/siblings. Optional packages are absent
or present-and-conforming, not unconditionally required. Preserve a complete
abstract model without constructing an irrelevant detailed machine underneath.

### L5 — end-to-end enforcement

Carry the admitted leaf and structure constraints through planning, authenticated
handoff, realization disclosure and comparison. Unknown capabilities do not
authorize execution; open siblings do not weaken exact siblings. Evaluate
actual declared values and coverage under the same constraint relation as
authoring. Negative cases must fail before mutation when knowable at admission,
and reject non-conforming results before replacing accepted state. Extend
existing SEM-218/219 contracts and retain honestly selected evidence-strength
requirements. Resolve delegated choices in the backend rather than demanding
author values where a supported completion exists. Distinguish chosen-witness
admission from full-envelope coverage claims, with explicit migration for any
changed gate. L13 determines requested observations; #1112 admits those actual
requirements. Exact scenario detail alone must not invent capture obligations.

### L6 — motivating software/repository case

Choose one owning software-requirement surface and migrate the current exact
package shorthand into it without changing old meaning. Let authors omit
versions as well as manager/acquisition detail when irrelevant; support exact,
older/newer and range constraints when important. An enclosing open scope
delegates the remainder without author per-property opt-outs.
Separate transient acquisition from final repository configuration and shared
repository/trust identity. Qualify APT, DNF/RPM, a private profile, a private
APT instance, cached/offline artifacts and a prebuilt image. Keep application
version distinct from package version; never infer arbitrary source-label
semantics. Use env-packs#312's six endpoints as downstream acceptance, including
its declared enrollment/readiness/behavior obligations, not only successful
package parsing. Do not universalize that pack's telemetry as experimental data
for other scenarios. Test software-presence-only authoring, private acquisition
remaining internal, and separately requested realization reporting without
automatic package digests or acquisition provenance. Include the Kali ladder.

### L7 — runtime vocabulary migration

Use the full census and scope inventory to dispose of every externally owned
product, protocol, format, provenance and classification vocabulary. Preserve
known exact private identifiers and existing numeric extension identities.
Retain valid structural/security enums. Migrate comparison, projection,
schemas, examples and consumer-facing diagnostics together. Do not introduce a
new built-in term each time a test adds another product.
Do not replace a compulsory core catalog with a compulsory profile catalog;
omit irrelevant implementation identity entirely under an open scope.

### L8 — partial descriptions and selected completeness

Correct datastore, forwarding and orchestration profile guards; examine their
adjacent families using #959's rubric. Base descriptions must allow partial
knowledge and legitimate empty configured state. Selected executable profiles
can require persistence, destinations, replication, interfaces or evidence when
the selected contract actually needs them. Concrete execution prerequisites
that can be chosen within an open scope are for the backend to resolve, not
automatically mandatory authored fields. Preserve #956's capability-based correction,
security admission and non-approximation. Include counterexamples with a
nonpersistent key-value service and a non-IOC content synchronizer.

### L9 — remaining domain profile selections

Provide the common extension seam for generated artifacts, service content
materialization, authored identity/federation/access and participant resource
kinds. Resolve authoring/manifest mismatches, including OS-family extensions.
Preserve existing certificate/SSH-key confidentiality and delivery contracts,
identity authority, and resource accounting. Include one private generator,
one additional typed access/profile case, and one new resource measure without
a core vocabulary release. Coordinate participant-control ownership with #1068.
The extension seam is optional when the mechanism is irrelevant. Backend
internal generators, identity setup or resource choices need not become
authored profile declarations merely because the backend uses them.

### L10 — realization and capture descriptions

Carry typed additional detail, extension identities and field/collection
coverage in existing lifecycle envelopes. Preserve observer/time/basis and
differentiate not-observed, known absent, withheld and contradictory. A report
must not rewrite original author intent. A promotion operation selects which
captured facts become constraints and records that decision. Coordinate with
#1112; do not duplicate capture capability admission or treat a capture schema
pass as proof of successful realization.
Make actual selected Linux/Kali choices reportable at requested depth. Distinguish
backend-known selections from independent measurement, preserve the original
request, and apply L13 collection/report/retention policy. Do not acquire a full
inventory just to discard it from a no-experimental-data response.

### L11 — migration and tools

Version changed semantics explicitly. Preserve old closed-collection, omission
and APT-final-state meanings in the legacy reader. Do not silently reinterpret
old `other`/`unknown`: use provenance or report ambiguity requiring an author
decision. Keep immutable historical evidence readable with its original
contract. Supply formatting, composition/import, canonicalization, semantic
diff, schema/binding generation and conversion tests. Link #989's existing
classification migration rather than copy it into a new implementation.
Explain omission as inherited policy, not an incomplete form. Tools must show
author constraints, delegated choices and observation demand separately, and
must not materialize hidden package/OS requirements into an abstract model.
Migrate any changed admission quantifier or implicit evidence floor explicitly.

### L12 — integrated conformance and usability

Run positive and negative cases across parser/schema, semantic model, compiler,
planner, runtime result validation, capture and round trip. Include private,
offline and non-cyber cases, supported and unsupported backends, and bounds
exhaustion. Check composition/refinement properties and preservation of exact
siblings. Rehearse sparse-to-deep authoring with ordinary YAML and inspectable
choices/evidence; coordinate the released backend/pack journey with Hub#3.
Run every acceptance anchor in [design intent](design-intent.md), including
five Linux boxes, the Kali refinement ladder, complete abstract machines and
independent detail/evidence combinations. Verify absence of unnecessary data
collection, retention and export, not only concise output. A backend with one
allowed completion should not need universal support for all open alternatives.

Add a practical vocabulary/profile review rule: name the owner, state why a set
is closed, distinguish domain identities from grammar operators, show a new
private case and a partial capture, and identify extension/admission behavior.
A mechanical census can flag changes for review; it cannot decide semantic
correctness. Complete a disposition ledger for all candidates and reconcile
#959/#989/#1167 before claiming the class addressed.

### L13 — independent observation and reporting demand

Define scope-aware no-experimental-data, explicit prohibition, operational-only,
inherited/no-preference, selected-observation and scoped exhaustive modes through
existing scenario/task/evidence owners. Collection, retention and export are
distinct stages. Include field/stream/artifact, component, time and coverage
bounds, and explicit defaults/precedence. Separate chosen-realization reports
from independent measurements and required operational inputs. No-data mode
does not authorize false verification claims or waive a selected execution,
control, termination, analysis or operator-policy obligation; conflicts must be
diagnosed. #1212 owns the contract/carriage, L5/L10 integrated enforcement and
projection, and #1112 required capture admission. Reuse evidence integrity and
source-provenance owners without imposing capture on every scenario. Build on
ADR-064/066 and the delivered #127/#337/#338/#339 boundaries. #341 retains
task/run/study refinement, #340 augmentation conformance and #342 provenance;
L13 must reuse and correct their shared demand semantics, not duplicate them.

## Migration and release policy

The project is early, but it already publishes 3.x packages and independently
versioned contracts. Semantic changes need an honest compatibility boundary.
Keep old meanings available in versioned readers/migrations, make new defaults
explicit, publish schema change records, and update the reference generator
and downstream compatibility claims together. Never infer a release from the
presence of an ADR or this plan. APT-only code remains current until L6 ships.

Do not impose a speculative release date or promise backend support from core
contract work. RAE owns the common semantics/conformance; backend and catalog
integration can produce linked evidence without relocating those products into
RAE. The design review is documentation only and is not a request to merge a
breaking implementation.

## Milestone exit criteria

- The F2 exact-sibling counterexample is prevented through the admitted path.
- Five Linux boxes and all Kali refinement cases execute through inherited
  delegation, without compulsory release/package/repository forms.
- A complete abstract two-computer/three-action model needs no invented OS,
  filesystem, image or packet-network detail.
- A single scenario can constrain one deep value, delegate another, close one
  collection, leave another partial, and round-trip all distinctions.
- A backend can realize the software outcome through APT, DNF or a private
  route when permitted, and rejects disallowed routes or changed exact values.
- Private typed domain detail survives capture and exchange without a core
  release, with explicit unsupported semantics where required.
- Partial captures remain useful without claiming completeness or becoming
  requirements automatically.
- Actual backend choices are reportable at requested depth. No experimental
  data, operational-only, no-preference and scoped exhaustive modes work
  independently of scenario specificity, including retention/export.
- Admission distinguishes choosing one allowed realization from guaranteeing
  all possibilities; declared constraints and genuinely required capture remain
  binding, with unsupported claims and policy conflicts reported honestly.
- The candidate/disposition ledger has an owner and verified outcome for every
  confirmed instance; retained closed sets have a rationale.
- Migrations, schemas, docs, tool support and downstream journey evidence are
  published together with their actual limitations.

## Delivery links

The [milestone](https://github.com/OpenRAE/rae/milestone/70) and its initial twelve
remediation issues were created on 2026-09-04. The 2026-09-05 clarification added
L13 (#1212) and strengthened all existing work packages. Each issue includes scope,
dependencies and acceptance criteria. The design issue also contains the
review/research baseline; the correctness issue contains the full reproducer.

| Work package | GitHub issue |
|---|---|
| L1 | [#1200: Preserve exact runtime constraints beside unknown or open sibling fields](https://github.com/OpenRAE/rae/issues/1200) |
| L2 | [#1201: Define recursive partial-description, closure, refinement and lifecycle semantics](https://github.com/OpenRAE/rae/issues/1201) |
| L3 | [#1202: Add independently distributable typed domain profiles and support negotiation](https://github.com/OpenRAE/rae/issues/1202) |
| L4 | [#1203: Represent nested constraints and collection closure without aggregate authority loss](https://github.com/OpenRAE/rae/issues/1203) |
| L5 | [#1204: Enforce granular realization constraints through planning and runtime validation](https://github.com/OpenRAE/rae/issues/1204) |
| L6 | [#1205: Separate software outcomes, acquisition constraints and final repository state](https://github.com/OpenRAE/rae/issues/1205) |
| L7 | [#1206: Replace closed runtime implementation vocabularies with identity-preserving extensions](https://github.com/OpenRAE/rae/issues/1206) |
| L8 | [#1207: Separate partial descriptions from executable-profile completeness requirements](https://github.com/OpenRAE/rae/issues/1207) |
| L9 | [#1208: Extend artifact, materialization, identity/access and resource profile selections](https://github.com/OpenRAE/rae/issues/1208) |
| L10 | [#1209: Preserve partial typed descriptions and coverage in realization reports and capture](https://github.com/OpenRAE/rae/issues/1209) |
| L11 | [#1210: Version and migrate progressive semantics across schemas and authoring tools](https://github.com/OpenRAE/rae/issues/1210) |
| L12 | [#1211: Verify progressive specification end to end and prevent catalog-shaped regressions](https://github.com/OpenRAE/rae/issues/1211) |
| L13 | [#1212: Separate scoped observation and reporting demand from realization detail](https://github.com/OpenRAE/rae/issues/1212) |

Existing #959, #989, #1112 and participant-control issues remain with their
current owners and milestones. They are linked dependencies, not duplicated
or closed by this review. #1198 can close with publication of this audit; the
milestone remains open for implementation and verified remediation.

The documentation PR publishes the review, research, plan and reproducer from
`1198-language-design-review` against `dev`. Its closure reference targets only audit #1198, not
the implementation issues or milestone. No runtime fix or accepted language
revision is delivered by this documentation change. The substantive records
are also preserved in the linked GitHub issues.
