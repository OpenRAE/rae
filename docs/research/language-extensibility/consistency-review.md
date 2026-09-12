# Design-intent consistency review, 2026-09-05

Scope: the documents and backlog produced for #1198, their directly relevant
ADRs and explanatory guidance, and existing issue/milestone ownership. No
implementation workflow, runtime/schema change or ADR acceptance is part of
this pass. The initial review created research documents, not a new ADR.

## Corrective finding

The first review was directionally aligned but not a sufficient design brief.
It emphasized typed extensibility and completion of partial concrete models,
showed explicit per-field package-manager/acquisition delegation, and made
backend provenance reporting sound unconditional. That could perpetuate the
same design drift the user wanted corrected under a better extension mechanism.

The [clarified intent](design-intent.md) is now the starting point: inherited
open scopes delegate materialization choices; exact descendants remain binding;
abstract models can be complete; the backend must be able to report its actual
choices; and experimental observation, retention and export are independently
requested. Installation recipes and captured specimens are not universal author
requirements. This is explicitly a deliberate correction of a tendency against
the intended design, not neutral catalog growth or merely a DNF addition.

## Documents and ADRs

All ADR notes are preserved as dated [companion follow-ups](adr-follow-ups.md).
Full publication verification identified protected historical content digests
and accepted-ADR pins, so the notes were moved out of the ADR files rather than
changing their records or refreshing their hashes. Original ADR content and
status are unchanged; the companion is linked alongside the pinned ADR index
from the developer documentation. Conflicts with current contracts remain
assigned to versioned remediation rather than silently declared fixed.

| Record | Disposition |
|---|---|
| [Design review](design-review.md) | Corrected the software example and compulsory-reporting implication; added inherited delegation, abstraction-level completeness, independent demand and admission-quantifier review. |
| [Research basis](research.md) | Distinguished maintainer requirements from literature-derived precedents; reinforced reuse of existing observation planes and the difference between witness selection and universal subsumption. |
| [Scope inventory](scope-inventory.md) | Applied the intent across all families; added cross-layer admission/demand concerns without labeling them new full-run counterexamples. Baseline census/probes unchanged. |
| [Remediation plan](remediation-plan.md) | Strengthened every work package and exit criteria; added L13/#1212 for scoped-demand correction and explicit ownership dependencies. |
| ADR-012 ([historical index](../../decisions/adrs/README.md)) | Clarified that governed meaning does not require cataloging or registering every private backend choice. |
| [ADR-021](../../decisions/adrs/adr-021-falsification-first-claim-evidence-gate.md) | Its major architecture/maturity claim gate remains valid; explicitly separated it from a universal per-run telemetry mandate. |
| [ADR-033](../../decisions/adrs/adr-033-scenario-delivery-boundary-for-runtime-node-state.md) | Reinforced representability versus required authoring/capture. Flagged the historical evidence-by-default amendment for scoped-policy reconciliation, without removing history. |
| [ADR-048](../../decisions/adrs/adr-048-datastore-service-runtime-inventory.md) | Marked required geometry/mappings/persistence guards as corrective-design targets under #1207, not universal authoring guidance. |
| [ADR-050](../../decisions/adrs/adr-050-forwarding-agent-runtime-inventory.md) | Marked specimen guards and unconditional reading of corroboration for review; retained actual selected verification and augmentation obligations. |
| [ADR-051](../../decisions/adrs/adr-051-orchestration-authority-runtime-inventory.md) | Separated incomplete/abstract description from real execution authority and concrete interface prerequisites; backend choice is not a privilege grant. |
| [ADR-064](../../decisions/adrs/adr-064-experiment-evidence-and-measure-contract-boundary.md) | Kept capture intent/record/measure ownership; capability to represent evidence is not a duty to collect it. |
| [ADR-066](../../decisions/adrs/adr-066-observability-evidence-plane-separation.md) | Reused the five existing planes and ownership. Added explicit independent-demand clarification while retaining conditional augmentation/visibility disclosures. |
| [ADR-070](../../decisions/adrs/adr-070-realization-envelope-semantics.md) | Flagged one-choice admission versus universal coverage; preserved the accepted subset relation pending explicit gate/contract remediation. |
| [ADR-072](../../decisions/adrs/adr-072-validation-and-admission-profiles.md) | Distinguished selected validation strength from deciding what experimental data is required; retained proposed status. |
| [Design precedents](../../explain/sdl/precedents.md) | Added a prominent warning that historical inventory/guard descriptions are not compulsory authoring guidance. No lineage classifications were changed. |
| [Scientific completeness guide](../../explain/sdl/scientific-scenario-completeness.md) | Clarified completeness at a chosen abstraction and evidence intent, without upgrading current delivery assessments. |

The envelope formal contract's R4 and the
`raes_processor/semantics/realization.py` open-demand call establish a concrete
review target: the current relation checks universal coverage, whereas delegated
materialization asks the backend to choose a supported allowed completion.
This pass does not change that contract or claim a new deployed-backend failure.
#1201/#1204 own the quantifier review and #1210 its compatibility implications.

## GitHub ownership and reinforcement

- #1198 retains its original motivating evidence and now carries the clarified
  intent, revised full remediation plan and this consistency record.
- #1201 leads with the maintainer's concrete examples and governing rules,
  followed by the revised review/research; it links the plan in #1198. This
  avoids burying the intent in a repeated implementation checklist.
- Every existing work package #1200–#1211 has strengthened scope and acceptance
  criteria for its part of the correction. #1206 retains the full inventory;
  #1200 retains the original reproducible baseline and negative control.
- #1212 adds scoped observation/reporting-demand correction. It reuses the
  delivered #127/#337/#338/#339 foundations and ADR-064/066; #341 remains the
  task/run/study refinement owner, #340 augmentation conformance, #342 source
  provenance and #273 evidence integrity. None is duplicated or reopened.
- #1112 remains required-capture admission: enforce actually declared/inherited
  obligations and required operational inputs, not invented evidence from an
  exact image or available observation type. Its added clarification does not
  weaken the missing-required-evidence negative case.
- #959 gains the inherited-delegation and abstraction/demand audit rubric.
  #1167 gains explicit status reconciliation for this program. Neither changes
  owners or milestone; #989's classification migration remains unchanged.
- Milestone 70 now states the deliberate correction and the Linux/Kali,
  abstract-model, reporting and independent-observation exit criteria. Its
  thirteen remediation issues remain open for implementation. #1198 is the
  completed audit/planning deliverable and can close with its documentation PR.

All open milestone descriptions were inspected. Related milestones 59 (SDL),
60 (runtime/participant), 61 (backend conformance), 64 (governance/evidence),
67 (participant control), and 69 (developer artifacts) define compatible
ownership scopes rather than compulsory per-scenario detail. They are unchanged;
milestone 69's developer acquisition/provenance is not the owner of scenario
materialization. No unrelated milestone was renamed or repurposed.

## Verification boundary

The baseline research probes and their recorded results are not modified by
this consistency pass. Verification checks documentation policy, local links,
whitespace, issue-body round trips, issue/milestone membership, dependency
references and the presence of the concrete acceptance anchors. These checks
establish publication consistency, not implementation of the proposed semantics.
No runtime code, published schema or accepted ADR status is changed by this
pass. The follow-up documentation PR publishes the repository edits from
`1198-language-design-review` against `dev` with a closure reference for only audit #1198.
Because `main` is the default branch, merging into `dev` does not itself trigger
GitHub's default-branch issue auto-closure; the merge handoff must close the audit
explicitly if it remains open.
The governing intent, review, research, plan and consistency record are also
published through the linked GitHub issues. Native GitHub blocking relationships
now enforce the immediate prerequisites in the [remediation plan](remediation-plan.md);
implementation completion and milestone closure remain separate from publication
of the audit.
