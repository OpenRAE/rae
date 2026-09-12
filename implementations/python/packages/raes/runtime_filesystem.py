"""Observed runtime filesystem inventory models for SDL nodes."""

import re
from enum import Enum

from pydantic import ValidationInfo, field_validator, model_validator

from raes.runtime_vocabulary import GovernedVocabulary

from ._base import SDLModel, is_variable_ref, parse_int_or_var
from .runtime_values import absolute_path_or_var, parse_runtime_enum_or_var


class RuntimeMountPropagation(str, Enum):
    """Portable propagation mode for a runtime filesystem mount."""

    PRIVATE = "private"
    RPRIVATE = "rprivate"
    SHARED = "shared"
    RSHARED = "rshared"
    SLAVE = "slave"
    RSLAVE = "rslave"
    UNKNOWN = "unknown"
    OTHER = "other"


class RuntimeFilesystemEntryType(str, Enum):
    """Observed type of a runtime filesystem inventory entry."""

    FILE = "file"
    DIRECTORY = "directory"
    SYMLINK = "symlink"
    DEVICE = "device"
    SOCKET = "socket"
    FIFO = "fifo"
    OTHER = "other"
    UNKNOWN = "unknown"


class RuntimeFilesystemPresence(str, Enum):
    """Observed presence state for a runtime filesystem inventory entry.

    ``present`` is the default and preserves prior behavior. ``expected_absent``
    records an authored or expected path that was not observed at capture time —
    for example a deploy-key path attempted by setup code but missing in the
    captured steady state. Absent entries retain their expected ``entry_type``
    instead of collapsing to ``other``; present-only facts (size, content
    digest, owner ids, mode) must be omitted, per ADR-037.
    """

    PRESENT = "present"
    EXPECTED_ABSENT = "expected_absent"
    UNKNOWN = "unknown"
    OTHER = "other"


class RuntimeFilesystemStability(str, Enum):
    """Stability class for an observed runtime filesystem or mount fact."""

    STABLE = "stable"
    GENERATED = "generated"
    LOG = "log"
    CACHE = "cache"
    RUNTIME_CREATED = "runtime_created"
    VOLUME_BACKED = "volume_backed"
    TRANSIENT = "transient"
    UNKNOWN = "unknown"
    OTHER = "other"


class RuntimeSensitivityClassification(str, Enum):
    """Sensitivity/redaction class for observed runtime facts."""

    PLAIN = "plain"
    REDACTED = "redacted"
    SECRET_FIXTURE = "secret_fixture"  # noqa: S105
    OPERATOR_SECRET = "operator_secret"  # noqa: S105
    UNKNOWN = "unknown"
    OTHER = "other"


_REDACTED_LABEL_PATTERN = r"^[Rr][Ee][Dd][Aa][Cc][Tt][Ee][Dd]$"
_OPERATOR_SECRET_LABEL_PATTERN = r"^[Oo][Pp][Ee][Rr][Aa][Tt][Oo][Rr][_-][Ss][Ee][Cc][Rr][Ee][Tt]$"  # noqa: S105


def redacted_raw_value_schema(
    *,
    sensitivity_field: str,
    raw_field: str,
    raw_value_schema: dict[str, object],
) -> dict[str, object]:
    return {
        "if": {
            "properties": {
                sensitivity_field: {
                    "anyOf": [
                        {"type": "string", "pattern": _REDACTED_LABEL_PATTERN},
                        {"type": "string", "pattern": _OPERATOR_SECRET_LABEL_PATTERN},
                    ]
                }
            },
            "required": [sensitivity_field],
        },
        "then": {
            "not": {
                "required": [raw_field],
                "properties": {raw_field: raw_value_schema},
            }
        },
    }


_PRESENT_ONLY_FIELDS: tuple[str, ...] = (
    "owner_user",
    "owner_group",
    "uid",
    "gid",
    "mode",
    "size",
    "content_digest",
    "digest_algorithm",
)


class RuntimeFilesystemEntry(SDLModel):
    """A filesystem entry observed inside a runtime node or container asset."""

    path: str
    entry_type: GovernedVocabulary[RuntimeFilesystemEntryType] = RuntimeFilesystemEntryType.OTHER
    presence: GovernedVocabulary[RuntimeFilesystemPresence] = RuntimeFilesystemPresence.PRESENT
    owner_user: str = ""
    owner_group: str = ""
    uid: int | str | None = None
    gid: int | str | None = None
    mode: str = ""
    size: int | str | None = None
    content_digest: str = ""
    digest_algorithm: str = ""
    source_path: str = ""
    provenance: str = ""
    stability: GovernedVocabulary[RuntimeFilesystemStability] = RuntimeFilesystemStability.UNKNOWN
    sensitivity: GovernedVocabulary[RuntimeSensitivityClassification] = RuntimeSensitivityClassification.UNKNOWN
    description: str = ""

    @field_validator("path")
    @classmethod
    def validate_path(cls, v: str) -> str:
        return absolute_path_or_var(v, field_name="path")

    @field_validator("entry_type", mode="before")
    @classmethod
    def normalize_entry_type(cls, v: RuntimeFilesystemEntryType | str) -> RuntimeFilesystemEntryType | str:
        return parse_runtime_enum_or_var(v, RuntimeFilesystemEntryType, field_name="entry_type")

    @field_validator("presence", mode="before")
    @classmethod
    def normalize_presence(cls, v: RuntimeFilesystemPresence | str) -> RuntimeFilesystemPresence | str:
        return parse_runtime_enum_or_var(v, RuntimeFilesystemPresence, field_name="presence")

    @field_validator("uid", "gid", mode="before")
    @classmethod
    def parse_identity_id(cls, v: int | str | None, info: ValidationInfo) -> int | str | None:
        return parse_int_or_var(v, minimum=0, field_name=info.field_name) if v is not None else v

    @field_validator("mode", mode="before")
    @classmethod
    def validate_mode(cls, v: str | int) -> str:
        if v is None or v == "" or is_variable_ref(v):
            return v
        if isinstance(v, bool):
            raise ValueError("mode must be octal permission bits")
        if isinstance(v, int):
            if 0 <= v <= 0o7777:
                return f"{v:04o}"
            raise ValueError("mode must be octal permission bits")
        text = str(v).strip()
        if re.fullmatch(r"(0o)?[0-7]{3,4}", text):
            return text
        raise ValueError("mode must be octal permission bits")

    @field_validator("size", mode="before")
    @classmethod
    def parse_size(cls, v: int | str | None) -> int | str | None:
        return parse_int_or_var(v, minimum=0, field_name="size") if v is not None else v

    @field_validator("stability", mode="before")
    @classmethod
    def normalize_stability(cls, v: RuntimeFilesystemStability | str) -> RuntimeFilesystemStability | str:
        return parse_runtime_enum_or_var(v, RuntimeFilesystemStability, field_name="stability")

    @field_validator("sensitivity", mode="before")
    @classmethod
    def normalize_sensitivity(
        cls,
        v: RuntimeSensitivityClassification | str,
    ) -> RuntimeSensitivityClassification | str:
        return parse_runtime_enum_or_var(v, RuntimeSensitivityClassification, field_name="sensitivity")

    @model_validator(mode="after")
    def validate_digest_pair(self) -> "RuntimeFilesystemEntry":
        if self.content_digest and not self.digest_algorithm:
            raise ValueError("content_digest requires digest_algorithm")
        if self.digest_algorithm and not self.content_digest:
            raise ValueError("digest_algorithm requires content_digest")
        return self

    @model_validator(mode="after")
    def validate_presence(self) -> "RuntimeFilesystemEntry":
        if self.presence != RuntimeFilesystemPresence.EXPECTED_ABSENT:
            return self
        for field_name in _PRESENT_ONLY_FIELDS:
            value = getattr(self, field_name)
            if value not in ("", None):
                raise ValueError(
                    f"filesystem entry '{self.path}' with presence 'expected_absent' must omit '{field_name}'"
                )
        return self
