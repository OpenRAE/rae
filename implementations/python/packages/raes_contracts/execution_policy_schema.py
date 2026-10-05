"""Portable semantic annotations for embedded execution requirements."""

from typing import Any

_POLICY_POINTER = "#/execution_policy"


def execution_policy_schema(schema: dict[str, Any], model: type) -> None:
    owners = {
        "ExecutionPolicy": ("sdl-authoring-input-v1", _POLICY_POINTER),
        "ExecutionPolicyDocument": ("sdl-authoring-input-v1", _POLICY_POINTER),
        "EffectiveExecutionPolicy": ("provisioning-plan-v1", "#/operations"),
        "ExecutionPolicyCapabilities": ("backend-operation-capabilities-v1", _POLICY_POINTER),
        "PlanOperationModel": ("provisioning-plan-v1", "#/operations"),
    }
    owner = next(base.__name__ for base in model.__mro__ if base.__name__ in owners)
    contract_id, pointer = owners[owner]
    schema["x-raes-invariants"] = [
        {
            "id": "execution-policy-" + model.__name__.lower(),
            "description": "Execution choices are complete, bounded and consistent; scope identities and "
            "references are unique, effective evidence resolves exactly, "
            "and unsupported continuation claims fail closed. "
            "See specs/sdl/execution-recovery.md for the portable semantic obligations.",
            "level": "error",
            "validator": model.__module__ + "." + model.__name__ + ".model_validate",
            "inputs": [{"contract_id": contract_id, "instance_path": pointer}],
        }
    ]
