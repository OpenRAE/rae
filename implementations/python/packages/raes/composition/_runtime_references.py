"""Node-runtime reference rewriters for module composition.

A security-monitoring detection definition names the artifact it was parsed
from (``source_artifact_ref``) and the SDL elements it covers
(``target_refs``). Both resolve through the generic named-reference index
(ADR-045), so composition rewrites them through the named map, as it does
every other generic reference field (ADR-053).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..runtime_values import coerce_string_list
from ._references import _maybe_rename


def _rewrite_detection_definition(definition: dict[str, Any], named: Mapping[str, str]) -> None:
    if definition.get("source_artifact_ref"):
        definition["source_artifact_ref"] = _maybe_rename(str(definition["source_artifact_ref"]), named)
    target_refs = coerce_string_list(definition.get("target_refs"))
    if target_refs:
        definition["target_refs"] = [_maybe_rename(ref, named) for ref in target_refs]


def _rewrite_security_monitoring_references(
    runtime: dict[str, Any],
    symbols: dict[str, dict[str, str] | set[str]],
) -> None:
    named = symbols["named"]
    for manager in runtime.get("security_monitoring_managers", []):
        if not isinstance(manager, dict):
            continue
        for definition in manager.get("detection_definitions", []):
            if isinstance(definition, dict):
                _rewrite_detection_definition(definition, named)
