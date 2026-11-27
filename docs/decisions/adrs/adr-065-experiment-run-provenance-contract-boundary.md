# ADR-065: Experiment Run Provenance Contract Boundary

## Status

accepted

## Date

2026-06-22

## Classification

Classification: FM2
Required artifacts: ADR, formal spec, schema update, fixtures, contract tests
Waivers: none

Issue #89 publishes the joint design for EXP-710, EXP-720, and EXP-722. The
work extends the existing `experiment-run-v1` archival run contract; it does
not create a second run-provenance root schema.

## Context

ADR-055 established the experiment-core family for tasks, apparatus contexts,
runs, and studies. ADR-064 added evidence capture specifications, raw evidence
records, derived measures, and backend observation capability declarations.

The remaining joint provenance requirements need the run record to act as the
canonical archival join point:

- EXP-710 requires traceability from task and run context through captured
  evidence to derived measures, evaluations, and experiment claims.
- EXP-720 requires a canonical run provenance record distinct from live
  execution state, with task, scenario/module digest, processor, backend,
  manifest, configuration, parameter, stochastic-control, timestamp, result,
  and evidence pointers.
- EXP-722 requires realized forms chosen by processors and backends for
  underspecified concerns to be preserved separately from authored scenario
  material and derived results.

The pre-existing `ExperimentRunModel` already carries most EXP-720 context. A
new root schema would split the authoritative record and force consumers to
reconcile two provenance shapes for one run. The correct boundary is therefore
to extend `experiment-run-v1` with the missing traceability and realized-form
surfaces.

## Decision

`experiment-run-v1` is the canonical run provenance record. It remains the
authoritative archival record for one task execution and now includes two
additional surfaces:

1. `traceability` - a required block that links the run to capture
   specifications, raw evidence records, derived measures, and claim/report
   references. Claims require at least one derived-measure reference so a result
   claim cannot float free of interpreted evidence.
2. `realized_form_disclosures` - optional disclosures for underspecified
   concerns whose concrete form was chosen by a processor, backend, operator, or
   observation. Each disclosure names the concern, realization basis,
   realization authority, authored reference when present, realized reference or
   value summary, disclosure text, and supporting evidence-record refs.

The existing fields continue to carry the rest of the canonical provenance:
`task_ref`, `scenario_snapshot_ref`, embedded `apparatus_context`, participant
implementation provenance, parameter set, stochastic controls, clocks,
timestamps, result summaries, run evidence artifacts, and used/generated/
derived reference lists.

The contract deliberately keeps these concepts separate:

- authored scenario material remains `scenario` or `scenario-snapshot`
  references;
- realized choices are disclosures under the run record;
- raw observations are `experiment-evidence-record-v1`;
- interpreted outputs are `experiment-derived-measure-v1` and run result
  summaries;
- live control-plane snapshots and operation statuses are not canonical run
  provenance.

The published JSON Schema remains the portable structural contract. Semantic
constraints that standard JSON Schema cannot fully express are declared through
the existing `x-aces-invariants` profile and enforced by the Pydantic contract
models.

## Consequences

### Positive

- There is one canonical run provenance artifact for EXP-710, EXP-720, and
  EXP-722 rather than parallel provenance and realized-form schemas.
- Consumers can follow a durable chain from task/run context to capture specs,
  evidence records, derived measures, and claims.
- Realized choices for underspecified concerns are reviewable without treating
  them as authored scenario meaning or as metric results.

### Negative / Costs

- The `experiment-run-v1` schema hash changes because a required traceability
  block is added to the existing draft contract.
- Fixtures and producers of run records must now publish capture/evidence
  traceability alongside result summaries.

### Risks

- Implementers may try to use `realized_form_disclosures` as a free-form log
  field. The contract requires a concern id, basis, realization authority, and a
  realized reference or value summary to keep disclosures inspectable.
- Traceability references can identify artifacts but do not fetch or validate
  external payloads. Future storage/API work must reuse the existing
  control-plane authorization, redaction, request-size, audit, and idempotency
  patterns before dereferencing artifact URIs.

## Alternatives Considered

- **Add `experiment-run-provenance-v1` as a new root schema.** Rejected because
  `experiment-run-v1` is already the archival run record; a second root would
  duplicate authority and make traceability reconciliation ambiguous.
- **Put realized-form disclosure into apparatus context only.** Rejected
  because realized choices can involve processor resolution, backend defaults,
  participant implementations, capture windows, and parameter defaults. The run
  is the only artifact that sees all of those choices together.
- **Use only `used_refs`, `generated_refs`, and `derived_from_refs`.** Rejected
  because generic lineage lists do not state the EXP-710 path from capture spec
  to raw evidence to derived measure to claim, and they cannot express
  realized-form disclosure semantics.

## Amendments

| Date | Commit/PR | Summary |
|------|-----------|---------|
| 2026-10-29 | #1630 | Record all started work, missing evidence, distinct attempt history, and unchanged retry and safe-reuse authority (#1630). |

## Amendment: complete failure accounting (#1630, 2026-10-29)

Every started run must remain represented, including failure before scientific capture.
Run existence does not depend on available metrics, evidence artifacts, or successful checks.
The run contract can carry an explicit partial record with known work facts and missing observed facts.
Existing complete archival records keep their checks requirements.
Unknown end times, apparatus observed facts, and cleanup receipts must not be invented.
A stored failure record does not establish task evidence satisfaction.
Runtime lifecycle facts remain in the existing durable decision and operation stores.
Fixed archival versions keep the facts available at each recorded cut.
The [complete accounting design](../issue-1630-run-accounting-design.md) defines the boundaries and authoritative reference patterns.

For example, a node fails to start before a model is called.
Keep a record of that failed run. State that no score was measured.
Keep any cleanup facts. Do not invent output to fill a required field.
A later retry keeps the first attempt in the run's history.
A new trial has a new run ID and a link to the old run.
The old record must still be read in its original form.
