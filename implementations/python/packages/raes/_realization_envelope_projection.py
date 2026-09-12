"""Offer membership for admitted safe values with their typed presence rules."""

from collections.abc import Mapping

from pydantic import BaseModel
from raes_contracts.realization_envelope import RealizationEnvelopeModel

from ._realization_envelope_engine import assign_path, effective_constraints, present_children, tokenize_path
from .realization_envelope import (
    _UNRESOLVED,
    RelationResult,
    _closed_extra_diagnostics,
    _diag,
    _envelope_r2_diagnostics,
    _member_constraint_diagnostics,
    _resolve_scope_value,
)


def _typed_children(value: object, typed: object) -> set[str] | None:
    if not isinstance(typed, BaseModel):
        return None
    children = present_children(typed)
    if isinstance(value, Mapping):
        # Safe commitments preserve logical presence without reconstructing raw
        # material. Their marker names are not extra SDL realization dimensions.
        for key, present in value.items():
            field = key.removesuffix("_present")
            if key.endswith("_present") and present is True and field in type(typed).model_fields:
                children.add(field)
    return children


def projected_member(
    value: object,
    field_path: str,
    envelope: RealizationEnvelopeModel,
    *,
    typed_value: object = None,
) -> RelationResult:
    """Use original safe values for domains, owner-validated types for closure.

    A typed value is only a presence view. It must have been reconstructed by
    the concern's existing validator from this safe value, never supplied as
    independently editable authority. It does not provide missing evidence.
    """

    invalid = _envelope_r2_diagnostics(envelope)
    if invalid:
        return RelationResult(False, invalid)
    prefix = tokenize_path(field_path)
    payload, shapes = {}, {}
    if assign_path(payload, prefix, value) is not None:
        return RelationResult(
            False, (_diag("membership.projection-unsupported", field_path, "Unsupported projection path"),)
        )
    assign_path(shapes, prefix, typed_value)
    constraints, closed = effective_constraints(envelope)
    selected = {path: rule for path, rule in constraints.items() if tokenize_path(path)[: len(prefix)] == prefix}
    diagnostics = _member_constraint_diagnostics(payload, selected)
    for path, admitted in closed.items():
        tokens = tokenize_path(path) if path else []
        if prefix[: len(tokens)] != tokens and tokens[: len(prefix)] != prefix:
            continue
        actual = _resolve_scope_value(payload, path)
        if actual is not _UNRESOLVED:
            shape = _resolve_scope_value(shapes, path)
            diagnostics.extend(
                _closed_extra_diagnostics(path, actual, admitted, children=_typed_children(actual, shape))
            )
    return RelationResult(not diagnostics, tuple(diagnostics))
