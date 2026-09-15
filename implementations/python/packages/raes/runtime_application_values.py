"""Sensitivity-governed values exposed through runtime application routes."""

from pydantic import ConfigDict, field_validator, model_validator

from ._base import SDLModel
from .runtime_filesystem import RuntimeSensitivityClassification, redacted_raw_value_schema
from .runtime_values import enforce_observed_value_redaction, parse_runtime_enum_or_var
from .runtime_vocabulary import GovernedVocabulary

_REDACTED_SENSITIVITIES = (
    RuntimeSensitivityClassification.REDACTED,
    RuntimeSensitivityClassification.OPERATOR_SECRET,
)


class RuntimeApplicationExposedField(SDLModel):
    """A route-visible fixture secret or intentionally exposed diagnostic field.

    The sensitivity vocabulary is shared with the rest of the runtime surface.
    A ``redacted`` or ``operator_secret`` field must omit its raw ``value``.
    Other values, including credential-shaped fixture facts, are scenario
    content needed for range realization and participant observation.
    """

    model_config = ConfigDict(
        json_schema_extra=redacted_raw_value_schema(
            sensitivity_field="sensitivity",
            raw_field="value",
            raw_value_schema={"type": "string", "minLength": 1},
        )
    )

    name: str
    sensitivity: GovernedVocabulary[RuntimeSensitivityClassification] = RuntimeSensitivityClassification.UNKNOWN
    value: str = ""
    description: str = ""

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip():
            raise ValueError("exposed field name must be a non-empty string")
        return v

    @field_validator("sensitivity", mode="before")
    @classmethod
    def normalize_sensitivity(
        cls,
        v: RuntimeSensitivityClassification | str,
    ) -> RuntimeSensitivityClassification | str:
        return parse_runtime_enum_or_var(v, RuntimeSensitivityClassification, field_name="sensitivity")

    @model_validator(mode="after")
    def validate_redacted_value(self) -> "RuntimeApplicationExposedField":
        enforce_observed_value_redaction(
            owner_label=f"exposed field '{self.name}'",
            value=self.value,
            classification=self.sensitivity,
            redacted_classifications=_REDACTED_SENSITIVITIES,
        )
        return self
