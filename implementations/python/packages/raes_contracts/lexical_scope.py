"""Complete-value selection for lexical author defaults."""

from collections.abc import Sequence
from typing import Protocol

from .realization_structure import semantic_address_contains


class LexicalScope(Protocol):
    namespace: tuple[str, ...]
    scope: str


def select_lexical_scope[Rule: LexicalScope](
    rules: Sequence[Rule], scope: str, namespace: tuple[str, ...]
) -> Rule | None:
    """Select one nearest defining scope; callers reject duplicate identities."""
    matches = [
        rule
        for rule in rules
        if namespace[: len(rule.namespace)] == rule.namespace and semantic_address_contains(rule.scope, scope)
    ]
    return max(matches, key=lambda rule: (len(rule.namespace), rule.scope.count("/")), default=None)
