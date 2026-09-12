# Dated ADR follow-ups for issue 1198

Recorded 2026-09-05. These are corrective design-review notes for #1201 and
milestone 70, not amendments to accepted decisions or claims of shipped changes.
The original ADRs, their acceptance pins and historical identity digests remain
unchanged. This companion is linked alongside the historical ADR index in the
[developer documentation](../../README.md).

The governing rule is: the author constrains what matters; the backend resolves
remaining materialization choices; RAE can describe the result at requested
depth. See [design intent](design-intent.md), the [review](design-review.md) and
the [consistency record](consistency-review.md).

## ADR-012

Original: ADR-012, listed in the [historical ADR index](../../decisions/adrs/README.md).

[#1201](https://github.com/OpenRAE/rae/issues/1201) deliberately corrects a
tendency to turn externally owned implementation detail into compulsory core
catalogs. Shared meaning for a declared concept does not require an author to
declare every backend materialization choice or register an irrelevant private
mechanism. Retain typed comparison and justified closed operational terms;
apply extensible profiles only where detail is described, constrained or
exchanged. See the [clarified intent](design-intent.md).
This follow-up identifies remediation, not a shipped vocabulary migration or a
change to this ADR's historical acceptance status.

## ADR-021

Original: [ADR-021](../../decisions/adrs/adr-021-falsification-first-claim-evidence-gate.md).

The evidence gate in the original ADR concerns major architecture/maturity claims; it is not
a mandate to collect experimental telemetry for every scenario or independently
measure every backend choice. A detailed scenario may request no experimental
data, while an abstract one may request exhaustive scoped traces. Claims still
must not exceed their actual basis. See [#1201](https://github.com/OpenRAE/rae/issues/1201)
and the [clarified intent](design-intent.md).
No falsification gate is waived or claimed implemented by this clarification.

## ADR-033

Original: [ADR-033](../../decisions/adrs/adr-033-scenario-delivery-boundary-for-runtime-node-state.md).

Representability at an owning surface is not mandatory authoring or mandatory
collection. [#1201](https://github.com/OpenRAE/rae/issues/1201) deliberately
corrects the drift from detailed inventory support to compulsory specification:
authors constrain what matters, effective open scopes delegate remaining
materialization choices, and backends can report actual choices at requested
depth. An abstract model need not acquire concrete machine detail merely
because this ADR provides a place to describe it.

The historical #417 amendment's evidence-by-default wording must be reconciled
with scoped observation/reporting policy in [#1212](https://github.com/OpenRAE/rae/issues/1212),
not treated as authority for universal collection, retention or export.
Observed facts still do not become author requirements automatically. See the
[clarified intent](design-intent.md).
Historical decisions and current runtime contracts remain visible in the original ADR;
this follow-up is not a claim that their migration has shipped.

## ADR-048

Original: [ADR-048](../../decisions/adrs/adr-048-datastore-service-runtime-inventory.md).

The required-profile guards recorded in the original ADR are specifically under remediation
in [#1207](https://github.com/OpenRAE/rae/issues/1207). A typed datastore surface
must not force the author to specify geometry, mappings or persistence merely
because a captured specimen or a backend's concrete installation needs them.
Under an open scope the backend resolves permitted choices; explicit child
constraints remain binding. Abstract models and partial captures need no
fabricated complete datastore inventory. Selected execution/verification
profiles may impose genuine obligations without making them universal base
validity rules. See [design intent](design-intent.md)
and [#1201](https://github.com/OpenRAE/rae/issues/1201).
The text in the original ADR records existing decisions, not the completed correction.

## ADR-050

Original: [ADR-050](../../decisions/adrs/adr-050-forwarding-agent-runtime-inventory.md).

[#1201](https://github.com/OpenRAE/rae/issues/1201) deliberately corrects
compulsory specimen-shaped detail and unconditional evidence expectations.
The required-profile guards in the original ADR are owned by [#1207](https://github.com/OpenRAE/rae/issues/1207)
for migration: open scopes delegate concrete choices, while explicit constraints
remain binding and partial/abstract descriptions remain useful.

The existing corroborated-inventory contract is not authority to collect every
agent's telemetry or configuration on every run. Separate selected realization
verification, requested experimental observations, actual choice reporting and
operational inputs through [#1212](https://github.com/OpenRAE/rae/issues/1212),
#1204 and #1209. Preserve honesty about corroboration where required; do not
silently waive current gates or reclassify an echoed plan as evidence. See
[design intent](design-intent.md).
Historical decisions in the original ADR remain until explicit contract migration.

## ADR-051

Original: [ADR-051](../../decisions/adrs/adr-051-orchestration-authority-runtime-inventory.md).

The concrete-interface and Docker-shaped privilege guard in the original ADR is reviewed
under [#1207](https://github.com/OpenRAE/rae/issues/1207) and #959. The deliberate
correction is to keep requested authority constraints binding without forcing
irrelevant implementation detail into every author description or capture.
An open materialization scope delegates permitted choices; it does not grant
privileges, bypass operator policy or make a partial observation executable.
The backend must resolve real execution prerequisites within its authority.
See [#1201](https://github.com/OpenRAE/rae/issues/1201) and
[design intent](design-intent.md).
This follow-up does not change shipped validation or the historical decision.

## ADR-064

Original: [ADR-064](../../decisions/adrs/adr-064-experiment-evidence-and-measure-contract-boundary.md).

The ability to declare capture capability or represent evidence does not oblige
every scenario to request capture. Precise images, files or package constraints
do not automatically imply experimental collection, retention or export.
[#1201](https://github.com/OpenRAE/rae/issues/1201) and
[#1212](https://github.com/OpenRAE/rae/issues/1212) reinforce that deliberate
boundary using these existing contracts, not a parallel evidence system.
Selected capture requirements and honest claim-strength obligations remain
binding. See [design intent](design-intent.md).
This clarification does not change published artifact behavior.

## ADR-066

Original: [ADR-066](../../decisions/adrs/adr-066-observability-evidence-plane-separation.md).

The separation in the original ADR is a foundation for [#1201](https://github.com/OpenRAE/rae/issues/1201),
not something the remediation replaces. It deliberately corrects the tendency
to make scenario detail or backend materialization choices imply universal
experimental data obligations. Open scopes delegate unspecified materialization;
backends can report actual choices at requested depth without measuring,
retaining or exporting every possible detail. Precise scenarios may request
no experimental telemetry; abstract scenarios may request exhaustive scoped traces.

[#1212](https://github.com/OpenRAE/rae/issues/1212) reconciles scoped no-data,
operational-only, inherited/default and detailed demand through these existing
planes and contracts. #341 retains task/run/study refinement, #340 augmentation
conformance, #342 source provenance and #1112 required capture admission.
An open choice does not waive augmentation visibility or comparability
disclosures where their existing conditions apply. See
[design intent](design-intent.md).
This is clarification and planned reconciliation, not a change to shipped gates.

## ADR-070

Original: [ADR-070](../../decisions/adrs/adr-070-realization-envelope-semantics.md).

[#1201](https://github.com/OpenRAE/rae/issues/1201) makes inherited open scopes
an explicit backend obligation to resolve unspecified materialization choices
while preserving declared constraints. Five Linux boxes, open in the original ADR, must not
require the author to select distributions/images/packages; abstract scenarios
can be complete without any concrete machine representation.

The universal `subsumes(offered, requested)` relation in the original ADR answers whether
every requested instance is supported. Choosing one allowed realization is a
different obligation: find a supported witness satisfying the request and
selected policy. #1201/#1204 must distinguish these quantifiers at admission and
conformance boundaries, including the current open-demand subsumption call.
Do not silently redefine subsumption or weaken universal capability claims.
Any changed contract/gate requires explicit versioned remediation. Realization
reportability also does not imply unrequested experimental collection; #1212
owns that policy boundary. See [design intent](design-intent.md).
This note records a corrective requirement, not a shipped change to the formal
contract or the accepted decision in the original ADR.

## ADR-072

Original: [ADR-072](../../decisions/adrs/adr-072-validation-and-admission-profiles.md).

Validation/evidence strength describes the basis of a selected claim; it does
not select experimental collection for the author. [#1201](https://github.com/OpenRAE/rae/issues/1201)
and [#1212](https://github.com/OpenRAE/rae/issues/1212) deliberately separate
scenario specificity, requested observations/reports, collection/retention/export
and operational requirements. Exact images or files need not imply independent
measurement, and abstract models may request extensive traces. A backend must
resolve open materialization choices, not demand a completed author recipe.
Required inputs and honestly selected claim-strength gates remain binding;
unrequested evidence must not become a universal admission prerequisite.
See [design intent](design-intent.md).
This clarification does not accept this proposed ADR or change current schemas.
