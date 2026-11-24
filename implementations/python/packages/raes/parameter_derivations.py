"""Capture and lower portable public scalar substitution evidence."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Annotated, Literal

from pydantic import BaseModel, Field, model_validator
from raes_contracts.identifiers import PortableIdentifier, QualifiedName
from raes_contracts.json_pointer import unescape_token
from raes_contracts.realization_structure import DEFAULT_REALIZATION_CONSTRAINT_LIMITS, validate_realization_value
from raes_contracts.variable_references import VARIABLE_TOKEN_RE, contains_variable_token

from ._capability_binding_normalization import normalize_capability_binding
from ._phase_base import JSON_POINTER_RE as _JSON_POINTER_RE
from ._phase_base import FrozenPhaseModel, JSONScalar
from ._phase_base import json_value_equal as _json_value_equal
from .variables import Variable, VariableType, _matches_variable_type


class ParameterLiteralSegment(FrozenPhaseModel):
    """Literal part of a substitution, without unresolved token syntax."""

    kind: Literal["literal"]
    value: str = Field(max_length=4096)


class ParameterReferenceSegment(FrozenPhaseModel):
    """One typed input, distinct from the derived field's output."""

    kind: Literal["parameter"]
    parameter: tuple[PortableIdentifier, ...] = Field(min_length=1, max_length=32)
    variable_type: VariableType
    allowed_values: tuple[JSONScalar, ...] = ()

    @model_validator(mode="after")
    def _validate_values(self) -> ParameterReferenceSegment:
        if any(not _matches_variable_type(value, self.variable_type) for value in self.allowed_values):
            raise ValueError("derivation alternatives must match the declared input type")
        return self


ParameterSegment = Annotated[ParameterLiteralSegment | ParameterReferenceSegment, Field(discriminator="kind")]


class ParameterDerivation(FrozenPhaseModel):
    """Portable substitution evidence for a publication-safe runtime scalar.

    A whole-field reference preserves its input type; an interpolation renders
    each input with the incumbent single-pass string conversion. An input with
    no finite domain binds its selected value, not all values of its type.
    """

    field_pointer: str = Field(max_length=4096, pattern=r"^/nodes/[^/]+/runtime/")
    segments: tuple[ParameterSegment, ...] = Field(min_length=1, max_length=128)

    @model_validator(mode="after")
    def _validate_segments(self) -> ParameterDerivation:

        if _JSON_POINTER_RE.fullmatch(self.field_pointer) is None:
            raise ValueError("derivation field_pointer must be an RFC 6901 JSON Pointer")
        QualifiedName.parse(unescape_token(self.field_pointer.split("/")[2]))
        references = [segment for segment in self.segments if isinstance(segment, ParameterReferenceSegment)]
        if not references:
            raise ValueError("parameter derivation must reference an input")
        declarations: dict[tuple[str, ...], ParameterReferenceSegment] = {}
        for segment in references:
            if declarations.setdefault(segment.parameter, segment) != segment:
                raise ValueError("derivation references must agree on the input declaration")
        if any(
            isinstance(segment, ParameterLiteralSegment) and contains_variable_token(segment.value)
            for segment in self.segments
        ):
            raise ValueError("derivation literals must not contain unresolved tokens")
        return self

    def resolve(self, bindings: Mapping[tuple[str, ...], JSONScalar]) -> JSONScalar:
        """Validate inputs and reproduce the selected concrete output."""

        inputs = {
            segment.parameter: segment for segment in self.segments if isinstance(segment, ParameterReferenceSegment)
        }
        for segment in inputs.values():
            if segment.parameter not in bindings:
                raise ValueError("parameter derivation references an unresolved input")
            value = bindings[segment.parameter]
            if not _matches_variable_type(value, segment.variable_type):
                raise ValueError("parameter derivation binding does not match its declared type")
            if segment.allowed_values and not any(
                _json_value_equal(value, member) for member in segment.allowed_values
            ):
                raise ValueError("parameter derivation binding is outside its input domain")
        return self._render(bindings)

    def _render(self, bindings: Mapping[tuple[str, ...], JSONScalar]) -> JSONScalar:
        """Single-pass rendering after the caller has validated the input set."""

        values = [
            segment.value if isinstance(segment, ParameterLiteralSegment) else bindings[segment.parameter]
            for segment in self.segments
        ]
        return (
            values[0]
            if len(self.segments) == 1 and isinstance(self.segments[0], ParameterReferenceSegment)
            else "".join(map(str, values))
        )


def _is_whole_finite_reference(value: str, variables: Mapping[str, Variable]) -> bool:
    match = VARIABLE_TOKEN_RE.fullmatch(value)
    variable = variables.get(match.group(1)) if match is not None else None
    return variable is not None and bool(variable.allowed_values)


def capture_parameter_derivation(
    *, field_pointer: str, value: object, variables: Mapping[str, Variable]
) -> ParameterDerivation | None:
    if not isinstance(value, str):
        return None
    matches = list(VARIABLE_TOKEN_RE.finditer(value))
    if (
        not matches
        or any(match.group(1) not in variables for match in matches)
        or _is_whole_finite_reference(value, variables)
    ):
        # The incumbent whole-field finite constraint retains its full domain.
        return None
    segments: list[ParameterLiteralSegment | ParameterReferenceSegment] = []
    offset = 0
    for match in matches:
        if match.start() > offset:
            segments.append(ParameterLiteralSegment(kind="literal", value=value[offset : match.start()]))
        name = match.group(1)
        variable = variables[name]
        segments.append(
            ParameterReferenceSegment(
                kind="parameter",
                parameter=(name,),
                variable_type=variable.type,
                allowed_values=tuple(variable.allowed_values),
            )
        )
        offset = match.end()
    if offset < len(value):
        segments.append(ParameterLiteralSegment(kind="literal", value=value[offset:]))
    return ParameterDerivation(field_pointer=field_pointer, segments=tuple(segments))


def _render_bounded_alternative(
    derivation: ParameterDerivation,
    identity: tuple[str, ...],
    value: JSONScalar,
    scenario: BaseModel | None,
) -> object:
    if not validate_realization_value(value).conformant:
        raise ValueError("finite derivation input exceeds the scalar budget")
    # The reference model has validated every declared alternative. Reusing
    # resolve here would scan the same domain for each member, quadratically.
    rendered = derivation._render({identity: value})
    if scenario is not None:
        rendered = normalize_capability_binding(scenario, derivation.field_pointer, rendered)
    if not validate_realization_value(rendered).conformant:
        raise ValueError("finite derivation output exceeds the scalar budget")
    return rendered


def finite_derivation_image(
    derivation: ParameterDerivation, *, scenario: BaseModel | None = None
) -> tuple[object, ...] | None:
    """Transform a single finite input without a Cartesian-product expansion.

    Repeated references share one binding. Unenumerated inputs bind the selected
    output; multiple independently finite inputs require a richer image domain.
    """

    inputs = {
        segment.parameter: segment for segment in derivation.segments if isinstance(segment, ParameterReferenceSegment)
    }
    if any(not reference.allowed_values for reference in inputs.values()):
        return None
    if len(inputs) != 1:
        raise ValueError("multi-input finite images are not representable")
    identity, reference = next(iter(inputs.items()))
    limits = DEFAULT_REALIZATION_CONSTRAINT_LIMITS
    if len(reference.allowed_values) > limits.max_members:
        raise ValueError("finite derivation image exceeds the member budget")
    values: list[object] = []
    seen: set[tuple[type, object]] = set()
    total_bytes = 0
    for value in reference.allowed_values:
        rendered = _render_bounded_alternative(derivation, identity, value, scenario)
        key = (type(rendered), rendered)
        if key not in seen:
            seen.add(key)
            total_bytes += len(str(rendered).encode("utf-8"))
            if total_bytes > limits.max_total_scalar_bytes:
                raise ValueError("finite derivation image exceeds the total scalar budget")
            values.append(rendered)
    return tuple(values)
