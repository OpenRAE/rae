# RAES examples

Use this catalogue to select an authored example, template, or pattern.
For a guided first result, start with the [quickstart](../docs/public/quickstart.md).
Continue with the [first-scenario tutorial](../docs/public/tutorials/first-scenario.md) before selecting a larger example.

These files are non-normative authoring examples.
They are not conformance fixtures, deployment recipes, or backend guarantees.
The corpus mainly covers cyber and infrastructure scenarios.
This coverage does not limit the language to cyber or establish support for every research domain.
Other domains need their own examples, vocabularies, profiles, assets, backends, and evidence requirements.

## Current corpus

Each scenario below can be read with the RAES file parser.
Use the [validation procedure](#validate-the-examples) for local checks.
The support column names additional requirements or important limits.
Parsing does not install software, realize a topology, or execute a participant.

| Example | Purpose | Required support and limits | Reference or explanation |
| --- | --- | --- | --- |
| [Cross-project secret](scenarios/cloud-resources/cloud-secret-cross-project.sdl.yaml) | Describe identity, policy, metadata, and secret-version access across projects. | Local parser reports capacity advisories; no cloud access result. | [Cloud example notes](scenarios/cloud-resources/README.md) |
| [Hospital](scenarios/hospital-ransomware-surgery-day.sdl.yaml) | Read a large clinical recovery exercise. | Local parser; clinical adequacy and live realization are not established. | [SDL sections](../specs/sdl/sections.md) |
| [Satellite release](scenarios/satcom-release-poisoning.sdl.yaml) | Read supply-chain compromise, tenant isolation, and rollback declarations. | Local parser; no CI/CD or production release backend. | [Workflows](../specs/formal/workflows/README.md) |
| [Port authority](scenarios/port-authority-surge-response.sdl.yaml) | Read IT/OT operations and recovery declarations. | Local parser; no OT control or safety result. | [SDL sections](../specs/sdl/sections.md) |
| [Enterprise identity and tenancy](scenarios/enterprise-identity-tenancy.sdl.yaml) | Inspect an enterprise forest, carrier placement, and shared inference tenancy. | Local parser; native identity and inference services need a backend. | [Identity and tenancy](../specs/sdl/enterprise-deployment-tenancy.md) |
| [Participant evidence loop](scenarios/enterprise-participant-evidence-loop.sdl.yaml) | Follow a portal probe's action, observation, and evidence declarations. | Parser and processor checks; native runner and Wazuh evidence need a backend binding. | [Evidence-loop notes](scenarios/enterprise-participant-evidence-loop.README.md) |
| [Initial service state](scenarios/initial-service-state.sdl.yaml) | Describe service-owned initial content and readback requirements. | Local semantic checks; no current backend claims the `service-content-v1` materialization profile. | [Initial service state](../specs/sdl/initial-service-state.md) |
| [Cross-backend minimum](scenarios/cross-backend-minimal.sdl.yaml) | Supply a small common input for backend parity checks. | Local parser; live OCI or libvirt execution requires a separate backend. | [Backend ownership](../docs/public/backends.md) |
| [Reconciliation v1](scenarios/reconciliation-demo-v1.sdl.yaml) | Supply the baseline for a reconciliation plan. | Processor dry-run manifest; projected state is synthetic. | [Reconciliation demonstration](#reconciliation-demonstration) |
| [Reconciliation v2](scenarios/reconciliation-demo-v2.sdl.yaml) | Show create, update, delete, and unchanged plan actions. | Same dry-run support; no backend readback. | [Reconciliation demonstration](#reconciliation-demonstration) |
| [Guided web probe](scenarios/guided-web-probe.sdl.yaml) | Inspect the finished file from the scenario-plan guide. | Reference dry-run manifest reports `capture.offer-missing`; nothing is realized. | [Scenario-plan guide](../docs/public/sdl/validate-compile-plan.md) |
| [TechVault inventory](scenarios/techvault.sdl.yaml) | Inspect runtime inventory and image provenance declarations. | Local parser; no application or image build pipeline is supplied. | [Runtime inventory](../specs/sdl/runtime-inventory.md) |
| [TechVault operational](scenarios/techvault-operational.sdl.yaml) | Inspect steady-state service and network declarations. | Local parser; live startup requires a backend distribution. | [Backend ownership](../docs/public/backends.md) |
| [TechVault observability](scenarios/techvault-observability-core.sdl.yaml) | Inspect the OTEL core slice. | Local parser; no live startup or monitoring result. | [Backend ownership](../docs/public/backends.md) |
| [TechVault defensive minimum](scenarios/techvault-defensive-min.sdl.yaml) | Inspect Wazuh and OTEL declarations without the wider SOC. | Local parser; native services require a backend. | [Backend ownership](../docs/public/backends.md) |
| [TechVault enterprise web](scenarios/techvault-enterprise-web.sdl.yaml) | Inspect the enterprise web, Wazuh, and OTEL slice. | Local parser; no live application or detection result. | [Backend ownership](../docs/public/backends.md) |
| [TechVault attacker and target](scenarios/techvault-attacker-target.sdl.yaml) | Inspect Kali, capture, victim, Wazuh, and OTEL declarations. | Local parser; no participant or native execution result. | [Backend ownership](../docs/public/backends.md) |
| [TechVault bounded native](scenarios/techvault-bounded-native.sdl.yaml) | Retain the bounded VM/network substrate used by RAES 7.0.0. | Local parser; the bundled libvirt certifier was removed. Guest images, services, ACLs, readiness, applications, and SOC results are excluded. | [Backend extraction](../docs/migration/concrete-backends.md) |
| [TechVault guest certification](scenarios/techvault-guest-certified.sdl.yaml) | Retain the guest-readback example used by RAES 7.0.0. | Local parser; current native certification needs a backend-owned producer. | [Backend extraction](../docs/migration/concrete-backends.md) |
| [Control-context kit](scenarios/participant-control-context/context-kit.sdl.yaml) | Select shared and distinct reference-only participant assets. | Synthetic descriptors; no private content or delivery. | [Control-context notes](scenarios/participant-control-context/README.md) |
| [Control-context imports](scenarios/participant-control-context/twice-imported.sdl.yaml) | Inspect two namespaced imports with immutable asset pins. | File parser with local imports; no runtime withholding result. | [Control-context notes](scenarios/participant-control-context/README.md) |
| [Tool kit](scenarios/participant-tools/tool-kit.sdl.yaml) | Bind a participant's tool affordance, action, and access carrier. | File parser; declarations grant no invocation authority. | [Tool notes](scenarios/participant-tools/README.md) |
| [Tool imports](scenarios/participant-tools/twice-imported.sdl.yaml) | Inspect local participants over an imported action and tool. | File parser with local imports; no tool installation or scan. | [Tool notes](scenarios/participant-tools/README.md) |
| [User deadline](scenarios/temporal-profiles/user-deadline.sdl.yaml) | Declare a probe completion deadline at tick 5. | Temporal-capable implementation and evidence are needed for execution. | [Temporal notes](scenarios/temporal-profiles/README.md) |
| [Automation dwell](scenarios/temporal-profiles/automation-dwell.sdl.yaml) | Declare continuous evidence over `[0, 10)` before a probe. | Temporal-capable implementation and continuous evidence are needed for execution. | [Temporal notes](scenarios/temporal-profiles/README.md) |

The [minimal completeness fragment](completeness/rev1/valid-sdl-fragment/minimal.sdl.yaml) supports completeness tests.
It is a versioned test input, not a second first-use lesson.
See the [completeness reference](../specs/sdl/scientific-scenario-completeness.md).

### Experiment examples

These files describe pre-run design under `experiment-authoring-input-v1`.
They require the experiment loader, not the SDL parser.
They do not admit, schedule, or run experiments.

| Example | Purpose | Required support and limits | Reference |
| --- | --- | --- | --- |
| [Smoke run](experiments/techvault-smoke-run.exp.yaml) | Describe a small replication count for one task. | Experiment loader; the task reference is unresolved unless a task is supplied. | [Experiment input boundary](../docs/decisions/adrs/adr-074-experiment-authoring-input-contract-boundary.md) |
| [Red-tactic sweep](experiments/techvault-red-tactic-sweep.exp.yaml) | Compare declared red-tactic conditions with seeded replication. | Experiment loader; labels and seed declarations establish no applied treatment or reproducibility result. | [Experiment input boundary](../docs/decisions/adrs/adr-074-experiment-authoring-input-contract-boundary.md) |
| [Variation selection](experiments/techvault-variation-selection.exp.yaml) | Select declared scenario-family variation domains before trial compilation. | Experiment loader and compatible trial bindings; no trial record is produced by this file. | [Variation points](../specs/sdl/variation-points.md) |

## Reconciliation demonstration

This is a planning demonstration for readers with a repository checkout.
Use the frozen environment from [contributor setup](../CONTRIBUTING.md#set-up-the-repository).
Run from the repository root:

```shell
uv run --project implementations/python --frozen raes processor reconcile \
  examples/scenarios/reconciliation-demo-v1.sdl.yaml \
  examples/scenarios/reconciliation-demo-v2.sdl.yaml \
  --format json
```

The command exits with code `0` and prints a JSON action report.
It plans v1 against the reference dry-run manifest and projects that plan into an assumed snapshot.
It then plans v2 against that snapshot.
The report creates `provision.node.cache`, updates `provision.node.database`, deletes `provision.node.retired`, and leaves the remaining resources unchanged.
`evaluation.condition.database.health` also updates because its refresh dependency is the database node.
Its own payload is unchanged.

Both files are import-free and regenerate nothing per run or instantiation.
The result is deterministic and offline.
The snapshot is synthetic assumed state, not backend readback or a durable checkpoint.
The command applies, provisions, and starts nothing.
The report omits resource payloads because they can contain authored credentials and content.
See the [reconciliation tests](../implementations/python/tests/test_reconciliation_demonstration.py) for exact assertions.

## Template and pattern library

The machine-readable [catalogue](library/catalog.yaml) owns the library's IDs, contracts, status, users, and limits.
The [example-library reference](../docs/explain/reference/example-library.md) defines the metadata and loader behavior.
A template has a complete `body` to copy.
A pattern gives authoring guidance; it is not a complete scenario.
The existing gate checks `validation` command strings for shape but does not execute them.

| Template | Purpose | Required support and limits | Reference |
| --- | --- | --- | --- |
| [Minimal scenario](library/templates/scenario/minimal-validated-scenario.yaml) | Connect a host, participant, objective, and workflow. | SDL parser; no backend realizability claim. | [SDL sections](../specs/sdl/sections.md) |
| [Segmented network](library/templates/scenario/segmented-network-scenario.yaml) | Declare two segments, addresses, access rules, and a service feature. | SDL parser; native enforcement and feature installation need a backend. | [SDL sections](../specs/sdl/sections.md) |
| [Parameterized scenario](library/templates/scenario/parameterized-scenario.yaml) | Take host settings and instance count from declared variables. | SDL parser and instantiation for supplied values; the catalogue gate does not instantiate. | [Variables](../specs/sdl/variables-and-instantiation.md) |
| [Parallel workflow](library/templates/workflow/parallel-objective-workflow.yaml) | Join parallel objective branches. | SDL parser; no workflow execution result. | [Workflows](../specs/formal/workflows/README.md) |
| [Participant behavior](library/templates/participant_behavior/action-contract-observation-boundary.yaml) | Bind actions, contracts, and observation boundaries. | SDL parser; native execution needs an admitted implementation. | [Participant semantics](../specs/formal/participant-semantics/README.md) |
| [Single-objective task](library/templates/task/single-objective-task.yaml) | Express one task through an SDL objective. | SDL parser; no first-class `tasks` section. | [Task boundary](../docs/explain/reference/example-library.md#task-run-and-study-entries) |
| [Timed run control](library/templates/run/timed-run-control.yaml) | Connect story/script timing to objective and workflow windows. | SDL parser; no run scheduling or storage. | [Run boundary](../docs/explain/reference/example-library.md#task-run-and-study-entries) |
| [Seeded run plan](library/templates/run/seeded-run-plan.yaml) | Describe seeded replication, turns, and a step limit. | Experiment loader; seed declarations do not establish a random-stream contract. | [Experiment inputs](../docs/explain/reference/example-library.md#task-run-and-study-entries) |
| [Observational study](library/templates/study/observational-study-protocol.yaml) | Connect observed conditions to objective and workflow declarations. | SDL parser; graded scoring belongs to the experiment/evaluator plane. | [Study boundary](../docs/explain/reference/example-library.md#task-run-and-study-entries) |
| [Two-condition study](library/templates/study/two-condition-study-design.yaml) | Describe two levels of one treatment factor and runs per condition. | Experiment loader; membership checks establish no applied treatment. | [Experiment inputs](../docs/explain/reference/example-library.md#task-run-and-study-entries) |

| Pattern | Purpose | Required support | Reference |
| --- | --- | --- | --- |
| [Scenario references](library/patterns/scenario-reference-integrity.yaml) | Keep node, participant, objective, and workflow references valid. | Guidance; validate the authored result with the SDL parser. | [SDL validation](../docs/explain/sdl/validation.md) |
| [Workflow graph](library/patterns/workflow-explicit-control-graph.yaml) | Declare branches, joins, retries, calls, and endings. | Guidance; validate the authored graph. | [Workflows](../specs/formal/workflows/README.md) |
| [Participant binding](library/patterns/participant-behavior-contract-binding.yaml) | Bind actions and participant views. | Guidance; validate the authored result. | [Participant semantics](../specs/formal/participant-semantics/README.md) |
| [Task objective](library/patterns/task-as-objective-contract.yaml) | Express participant, target, and success through an objective. | Guidance; no first-class task section. | [Task boundary](../docs/explain/reference/example-library.md#task-run-and-study-entries) |
| [Run window](library/patterns/run-window-with-evidence.yaml) | Connect timed material and evidence to objective windows. | Guidance; no runtime execution result. | [SDL sections](../specs/sdl/sections.md) |
| [Study conditions](library/patterns/observable-study-conditions.yaml) | Connect propositions, assertions, evidence, and workflow protocol. | Guidance; scoring needs the experiment/evaluator plane. | [Scoring boundary](../docs/decisions/adrs/adr-073-scoring-reward-language-scope.md) |

### Catalog entry metadata

See [catalogue metadata](../docs/explain/reference/example-library.md#catalog-entry-metadata) for exact fields and validation behavior.
`validated` means acceptance by the stated contract's validator.
It establishes neither backend support nor execution.
`guidance` marks material that the gate does not validate against a contract.

### Scenario templates

See the individual templates above for their purpose and limits.
Use the [template validation procedure](../docs/explain/reference/example-library.md#validate-an-adapted-template) after copying a `body`.

### Task, run, and study entries

See the [contract boundary](../docs/explain/reference/example-library.md#task-run-and-study-entries) for SDL, experiment inputs, and task loading.
These categories do not add `tasks`, `runs`, or `studies` sections to SDL.

## Validate the examples

For checkout checks, use the [frozen development environment](../CONTRIBUTING.md#set-up-the-repository).
Run this focused test module from the repository root:

```shell
uv run --project implementations/python --frozen pytest -c implementations/python/pyproject.toml implementations/python/tests/test_scenarios.py -q
```

Exit code `0` means the selected assertions passed.
It does not mean that any backend realized the scenarios.
The [schema tests](../implementations/python/tests/test_example_schema_conformance.py) separately check disk-backed scenarios and experiment inputs.

For one scenario, run the file parser from the repository root:

```shell
uv run --project implementations/python --frozen python - <<'PY'
from pathlib import Path
from raes import parse_sdl_file

scenario = parse_sdl_file(Path("examples/scenarios/port-authority-surge-response.sdl.yaml"))
assert scenario.advisories == []
PY
```

The command exits with code `0` and prints nothing.
The assertion also checks advisories, which the semantic CLI success line does not report.

Check the template and pattern catalogue:

```shell
uv run --project implementations/python --frozen python tools/check_example_library.py
```

Exit code `0` with no output means the catalogue and validated bodies passed their checks.
A failure reports a rule and path, then exits nonzero.
The gate does not run each entry's command strings.
The [catalogue reference](../docs/explain/reference/example-library.md) gives its exact coverage.

## How to use these files

Select an entry with the declarations you need.
Read its reference and support limits before adapting it.
Use the [section reference](../docs/explain/sdl/sections.md) for fields and the [validation guide](../docs/explain/sdl/validation.md) for checks.
The [limitations](../docs/explain/sdl/limitations.md) and [testing guide](../docs/explain/sdl/testing.md) explain the result boundaries.
The [revised-control examples](../docs/examples/revised-control.md) show controlled runtime tests after the first-use lesson.

## Template boundary

Scenario files are positive examples that must load from disk.
Template bodies are complete SDL or `experiment-authoring-input-v1` documents.
Keep invalid inputs in focused negative tests.
The [template reference](../docs/explain/reference/example-library.md#template-boundary) gives variable and contract rules.
Native deployment, credentials, execution, rollback, and cleanup belong to backend distributions under [ADR-115](../docs/decisions/adrs/adr-115-concrete-backends-owned-outside-raes.md).
