"""Portable structural and semantic constraints for safe-state declarations."""

from typing import Any


def safe_state_schema(schema: dict[str, Any], model: type) -> None:
    reference_map = {"SafeStateProof": "evidence_requirements", "ResolvedSafeState": "proofs"}.get(model.__name__)
    if reference_map is not None:
        mapping = schema["properties"][reference_map]
        mapping["additionalProperties"] = False
        mapping["propertyNames"] = {"minLength": 1, "maxLength": 2048, "not": {"pattern": r"\s"}}
    authored = model.__name__ in {"SafeState", "SafeStateScope", "SafeStateDocument"}
    schema["x-raes-invariants"] = [
        {
            "id": "safe-state-" + model.__name__.lower(),
            "description": "Safe states are complete lexical values with unique scopes and assertions. "
            "Resolved values bind exact observed postconditions and target-specific evidence. "
            "Resolved collections obey aggregate PLAN_VALUE_LIMITS before proof copying. "
            "See specs/sdl/safe-state.md.",
            "level": "error",
            "validator": model.__module__ + "." + model.__name__ + ".model_validate",
            "inputs": [
                {
                    "contract_id": "sdl-authoring-input-v1" if authored else "provisioning-plan-v1",
                    "instance_path": "#/safe_state" if authored else "#/safe_states",
                }
            ],
        }
    ]
    if model.__name__ == "SafeState":
        schema["properties"]["assertion_refs"]["uniqueItems"] = True
        schema.setdefault("allOf", []).append(
            {
                "if": {"properties": {"kind": {"const": "continue"}}, "required": ["kind"]},
                "then": {"required": ["continuing_mode"], "properties": {"continuing_mode": {"type": "string"}}},
                "else": {"properties": {"continuing_mode": {"type": "null"}}},
            }
        )
