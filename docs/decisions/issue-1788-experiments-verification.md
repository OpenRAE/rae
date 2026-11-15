# Experiment and trial port verification

This record identifies the native owners and their behavioral evidence for
issue #1788. The reference inventory pins 77 Python modules and 16,132 lines.
It includes the issue's 71 modules and six record-support modules called by
those modules. A source hash identifies the reference; it does not prove coverage.

## Ownership and acceptance

| Issue criterion | Native owner | Behavioral evidence |
| --- | --- | --- |
| Experiment documents and shipped examples retain their results. | `contract/admission/experiment_yaml.go` and `internal/parity/experiment_operations.go` | `TestExperimentYAMLMatchesExamplesAndReferenceRefusals`; six unchanged `mcp experiment_validate` goldens, including all three experiment examples. |
| Published contract behavior remains unchanged. | Existing `contract/admission` registry and `contract/validation` schema owner. | 95 selected experiment and trial cases in `TestFullValidationGoldenCorpus`; `TestRecordedLocalModelsMatchIndependentPython`; published schemas and original goldens have no edits. |
| Entry and plan identities, canonical content, and digests remain exact. | `contract/admission/trial_sealing.go`, `trial_plan.go`, and `processor/trial/plan_compile.go`. | `TestTrialSealingMatchesIndependentConstructors`, `TestCompilerMatchesIndependentPlansAndDraws`, and `TestTrialSealingKeepsExplicitByteAllowanceAboveDefault`. |
| Selection and realization preserve recorded random draws. | Public SDL phase owners, existing random-stream owner, and `processor/trial`. | `TestInstantiationMatchesIndependentSnapshotsAndLineage`, `TestTrialRealizationUsesExistingProcessorPlans`, `TestTypedRealizationReplaysIndependentAuthoringSelections`, and mixed reference cases. |
| Runtime records preserve starts, facts, scientific results, and histories. | `runtime/experiment/records.go`, `lineage.go`, `studies.go`, and `publication.go`. | Independent record, scientific accounting, study, replacement, and publication tests. Execution completion alone does not establish scientific validity. |
| Runtime ownership remains identifiable for extraction. | The `runtime/experiment` package in the declared runtime layer. | Actual architecture check; required `Host`, `Journal`, and `OwnerCalls` composition. |
| Engineering and architecture standards apply. | Existing Go policy, lint, architecture, and CI commands. | Changed-package lint, actual architecture check, targeted tests, documentation checks, mandatory review, and PR checks. |

## Limits and security boundaries

| Boundary | Evidence |
| --- | --- |
| Experiment input: 64 KiB, UTF-8, one mapping document, no aliases or duplicate equivalent keys. | YAML reference and binary-constructor cases; contained file loading and sorted discovery tests. |
| Schema, native carriers, depth, and aggregate work. | Existing schema/model reference cases; `TestTransportBoundsBeforeSerialization`, `TestTransportTreeBoundsKnownRecordsWithoutForeignMethods`, and runtime portable-value tests. |
| Coordinate, finite-domain, product, binding, mixed-profile, and context work. | `TestCompilerLimitsPreserveIndependentAtomicRefusals`; mixed authority/work refusal cases; independent scalar-domain bounds. Admission precedes expansion. |
| Random draw work. | `TestEntryDrawLimitPrecedesConfigurationConstruction`. The defensive entry guard runs before participant configuration construction. |
| Plan bytes and source order. | Explicit larger byte allowance, default byte refusal, 600-entry sealing, 800-entry source-order cases, and stable ties. The default plan limit remains 32 MiB. |
| Diagnostic order. | Independent capture refusal cases, including two diagnostics with `max_diagnostics=1`. The reference compiler accepts the positive setting but does not truncate its capture diagnostic set. |
| Validator identity and participant configuration authority. | Declared validator-key test; participant configuration tests for aliases, concrete manifests, integer types, complete defaults, origins, and changed authority. |
| Foreign callbacks, errors, and private values. | Configuration normalizer, factory, snapshot, and foreign error-inspection tests. Foreign failures retain safe codes without private messages. |
| Aggregate configuration budgets. | Header and aggregate limits apply before installed normalizers and again to their results. Duplicate controls refuse before callbacks. |
| Apparatus and execution intent. | Backend/processor allowlists, compatibility, capture offers, selected processor requirements, cleanup actions, and operation-supervision tests. Unused manifests do not grant or remove selected authority. |
| Live handoffs. | Runtime request/result portable-value budgets, actor/scope checks, evidence scope, operation receipts, detached snapshots, and terminal oversize refusal. |
| Evidence content. | Content-backed run and study cases, checksum and media checks, JSON Lines CR/CRLF cases, reader ownership, and safe foreign EOF inspection. Locators remain inert labels. |
| Evidence volume. | Existing content limits remain 64 MiB per artifact, 256 MiB total, and 1,024 items. A 1,025-record history retains references and source facts while omitting the oversized embedded proof set. |
| Runtime capacity. | Required owners, bounded retained admission, 4,096 entries, 1,000 attempts, exact UUIDv5 attempt identity, and closed private decision shapes. |
| Deadline and interruption. | Restart retains the original deadline; rollback refuses. Cancellation remains available during blocked progress. Stop acknowledgement does not establish cessation. |
| Retry and cleanup. | All four author retry policies, attempt exhaustion, failed cleanup, unsettled reset/compensation, retained evidence, and foreign obligation refusal. |
| Retirement and replacement. | Durable shared retirement, lost retirement acknowledgement, exact source child plans, lost archive acknowledgement, and child allocation before parent retirement. |
| Record publication. | Frozen candidates, exact readback, immutable version ownership, scientific-original linkage, every supplied archive, and retained records during reader outages. |

## Defect-case families

The tests use the native boundary that owns each invariant. A Python function
that also starts a backend or a worker is not evidence that those other
components have been exercised by a pure compiler test.

| Reference family | Native evidence |
| --- | --- |
| Experiment authoring, #380, #1519, and #1563. | Independent YAML refusals, actual dates, binary text construction, constructor defaults, task/run/study joins, and published fixture cases. |
| SCE-002 and EXP-719. | Nine exact compiled plans, deterministic instantiation, large plans, source ordering, atomic limits, apparatus refusals, and complete source readmission. |
| #1625, #1626, #1665, and #1666. | Typed selection authority, crossed participant/structural effects, canonical aliases, manifest pins, strict boolean/number agreement in existing contract owners, equal-effect refusal, and original-input replay. |
| #1015 and mixed composition. | Alternative, simultaneous, staged, nested, and replacement reference plans; missing authority, closure, resources, projection membership, and bounded work refusals. |
| #1627. | Minted native requests, public processor artifacts, scoped results, evidence roles, operation receipts, nested reconstruction, item limits, and snapshot detachment. |
| #1628 and #1629. | Static control admission plus required shared-owner calls, cessation evidence, capture/cleanup separation, cancellation, retry policy, deadline recovery, retirement, and lost-acknowledgement replacement tests. |
| #1396. | Exact replacement identities, fresh initialization, preserved parent versions, complete history, conflict, exhaustion, cleanup/reuse refusal, and retained study lineage. |
| EXP-731, EXP-732, and #1630. | Content-backed evidence, run/study joins, scientific-original accounting, retained failed work, reader failure/closure, immutable publication, exact versions, and replacement history. |

The selected Go output contains no concrete engine, store, worker pool, backend,
or Temporal worker. These are supplied through the existing ownership
boundaries. Tests assert forwarding and reconciliation at those boundaries;
they do not claim live integration with components absent from this checkout.
This preserves the issue's runtime extraction boundary without a second engine.

The operation-budget arithmetic assertion in
`test_authored_attempt_allowance_caps_operation_budget_without_limiting_cleanup`
exercises `operation_policy_admission`, which is outside the selected source
inventory. The Temporal-worker guarantee assertions likewise exercise that
worker. They do not require another operation-policy engine or worker here.
The native controller tests retain the deadline, pass exact trial controls and
identity to the required shared owner, and keep cleanup separate from execution.


## Verification record

Local checks select the changed packages and named cases. Full tests,
integration, fuzz, coverage, and full mutation gates run in CI/CD.

Three targeted mutations verify the result value budget, native cleanup-obligation
ownership, and draw-limit ordering before participant callbacks. Each mutation
failed its behavioral test. Each source file was restored.

Shared plaintext API fragments retain each package's complete canonical closure.
`TestSharedAPIFragmentsPreserveExactClosuresAndDuplicates` checks fragment order,
changed declarations, and duplicates. Exact comparison and existing snapshot
bounds remain in force.

The PR records the final commands, required review, CI results, and readiness.
