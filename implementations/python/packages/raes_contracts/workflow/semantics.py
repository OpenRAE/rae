"""Pure workflow semantic rules shared across validation, compilation, and runtime."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from raes_contracts.graphs import has_cycle, stable_topological_order

_OBSERVABLE_OUTCOMES_BY_STEP_TYPE: dict[str, tuple[str, ...]] = {
    "objective": ("succeeded", "failed"),
    "retry": ("succeeded", "exhausted"),
    "parallel": ("succeeded", "failed"),
    "call": ("succeeded", "failed"),
}
_FIXED_ATTEMPTS_BY_STEP_TYPE: dict[str, int] = {
    "objective": 1,
    "parallel": 1,
    "call": 1,
}


@dataclass(frozen=True)
class WorkflowStepSemanticContract:
    """Portable contract for workflow-visible step state."""

    step_type: str
    state_observable: bool = False
    observable_outcomes: tuple[str, ...] = ()
    supports_attempt_counts: bool = False
    fixed_attempts: int | None = None

    @classmethod
    def from_mapping(
        cls,
        payload: Mapping[str, object] | None,
        *,
        default_step_type: str = "",
    ) -> WorkflowStepSemanticContract:
        if payload is None:
            return workflow_step_semantic_contract(default_step_type)
        return cls(
            step_type=str(payload.get("step_type", default_step_type)),
            state_observable=bool(payload.get("state_observable", False)),
            observable_outcomes=tuple(str(outcome) for outcome in payload.get("observable_outcomes", ())),
            supports_attempt_counts=bool(payload.get("supports_attempt_counts", False)),
            fixed_attempts=(int(payload["fixed_attempts"]) if payload.get("fixed_attempts") is not None else None),
        )


def workflow_step_semantic_contract(step_type: str) -> WorkflowStepSemanticContract:
    """Return the semantic contract for a workflow step type."""

    observable_outcomes = _OBSERVABLE_OUTCOMES_BY_STEP_TYPE.get(step_type, ())
    fixed_attempts = _FIXED_ATTEMPTS_BY_STEP_TYPE.get(step_type)
    state_observable = bool(observable_outcomes)
    return WorkflowStepSemanticContract(
        step_type=step_type,
        state_observable=state_observable,
        observable_outcomes=observable_outcomes,
        supports_attempt_counts=state_observable,
        fixed_attempts=fixed_attempts,
    )


def branch_closure(
    graph: Mapping[str, Iterable[str]],
    *,
    branches: Iterable[str],
    join_step: str,
) -> frozenset[str]:
    """Return the owning parallel's branch closure up to, but excluding, the join."""

    closure: set[str] = set()
    stack = list(branches)
    while stack:
        node = stack.pop()
        if node == join_step or node in closure:
            continue
        closure.add(node)
        for successor in graph.get(node, ()):
            if successor != join_step:
                stack.append(successor)
    return frozenset(closure)


def workflow_join_states(
    graph: Mapping[str, Iterable[str]],
    *,
    join_step: str,
    observable_steps: Iterable[str],
) -> dict[str, frozenset[str]]:
    """Return guaranteed state for nodes whose every path reaches ``join_step``.

    The graph maps named steps to successors. The join is a boundary, so its
    continuation contributes no state. Cyclic graphs are refused before analysis.
    Shared graph mechanics provide successor-first ordering; intersection keeps
    only observable steps present on every path to the join.
    """

    successors = {node: tuple(targets) for node, targets in graph.items()}
    if join_step not in successors:
        raise ValueError("Workflow join must name a graph step")
    if has_cycle(successors):
        raise ValueError("Workflow join analysis requires an acyclic graph")
    dependencies = {node: () if node == join_step else targets for node, targets in successors.items()}
    observed = frozenset(observable_steps)
    states: dict[str, frozenset[str]] = {join_step: frozenset()}
    for node in stable_topological_order(dependencies, key=str):
        if node == join_step:
            continue
        targets = successors.get(node, ())
        if targets and all(target in states for target in targets):
            guaranteed = frozenset.intersection(*(states[target] for target in targets))
            states[node] = guaranteed | {node} if node in observed else guaranteed
    return states


def validate_workflow_step_result(
    contract: WorkflowStepSemanticContract,
    *,
    lifecycle: str,
    outcome: str | None,
    attempts: int,
) -> tuple[str, ...]:
    """Return semantic violations for a workflow step execution state."""

    errors: list[str] = []
    if attempts < 0:
        errors.append("attempts must be >= 0")

    if lifecycle not in _STEP_LIFECYCLES:
        errors.append(f"lifecycle '{lifecycle}' is invalid")
        return tuple(errors)

    errors.extend(_lifecycle_violations(contract, lifecycle, outcome, attempts))
    errors.extend(_outcome_violations(contract, lifecycle, outcome))
    errors.extend(_attempt_limit_violations(contract, lifecycle, attempts))
    return tuple(errors)


_STEP_LIFECYCLES = frozenset({"pending", "running", "completed"})


def _lifecycle_violations(
    contract: WorkflowStepSemanticContract, lifecycle: str, outcome: str | None, attempts: int
) -> list[str]:
    errors: list[str] = []
    if lifecycle != "completed" and outcome is not None:
        errors.append("non-completed steps may not report an outcome")
    if lifecycle == "pending" and attempts != 0:
        errors.append("pending steps must report 0 attempts")
    if lifecycle == "running" and contract.state_observable and attempts < 1:
        errors.append("running observable steps must report at least 1 attempt")
    return errors


def _outcome_violations(contract: WorkflowStepSemanticContract, lifecycle: str, outcome: str | None) -> list[str]:
    if lifecycle != "completed" or not contract.state_observable or outcome in contract.observable_outcomes:
        return []
    if outcome is None:
        return ["completed observable steps must report an outcome"]
    allowed = ", ".join(contract.observable_outcomes)
    return [f"outcome '{outcome}' is invalid for step type '{contract.step_type}' (allowed: {allowed})"]


def _attempt_limit_violations(contract: WorkflowStepSemanticContract, lifecycle: str, attempts: int) -> list[str]:
    fixed = contract.fixed_attempts
    if fixed is None:
        return []
    if lifecycle == "completed":
        return (
            [f"completed '{contract.step_type}' steps must report exactly {fixed} attempts"]
            if attempts != fixed
            else []
        )
    return [f"'{contract.step_type}' steps may not exceed {fixed} attempts"] if attempts > fixed else []
