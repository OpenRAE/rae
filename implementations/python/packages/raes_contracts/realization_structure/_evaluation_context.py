"""Shared state and closure checks for recursive evaluation."""

from __future__ import annotations

from dataclasses import dataclass

from ._common import RealizationRelationResult, RelationBudget, closure_for, pointer, relation_result
from ._models import (
    RealizationClosure,
    RealizationClosurePosture,
    RealizationConstraintDocument,
    RealizationRelationStatus,
)


@dataclass(frozen=True)
class EvaluationContext:
    document: RealizationConstraintDocument
    budget: RelationBudget
    reference_stack: tuple[str, ...] = ()
    reference_hops: int = 0

    def follow_reference(self, target: str) -> EvaluationContext:
        return EvaluationContext(
            document=self.document,
            budget=self.budget,
            reference_stack=(*self.reference_stack, target),
            reference_hops=self.reference_hops + 1,
        )


def evaluate_closure(
    context: EvaluationContext,
    local: RealizationClosure,
    path: tuple[str, ...],
    *,
    has_extras: bool,
    undefined_message: str,
    closed_message: str,
) -> RealizationRelationResult | None:
    closure = closure_for(context.document, local, path, context.budget)
    result = None
    if closure is None:
        result = relation_result(
            RealizationRelationStatus.LIMIT_EXCEEDED,
            pointer(path),
            "Closure resolution exceeded max_operations.",
        )
    elif closure.posture is RealizationClosurePosture.UNDEFINED:
        result = relation_result(
            RealizationRelationStatus.UNSUPPORTED,
            pointer(path),
            undefined_message,
        )
    elif closure.posture is RealizationClosurePosture.CLOSED and has_extras:
        result = relation_result(
            RealizationRelationStatus.NONCONFORMANT,
            pointer(path),
            closed_message,
        )
    return result


__all__ = ["EvaluationContext", "evaluate_closure"]
