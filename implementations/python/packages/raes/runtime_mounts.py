"""Runtime mount and local control interface models."""

from enum import Enum

from pydantic import Field, GetJsonSchemaHandler, ValidationInfo, field_validator, model_validator
from pydantic.json_schema import JsonSchemaValue
from pydantic_core import CoreSchema

from raes.runtime_vocabulary import GovernedVocabulary

from ._base import SDLModel, is_variable_ref, parse_bool_or_var
from .runtime_filesystem import (
    RuntimeFilesystemStability,
    RuntimeMountPropagation,
    RuntimeSensitivityClassification,
    redacted_raw_value_schema,
)
from .runtime_values import (
    absolute_path_or_var as _absolute_path_or_var,
)
from .runtime_values import (
    control_interface_path_or_var as _control_interface_path_or_var,
)
from .runtime_values import (
    is_windows_named_pipe as _is_windows_named_pipe,
)
from .runtime_values import (
    parse_optional_bool_or_var as _parse_optional_bool_or_var,
)
from .runtime_values import (
    parse_runtime_enum_or_var as _parse_runtime_enum_or_var,
)
from .runtime_values import (
    require_symbol as _require_symbol,
)

__all__ = [
    "RuntimeControlInterface",
    "RuntimeControlInterfaceAccess",
    "RuntimeControlInterfaceKind",
    "RuntimeMount",
    "RuntimeMountSourceKind",
]


class RuntimeMountSourceKind(str, Enum):
    """Portable source kind for a runtime filesystem mount."""

    VOLUME = "volume"
    BIND = "bind"
    TMPFS = "tmpfs"
    IMAGE = "image"
    OTHER = "other"
    UNKNOWN = "unknown"


class RuntimeControlInterfaceKind(str, Enum):
    """Path-local control interface shape observed at runtime."""

    UNIX_SOCKET = "unix_socket"
    NAMED_PIPE = "named_pipe"
    FILE = "file"
    OTHER = "other"
    UNKNOWN = "unknown"


class RuntimeControlInterfaceAccess(str, Enum):
    """Observed local-control access mode."""

    READ_ONLY = "read_only"
    READ_WRITE = "read_write"
    UNKNOWN = "unknown"
    OTHER = "other"


class RuntimeMount(SDLModel):
    """A filesystem mount observed on a runtime node."""

    target: str
    source: str = ""
    source_sensitivity: GovernedVocabulary[RuntimeSensitivityClassification] = RuntimeSensitivityClassification.UNKNOWN
    source_kind: GovernedVocabulary[RuntimeMountSourceKind] = RuntimeMountSourceKind.OTHER
    filesystem_type: str = ""
    read_only: bool | str = False
    options: list[str] = Field(default_factory=list)
    options_sensitivity: GovernedVocabulary[RuntimeSensitivityClassification] = RuntimeSensitivityClassification.UNKNOWN
    propagation: GovernedVocabulary[RuntimeMountPropagation] = RuntimeMountPropagation.UNKNOWN
    stability: GovernedVocabulary[RuntimeFilesystemStability] = RuntimeFilesystemStability.UNKNOWN
    backend_generated: bool | str | None = None
    description: str = ""

    @field_validator("target")
    @classmethod
    def validate_target(cls, v: str) -> str:
        return _absolute_path_or_var(v, field_name="target")

    @field_validator("source_sensitivity", "options_sensitivity", mode="before")
    @classmethod
    def normalize_mount_sensitivity(
        cls,
        v: RuntimeSensitivityClassification | str,
        info: ValidationInfo,
    ) -> RuntimeSensitivityClassification | str:
        return _parse_runtime_enum_or_var(v, RuntimeSensitivityClassification, field_name=info.field_name)

    @field_validator("source_kind", mode="before")
    @classmethod
    def normalize_source_kind(cls, v: RuntimeMountSourceKind | str) -> RuntimeMountSourceKind | str:
        return _parse_runtime_enum_or_var(v, RuntimeMountSourceKind, field_name="source_kind")

    @field_validator("read_only", mode="before")
    @classmethod
    def parse_read_only(cls, v: bool | str) -> bool | str:
        return parse_bool_or_var(v, field_name="read_only")

    @field_validator("propagation", mode="before")
    @classmethod
    def normalize_propagation(cls, v: RuntimeMountPropagation | str) -> RuntimeMountPropagation | str:
        return _parse_runtime_enum_or_var(v, RuntimeMountPropagation, field_name="propagation")

    @field_validator("stability", mode="before")
    @classmethod
    def normalize_stability(cls, v: RuntimeFilesystemStability | str) -> RuntimeFilesystemStability | str:
        return _parse_runtime_enum_or_var(v, RuntimeFilesystemStability, field_name="stability")

    @field_validator("backend_generated", mode="before")
    @classmethod
    def parse_backend_generated(cls, v: bool | str | None) -> bool | str | None:
        return _parse_optional_bool_or_var(v, field_name="backend_generated")

    @model_validator(mode="after")
    def validate_redacted_mount_details(self) -> "RuntimeMount":
        if (
            self.source_sensitivity
            in {
                RuntimeSensitivityClassification.REDACTED,
                RuntimeSensitivityClassification.OPERATOR_SECRET,
            }
            and self.source
        ):
            raise ValueError("redacted runtime mount source must omit source")
        if (
            self.options_sensitivity
            in {
                RuntimeSensitivityClassification.REDACTED,
                RuntimeSensitivityClassification.OPERATOR_SECRET,
            }
            and self.options
        ):
            raise ValueError("redacted runtime mount options must omit options")
        return self

    @classmethod
    def __get_pydantic_json_schema__(
        cls,
        core_schema: CoreSchema,
        handler: GetJsonSchemaHandler,
    ) -> JsonSchemaValue:
        json_schema = handler(core_schema)
        json_schema = handler.resolve_ref_schema(json_schema)
        json_schema.setdefault("allOf", []).extend(
            [
                redacted_raw_value_schema(
                    sensitivity_field="source_sensitivity",
                    raw_field="source",
                    raw_value_schema={"type": "string", "minLength": 1},
                ),
                redacted_raw_value_schema(
                    sensitivity_field="options_sensitivity",
                    raw_field="options",
                    raw_value_schema={"type": "array", "minItems": 1},
                ),
            ]
        )
        return json_schema


class RuntimeControlInterface(SDLModel):
    """A non-network local control API exposed inside a runtime node."""

    control_interface_id: str
    path: str
    kind: GovernedVocabulary[RuntimeControlInterfaceKind] = RuntimeControlInterfaceKind.UNIX_SOCKET
    protocol: str = ""
    bind_source: str = ""
    bind_source_sensitivity: GovernedVocabulary[RuntimeSensitivityClassification] = (
        RuntimeSensitivityClassification.UNKNOWN
    )
    access: GovernedVocabulary[RuntimeControlInterfaceAccess] = RuntimeControlInterfaceAccess.UNKNOWN
    description: str = ""

    @field_validator("control_interface_id")
    @classmethod
    def validate_control_interface_id(cls, v: str) -> str:
        return _require_symbol(v, field_name="control_interface_id")

    @field_validator("path")
    @classmethod
    def validate_path(cls, v: str) -> str:
        return _control_interface_path_or_var(v, field_name="path")

    @field_validator("bind_source")
    @classmethod
    def validate_bind_source(cls, v: str) -> str:
        return _control_interface_path_or_var(v, field_name="bind_source") if v else v

    @field_validator("bind_source_sensitivity", mode="before")
    @classmethod
    def normalize_bind_source_sensitivity(
        cls,
        v: RuntimeSensitivityClassification | str,
    ) -> RuntimeSensitivityClassification | str:
        return _parse_runtime_enum_or_var(
            v,
            RuntimeSensitivityClassification,
            field_name="bind_source_sensitivity",
        )

    @field_validator("kind", mode="before")
    @classmethod
    def normalize_kind(cls, v: RuntimeControlInterfaceKind | str) -> RuntimeControlInterfaceKind | str:
        return _parse_runtime_enum_or_var(v, RuntimeControlInterfaceKind, field_name="kind")

    @field_validator("access", mode="before")
    @classmethod
    def normalize_access(cls, v: RuntimeControlInterfaceAccess | str) -> RuntimeControlInterfaceAccess | str:
        return _parse_runtime_enum_or_var(v, RuntimeControlInterfaceAccess, field_name="access")

    @model_validator(mode="after")
    def validate_redacted_bind_source_and_named_pipe_kind(self) -> "RuntimeControlInterface":
        if (
            self.bind_source_sensitivity
            in {
                RuntimeSensitivityClassification.REDACTED,
                RuntimeSensitivityClassification.OPERATOR_SECRET,
            }
            and self.bind_source
        ):
            raise ValueError("redacted runtime control interface bind_source must omit bind_source")
        if is_variable_ref(self.kind):
            return self
        has_windows_named_pipe_endpoint = _is_windows_named_pipe(self.path) or _is_windows_named_pipe(self.bind_source)
        if has_windows_named_pipe_endpoint and self.kind != RuntimeControlInterfaceKind.NAMED_PIPE:
            raise ValueError("Windows named pipe paths require kind 'named_pipe'")
        return self

    @classmethod
    def __get_pydantic_json_schema__(
        cls,
        core_schema: CoreSchema,
        handler: GetJsonSchemaHandler,
    ) -> JsonSchemaValue:
        json_schema = handler(core_schema)
        json_schema = handler.resolve_ref_schema(json_schema)
        json_schema.setdefault("allOf", []).append(
            redacted_raw_value_schema(
                sensitivity_field="bind_source_sensitivity",
                raw_field="bind_source",
                raw_value_schema={"type": "string", "minLength": 1},
            )
        )
        return json_schema
