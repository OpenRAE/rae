"""Pure truth algebra for backend-neutral SDL assertions."""

from __future__ import annotations

from collections.abc import Sequence
from enum import Enum

from raes_contracts.propositions import AssertionPolarity, SubjectQuantifier, TruthCompositionMode


class TruthValue(str, Enum):
    """Portable outcome domain for proposition evaluation.

    ``UNSUPPORTED`` is a realization disposition, not a logical truth value.
    It is present in this wire-facing domain so inability to realize a
    proposition cannot be collapsed into missing evidence or falsity.
    """

    TRUE = "true"
    FALSE = "false"
    UNKNOWN = "unknown"
    UNSUPPORTED = "unsupported"


def negate_truth(value: TruthValue) -> TruthValue:
    """Negate a decided truth value without inventing knowledge or support."""

    if value is TruthValue.TRUE:
        return TruthValue.FALSE
    if value is TruthValue.FALSE:
        return TruthValue.TRUE
    return value


def evaluate_assertion_polarity(value: TruthValue, polarity: AssertionPolarity) -> TruthValue:
    """Apply assertion polarity to one proposition outcome."""

    return negate_truth(value) if polarity is AssertionPolarity.NEGATIVE else value


def _indeterminate(values: Sequence[TruthValue]) -> TruthValue:
    return TruthValue.UNSUPPORTED if TruthValue.UNSUPPORTED in values else TruthValue.UNKNOWN


def _compose_at_least(values: Sequence[TruthValue], threshold: int) -> TruthValue:
    true_count = values.count(TruthValue.TRUE)
    if true_count >= threshold:
        return TruthValue.TRUE
    undecided_count = values.count(TruthValue.UNKNOWN) + values.count(TruthValue.UNSUPPORTED)
    if true_count + undecided_count < threshold:
        return TruthValue.FALSE
    return _indeterminate(values)


def _validate_composition(
    values: Sequence[TruthValue],
    mode: TruthCompositionMode,
    threshold: int | None,
) -> None:
    if not values:
        raise ValueError("truth composition requires at least one truth value")
    if mode is TruthCompositionMode.AT_LEAST:
        if threshold is None:
            raise ValueError("at_least truth composition requires threshold")
        if threshold < 1 or threshold > len(values):
            raise ValueError("at_least threshold must be within the truth-value count")
    elif threshold is not None:
        raise ValueError(f"{mode.value} truth composition must not declare threshold")


def _compose_all(values: Sequence[TruthValue]) -> TruthValue:
    if TruthValue.FALSE in values:
        return TruthValue.FALSE
    return TruthValue.TRUE if all(value is TruthValue.TRUE for value in values) else _indeterminate(values)


def _compose_any(values: Sequence[TruthValue]) -> TruthValue:
    if TruthValue.TRUE in values:
        return TruthValue.TRUE
    return TruthValue.FALSE if all(value is TruthValue.FALSE for value in values) else _indeterminate(values)


def compose_truth(
    values: Sequence[TruthValue],
    *,
    mode: TruthCompositionMode,
    threshold: int | None = None,
) -> TruthValue:
    """Compose non-empty assertion outcomes using the portable truth tables."""

    _validate_composition(values, mode, threshold)
    if mode is TruthCompositionMode.AT_LEAST:
        assert threshold is not None
        return _compose_at_least(values, threshold)
    if mode is TruthCompositionMode.ALL_OF:
        return _compose_all(values)
    return _compose_any(values)


def quantify_subject_truth(
    values: Sequence[TruthValue],
    *,
    quantifier: SubjectQuantifier,
    threshold: int | None = None,
) -> TruthValue:
    """Aggregate per-subject predicate outcomes for one finite proposition."""

    mode = {
        SubjectQuantifier.ALL: TruthCompositionMode.ALL_OF,
        SubjectQuantifier.ANY: TruthCompositionMode.ANY_OF,
        SubjectQuantifier.AT_LEAST: TruthCompositionMode.AT_LEAST,
    }[quantifier]
    return compose_truth(values, mode=mode, threshold=threshold)


__all__ = [
    "TruthValue",
    "compose_truth",
    "evaluate_assertion_polarity",
    "negate_truth",
    "quantify_subject_truth",
]
