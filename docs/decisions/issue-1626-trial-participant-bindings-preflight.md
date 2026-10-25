# Issue 1626 trial participant bindings preflight

Date: 2026-10-25

The issue title and body define the delivery contract.
The issue has no requirement scope.

## Existing authority

[ADR-094](adrs/adr-094-authoritative-cross-plane-experiment-bindings.md) owns the three binding planes.
It also owns complete participant configuration and secret-reference handling.
ADR-084 owns sealed trial entries and their archival `run_id`.
`ExperimentRunModel` remains the sole run record.
No new ADR, configuration root, or run type is needed.

The factorial compiler already carries the required results.
Explicit conditions must use this same path.
Each entry carries its condition's participant descriptors.
`required_bindings` can distinguish conditions without invented `required_refs`.
Legacy `required_parameters` do not grant mutation authority.

The compiler realizes each configuration once during atomic admission.
The complete result belongs inside the sealed entry.
One-entry realization passes that result to the run producer.
It must not recompute the result after scheduling or execution.
Owner inputs may have changed by that point.

The run preserves the admitted descriptor, origin, and configuration digest.
Its participant selection also preserves the manifest and configuration identities.
A `configuration_ref` can locate the retained result.
This issue defines no storage service or reference URI scheme.
The run must not gain another full configuration payload.

## Required reuse

All package paths below start at `implementations/python/packages/`.

| Boundary | Existing owner |
| --- | --- |
| Factors, levels, conditions and run matching | `raes_contracts/contracts/experiment_study.py`, `experiment_spec.py`, `experiment_factorial.py`, `experiment_conditions.py` |
| Plane and canonical target resolution | `raes_contracts/experiment_bindings.py::validate_experiment_binding_targets()` |
| Exact selected manifest and digest | `raes_processor/trial_compiler/apparatus.py::validate_selected_participant_manifests()` |
| Complete atomic configuration | `raes_contracts/participant_configuration.py::realize_participant_configuration()` |
| Trusted owner normalization | `ParticipantConfigurationValidator`, keyed by governed validator id and version |
| Result carriage, authority joins and seals | `AdmittedTrialEntryModel`, `validate_entry_participant_configurations()`, and the existing seal helpers |
| Bounded JSON and whole-plan checks | `parse_admitted_trial_plan_json()`, `parse_bounded_json_object()`, `revalidate_admitted_trial_plan()` |
| Sealed result handoff | `raes_processor/trial_realization.py::realize_admitted_trial_entry()` |
| Archive comparison | `RealizedBindingProvenanceModel`, participant provenance, `validate_admitted_trial_run()` |
| Safe failure | `CompilationFailure`, `TrialCompilationResult`, `Diagnostic`, and `AdmittedTrialPlanIngressError` |

Reuse strict scalar types and finite-number checks.
Resolve aliases before checking for duplicate canonical targets.
Equal duplicate values must still fail.
Use only the selected manifest's registry and owner.
Do not fall back to another plane or manifest.
Apply all defaults and require every target without a default.
Reject the whole plan when any coordinate fails.

Normalization must preserve target identity and scalar type.
It must also preserve value kind and default/override origin.
Secret-reference identity must remain unchanged.
Keep descriptor, normalized value, owner, and manifest joins checked.
Use the existing canonical JSON and digest helpers.
Input spelling and traversal order must not change configuration identity.

## Security boundaries

The reference document contains the data flow diagram.
Author input crosses the manifest-owner boundary at target admission.
Exact manifest pins and target checks prevent configuration injection.
The owner validator checks the complete result before sealing.
Entry and plan digests protect the admitted result's integrity.
Whole-plan reconstruction checks nested models before use.
Run comparison detects a changed archival configuration digest.
A digest proves neither permission nor successful runtime application.

Keep strict input shapes, byte bounds, and field limits.
Reject duplicate JSON members and non-finite numbers.
Keep the existing trial compilation limits.
No failed coordinate may disappear silently.

Secret references carry non-sensitive reference identities only.
Resolved secrets must never enter artifacts, digests, logs, or arguments.
Other permitted literal values can also need protection.
Do not dump full configurations or owner exception text.
Public errors must remain bounded and value-free.

This pure path adds no network or process calls.
It adds no file access or environment lookup.
It adds no authentication or authorization surface.
A later sink must still enforce its own access controls.
It must also enforce its information-flow and secret-delivery rules.
Never treat the sealed plan as a dispatch credential.

## Compatibility and extension

Keep empty legacy entries' wire shape and digest behavior.
Do not require configurations on every entry.
Do not synthesize defaults for an unbound participant.
For a bound participant, the result must be complete.
Keep participant address, implementation identity, and manifest identity distinct.
A manifest digest is not a configuration digest.
A location reference is not either digest.

Extend the existing manifest map, target registry, and validator map.
Another participant, target, alias, default, or validator revision needs no new entry field.
A new authority plane needs a versioned contract and ADR review.
Preserve published schemas, bundle parity, and publication records.
The current change needs no schema edit.

This issue adds no runtime mutation or secret resolution.
It adds no apparatus configuration realization or scheduling changes.
Mixed-profile admission retains its current authority rules.
The single-backend realizer still rejects mixed runtime execution.
No new run builder, artifact store, API, logger, or persistence layer is needed.
`ControlPlaneStore` must not become a configuration archive.
