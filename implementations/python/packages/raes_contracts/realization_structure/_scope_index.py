"""Evaluation-local, budgeted lookup of decoded lexical scope tokens."""

from __future__ import annotations

from dataclasses import dataclass, field

from ..json_pointer import pointer_tokens
from ._common import RelationBudget
from ._models import RealizationClosure, RealizationConstraintDocument


@dataclass
class ScopeIndex:
    closure: RealizationClosure | None = None
    children: dict[str, ScopeIndex] = field(default_factory=dict)

    @classmethod
    def build(cls, document: RealizationConstraintDocument, budget: RelationBudget) -> ScopeIndex | None:
        root = cls()
        for scope in document.scopes:
            if budget.spend_operation():
                return None
            node = root
            for token in pointer_tokens(scope.field_pointer):
                if budget.spend_operation():
                    return None
                if token not in node.children:
                    node.children[token] = cls()
                node = node.children[token]
            node.closure = scope.closure
        return root

    def inherited_closure(
        self, path: tuple[str, ...], default: RealizationClosure, budget: RelationBudget
    ) -> RealizationClosure | None:
        node = self
        closure = node.closure or default
        for token in path:
            if budget.spend_operation():
                return None
            child = node.children.get(token)
            if child is None:
                break
            node = child
            if node.closure is not None:
                closure = node.closure
        return closure

    def declared_children(self, path: tuple[str, ...], budget: RelationBudget) -> set[str] | None:
        node = self
        for token in path:
            if budget.spend_operation():
                return None
            child = node.children.get(token)
            if child is None:
                return set()
            node = child
        children: set[str] | None = set()
        for token in node.children:
            if budget.spend_operation():
                children = None
                break
            children.add(token)
        return children
