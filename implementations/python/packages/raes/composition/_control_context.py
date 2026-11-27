"""Control-context symbol rewriting without changes to immutable asset pins."""

from typing import Any

from ._references import _maybe_rename


def rewrite_control_context(owner: dict[str, Any], symbols: dict[str, dict[str, str] | set[str]]) -> None:
    for binding in owner.get("control_context", {}).values():
        if not isinstance(binding, dict):
            continue
        reference = binding.get("declaration_ref", "")
        own = symbols["control_context_assets"]
        binding["declaration_ref"] = _maybe_rename(reference, own if reference in own else symbols["named"])
