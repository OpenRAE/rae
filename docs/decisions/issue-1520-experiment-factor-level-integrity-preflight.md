# Issue 1520: Experiment condition factor and level integrity

Architecture preflight; issue #1520 is the authoritative contract. No formal
requirement is attached. This note changes no executable behavior and is not an
implementation plan.

## Recommended contract and decision boundary

The maintainer selected option 1: every condition's `factor_levels` must reference a key in
the containing spec's `factors`, and its value must belong to that factor's
`levels`, in both `descriptive` and `explicit-required` postures.
Authors supply these declarations for each experiment; RAE needs no domain catalog.
This note is not an accepted ADR or a claim that the behavior has shipped.

Declaration integrity and configuration authority are separate concerns.
`descriptive` continues to make no mutation claim under
[ADR-094](adrs/adr-094-authoritative-cross-plane-experiment-bindings.md).
Declared membership does not create a binding, prove that configuration was
applied, or establish execution evidence. `required_parameters` remain
descriptive criteria; their names and values need not equal factor ids or level
labels. Explicit descriptors retain their independent source/target/owner and
condition joins.

The archival `ExperimentStudyModel` already enforces this membership rule in
`_validate_run_allocation_condition_assignments()` in
`implementations/python/packages/raes_contracts/contracts/experiment_study_contract.py`.
The spec's `_validate_experiment_spec()` currently checks only blocking-factor
declarations, followed by descriptor and selection joins. Neither joining path
covers every assigned factor. Strict rejection would align authoring with the
existing archival rule without importing archival lifecycle requirements.
It tightens compatibility: previously accepted misspellings will fail. Explain
the correction as declaring or correcting the intended factor/level, without
silently adding declarations, dropping assignments, or switching postures.

## Validation ownership and reuse

The containing `ExperimentSpecModel` owns this cross-field invariant, after
factorial materialization and normal nested-model validation. It has both the
factor declarations and allocation. Neither the YAML reader nor an individual
`ExperimentConditionAssignmentModel` has that complete authority. A loader-only
fix would leave direct Python and conformance ingress inconsistent.

Reuse the archival membership loop through a small pure helper in the shared
experiment contract layer, called by both parent models. Its inputs are declared
factors and condition assignments, with a diagnostic scope only if needed to
preserve existing study messages. Do not construct a synthetic study or call a
study instance method on a spec. This is the extensibility seam for another
carrier of the same relationship; no validator registry, configurable strictness,
new DTO, or new base model is needed.

Keep `ExperimentStudyFactorModel`, `ExperimentConditionAssignmentModel`,
`ExperimentRunAllocationPlanModel`, and `ContractModel` as the canonical shapes.
Allocation already checks condition-map keys, embedded ids, compared-condition
coverage, uniqueness, and distinct run criteria. Descriptor source validation,
condition `required_bindings`, selection strata, and bounded factorial generation
own additional relationships; preserve those checks rather than replacing them
with membership validation or expanding this fix to rewrite their machinery.

Membership uses the factor map key, not the factor's display `name`, and exact
level-string equality. Do not normalize case, trim labels, or migrate these
`NonEmptyString` fields to `PortableIdentifier`. Check every assigned pair,
including factors not mentioned by a descriptor or stratum. A referenced factor
with no declared levels cannot satisfy membership. Conditions need not assign
every declared factor; unused factors and the no-allocation `target_run_count`
path retain their current meaning. Do not impose exhaustive combinations,
nonempty levels on unused factors, or new blocking-factor-kind rules here.

## Cross-cutting layers and security boundaries

| Layer and canonical incumbent | Required treatment |
| --- | --- |
| YAML/file ingress: `raes_contracts/experiment_spec.py` | Preserve the 64 KiB bound, safe loader, duplicate-key/alias rejection, mapping root, string keys and finite JSON values. Delegate membership to the model; no second parser or reference acquisition. |
| Portable JSON ingress: `raes_cli/_semantic_portable.py`, `raes_contracts/json_ingress.py` | Preserve bounded, duplicate-rejecting JSON and registered root-shape checks. Direct `ExperimentSpecModel.model_validate()` must enforce the same relationship without requiring loader context. |
| Contract/config shapes: `raes_contracts/_base.py`, `contracts/experiment_spec.py`, `contracts/experiment_study.py` | Preserve `extra="forbid"`, existing field types, allocation checks and posture conditionals. Parent validation checks only in-document declarations. No environment lookup, schema duplication, or global factor catalog. |
| Exceptions and error envelopes: `ExperimentSpecValidationError`, `_safe_validation_details()`, conformance `sanitized_failure_message()` | Raise ordinary contract `ValueError`; let Pydantic wrap it and the loader emit `contract-invalid`. Conformance retains its existing diagnostic code and the CLI retains `SemanticCommandResult`. Do not return raw `ValidationError`, `str(exc)` or rejected payloads through a new path. Parent-level failure locations may be coarse; do not defeat sanitization to improve wording. |
| Tooling and observability: `raes_mcp/tools/experiment_authoring.py`, `raes_conformance/conformance/validators.py`, `tools/example_library_checks.py` | Reuse `experiment_validate`, the registered `ExperimentSpecModel.model_validate` validator, and the library's `parse_experiment_spec` adapter. Preserve their existing error rendering. Reuse the loader logger; no new raw-input logs, warnings pipeline or audit stream. |
| Authentication, secrets, environment and host OS | This pure local relationship check introduces no endpoint, principal, permission, credential, secret resolution, environment binding, subprocess or network fetch. Existing MCP/CLI entry surfaces stay in place. ADR-094 secret references remain opaque. Factor/level strings must never become commands, process arguments, paths or provider locators. |
| Downstream admission and persistence | `raes.experiment_selection`, `raes_processor/trial_compiler`, and `raes_processor/trial_realization.py` consume experiment designs; declaration validity does not confer scenario admission, execution authority or realized provenance. `raes_contracts/associated_artifacts.py` retains carrier identity checks. No scheduler, backend, store, database migration, digest format or run/study lifecycle change belongs here. |

Use the existing sanitized boundaries even when an offending id or level
contains sensitive-looking text. Do not log model exception chains or add
attacker-controlled dictionary keys to outward error locations. `ContractModel`
is mutable and is not globally strict; this issue does not authorize redesigning
trusted in-process model handling or claiming that unchecked construction or
post-validation mutation has become safe.

## Published contract, documentation and verification guardrails

Publish the authoring membership rule as an error-level `x-raes-invariants`
entry through `contracts/schema_invariants.py::_add_raes_invariant`, naming its
real validator and root input. Ordinary JSON Schema cannot compare arbitrary
instance factor declarations with condition assignments. Do not encode dynamic
level enums in the schema or claim that a schema-only validator enforces the
relationship. The existing conformance model registry already supplies the
executable semantic gate.

Under ADR-009 and ADR-061, `contracts/schemas/` is the normative authority;
`contracts/bundle.py::schema_bundle()`, `tools/generate_contract_schemas.py`, and
`tools/check_generated_schemas.py` provide generation and parity. The current
publication manifest is v2: its entries live in
`contracts/schema-publication/entries/`. A changed authoring schema needs matching
`content_hash` and `last_change` in `experiment-authoring-input-v1.json`, checked
by `tools/check_schema_publication.py`. Its present stability is `draft`; do not
invent a v2 contract or alter unrelated schemas merely to add this invariant.

Update `examples/README.md` and the `two-condition-study-design` limits in
`examples/library/catalog.yaml` only when behavior ships. Replace their #1520
unchecked-membership limitation while preserving the unresolved-task and
descriptive-parameter limits. Keep the authoring description in
`specs/formal/experiment-core/README.md` consistent. ADR-094 does not explicitly
waive declaration integrity, so this recommendation needs no accepted-ADR edit.
If the chosen disposition changes ADR meaning, follow ADR-059's recorded
amendment or supersession rules, including its pin; never silently edit ADR-094.

Behavioral evidence must isolate undeclared factor and undeclared level cases
under both omitted/default and explicit `descriptive`, without descriptors or
strata. Include an extra unjoined invalid pair in an otherwise valid
`explicit-required` spec. Reuse `test_experiment_authoring.py`,
`test_experiment_bindings.py`, `test_experiment_selection.py`, the archival cases
in `test_runtime_contracts.py`, and the experiment-core conformance fixtures.
Show direct-model, parser, MCP and conformance agreement, with sensitive sentinel
values absent from outward diagnostics. Preserve positive evidence for the
shipped sweep, scaffolds/library template, valid subset assignments, factorial
generation and simple no-allocation run plans. Reuse existing coverage rather
than multiplying equivalent tests or running whole suites locally.

Workflow authority remains `.ground-control.yaml`, `.gc/plan-rules.md`,
`tools/check_repo_policy.py`, and the existing hygiene/pre-push hooks. This is a
requirement-free issue: do not invent a requirement UID to satisfy tooling.
Use targeted local cases or `verify-fast-feedback`; CI owns full verification,
integration, fuzz, completion and policy suites. No implementation plan,
runtime changes, tests, fixtures, publication records or shipped-support claims
are added by this preflight.
