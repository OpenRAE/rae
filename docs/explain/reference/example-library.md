# Example-library reference

This page describes catalogue metadata, template contracts, and loader behavior.
Use the [example catalogue](../../../examples/README.md) to select material.
Use the [quickstart](../../public/quickstart.md) for guided learning.
The source owners are `tools/check_example_library.py`, `tools/example_library_checks.py`, and `raes_contracts.experiment_spec`.

## Catalog entry metadata

Every worked example, template, and pattern records `validation_status`, `intended_user`, and `limits`.
SDL entries also record `sdl_sections`.
Templates with a non-SDL body record `contract`.
The gate rejects missing or incompatible fields.

| Field | Values and checks |
| --- | --- |
| `contract` | `sdl-yaml/v1` is the default. Run and study templates can instead use `experiment-authoring-input-v1`. The contract selects the validator and intended user. |
| `validation_status` | `validated` or `guidance`. Templates must be validated; patterns must be guidance. |
| `sdl_sections` | Current top-level SDL section names from the [section reference](../../../specs/sdl/sections.md). Metadata and composition fields such as `name` and `imports` are excluded. Each listed section must occur in a validated entry. |
| `intended_user` | `sdl-author` for SDL; `experiment-author` for experiment input templates. |
| `limits` | A non-empty list of limitations. Reviewers check the meaning. |

For a validated SDL entry, the gate parses the worked-example file or template body and checks semantic errors and advisories.
The template loader uses `sdl-yaml/v1` source admission.
It rejects duplicate keys, merge keys, and explicit tags in the template file.
For experiment templates, the experiment loader checks the body and rejects reported errors.
Its YAML reader rejects duplicate keys, aliases, and `<<` merge keys.
A guidance entry is not checked against a contract.

`sdl_sections` records the sections an entry demonstrates.
A large example can list only some of its sections.
Contract acceptance establishes neither backend realizability nor execution.
It does not establish resolution of references to external artifacts.

Each template has metadata, a complete `body`, and a non-empty `validation` list.
Each validation entry has non-empty `command` and `expected` strings.
The gate checks these strings for shape; it does not execute the commands.
It also checks stable IDs, referenced paths, AUT-806 references, and entry metadata.
See the [validation procedure](../../../examples/README.md#validate-the-examples).

## Validate an adapted template

Use the frozen [checkout environment](../../../CONTRIBUTING.md#set-up-the-repository).
For an SDL template, save its `body` as `my-scenario.sdl.yaml` at the repository root.
Run from that directory:

```shell
uv run --project implementations/python --frozen raes semantic validate my-scenario.sdl.yaml
```

The command prints `validate: success` and exits with code `0` on acceptance.
It does not report semantic-validator advisories, such as a compute node without `resources`.
Use the [file-parser check](../../../examples/README.md#validate-the-examples) to examine advisories too.

For an experiment template, save its `body` as `my-experiment.exp.yaml` at the repository root.
Run:

```shell
uv run --project implementations/python --frozen python -c "import sys; from pathlib import Path; from raes_contracts.experiment_spec import load_experiment_spec; print(load_experiment_spec(Path(sys.argv[1])).spec_id)" my-experiment.exp.yaml
```

The command prints the document's `spec_id` and exits with code `0`.
An invalid document raises `ExperimentSpecValidationError` and exits with code `1`.

## Task, run, and study entries

SDL has no `tasks`, `runs`, or `studies` sections.
The `single-objective-task`, `timed-run-control`, and `observational-study-protocol` templates use objectives, workflows, timing, and observable conditions.
The task, run, and study patterns give authoring guidance.
Graded scoring and reward belong to the experiment/evaluator plane under [ADR-073](../../decisions/adrs/adr-073-scoring-reward-language-scope.md).

`seeded-run-plan` and `two-condition-study-design` contain `experiment-authoring-input-v1` bodies.
This pre-run contract binds a task reference to a run plan under [ADR-074](../../decisions/adrs/adr-074-experiment-authoring-input-contract-boundary.md).
The seeded plan declares run count, seed, and episode controls for one task.
The study design declares a treatment factor, two conditions, and runs per condition.

In both `descriptive` and `explicit-required` modes, each condition names factors and levels declared in that experiment.
Authors supply these declarations; RAE supplies no domain catalogue.
Membership validation does not resolve an ontology or prove that a treatment was applied.
Descriptive parameters do not apply configuration.
Explicit bindings retain the additional source and target checks of [ADR-094](../../decisions/adrs/adr-094-authoritative-cross-plane-experiment-bindings.md).

An authored JSON task can be checked with:

```shell
raes semantic validate --contract experiment-task-v1 my-task.json
```

This checks the task contract, including protocol and artifact fields.
It fetches no scenario and verifies no artifact bytes.
No task template is shipped: the author's protocol artifact needs its own checksum, byte size, and creation time.
The catalogue records this limit.

The loader does not acquire the task named by `task_ref`.
Without a supplied task, that reference remains unresolved.
To check against your own task and experiment files, load both explicitly:

```python
from pathlib import Path
from raes_contracts.contracts import ExperimentTaskModel
from raes_contracts.experiment_spec import load_experiment_spec

task = ExperimentTaskModel.model_validate_json(Path("my-task.json").read_text())
plan = load_experiment_spec(Path("my-experiment.exp.yaml"), task=task)
```

The task ID and any version in `task_ref` must match.
A mismatch raises `ExperimentSpecValidationError` with code `task-reference-mismatch`.
`parse_experiment_spec(text, task=task)` performs the same check for YAML text.
Neither function fetches task references or checks scenario or artifact content.

These templates do not admit, schedule, or run a plan.
They do not produce `experiment-run-v1` or `experiment-study-v1` execution and analysis records.

## Template boundary

No template contains incomplete SDL.
Files in `examples/scenarios/` are positive examples that must load from disk.
Templates contain complete SDL or experiment-input bodies.
Negative examples belong in focused parser, model, validator, contract, or conformance tests.

An SDL body can use `${name}` placeholders for declared variables.
Names follow the [variable grammar](../../../specs/sdl/variables-and-instantiation.md): lowercase letters, digits, `-`, and `_`.
The gate rejects placeholders whose names are absent from the body's `variables` section.
`${Web OS}` and `${CUSTOMER_NAME}` remain literal text.
They do not match the placeholder grammar and are not reported as undeclared variables.

## Control-context factor target

An ADR-094 participant target can declare a `control_context` domain:

```yaml
context.briefing:
  target_id: context.briefing
  value_type: string
  allowed_value_kinds: [literal]
  sensitivity: restricted
  control_context:
    slot_id: briefing
    references:
      control_context_assets.alpha.shared:
        asset_id: privacy-instruction
        asset_version: one
        asset_digest: sha256:83c7094c1ac208ad0b6cbe65560801b2512b93edf919b3b4e1debf6ae6eada8a
```

The participant factor selects the literal `control_context_assets.alpha.shared`.
The participant and slot must have no competing SDL selection.
The selected manifest owns the target and pins this domain.
The existing owner-validator hook accepts a trusted `SDLControlContextConfigurationValidator`.
The compiler binds it to each concrete trial scenario before sealing the configuration.
The result retains a typed selection and exact asset pin for the run producer.
ACT-620 consumer checks still apply.
The [control-context contract](../../../specs/sdl/participant-control-context.md) owns the rules.

## Participant tool references

| Concern | Authored field |
| --- | --- |
| Tool | `tool_ref` names one scenario `content` identity. |
| Affordance | `behavior_specifications.<spec>.tool_affordances.<id>` |
| Invocation interface | The bound action contract's `arguments`, reached through the compiled action address. The affordance copies none of it. |
| Access interface and channel | `agents.<name>.interactive_access.<id>` names a compute-node `target_ref`, optional `account_ref`, and `channel`. The channel is `ssh`, `rdp`, or a typed profile binding admitted by the target under ADR-120. |
| Scope and availability | The specification's participant selectors and `authority_scope_refs`, the participant's actions and boundaries, and the action contract's preconditions and argument domains. |

A module-local `tool_ref` binds the same declaration in every import.
This applies to bare names such as `scanner-package` and section-qualified names such as `content.scanner-package`.
If two declarations share that bare name, composition fails with an `is ambiguous` diagnostic.
Use `content.<name>` or rename the other declaration.
A reference absent from the module resolves against the complete composed scenario.

Stateful-resource `ordering_dependencies` and `refresh_dependencies` have separate checks.
A name shared by a generated artifact and persistent volume is ambiguous.
The diagnostic contains `dependency reference ... is ambiguous; use one of`.
Behavior `authority_scope_refs` also reject ambiguous local names before rewriting, with the standalone diagnostic.
Use a qualified name such as `nodes.web` when another declaration shares the bare name.
Other reference families are tracked in [issue #1575](https://github.com/OpenRAE/rae/issues/1575).
Reference-typed action arguments are neither resolved nor namespaced on import; see [issue #1574](https://github.com/OpenRAE/rae/issues/1574).

Authored tool identities and action/observation relations cannot contain `__private` segments, including parameter-supplied values.
Export the declaration and use its public import address.
Generated private references inside a module remain valid through composition and instantiation.
The [composition decision](../../decisions/issue-298-tool-authoring.md) and [participant reference](../../../specs/formal/participant-semantics/README.md) give the design and semantics.

## Temporal profile support

| Authoring concern | Existing owner |
| --- | --- |
| Role and participant scope | `entities`, `agents`, and the behavior specification |
| Activity, application, and protocol | Action contract, target service, and selected implementation |
| Fixed cadence and ordering | Autonomous v1 |
| Work/pause windows, weighted actions, intervals, dependencies, retries, cooldowns | Autonomous v2 |
| Explicit resource budgets and fairness | Autonomous v3, with v2 activity semantics retained |
| Deadline event or continuous dwell | Action temporal contract and shared clock/constraint |
| Reusable profiles | Namespaced module imports and typed parameters |

Whole-field integer parameters such as `${name}` support these bounds:

| Field | Bounds |
| --- | --- |
| Attempt and occurrence limits | 1–1,000,000 |
| In-flight bounds | 1–1,024 |
| Timing ticks, weights, and burst size | 1–1,000,000,000 |
| Retry counts | 0–1,024 |
| Cooldown ticks | 0–1,000,000,000 |

Cross-field limits and stepped-clock reachability are checked after binding.
Booleans, fractions, and interpolated strings are not integers.
Each import binds its `parameters` mapping separately.
An omitted required value fails import expansion.

The conformance probe is
`raes_conformance.conformance.participant_temporal_probes.participant_temporal_scenario_case`.
It accepts a parsed scenario on a disposable reference target.
For dwell, pass `clock_advances=(("time.clock.scenario-clock", 10),)`.
The probe checks admission, execution, assessments, and durable-history consistency.
It stops its local clock driver before returning.
Unconfirmed shutdown fails the case.
The caller owns native setup and cleanup.
Do not clean up native resources while the report identifies residual work.
Generic registration probes cannot reconstruct a scenario from manifest digests.
See the [temporal-profile examples](../../../examples/scenarios/temporal-profiles/README.md) for evidence limits.
