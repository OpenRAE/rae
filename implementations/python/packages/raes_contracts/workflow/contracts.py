"""Compiled workflow result/execution contracts and their validation."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

from raes_contracts._validation import (
    require_dict,
    require_non_empty_string,
    require_string,
    require_strings,
)
from raes_contracts.versions import WORKFLOW_STATE_SCHEMA_VERSION
from raes_contracts.workflow.semantics import WorkflowStepSemanticContract
from raes_contracts.workflow.semantics import validate_workflow_step_result as _validate_workflow_step_result


@dataclass(frozen=True)
class WorkflowResultContract:
    """Compiled contract for validating portable workflow result envelopes."""

    state_schema_version: str = WORKFLOW_STATE_SCHEMA_VERSION
    observable_steps: dict[str, WorkflowStepSemanticContract] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.state_schema_version, str) or not self.state_schema_version:
            raise TypeError("workflow result contract state_schema_version must be a non-empty string")
        if not isinstance(self.observable_steps, dict):
            raise TypeError("workflow result contract observable_steps must be a dict")
        if any(not isinstance(step_name, str) for step_name in self.observable_steps):
            raise TypeError("workflow result contract step names must be strings")
        if any(not isinstance(contract, WorkflowStepSemanticContract) for contract in self.observable_steps.values()):
            raise TypeError("workflow result contract step contracts must be WorkflowStepSemanticContract values")

    @classmethod
    def from_mapping(
        cls,
        payload: Mapping[str, Any],
    ) -> WorkflowResultContract:
        if not isinstance(payload, Mapping):
            raise TypeError("workflow result contract must be a mapping")
        observable_steps_payload = payload.get("observable_steps", {})
        if not isinstance(observable_steps_payload, Mapping):
            raise TypeError("workflow result contract observable_steps must be a mapping")
        observable_steps: dict[str, WorkflowStepSemanticContract] = {}
        for step_name, step_payload in observable_steps_payload.items():
            if not isinstance(step_name, str):
                raise TypeError("workflow result contract step names must be strings")
            if not isinstance(step_payload, Mapping):
                raise TypeError("workflow result contract step payloads must be mappings")
            observable_steps[step_name] = WorkflowStepSemanticContract.from_mapping(step_payload)
            if not observable_steps[step_name].state_observable:
                raise ValueError("workflow result contract may only include observable steps")
        return cls(
            state_schema_version=str(payload.get("state_schema_version", WORKFLOW_STATE_SCHEMA_VERSION)),
            observable_steps=observable_steps,
        )


def validate_workflow_step_result_contract(
    contract: WorkflowStepSemanticContract,
    *,
    lifecycle: str,
    outcome: str | None,
    attempts: int,
) -> tuple[str, ...]:
    """Validate a backend-reported workflow step result against a compiled contract."""

    return _validate_workflow_step_result(
        contract,
        lifecycle=lifecycle,
        outcome=outcome,
        attempts=attempts,
    )


@dataclass(frozen=True)
class WorkflowExecutionContract:
    """Compiled contract for validating workflow-level execution state/history."""

    state_schema_version: str = WORKFLOW_STATE_SCHEMA_VERSION
    start_step: str = ""
    timeout_seconds: int | None = None
    steps: dict[str, WorkflowStepSemanticContract] = field(default_factory=dict)
    step_types: dict[str, str] = field(default_factory=dict)
    control_edges: dict[str, tuple[str, ...]] = field(default_factory=dict)
    join_owners: dict[str, str] = field(default_factory=dict)
    call_steps: dict[str, str] = field(default_factory=dict)
    compensation_mode: str = "disabled"
    compensation_triggers: tuple[str, ...] = ()
    compensation_targets: dict[str, str] = field(default_factory=dict)
    compensation_ordering: str = "reverse_completion"
    compensation_failure_policy: str = "fail_workflow"
    observable_steps: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _validate_workflow_execution_contract_identity(self)
        _validate_workflow_execution_contract_steps(self)
        _validate_workflow_execution_contract_compensation(self)

    @classmethod
    def from_mapping(
        cls,
        payload: Mapping[str, Any],
    ) -> WorkflowExecutionContract:
        if not isinstance(payload, Mapping):
            raise TypeError("workflow execution contract must be a mapping")
        return cls(
            state_schema_version=str(payload.get("state_schema_version", WORKFLOW_STATE_SCHEMA_VERSION)),
            start_step=str(payload.get("start_step", "")),
            timeout_seconds=(int(payload["timeout_seconds"]) if payload.get("timeout_seconds") is not None else None),
            steps=_workflow_contract_steps(payload.get("steps", {})),
            step_types=_workflow_contract_string_mapping(
                payload.get("step_types", {}),
                "workflow execution contract step_types",
            ),
            control_edges=_workflow_contract_edges(payload.get("control_edges", {})),
            join_owners=_workflow_contract_string_mapping(
                payload.get("join_owners", {}),
                "workflow execution contract join_owners",
            ),
            call_steps=_workflow_contract_string_mapping(
                payload.get("call_steps", {}),
                "workflow execution contract call_steps",
            ),
            compensation_mode=str(payload.get("compensation_mode", "disabled")),
            compensation_triggers=tuple(str(trigger) for trigger in payload.get("compensation_triggers", ())),
            compensation_targets=_workflow_contract_string_mapping(
                payload.get("compensation_targets", {}),
                "workflow execution contract compensation_targets",
            ),
            compensation_ordering=str(payload.get("compensation_ordering", "reverse_completion")),
            compensation_failure_policy=str(payload.get("compensation_failure_policy", "fail_workflow")),
            observable_steps=tuple(str(step_name) for step_name in payload.get("observable_steps", ())),
        )


def _workflow_contract_steps(raw: object) -> dict[str, WorkflowStepSemanticContract]:
    if not isinstance(raw, Mapping):
        raise TypeError("workflow execution contract steps must be a mapping")
    steps: dict[str, WorkflowStepSemanticContract] = {}
    for step_name, step_payload in raw.items():
        if not isinstance(step_name, str):
            raise TypeError("workflow execution contract step names must be strings")
        if not isinstance(step_payload, Mapping):
            raise TypeError("workflow execution contract step payloads must be mappings")
        steps[step_name] = WorkflowStepSemanticContract.from_mapping(step_payload)
    return steps


def _workflow_contract_edges(raw: object) -> dict[str, tuple[str, ...]]:
    if not isinstance(raw, Mapping):
        raise TypeError("workflow execution contract control_edges must be a mapping")
    return {
        str(step_name): tuple(str(successor) for successor in successors)
        for step_name, successors in raw.items()
        if isinstance(successors, Iterable)
    }


def _workflow_contract_string_mapping(raw: object, field_name: str) -> dict[str, str]:
    if not isinstance(raw, Mapping):
        raise TypeError(f"{field_name} must be a mapping")
    return {str(key): str(value) for key, value in raw.items()}


def _validate_workflow_execution_contract_identity(contract: WorkflowExecutionContract) -> None:
    require_non_empty_string(
        contract.state_schema_version,
        "workflow execution contract state_schema_version",
    )
    require_string(contract.start_step, "workflow execution contract start_step")
    if contract.timeout_seconds is None:
        return
    if isinstance(contract.timeout_seconds, bool) or not isinstance(contract.timeout_seconds, int):
        raise TypeError("workflow execution contract timeout_seconds must be an int or None")
    if contract.timeout_seconds <= 0:
        raise ValueError("workflow execution contract timeout_seconds must be > 0")


def _validate_workflow_execution_contract_steps(contract: WorkflowExecutionContract) -> None:
    require_dict(contract.steps, "workflow execution contract steps")
    require_strings(contract.steps, "workflow execution contract step names")
    if any(not isinstance(step_contract, WorkflowStepSemanticContract) for step_contract in contract.steps.values()):
        raise TypeError("workflow execution contract step contracts must be WorkflowStepSemanticContract values")
    require_dict(contract.step_types, "workflow execution contract step_types")
    if any(not isinstance(name, str) or not isinstance(kind, str) for name, kind in contract.step_types.items()):
        raise TypeError("workflow execution contract step_types must map strings to strings")
    require_dict(contract.control_edges, "workflow execution contract control_edges")
    require_dict(contract.join_owners, "workflow execution contract join_owners")
    _require_string_mapping(contract.call_steps, "workflow execution contract call_steps")
    require_strings(contract.observable_steps, "workflow execution contract observable_steps")


def _validate_workflow_execution_contract_compensation(contract: WorkflowExecutionContract) -> None:
    require_string(contract.compensation_mode, "workflow execution contract compensation_mode")
    require_strings(contract.compensation_triggers, "workflow execution contract compensation_triggers")
    _require_string_mapping(contract.compensation_targets, "workflow execution contract compensation_targets")
    require_string(contract.compensation_ordering, "workflow execution contract compensation_ordering")
    require_string(contract.compensation_failure_policy, "workflow execution contract compensation_failure_policy")


def _require_string_mapping(value: object, field_name: str) -> None:
    require_dict(value, field_name)
    if any(not isinstance(key, str) or not isinstance(item, str) for key, item in value.items()):
        raise TypeError(f"{field_name} must map strings to strings")
