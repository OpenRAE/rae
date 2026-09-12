# Requirement disposition

Design cut: 2026-09-06. [ADR-108](../../decisions/adrs/adr-108-modular-participant-control-and-governed-effects.md)
records the decision. Ground Control now reads version-controlled requirement
files; these changes become authoritative at the merged delivery revision.
New DRAFT requirements scope implementation; they are not fulfillment claims.
The retired HTTP service and stale historical research status tables are not
the source of current requirement state.

## New authority

| UID | Status | Bounded ownership | Delivery |
| --- | --- | --- | --- |
| [SEM-235](../../requirements/SEM-235/requirement.md) | DRAFT | Modular profiles, dynamic IFC domains, mandatory/advisory composition, conflict, effect and causal semantics. | #1070 publishes formal semantics, approved concept-authority placement and lineage. |
| [API-424](../../requirements/API-424/requirement.md) | DRAFT | Closed provider, selection, result, composition and trigger-to-effect bindings; public protocol and versioning. | #1072 publishes contracts after #1070. |
| [RUN-320](../../requirements/RUN-320/requirement.md) | DRAFT | Provider orchestration, final admission/commit, typed dispatch, bounded triggers, idempotency and recovery. | #1069 after #1072. |
| [ASR-538](../../requirements/ASR-538/requirement.md) | DRAFT | Independently runnable modular conformance and exact realization/claim boundaries. | #1071 after #1069; backend proofs consume the released result. |

These UIDs are new in this repository, not renumbered versions of SEM-233 or
SEM-234. Traceability to future issues uses DOCUMENTS; there is no IMPLEMENTS
link claiming unshipped executable behavior. The abstract-model TESTS links
explicitly cover design falsification only. Each implementation child must
reconcile its actual code/test links and fulfillment status in its delivery PR.

## Amended authority

[ASR-536](../../requirements/ASR-536/requirement.md) remains DRAFT. Its original
intentional-subversion protocol, adaptive knowledge, monitor topology, memory,
audit and intervention cost, safety/usefulness, and nonclaim requirements are
retained. The added paragraph requires exact modular composition and backend
realization evidence, allows policy-admitted adversarial inputs, and separates
out-of-world integrity failure from an in-world attack. #1007 owns this scope.
This does not make adversarial evaluation the definition of participant control.

ADR-101 receives a recorded, hash-pinned amendment under ADR-059. Its
general-purpose taint-engine/policy-language non-goal continues to exclude an
interpreter or engine in the RAES runtime; new IFC domain semantics and
backend-chosen engines are explicitly permitted by ADR-108. The existing
security algebra, exact-sink gates, releases and historical records are intact.

## Reused and adjacent authority

| Authority | Disposition | Continuing responsibility |
| --- | --- | --- |
| SEM-230; ADR-085/095 | Reuse, unchanged statement | Participant-relative flow, exact cuts, policy, projection, memory and relation claims. |
| SEM-233; #1001–#1004 | Reuse, unchanged ACTIVE statement | Independent confidentiality/integrity, conservative derivation, release and final-sink semantics. Prior completion is not evidence of a modular engine. |
| SEM-220, SEM-226 | Reuse | Decision surfaces, exposure, projection, masking, withholding and delivery versus observation. |
| SEM-208/209/210/211/212/213 | Reuse | Participant/action/interaction, visibility, admission, attribution and time/order foundations. |
| API-409, ACT-617, RUN-310 | Reuse | Supervisory authority, control transitions, proposal/approval/edit/handoff and lifecycle distinctions. |
| API-423, RUN-319 | Reuse | Typed crossings and enforcement, expected histories, final-sink admission and evidence. |
| API-404, RUN-305/306/307/308; ADR-104 | Reuse | Operation/store mutation, append-only histories, shared state, ordering, idempotency and indeterminate external outcomes. |
| DSL-111, DSL-142, API-421 | Reuse | Orchestration inject identity, participant delivery and governed clocks/scheduling. |
| API-406/407/420 | Reuse | Participant carriers and declared/effective feature support, implementation manifests and compatibility. |
| EXP-701–EXP-705; ADR-055/064/065/094 | Reuse | Existing experiment, apparatus, evidence, provenance, measure and authoritative binding carriers. #1072 maps exact fields to these owners. |
| ASR-502/519/527/535 | Reuse | Conformance infrastructure, realization honesty, participant and bounded flow evidence. |
| SEM-234, ASR-537; ADR-102 | Adjacent, unchanged | Mixed-backend execution, temporal coupling and transfer evidence; needed only when those claims are made. |
| Backend-native requirements | Backend-owned design dependencies | LilRAE #6 and Shifter #1967 must name their own selected realization and integrity authorities before their implementation children begin. Portable UIDs do not choose mechanisms or claim host protection. |

No ACTIVE requirement is broadened while retaining a false fulfillment claim.
No requirement is deprecated or replaced. Existing statements are sufficient
for incumbent effects; new typed request binding belongs to API-424.

## Implementation-start and release conditions

The exact merged #1068 revision containing ADR-108, its ADR-101 amendment and
these records is the first authority gate. #1070 can then begin. #1072 waits
for published #1070 semantics; #1069 for #1072 contracts; #1071 for the runtime.
The repository's requirement-order configuration maps all four new UIDs to
that sequence. DRAFT records exist before implementation starts; ACTIVE is
earned by the requirement's bounded acceptance evidence, not by issue linking.

Backend design may proceed after the architecture gate, independently in each
repository. Backend implementation requires its own accepted selection and
requirement mapping plus released RAES semantics/contracts/runtime/conformance.
Backend proof then supplies real installed artifact/readback evidence. #1007
and #1008 select only completed exact backend branches. Hub records status and
publication pointers without duplicating semantic authority.

The issue bodies link the proposed design branch until merge. Those links are
preparation, not removal of the design block. At merge the authoritative base
revision supplies the accepted requirement and ADR state; downstream work must
pin that revision or a released descendant.
