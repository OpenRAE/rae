"""Published-schema conditional builders for capability contracts.

Split from ``capabilities.py`` to keep that module within the ADR-015 size cap.
Each function returns the ``allOf`` conditional list a capability model appends to
its JSON Schema so schema-only consumers enforce the same cross-field coupling the
Python models validate.
"""

from __future__ import annotations

from ..vocabulary import GeneratedArtifactKind

_RANDOM_VALUE = GeneratedArtifactKind.RANDOM_VALUE.value


def _flag_requires_values(flag: str, values: str) -> list[dict[str, object]]:
    """Bidirectional coupling: a true support flag requires a non-empty list and vice versa."""

    return [
        {
            "if": {"properties": {flag: {"const": True}}, "required": [flag]},
            "then": {"required": [values], "properties": {values: {"minItems": 1}}},
        },
        {
            "if": {"properties": {values: {"minItems": 1}}, "required": [values]},
            "then": {"required": [flag], "properties": {flag: {"const": True}}},
        },
    ]


def provisioner_capability_conditionals() -> list[dict[str, object]]:
    """Cross-field conditionals for ``ProvisionerCapabilitiesModel``."""

    random_value_kinds = {"contains": {"const": _RANDOM_VALUE}}
    return [
        *_flag_requires_values("supports_accounts", "supported_account_features"),
        *_flag_requires_values("supports_generated_artifacts", "supported_generated_artifact_kinds"),
        {
            "if": {
                "properties": {"supported_generated_artifact_kinds": random_value_kinds},
                "required": ["supported_generated_artifact_kinds"],
            },
            "then": {
                "required": ["supported_regeneration_scopes"],
                "properties": {"supported_regeneration_scopes": {"minItems": 1}},
            },
        },
        {
            "if": {
                "properties": {"supported_regeneration_scopes": {"minItems": 1}},
                "required": ["supported_regeneration_scopes"],
            },
            "then": {
                "required": ["supported_generated_artifact_kinds"],
                "properties": {"supported_generated_artifact_kinds": random_value_kinds},
            },
        },
    ]


__all__ = ["provisioner_capability_conditionals"]
