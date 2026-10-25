# Experiment Binding Contracts

Issue #903 publishes the portable contract surfaces that connect experiment
factors and conditions to scenario variation, participant implementation
configuration, and apparatus configuration. The contracts state intent and
validation results; they do not mutate a runtime.

## Authority planes

| Plane | Canonical owner | Target |
|-------|-----------------|--------|
| `scenario` | Composed SDL scenario family | Declared variation point and its owner target |
| `participant-implementation` | Selected participant implementation manifest | Manifest `configuration_registry` target |
| `apparatus` | Selected processor or backend manifest | Manifest `configuration_registry` target |

A descriptor carries its source factor, factor level, and condition. These
joins are validated by `ExperimentSpecModel` when
`binding_semantics: explicit-required` is selected. Legacy
`required_parameters` remain descriptive data and are rejected in that mode.

Targets never fall back across planes. A participant target that is absent
from the selected participant manifest does not become a scenario or backend
target because the same spelling exists elsewhere.

## Target registries

An owner registry declares canonical target ids, bounded aliases, exact scalar
types, admitted literal/secret-reference forms, sensitivity, optional defaults,
and the governing contract and validator version.

Aliases are input spellings only. Admission resolves aliases to canonical ids
before constructing a configuration or digest. Alias/canonical collisions and
two inputs that resolve to one target fail, including equal-value duplicates.

The extension seam is the owner registry: a manifest can add a target or a new
validator version without changing the cross-plane resolver. A new authority
plane is not an extension id; it requires a versioned contract change.

## Participant configuration realization

`realize_participant_configuration()` accepts a selected participant manifest
and an override list. It resolves the whole list, applies defaults, requires
missing values, enforces strict types, and optionally invokes a trusted
`ParticipantConfigurationValidator` over the complete configuration. It
returns no partial result.

The normalized entries are sorted by canonical target id and preserve whether
each value came from a default or override.
`participant-configuration-result-v1` records the selected manifest identity,
governed validator, normalized values, and a `canonical_contract_digest()`
RFC 8785/JCS digest. Alias spelling and input ordering do not affect that
digest.

## Scalar and secret posture

The scalar vocabulary is closed: string, integer, number, Boolean, and null.
Validation is non-coercing. Boolean does not satisfy integer, numeric strings
remain strings, and NaN or infinity is invalid.

A secret reference is structurally different from a string literal. Portable
artifacts carry only its non-sensitive reference identity. They contain no
resolved-secret field and do not resolve environment variables, files,
commands, provider objects, or private locators. The digest commits to the
reference identity, never to resolved secret material.

## Lifecycle integration

- `experiment-authoring-input-v1` carries explicit descriptors and validates
  their factor/condition provenance.
- Scenario admission delegates target resolution to the public SDL
  variation/instantiation authority.
- Participant, processor, and backend manifests publish their own target
  registries.
- `participant-configuration-result-v1` is the authoritative normalized
  participant configuration result.
- `experiment-run-v1` may archive the realized descriptor, its origin, and the
  configuration digest.

## Factorial designs and randomized allocation

An experiment can declare `factorial_design` with the
`factorial-bindings-v1` profile, explicit `factor_ids`, a `condition_bound`,
`target_runs_per_condition`, and `level_bindings[factor_id][level_id]`.
Each level holds one or more existing typed target/value/owner templates.
For example, two scenario path levels crossed with two participant temperature
levels produce four conditions; two replicates produce eight admitted entries.
A factor may affect targets in both planes. Unnamed factors are not crossed.

The authoring loader generates the existing allocation, condition
`required_bindings`, and binding descriptors. It rejects inconsistent supplied
materializations and retains the generation intent on serialization. Scenario
targets must cover every family variation point with scalar literal outcomes;
factorial generation cannot also declare selection policies. Participant
targets resolve against selected manifests and produce complete configuration
results with defaults and digests. Normalization cannot change the declared
binding values. Missing owner targets, alias collisions, incomplete
configurations, and operationally identical conditions fail admission.
Comparison includes complete effective defaults across the design's selected
participants and ignores whether an equal value came from a default or override.
The public one-entry realization result carries those admitted configurations
to the downstream participant owner alongside the processor plans.

Select executable order explicitly in the existing run plan:

```yaml
allocation_policy:
  kind: randomized
  policy_id: treatment-order
  algorithm_profile: fisher-yates-allocation-v1
  stochastic_control_ref: allocation-control
```

The referenced control needs `role: randomization` and an executable
`blake3-xof-v1` / `random-stream-profile/v1` binding with a namespace and public
seed. Compilation seals the policy, permutation, and bounded plan-scope draws;
dispatch and receipt validation consume that same order. Reconstruction checks
the whole record. A seed, free-text allocation method, or blocking-factor list
alone does not activate this behavior.

Archive canonical admitted descriptors as study matching criteria when input
aliases were used. Runs must preserve every admitted realized binding,
participant configuration digest, selected manifest, and allocation control.
Retain actual apparatus evidence and deviations for model/API or host drift:
random order mitigates confounding and does not certify unchanged conditions.

See the [normative generation rules](../../../specs/formal/experiment-core/README.md#factorial-condition-generation-exp-719),
[allocation procedure](../../../specs/formal/scenario-variation-trial-realization/README.md#designed-compiler-and-allocation-profiles-exp-719),
and [architecture guardrails](../../decisions/issue-275-exp-719-treatment-controlled-variation-preflight.md).
