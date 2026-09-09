"""Composite planning helpers for target conformance probes."""

from __future__ import annotations

from dataclasses import replace
from textwrap import dedent

from raes_contracts.planning import EvaluationPlan, OrchestrationPlan, RuntimeDomain
from raes_processor.models import ExecutionPlan
from raes_processor.reference import ScenarioInput, run_reference_processor
from raes_runtime.registry import RuntimeTarget

# Backend-neutral default for the target adapter probe. Backends with a bounded
# realization envelope may supply a different in-envelope witness through the
# public conformance runner.
DEFAULT_TARGET_CONFORMANCE_SCENARIO = dedent(
    """
    name: conformance
    nodes:
      vm:
        type: compute
        resources: {ram: 1 gib, cpu: 1}
        conditions: {health: ops}
        roles: {ops: operator}
    conditions:
      health: {proposition: health-state, command: /bin/true, interval: 15}
    entities:
      blue: {role: blue}
    propositions:
      health-state:
        description: The conformance VM is declared in the admitted scenario.
        subjects: [nodes.vm]
        basis: declared_state
        predicate:
          kind: presence
          property: node
          semantic_ref: urn:raes:declared-property:node
          operator: exists
    assertions:
      health:
        proposition: health-state
        role: postcondition
    objectives:
      validate:
        entity: blue
        success: {assertions: [health]}
    workflows:
      response:
        start: run
        steps:
          run:
            type: objective
            objective: validate
            on_success: finish
          finish: {type: end}
    """
)


def target_probe_execution_plan(
    scenario: ScenarioInput,
    target: RuntimeTarget,
    *,
    provisioning_only: bool,
) -> ExecutionPlan:
    """Build the valid composite plan authorized for a target probe."""

    execution_plan = run_reference_processor(scenario, target.manifest).execution_plan
    if not provisioning_only:
        return execution_plan
    return replace(
        execution_plan,
        orchestration=OrchestrationPlan(),
        evaluation=EvaluationPlan(),
        diagnostics=[
            diagnostic
            for diagnostic in execution_plan.diagnostics
            if diagnostic.domain not in {RuntimeDomain.ORCHESTRATION.value, RuntimeDomain.EVALUATION.value}
        ],
    )


__all__ = ["DEFAULT_TARGET_CONFORMANCE_SCENARIO", "target_probe_execution_plan"]
