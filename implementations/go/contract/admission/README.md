# Contract admission

Create one `Validator` with `New` and keep it for reuse.
`Validate` checks schema shape, published invariants and extra model rules.
It returns a `validation.Value` only after those checks pass.
That value keeps its bytes private.
`New` refuses a missing rule or bad catalog.
It binds all 180 rule IDs at their published schema paths.

`CheckPortable` keeps the reference portable entry point's local claim.
It checks local rules and model terms.
It needs trusted context for stronger claims.
Use `Validate` for full semantic checks.

## Trusted context

The service's existing owner provides its context.
Input fields cannot create a context or an admitted `Value`.
The library does not fetch references, open locators, dispatch work or publish data.
A shared validator needs contexts that are safe to share.

| Family | Context owner |
| --- | --- |
| Cleanup and completeness | `CleanupContext`, `CompletenessContext` |
| Experiment joins and evidence | `ExperimentTaskContext`, `ExperimentStudyContext`, `ExperimentDifficultyContext`, `EvidenceRelationContext` |
| Selected manifests and claims | `ApparatusManifestContext`, `BehavioralClaimContext` |
| Backend messages and injects | `BackendResponseContext`, `BackendAdmissionContext`, the inject context interfaces |
| Associated artifacts | `AssociatedArtifactsContext` supplies independent parent identity and bounded readers |
| Participant control | The agreement, content, occurrence, history and resolution context interfaces |
| Participant information and crossing | `InformationStateContext`, `CrossingContext` |
| Information flow | `FlowControlContext` supplies resolved source, policy, action, control and sink owners |
| Mixed composition | `MixedCompositionContext`, `MixedBackendBindingsContext`, `MixedBackendStagesContext` |
| Materialization | `MaterializationArchiveContext`, `MaterializationExecutionContext`, `MaterializationInventoryContext` |
| Satisfiable witness | `MaterializationCompiler` admits the exact instantiated SDL source and supplies its full model for the witness digest |

Contexts carry separate owner records and exact scope fields.
Go checks the report against those records.
Some tasks stay with their existing owners.
These include support checks and node shaping.
Go checks the joins, IDs, hashes, scope and history.
Owner errors are returned without private values.

## SDL report data

`MaterializationCompiler` calls the configured SDL semantic and compiler owner.
It must return full phase data for the exact source bytes.
`SourceSHA256` binds those bytes.
`Document` preserves supplied fields for canonical identity.
`FullDocument` includes model defaults for checks.
Resources keep original plan and prior snapshot data.
The registered owners supply collection keys, concern rules and typed presence.
A report cannot grant or change these facts.

The snapshot holds the full published plan and backend manifest.
It also holds the native prior state and actual state.
The plan uses its exclude-none serializer.
The native prior state has no published `schema_version` member.
Those views fix the existing plan and prior-state hashes.

The inventory context supplies the admitted configured envelope.
Its ID must match the chosen manifest.
It returns protected bytes for the exact retained record.
Go checks report order, ancestry and state changes.
It checks full scope, collection membership, backend support and permission for additions.
An SDL report grants no right to run work.

## Verification

The [rule inventory](../../../../specs/conformance/contract-invariant-rules.json)
states the published rules.
The [predicate crosswalk](../../../../specs/conformance/contract-predicate-sources.json)
links each rule to its code and reference owner.
The portable parity inventory in `internal/parity/admission-inventory.json`
fixes the recorded case set.
Full admission checks cover the complete packaged fixture inventory.
The maintainer chose separate full and structural reference results.
`TestFullValidationGoldenCorpus` scans the full fixture tree and published registry.
It checks 701 contract fixtures and one original selector regression.
Its separate Python results include 172 contextual comparisons with fixed owners.
Each remaining row has model validation or an explicit missing-context refusal.
A positive structural result may fail against a different parent or a real execution.
The table pins owner input hashes and retains every original input and result.
Cases with no trusted owner cannot grant contextual admission.
Context tests use separate reference-admitted data and refusal cases.
The [regression crosswalk](../../../../specs/conformance/contract-validation-regressions.md)
links limits, failures and source defect cases to Go tests.
CI runs all tests, race checks, mutation checks, fuzzing and coverage.
Local runs select affected test cases.
