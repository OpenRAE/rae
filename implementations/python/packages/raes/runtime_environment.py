"""Runtime environment value and generated environment-file contracts."""

from enum import Enum

from pydantic import Field, GetJsonSchemaHandler, field_validator, model_validator
from pydantic.json_schema import JsonSchemaValue
from pydantic_core import CoreSchema

from raes.runtime_vocabulary import GovernedVocabulary

from ._base import SDLModel
from .runtime_generated_value import (
    GeneratedArtifactValueSource,
    RuntimeEnvironmentFile,
    value_from_schema_exclusions,
)
from .runtime_values import enforce_observed_value_redaction
from .runtime_values import parse_runtime_enum_or_var as _parse_runtime_enum_or_var


class RuntimeEnvironmentValueClassification(str, Enum):
    """Sensitivity classification for a required runtime environment value."""

    PLAIN = "plain"
    REDACTED = "redacted"
    SECRET_FIXTURE = "secret_fixture"  # noqa: S105
    OPERATOR_SECRET = "operator_secret"  # noqa: S105
    UNKNOWN = "unknown"
    OTHER = "other"


_ENV_REDACTED_CLASSIFICATIONS = (
    RuntimeEnvironmentValueClassification.REDACTED,
    RuntimeEnvironmentValueClassification.OPERATOR_SECRET,
)


class RuntimeEnvironmentVariableProvenance(str, Enum):
    """Required origin class for a runtime environment variable."""

    COMPOSE = "compose"
    IMAGE = "image"
    OPERATOR = "operator"
    CONTAINER = "container"
    RUNTIME = "runtime"
    OTHER = "other"
    UNKNOWN = "unknown"


class RuntimeEnvironmentVariable(SDLModel):
    """Required runtime environment variable with provenance and sensitivity."""

    name: str
    value: str = ""
    value_from: GeneratedArtifactValueSource | None = Field(default=None, exclude_if=lambda v: v is None)
    value_classification: GovernedVocabulary[RuntimeEnvironmentValueClassification] = (
        RuntimeEnvironmentValueClassification.UNKNOWN
    )
    provenance: GovernedVocabulary[RuntimeEnvironmentVariableProvenance] = RuntimeEnvironmentVariableProvenance.UNKNOWN
    source: str = ""
    description: str = ""

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip():
            raise ValueError("environment variable name must be a non-empty string")
        if "=" in v:
            raise ValueError("environment variable name must not contain '='")
        return v

    @model_validator(mode="after")
    def validate_value_from_exclusivity(self) -> "RuntimeEnvironmentVariable":
        if self.value_from is not None:
            if self.value:
                raise ValueError(
                    "runtime environment variable must not set both a literal value and value_from; "
                    "a generated-artifact value is realized from the referenced output"
                )
            # `operator_secret` is reserved for out-of-SDL operator-controlled
            # material; a generated-artifact value is realized in-band and must
            # not claim that classification.
            if self.value_classification is RuntimeEnvironmentValueClassification.OPERATOR_SECRET:
                raise ValueError(
                    "runtime environment variable with value_from must not be classified operator_secret; "
                    "a generated-artifact value is not out-of-SDL operator material"
                )
        return self

    @field_validator("value_classification", mode="before")
    @classmethod
    def normalize_value_classification(
        cls,
        v: RuntimeEnvironmentValueClassification | str,
    ) -> RuntimeEnvironmentValueClassification | str:
        return _parse_runtime_enum_or_var(
            v,
            RuntimeEnvironmentValueClassification,
            field_name="value_classification",
        )

    @field_validator("provenance", mode="before")
    @classmethod
    def normalize_provenance(
        cls,
        v: RuntimeEnvironmentVariableProvenance | str,
    ) -> RuntimeEnvironmentVariableProvenance | str:
        return _parse_runtime_enum_or_var(v, RuntimeEnvironmentVariableProvenance, field_name="provenance")

    @model_validator(mode="after")
    def validate_redacted_value(self) -> "RuntimeEnvironmentVariable":
        enforce_observed_value_redaction(
            owner_label=f"runtime environment variable '{self.name}'",
            value=self.value,
            classification=self.value_classification,
            redacted_classifications=_ENV_REDACTED_CLASSIFICATIONS,
            raw_value_label="value",
        )
        return self

    @classmethod
    def __get_pydantic_json_schema__(
        cls,
        core_schema: CoreSchema,
        handler: GetJsonSchemaHandler,
    ) -> JsonSchemaValue:
        # Publish the model's value_from cross-field exclusions so schema-only
        # consumers reject the same payloads the Python model rejects (issue #1074).
        json_schema = handler(core_schema)
        json_schema = handler.resolve_ref_schema(json_schema)
        json_schema.setdefault("allOf", []).extend(value_from_schema_exclusions())
        return json_schema


__all__ = [
    "GeneratedArtifactValueSource",
    "RuntimeEnvironmentFile",
    "RuntimeEnvironmentValueClassification",
    "RuntimeEnvironmentVariable",
    "RuntimeEnvironmentVariableProvenance",
]
