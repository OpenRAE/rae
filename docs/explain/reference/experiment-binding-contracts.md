# Experiment binding contracts

These contracts bind experiment factors to three authority planes.
They state intent and validation results.
They do not change a runtime.

## Authority planes

| Plane | Canonical owner | Target |
|-------|-----------------|--------|
| `scenario` | Composed SDL scenario family | Declared variation point and its owner target |
| `participant-implementation` | Selected participant implementation manifest | Manifest `configuration_registry` target |
| `apparatus` | Selected processor or backend manifest | Manifest `configuration_registry` target |

Each descriptor names its source factor, level, and condition.
Every condition factor and level must belong to that experiment's declarations,
in both `descriptive` and `explicit-required` modes.
Authors or their tools choose those declarations; RAE supplies no domain catalog.
This local validation does not resolve an ontology or prove treatment execution.
`ExperimentSpecModel` also checks each descriptor's source joins in `explicit-required` mode.
That mode rejects legacy `required_parameters`.
Those parameters remain descriptive data in other modes.

A target belongs to one plane.
The same name in another plane grants no authority.
A missing participant target cannot become a scenario or backend target.

## Target registries

An owner registry declares canonical target ids and bounded aliases.
It defines exact scalar types and allowed value kinds.
It also defines sensitivity, defaults, and the contract and validator versions.

Aliases are input spellings, not identities.
Admission resolves them before it builds a result or digest.
Two inputs for one canonical target fail.
This rule also rejects equal duplicate values.

A manifest can add targets or validator versions through its registry.
A new authority plane needs a versioned contract change.

## Participant configuration realization

`realize_participant_configuration()` accepts a selected manifest and overrides.
It resolves the whole list and applies defaults.
It requires every target without a default.
It enforces strict types.
A trusted `ParticipantConfigurationValidator` can check the complete configuration.
Failure returns no partial result.

The result sorts values by canonical target id.
Each value retains its default or override origin.
`participant-configuration-result-v1` records the manifest, validator, and normalized values.
Its `canonical_contract_digest()` uses RFC 8785/JCS.
Alias spelling and input order do not affect that digest.

## Participant bindings on trial entries

Each entry carries the participant descriptors for its condition.
This applies to factorial designs and explicit condition descriptors.
Participant bindings need no scenario selection-policy reference.
Two conditions can differ only in participant configuration.
Their `required_bindings` record that difference without invented `required_refs`.

Admission checks each target against the selected manifest.
The compiler realizes the complete configuration once, before entry sealing.
Entry and plan digests cover the result.
One-entry realization passes the sealed result to the run producer.
Run validation compares the archived digest with the admitted result.

```mermaid
flowchart LR
    Author[Experiment author] -->|Condition descriptors| Admission[Target admission]
    Manifests[(Selected manifest inputs)] -->|Pinned identity and target registry| Admission
    Admission -->|Admitted participant overrides| Configuration[Complete configuration realization]
    Manifests -->|Defaults and owner validator| Configuration
    Configuration -->|Normalized result and digest| Plan[(Sealed trial plan)]
    Plan -->|Entry bindings and configurations| Producer[Run producer]
    Producer -->|Binding and selection digests| Run[(Experiment run)]
    Plan -->|Admitted digest| Validation[Run validation]
    Run -->|Archived digest| Validation
```

Author input crosses the manifest-owner boundary at target admission.
Unknown targets or wrong owners produce no plan.
Missing required values or owner rejection also produce no plan.
Compiler errors exclude values and owner exception text.
Secret references remain references throughout this flow.
A matching digest proves configuration identity only.
The run producer must still prove execution.

## Scalar and secret posture

The scalar types are string, integer, number, Boolean, and null.
Values must retain their types.
Boolean does not satisfy integer.
Numeric strings remain strings.
NaN and infinity are invalid.

A secret reference is distinct from a string literal.
Portable artifacts carry only its non-sensitive reference identity.
They have no resolved-secret field.
They do not resolve environment variables, files, commands, or private locators.
The digest covers the reference identity, never resolved secret material.

## Lifecycle integration

- `experiment-authoring-input-v1` carries descriptors and checks their source joins.
- The public SDL authority resolves scenario targets.
- Each selected manifest owns its target registry.
- `participant-configuration-result-v1` holds the complete normalized result.
- `experiment-run-v1` can archive the descriptor, origin, and configuration digest.

## Factorial designs and randomized allocation

An experiment can declare `factorial_design` with the `factorial-bindings-v1` profile.
It names `factor_ids`, a `condition_bound`, and `target_runs_per_condition`.
Each `level_bindings[factor_id][level_id]` holds typed target/value/owner templates.
Two scenario path levels and two participant temperature levels produce four conditions.
Two replicates produce eight entries.
A factor can affect both planes.
Unnamed factors are not crossed.

The loader generates allocation, condition `required_bindings`, and descriptors.
It rejects supplied records that differ from the generated result.
It retains the design intent when serialized.
Scenario targets must cover every family variation point.
Their outcomes must be scalar literals.
Factorial generation cannot also declare selection policies.

Participant targets resolve against selected manifests.
The complete results include defaults and digests.
Normalization cannot change declared binding values.
Missing targets, alias collisions, or incomplete results fail admission.
Distinct conditions must also have distinct effects after owner resolution.
Comparison includes all effective defaults across the design's selected participants.
Equal values compare the same, regardless of default or override origin.
The one-entry result carries admitted configurations with the processor plans.

Select the order through the run plan:

```yaml
allocation_policy:
  kind: randomized
  policy_id: treatment-order
  algorithm_profile: fisher-yates-allocation-v1
  stochastic_control_ref: allocation-control
```

The control needs `role: randomization` and an executable binding.
Use `blake3-xof-v1` / `random-stream-profile/v1` with a namespace and public seed.
Compilation seals the policy, order, and bounded plan-scope draws.
Dispatch and receipt checks use that same order.
Reconstruction checks the whole record.
A seed, free-text method, or blocking-factor list alone does not activate this behavior.

When input uses aliases, archive canonical admitted descriptors as study criteria.
Runs must preserve every admitted binding and configuration digest.
They must also preserve the selected manifest and allocation control.
Retain actual apparatus evidence and deviations for model/API or host drift.
Random order reduces confounding; it does not prove unchanged conditions.

See the [normative generation rules](../../../specs/formal/experiment-core/README.md#factorial-condition-generation-exp-719),
[allocation procedure](../../../specs/formal/scenario-variation-trial-realization/README.md#designed-compiler-and-allocation-profiles-exp-719),
and [architecture guardrails](../../decisions/issue-275-exp-719-treatment-controlled-variation-preflight.md).
