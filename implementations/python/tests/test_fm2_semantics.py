"""Cross-stage FM2 semantic agreement tests."""

from __future__ import annotations

import textwrap

import pytest
from raes import SDLInstantiationError, SDLValidationError, parse_sdl
from raes_backend_stubs.stubs import create_stub_manifest
from raes_processor.compiler import compile_runtime_model
from raes_processor.models import RuntimeDomain, RuntimeSnapshot, SnapshotEntry
from raes_processor.planner import plan


def _scenario(yaml_str: str):
    return textwrap.dedent(yaml_str)


def _snapshot_from_plan(execution_plan) -> RuntimeSnapshot:
    entries: dict[str, SnapshotEntry] = {}
    for domain, operations in (
        (RuntimeDomain.PROVISIONING, execution_plan.provisioning.operations),
        (RuntimeDomain.ORCHESTRATION, execution_plan.orchestration.operations),
        (RuntimeDomain.EVALUATION, execution_plan.evaluation.operations),
    ):
        for op in operations:
            if op.action.value == "delete":
                continue
            entries[op.address] = SnapshotEntry(
                address=op.address,
                domain=domain,
                resource_type=op.resource_type,
                payload=op.payload,
                ordering_dependencies=op.ordering_dependencies,
                refresh_dependencies=op.refresh_dependencies,
                status="snapshot",
            )
    return RuntimeSnapshot(entries=entries)


class TestObjectiveWindowAgreement:
    def test_validator_and_compiler_agree_on_window_errors(self):
        raw = _scenario("""
name: agreement
nodes:
  vm:
    type: compute
    os: linux
    resources: {ram: 1 gib, cpu: 1}
    conditions: {health: ops}
    roles: {ops: operator}
conditions:
  health: {command: /bin/true, interval: 15}
propositions:
  health:
    description: The governed VM has declared runtime state.
    subjects: [nodes.vm]
    basis: declared_state
    predicate: {kind: presence, property: runtime, semantic_ref: urn:raes:declared-property:runtime, operator: exists}
assertions:
  health: {proposition: health, role: postcondition, polarity: positive}
  pre-health: {proposition: health, role: precondition, polarity: positive}
entities:
  blue: {role: blue}
events:
  kickoff: {assertions: [pre-health]}
  cleanup: {assertions: [pre-health]}
scripts:
  timeline: {start_time: 0, end_time: 60, speed: 1, events: {kickoff: 10}}
  side: {start_time: 0, end_time: 60, speed: 1, events: {cleanup: 20}}
stories:
  main: {scripts: [timeline]}
objectives:
  initial:
    owner: blue
    success: {assertions: [health]}
    window:
      stories: [main]
      scripts: [side]
      events: [kickoff]
      workflows: [flow]
      steps: [other.finish]
workflows:
  flow:
    start: finish
    steps:
      finish: {type: end}
  other:
    start: finish
    steps:
      finish: {type: end}
""")

        with pytest.raises(SDLValidationError) as exc_info:
            parse_sdl(raw)

        errors = exc_info.value.errors
        assert any("window script 'side' is not included by the referenced stories" in error for error in errors)
        assert any("window event 'kickoff' is not included by the referenced scripts" in error for error in errors)
        assert any("window step 'other.finish' is not part of the referenced workflows" in error for error in errors)

        with pytest.raises(SDLInstantiationError) as compiler_exc:
            compile_runtime_model(parse_sdl(raw, skip_semantic_validation=True))
        assert compiler_exc.value.errors == errors

    def test_compiler_and_planner_agree_on_window_refresh_semantics(self):
        raw = _scenario("""
name: refresh-agreement
nodes:
  vm:
    type: compute
    os: linux
    resources: {ram: 1 gib, cpu: 1}
    conditions: {health: ops}
    roles: {ops: operator}
conditions:
  health: {command: /bin/true, interval: 15}
propositions:
  health:
    description: The governed VM has declared runtime state.
    subjects: [nodes.vm]
    basis: declared_state
    predicate: {kind: presence, property: runtime, semantic_ref: urn:raes:declared-property:runtime, operator: exists}
assertions:
  health: {proposition: health, role: postcondition, polarity: positive}
  pre-health: {proposition: health, role: precondition, polarity: positive}
entities:
  blue: {role: blue}
objectives:
  initial:
    owner: blue
    success: {assertions: [health]}
    window:
      workflows: [flow]
      steps: [flow.branch]
workflows:
  flow:
    start: branch
    steps:
      branch:
        type: decision
        when: {assertions: [pre-health]}
        then: finish
        else: finish
      finish: {type: end}
""")
        baseline = plan(
            compile_runtime_model(parse_sdl(raw)),
            create_stub_manifest(),
        )
        snapshot = _snapshot_from_plan(baseline)

        mutated = compile_runtime_model(
            parse_sdl(
                raw.replace("/bin/true", "/bin/false").replace(
                    "urn:raes:declared-property:runtime",
                    "urn:raes:declared-property:runtime-v2",
                ),
                skip_semantic_validation=False,
            )
        )
        objective = mutated.objectives["evaluation.objective.initial"]
        assert "orchestration.workflow.flow" in objective.refresh_dependencies

        updated = plan(
            mutated,
            create_stub_manifest(),
            snapshot=snapshot,
        )

        actions = {op.address: op.action.value for op in updated.evaluation.operations}
        assert actions["evaluation.condition.vm.health"] == "update"
        assert actions["evaluation.objective.initial"] == "update"


class TestObjectiveSemanticAgreement:
    def test_validator_and_compiler_agree_on_objective_reference_errors(self):
        raw = _scenario("""
name: objective-reference-errors
entities:
  blue: {role: blue}
objectives:
  base:
    owner: blue
    success: {assertions: [missing-assertion]}
    depends_on: [missing-objective]
""")

        with pytest.raises(SDLValidationError) as exc_info:
            parse_sdl(raw)

        errors = exc_info.value.errors
        assert any(
            "Objective 'base' references undefined assertion 'missing-assertion' in success criteria" in e
            for e in errors
        )
        assert any("Objective 'base' depends on undefined objective 'missing-objective'" in e for e in errors)

        with pytest.raises(SDLInstantiationError) as compiler_exc:
            compile_runtime_model(parse_sdl(raw, skip_semantic_validation=True))
        assert compiler_exc.value.errors == errors

    def test_compiler_and_planner_agree_on_objective_dependency_ordering_and_refresh(self):
        raw = _scenario("""
name: objective-dependency-agreement
nodes:
  vm:
    type: compute
    os: linux
    resources: {ram: 1 gib, cpu: 1}
    conditions: {ready: ops, gate: ops}
    roles: {ops: operator}
conditions:
  ready: {command: /bin/true, interval: 15}
  gate: {command: /bin/echo, interval: 15}
propositions:
  ready:
    description: The governed VM has declared ready state.
    subjects: [nodes.vm]
    basis: declared_state
    predicate: {kind: boolean, property: ready, semantic_ref: urn:raes:declared-property:ready, operator: equals, expected: true}
  gate:
    description: The governed VM has declared gate state.
    subjects: [nodes.vm]
    basis: declared_state
    predicate: {kind: boolean, property: gate, semantic_ref: urn:raes:declared-property:gate, operator: equals, expected: true}
assertions:
  ready: {proposition: ready, role: postcondition, polarity: positive}
  gate: {proposition: gate, role: postcondition, polarity: positive}
entities:
  blue: {role: blue}
objectives:
  base:
    owner: blue
    success: {assertions: [ready]}
  dependent:
    owner: blue
    success: {assertions: [gate]}
    depends_on: [base]
""")
        compiled = compile_runtime_model(parse_sdl(raw))
        dependent = compiled.objectives["evaluation.objective.dependent"]
        assert "evaluation.objective.base" in dependent.ordering_dependencies
        assert "evaluation.objective.base" in dependent.refresh_dependencies

        baseline = plan(compiled, create_stub_manifest())
        snapshot = _snapshot_from_plan(baseline)

        mutated = compile_runtime_model(
            parse_sdl(
                raw.replace("/bin/true", "/bin/false").replace(
                    "urn:raes:declared-property:ready",
                    "urn:raes:declared-property:ready-v2",
                )
            )
        )
        updated = plan(mutated, create_stub_manifest(), snapshot=snapshot)

        actions = {op.address: op.action.value for op in updated.evaluation.operations}
        assert actions["evaluation.condition.vm.ready"] == "update"
        assert actions["evaluation.objective.base"] == "update"
        assert actions["evaluation.objective.dependent"] == "update"
