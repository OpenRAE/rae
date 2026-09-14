"""Backend-neutral proposition and assertion authoring models."""

from __future__ import annotations

import math
from enum import Enum
from typing import Annotated, Literal

from pydantic import (
    Field,
    GetJsonSchemaHandler,
    StrictBool,
    StrictFloat,
    StrictInt,
    StrictStr,
    field_validator,
    model_validator,
)
from pydantic.json_schema import JsonSchemaValue
from pydantic_core import CoreSchema

from ._base import SDLModel
from .runtime_generated_value import GeneratedArtifactValueSource


def _string_predicate_operand_exclusions() -> list[dict[str, object]]:
    """Published-schema ``allOf`` encoding the exactly-one operand rule (issue #1276).

    Mirrors the Python model's requirement that a string predicate declare exactly
    one of ``expected`` or ``expected_from``, so schema-only consumers reject a
    predicate with neither operand or both.
    """

    present_expected = {"required": ["expected"], "properties": {"expected": {"not": {"type": "null"}}}}
    present_expected_from = {
        "required": ["expected_from"],
        "properties": {"expected_from": {"not": {"type": "null"}}},
    }
    return [
        {"anyOf": [present_expected, present_expected_from]},
        {"not": {"allOf": [present_expected, present_expected_from]}},
    ]


ObservableProperty = Annotated[
    str,
    Field(
        min_length=1,
        max_length=512,
        pattern=r"^[a-z0-9][a-z0-9_-]{0,63}(?:\.[a-z0-9][a-z0-9_-]{0,63})*$",
    ),
]
SemanticReference = Annotated[
    str,
    Field(
        min_length=1,
        max_length=2048,
        pattern=r"^(?:https://[^\s]+|urn:[A-Za-z0-9][A-Za-z0-9:._~-]*)$",
    ),
]


class PropositionBasis(str, Enum):
    """Source of facts that may decide a proposition."""

    DECLARED_STATE = "declared_state"
    OBSERVED_STATE = "observed_state"


class SubjectQuantifier(str, Enum):
    """Quantification over a proposition's finite, resolved subject set."""

    ALL = "all"
    ANY = "any"
    AT_LEAST = "at_least"


class AssertionRole(str, Enum):
    """Boundary at which an assertion constrains its owning construct."""

    PRECONDITION = "precondition"
    INVARIANT = "invariant"
    POSTCONDITION = "postcondition"


class AssertionPolarity(str, Enum):
    """Expected polarity of the referenced proposition."""

    POSITIVE = "positive"
    NEGATIVE = "negative"


class TruthCompositionMode(str, Enum):
    """Portable composition over assertion outcomes."""

    ALL_OF = "all_of"
    ANY_OF = "any_of"
    AT_LEAST = "at_least"


class PresencePredicate(SDLModel):
    """Test whether a governed property is present on a subject."""

    kind: Literal["presence"] = "presence"
    property: ObservableProperty
    semantic_ref: SemanticReference
    operator: Literal["exists"] = "exists"


class BooleanPredicate(SDLModel):
    """Compare a governed Boolean property with an expected Boolean."""

    kind: Literal["boolean"] = "boolean"
    property: ObservableProperty
    semantic_ref: SemanticReference
    operator: Literal["equals", "not_equals"] = "equals"
    expected: StrictBool


class StringPredicate(SDLModel):
    """Compare a governed string property with typed string operands."""

    kind: Literal["string"] = "string"
    property: ObservableProperty
    semantic_ref: SemanticReference
    operator: Literal["equals", "not_equals", "in", "not_in"] = "equals"
    expected: StrictStr | list[StrictStr] | None = None
    # Deferred expected value resolved from a generated-artifact output at the
    # backend comparison boundary (issue #1276), so a submission can be checked
    # against a generated secret without the value appearing in the SDL or plan.
    expected_from: GeneratedArtifactValueSource | None = Field(default=None, exclude_if=lambda value: value is None)

    @model_validator(mode="after")
    def validate_operand_shape(self) -> StringPredicate:
        if (self.expected is None) == (self.expected_from is None):
            raise ValueError("string predicate requires exactly one of 'expected' or 'expected_from'")
        membership = self.operator in {"in", "not_in"}
        if self.expected_from is not None:
            # A deferred single generated value only supports scalar comparison.
            if membership:
                raise ValueError(f"string operator {self.operator!r} cannot use expected_from")
            return self
        if membership and not isinstance(self.expected, list):
            raise ValueError(f"string operator {self.operator!r} requires a list operand")
        if not membership and isinstance(self.expected, list):
            raise ValueError(f"string operator {self.operator!r} requires a scalar operand")
        if isinstance(self.expected, list) and (not self.expected or len(set(self.expected)) != len(self.expected)):
            raise ValueError("string membership operands must be non-empty and unique")
        return self

    @classmethod
    def __get_pydantic_json_schema__(cls, core_schema: CoreSchema, handler: GetJsonSchemaHandler) -> JsonSchemaValue:
        json_schema = handler(core_schema)
        json_schema = handler.resolve_ref_schema(json_schema)
        json_schema.setdefault("allOf", []).extend(_string_predicate_operand_exclusions())
        return json_schema


class NumericPredicate(SDLModel):
    """Compare a governed numeric property using an explicit unit."""

    kind: Literal["number"] = "number"
    property: ObservableProperty
    semantic_ref: SemanticReference
    operator: Literal[
        "equals",
        "not_equals",
        "less_than",
        "less_than_or_equal",
        "greater_than",
        "greater_than_or_equal",
    ] = "equals"
    expected: StrictInt | StrictFloat
    unit: ObservableProperty
    unit_semantic_ref: SemanticReference

    @field_validator("expected")
    @classmethod
    def reject_boolean_operand(cls, value: int | float) -> int | float:
        if isinstance(value, bool):
            raise ValueError("numeric predicate expected value must not be Boolean")
        if not math.isfinite(value):
            raise ValueError("numeric predicate expected value must be finite")
        return value


TypedPredicate = Annotated[
    PresencePredicate | BooleanPredicate | StringPredicate | NumericPredicate,
    Field(discriminator="kind"),
]


class Proposition(SDLModel):
    """A side-effect-free claim over a finite set of stable SDL subjects."""

    description: str = Field(min_length=1)
    subjects: list[str] = Field(min_length=1)
    basis: PropositionBasis
    predicate: TypedPredicate
    quantifier: SubjectQuantifier = SubjectQuantifier.ALL
    threshold: int | None = Field(default=None, ge=1)
    evidence_requirements: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_semantic_shape(self) -> Proposition:
        if len(set(self.subjects)) != len(self.subjects):
            raise ValueError("proposition subjects must be unique")
        if len(set(self.evidence_requirements)) != len(self.evidence_requirements):
            raise ValueError("proposition evidence requirements must be unique")
        if self.basis is PropositionBasis.OBSERVED_STATE and not self.evidence_requirements:
            raise ValueError("observed-state propositions require at least one evidence requirement")
        if self.quantifier is SubjectQuantifier.AT_LEAST:
            if self.threshold is None:
                raise ValueError("at_least quantification requires threshold")
            if self.threshold > len(self.subjects):
                raise ValueError("threshold cannot exceed the finite subject count")
        elif self.threshold is not None:
            raise ValueError("threshold is valid only for at_least quantification")
        return self


class Assertion(SDLModel):
    """A typed use of one proposition at a governed semantic boundary."""

    description: str = ""
    proposition: str
    role: AssertionRole
    polarity: AssertionPolarity = AssertionPolarity.POSITIVE
