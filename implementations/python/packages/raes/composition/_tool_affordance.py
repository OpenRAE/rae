"""Tool-affordance reference rewriting for reusable modules."""

from typing import Any

from ._references import _maybe_rename


def _rewrite_tool_affordance(
    binding: dict[str, Any],
    symbols: dict[str, dict[str, str] | set[str]],
) -> None:
    if binding.get("tool_ref"):
        tool_ref = str(binding["tool_ref"])
        # Bare content names keep the content map; the unit import guard has
        # already rejected a bare name that another unit declaration shares.
        # Other spellings, such as content.<name>, resolve through the named map.
        content_symbols = symbols["content"]
        binding["tool_ref"] = _maybe_rename(
            tool_ref, content_symbols if tool_ref in content_symbols else symbols["named"]
        )
    binding["action_contract_refs"] = [
        _maybe_rename(name, symbols["action_contracts"]) for name in binding.get("action_contract_refs", [])
    ]
    binding["observation_boundary_refs"] = [
        _maybe_rename(name, symbols["observation_boundaries"]) for name in binding.get("observation_boundary_refs", [])
    ]
    if "participant_refs" in binding:
        # Role refs stay global (#297); only explicit participant selectors are namespaced.
        binding["participant_refs"] = [_maybe_rename(name, symbols["agents"]) for name in binding["participant_refs"]]
