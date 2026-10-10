# RAES Examples

This directory contains non-normative worked examples, templates, and reusable
patterns for authoring agentic environments with RAES SDL. They are useful for
reading, testing, and adapting current SDL behavior. They are not conformance
fixtures, schemas, deployment recipes, or backend guarantees.

The current corpus is strongest in cyber and infrastructure scenarios. Those
examples demonstrate the domain-neutral authored-scenario model; they do not
limit RAES to cyber or prove complete support for AI security, AI safety,
testing, research, evaluation, or any additional domain. Future application
areas extend through their own examples, vocabularies, profiles, assets,
backends, and evidence requirements.

## Current Corpus

| File | Best use | Current coverage | Limits |
|------|----------|------------------|--------|
| [`scenarios/hospital-ransomware-surgery-day.sdl.yaml`](scenarios/hospital-ransomware-surgery-day.sdl.yaml) | Large enterprise and clinical operations scenario | Disk-backed example test; complex example checks for objectives, agents, relationships, content, stories, conditions, direct refs | Does not deploy a hospital range or prove clinical exercise adequacy |
| [`scenarios/satcom-release-poisoning.sdl.yaml`](scenarios/satcom-release-poisoning.sdl.yaml) | Supply-chain, release, tenant, and rollback scenario | Disk-backed example test; complex example checks for objectives, agents, relationships, content, stories, conditions, workflows, enum-backed variables | Does not implement a CI/CD backend or production release system |
| [`scenarios/port-authority-surge-response.sdl.yaml`](scenarios/port-authority-surge-response.sdl.yaml) | IT/OT, customs, yard operations, and recovery scenario | Disk-backed example test; complex example checks for objectives, agents, relationships, content, stories, conditions, workflows, direct refs | Does not implement OT control, safety validation, or port operations |
| [`scenarios/techvault.sdl.yaml`](scenarios/techvault.sdl.yaml) | Runtime inventory and image provenance parity example | Disk-backed example test | Does not provide a deployable TechVault application or image build pipeline |
| [`scenarios/enterprise-participant-evidence-loop.sdl.yaml`](scenarios/enterprise-participant-evidence-loop.sdl.yaml) | Reference scenario for a generic enterprise participant/evidence loop | Disk-backed example test; focused processor compile check for participant behaviors, action contracts, observation boundaries, Wazuh evidence, policy provenance, and boundary evidence surfaces | Does not prove a concrete coding-agent runner, APTL/libvirt realization, TechVault coverage, or broad benchmark capability |
| [`scenarios/initial-service-state.sdl.yaml`](scenarios/initial-service-state.sdl.yaml) | Provider-neutral service-owned initial content | Disk-backed semantic validation of exact service binding, operation requirements, readback evidence, and participant projection | No current backend claims the `service-content-v1` materialization profile |
| [`scenarios/techvault-bounded-native.sdl.yaml`](scenarios/techvault-bounded-native.sdl.yaml) | Bounded TechVault libvirt VM/network substrate with explicit resources and network policy | Native driver exactness/readback tests and opt-in real-libvirt cleanup certification | Deliberately excludes guest images, placements, services, ACLs, readiness, applications, and SOC claims |
| [`scenarios/cross-backend-minimal.sdl.yaml`](scenarios/cross-backend-minimal.sdl.yaml) | Smallest scenario resolving inside more than one provisioning backend's realization envelope | Hermetic admission and apply on the reference in-process and recording-libvirt configurations, with resource correspondence and different bound substrate disclosures asserted | Does not exercise an OCI runtime or live libvirt/QEMU daemon and makes no infrastructure-equivalence or fidelity claim |
| [`scenarios/reconciliation-demo-v1.sdl.yaml`](scenarios/reconciliation-demo-v1.sdl.yaml) | Baseline version of the reconciliation demonstration pair | Planner reconciliation across scenario versions, exercised end to end through `raes processor reconcile` | Plans only; the projected snapshot is assumed state, never backend readback or proof of realization |
| [`scenarios/reconciliation-demo-v2.sdl.yaml`](scenarios/reconciliation-demo-v2.sdl.yaml) | Modified version that creates, updates, deletes, and leaves resources unchanged in one plan | Exact `create`/`update`/`delete`/`unchanged` outcomes across provisioning, orchestration, and evaluation | Same limits as the baseline; the pair demonstrates planner behavior, not a deployable environment |

The corpus tests are in
[`../implementations/python/tests/test_scenarios.py`](../implementations/python/tests/test_scenarios.py),
with the focused cross-backend checks in
[`../implementations/python/tests/test_cross_backend_minimal_scenario.py`](../implementations/python/tests/test_cross_backend_minimal_scenario.py)
and the reconciliation-pair checks in
[`../implementations/python/tests/test_reconciliation_demonstration.py`](../implementations/python/tests/test_reconciliation_demonstration.py).

## Reconciliation Demonstration

The `reconciliation-demo-v1` / `reconciliation-demo-v2` pair makes the
processor's reconciliation behavior directly observable. From the repository
root:

```shell
uv run --project implementations/python --frozen raes processor reconcile \
  examples/scenarios/reconciliation-demo-v1.sdl.yaml \
  examples/scenarios/reconciliation-demo-v2.sdl.yaml \
  --format json
```

The command plans v1 against the reference dry-run manifest, projects that
plan into a snapshot, plans v2 against the snapshot, and prints every
resulting action. Against the baseline's planned state, v2 creates
`provision.node.cache`, updates `provision.node.database`, deletes
`provision.node.retired`, and leaves the rest unchanged.
`evaluation.condition.database.health` also updates even though its own
payload is unchanged, because it refresh-depends on the database node -- the
case a payload comparison gets wrong.

Both files are import-free and declare nothing that regenerates per run or per
instantiation, so the demonstration is offline and deterministic. The projected
snapshot is synthetic assumed state: it is not backend readback, a durable
checkpoint, or evidence that anything was realized, and the command applies,
provisions, and starts nothing. The report summarizes resource identity and
dependencies and deliberately omits resource payloads, which can carry authored
credentials and content.

## Template And Pattern Library

The AUT-806 library is indexed by
[`library/catalog.yaml`](library/catalog.yaml). It is a versioned,
machine-readable catalog for the current non-normative authoring library.

| Surface | Templates | Pattern |
|---------|-----------|---------|
| Scenario | [`library/templates/scenario/minimal-validated-scenario.yaml`](library/templates/scenario/minimal-validated-scenario.yaml), [`library/templates/scenario/segmented-network-scenario.yaml`](library/templates/scenario/segmented-network-scenario.yaml), [`library/templates/scenario/parameterized-scenario.yaml`](library/templates/scenario/parameterized-scenario.yaml) | [`library/patterns/scenario-reference-integrity.yaml`](library/patterns/scenario-reference-integrity.yaml) |
| Workflow | [`library/templates/workflow/parallel-objective-workflow.yaml`](library/templates/workflow/parallel-objective-workflow.yaml) | [`library/patterns/workflow-explicit-control-graph.yaml`](library/patterns/workflow-explicit-control-graph.yaml) |
| Participant behavior | [`library/templates/participant_behavior/action-contract-observation-boundary.yaml`](library/templates/participant_behavior/action-contract-observation-boundary.yaml) | [`library/patterns/participant-behavior-contract-binding.yaml`](library/patterns/participant-behavior-contract-binding.yaml) |
| Task | [`library/templates/task/single-objective-task.yaml`](library/templates/task/single-objective-task.yaml) | [`library/patterns/task-as-objective-contract.yaml`](library/patterns/task-as-objective-contract.yaml) |
| Run | [`library/templates/run/timed-run-control.yaml`](library/templates/run/timed-run-control.yaml), [`library/templates/run/seeded-run-plan.yaml`](library/templates/run/seeded-run-plan.yaml) | [`library/patterns/run-window-with-evidence.yaml`](library/patterns/run-window-with-evidence.yaml) |
| Study | [`library/templates/study/observational-study-protocol.yaml`](library/templates/study/observational-study-protocol.yaml), [`library/templates/study/two-condition-study-design.yaml`](library/templates/study/two-condition-study-design.yaml) | [`library/patterns/observable-study-conditions.yaml`](library/patterns/observable-study-conditions.yaml) |

Each template has metadata, a `validation` list of commands with their
expected results, and a complete `body`. Most bodies are current SDL; the
`seeded-run-plan` and `two-condition-study-design` bodies are
`experiment-authoring-input-v1` documents. The
`tools/check_example_library.py` policy gate validates catalog shape, stable
IDs, referenced paths, AUT-806 requirement references, and entry metadata. It
checks every SDL template body and validated worked example with the SDL
parser and semantic validator, and every experiment template body with the
experiment authoring-input loader. It also checks that each template has a
non-empty `validation` list whose entries have non-empty `command` and
`expected` strings. The gate does not run those commands.

### Catalog entry metadata

Every `worked_examples`, `templates`, and `patterns` entry in the catalog
records `validation_status`, `intended_user`, and `limits`. SDL entries also
record `sdl_sections`, and a template whose body is not SDL records
`contract`. The policy gate rejects an entry that omits a field or breaks
these rules.

| Field | Allowed values | What the gate checks |
|-------|----------------|----------------------|
| `contract` | `sdl-yaml/v1`, the default when absent, or `experiment-authoring-input-v1` for a run or study template | The value is allowed for the entry. It selects how a `validated` body is checked and which `intended_user` the entry names. |
| `validation_status` | `validated` or `guidance` | For `validated`, the gate checks the template body or worked-example file against its contract. SDL goes through the SDL parser and semantic validator, on the worked-example file or on the template body as PyYAML loads it from the template file, and fails on any error or advisory they report. `experiment-authoring-input-v1` goes through the experiment authoring-input loader and fails on any error it reports for the body as PyYAML `safe_load` reads it from the template file. That read keeps the last of duplicate keys and expands scalar aliases and `<<` merge keys, which the loader rejects in a saved copy. A `guidance` file is not checked against a contract. Templates must be `validated`; patterns must be `guidance`. |
| `sdl_sections` | Top-level section names from [`../specs/sdl/sections.md`](../specs/sdl/sections.md), such as `nodes` or `workflows` | Present for SDL entries and absent otherwise. Each name is a current SDL section, not a metadata or composition field such as `name` or `imports`. For a `validated` entry, each listed section is present in the validated SDL. |
| `intended_user` | `sdl-author` for SDL entries, `experiment-author` for `experiment-authoring-input-v1` templates | The value matches the entry's contract. |
| `limits` | One or more short statements of what the entry does not show | The list is present and not empty. Reviewers check the wording. |

`sdl_sections` names the sections that an entry shows for its surface, so a
large worked example lists only some of the sections it uses. `validated`
means that the contract's validator accepts the file or template body. It does
not mean that a backend can realize the scenario, that anything has run, or
that references to other artifacts resolve. A `guidance` entry is reading
material, such as a prose pattern or a test module, and the gate does not
check it against a contract.

### Scenario templates

Each scenario template claims only that current SDL validation accepts its
body with no advisories.

| Template | Shows | Does not claim |
|----------|-------|----------------|
| [`minimal-validated-scenario`](library/templates/scenario/minimal-validated-scenario.yaml) | One host service, one participant, an objective whose success is an assertion over an observed proposition, and a workflow with one objective step | That a backend can realize the scenario |
| [`segmented-network-scenario`](library/templates/scenario/segmented-network-scenario.yaml) | Two switched segments, a linked host with a fixed address on each, access rules that admit only HTTPS from the user segment into the server segment, and a service feature | That a backend enforces the access rules or installs the feature |
| [`parameterized-scenario`](library/templates/scenario/parameterized-scenario.yaml) | Host operating system, size, instance count, and service port taken from declared variables with defaults and an allowed-values list | That the scenario instantiates with every supplied value; the gate does not instantiate it |

To check a template as shipped, run the catalog command in
[Validate The Examples](#validate-the-examples). To check an adapted copy, save
its `body` as `my-scenario.sdl.yaml` in the repository root and run this
command from there:

```shell
uv run --project implementations/python --frozen raes semantic validate my-scenario.sdl.yaml
```

The command prints `validate: success` and exits `0` when the SDL parser and
semantic validator accept the file. It does not report semantic-validator
advisories, such as a compute node without `resources`. The `parse_sdl_file`
check in [Validate The Examples](#validate-the-examples) asserts that there
are none.

### Task, run, and study entries

The task, run, and study surfaces keep these parts separate:

- **SDL:** the `single-objective-task`, `timed-run-control`, and
  `observational-study-protocol` templates and the worked examples. SDL has no
  `tasks`, `runs`, or `studies` sections, so these use objectives, workflows,
  timing, and observable conditions.
- **Experiment authoring input:** the `seeded-run-plan` and
  `two-condition-study-design` templates. Each body is an
  `experiment-authoring-input-v1` document, the pre-run design that binds a
  task to a run plan
  ([ADR-074](../docs/decisions/adrs/adr-074-experiment-authoring-input-contract-boundary.md)).
  `seeded-run-plan` declares the run count, seed, and episode controls for one
  task. `two-condition-study-design` declares a treatment factor, two compared
  conditions, and the runs per condition.
- **Guidance:** the task, run, and study patterns, which are prose.
- **Outside current support:**
  - An experiment task template. An experiment task is an
    `experiment-task-v1` document that a run plan names in `task_ref`. The
    repository has no task loader, `raes semantic validate` does not accept
    the `experiment-task-v1` contract, and every task needs an artifact
    reference with a checksum, size, and creation time that a reusable
    template would have to invent.
  - Resolving `task_ref`, and checking condition factor levels that no
    binding descriptor or stratified selection stratum joins. The experiment
    authoring-input loader does neither. It does check joined levels against
    the declared factors and the condition assignment: binding descriptors
    under `binding_semantics: explicit-required`
    ([ADR-094](../docs/decisions/adrs/adr-094-authoritative-cross-plane-experiment-bindings.md))
    and stratified selection strata. The shipped `two-condition-study-design`
    body joins none, so the loader does not check its levels.
  - Admitting, scheduling, or running a plan, and the `experiment-run-v1` and
    `experiment-study-v1` records that describe actual executions and
    analyses.

To check an adapted copy of an experiment template, save its `body` as
`my-experiment.exp.yaml` in the repository root and run this command from
there:

```shell
uv run --project implementations/python --frozen python -c "import sys; from pathlib import Path; from raes_contracts.experiment_spec import load_experiment_spec; print(load_experiment_spec(Path(sys.argv[1])).spec_id)" my-experiment.exp.yaml
```

The command prints the document's `spec_id` and exits `0`. An invalid
document raises `ExperimentSpecValidationError` and exits `1`.

## Validate The Examples

From the Python implementation directory:

```shell
cd implementations/python
uv run --extra dev pytest tests/test_scenarios.py -q
```

For one file, use the parser boundary directly:

```python
from pathlib import Path

from raes import parse_sdl_file

scenario = parse_sdl_file(
    Path("../../examples/scenarios/port-authority-surge-response.sdl.yaml")
)
assert scenario.advisories == []
```

Validate the template and pattern catalog from the repository root:

```shell
uv run --project implementations/python --frozen python tools/check_example_library.py
```

## How To Use These Files

Use the examples as references for current SDL shape:

- section structure
- stable identifiers and references
- variables
- workflows
- objectives
- entities and agents
- content and evidence-like scenario material
- runtime inventory fields where present

Check the section reference and limitations before adapting a file:

- [`../docs/explain/sdl/sections.md`](../docs/explain/sdl/sections.md)
- [`../docs/explain/sdl/validation.md`](../docs/explain/sdl/validation.md)
- [`../docs/explain/sdl/limitations.md`](../docs/explain/sdl/limitations.md)
- [`../docs/explain/sdl/testing.md`](../docs/explain/sdl/testing.md)

## Template Boundary

No template in this directory contains incomplete SDL. Files under
`examples/scenarios/` are positive SDL examples and must load successfully from
disk. Files under `examples/library/templates/` are reusable authoring
templates with complete SDL or `experiment-authoring-input-v1` bodies; they are
validated by the example-library policy gate. An SDL template body may use
`${name}` variable placeholders, as `parameterized-scenario` does. A
placeholder's `name` follows the variable-name grammar in
[`../specs/sdl/variables-and-instantiation.md`](../specs/sdl/variables-and-instantiation.md)
(lowercase letters, digits, `-`, and `_`), and the gate rejects a body whose
placeholder names a variable that the body does not declare under `variables`.
Text such as `${Web OS}` or `${CUSTOMER_NAME}` is not a placeholder: it stays
literal text, and the gate does not report it as an undeclared variable.

Do not add invalid or incomplete SDL files under `examples/scenarios/`.
Negative-path examples belong in focused parser, model, validator, contract, or
conformance tests.

The task, run, and study SDL templates use current SDL wrappers rather than
first-class `tasks`, `runs`, or `studies` sections. They show how to express
those concepts with objectives, workflows, timing, observable conditions, and
evidence-like references that the current implementation can validate. Graded
scoring and reward are experiment/evaluator-plane concerns (experiment-*
contracts) per ADR-073, not SDL surfaces. The run and study experiment
templates are pre-run designs; see
[Task, run, and study entries](#task-run-and-study-entries).
