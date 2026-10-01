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

| Surface | Template | Pattern |
|---------|----------|---------|
| Scenario | [`library/templates/scenario/minimal-validated-scenario.yaml`](library/templates/scenario/minimal-validated-scenario.yaml) | [`library/patterns/scenario-reference-integrity.yaml`](library/patterns/scenario-reference-integrity.yaml) |
| Workflow | [`library/templates/workflow/parallel-objective-workflow.yaml`](library/templates/workflow/parallel-objective-workflow.yaml) | [`library/patterns/workflow-explicit-control-graph.yaml`](library/patterns/workflow-explicit-control-graph.yaml) |
| Participant behavior | [`library/templates/participant_behavior/action-contract-observation-boundary.yaml`](library/templates/participant_behavior/action-contract-observation-boundary.yaml) | [`library/patterns/participant-behavior-contract-binding.yaml`](library/patterns/participant-behavior-contract-binding.yaml) |
| Task | [`library/templates/task/single-objective-task.yaml`](library/templates/task/single-objective-task.yaml) | [`library/patterns/task-as-objective-contract.yaml`](library/patterns/task-as-objective-contract.yaml) |
| Run | [`library/templates/run/timed-run-control.yaml`](library/templates/run/timed-run-control.yaml) | [`library/patterns/run-window-with-evidence.yaml`](library/patterns/run-window-with-evidence.yaml) |
| Study | [`library/templates/study/observational-study-protocol.yaml`](library/templates/study/observational-study-protocol.yaml) | [`library/patterns/observable-study-conditions.yaml`](library/patterns/observable-study-conditions.yaml) |

Each template has metadata plus a complete current-SDL `body`. The
`tools/check_example_library.py` policy gate validates catalog shape, stable
IDs, referenced paths, AUT-806 requirement references, and every template body
through the SDL parser and semantic validator.

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

There are no placeholder templates in this directory. Files under
`examples/scenarios/` are positive SDL examples and must load successfully from
disk. Files under `examples/library/templates/` are reusable authoring
templates with complete SDL bodies; they are validated by the example-library
policy gate.

Do not add invalid or incomplete SDL files under `examples/scenarios/`.
Negative-path examples belong in focused parser, model, validator, contract, or
conformance tests.

Task, run, and study templates use current SDL wrappers rather than first-class
`tasks`, `runs`, or `studies` sections. They show how to express those concepts
with objectives, workflows, timing, observable conditions, and evidence-like
references that the current implementation can validate. Graded scoring and
reward are experiment/evaluator-plane concerns (experiment-* contracts) per
ADR-073, not SDL surfaces.
