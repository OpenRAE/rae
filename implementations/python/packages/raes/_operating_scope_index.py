"""The derived operating-scope alias index (ADR-020 §2).

Operating scope admits the declaration kinds that the shared reference policy
names for it, and then only compute nodes and switch-backed infrastructure, and,
unlike general references, it also resolves bare service and subnet names.
"""

from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING

from ._declarations import Declaration, DeclarationIndex
from ._reference_targetability import ReferencePurpose, is_eligible
from .nodes import NodeType

if TYPE_CHECKING:
    from .scenario import ScenarioContent


def operating_scope_aliases(index: DeclarationIndex, scenario: ScenarioContent) -> dict[str, set[str]]:
    """Project the operating-scope purpose through the shared reference policy.

    The policy admits node, infrastructure, service, and content declarations.
    Operating scope further keeps only compute hosts and switch-backed subnets,
    and, unlike general references, also resolves bare service and subnet names.
    """

    aliases: dict[str, set[str]] = defaultdict(set)
    for declaration in index.declarations:
        if not is_eligible(declaration.kind, ReferencePurpose.OPERATING_SCOPE):
            continue
        local_name = _operating_scope_local_name(scenario, declaration)
        if local_name:
            aliases[declaration.address].add(declaration.address)
            aliases[local_name].add(declaration.address)
    return dict(aliases)


# Nested scope kinds carry their own local name: (owner section, item collection).
_SCOPE_ITEMS = {"service": ("nodes", "services"), "content-item": ("content", "items")}
_SCOPE_NODE_TYPES = {"node": NodeType.COMPUTE, "infrastructure": NodeType.SWITCH}


def _operating_scope_local_name(scenario: ScenarioContent, declaration: Declaration) -> str | None:
    tokens = declaration.model_tokens
    if declaration.kind in _SCOPE_ITEMS:
        section, collection = _SCOPE_ITEMS[declaration.kind]
        return getattr(getattr(scenario, section)[tokens[1]], collection)[int(tokens[3])].name
    required = _SCOPE_NODE_TYPES.get(declaration.kind)
    node = scenario.nodes.get(tokens[1]) if required is not None else None
    return None if required is not None and (node is None or node.type != required) else tokens[1]


__all__ = ["operating_scope_aliases"]
