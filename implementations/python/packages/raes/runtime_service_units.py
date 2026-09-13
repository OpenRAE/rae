"""Observed service-manager unit state models for SDL nodes.

These models express participant-observable service-manager (initially
``systemd``) unit lifecycle facts -- ``loaded``/``failed`` / ``active``/``exited`` /
``enabled``/``disabled``/``static``, observed PID, ``ExecStart`` evidence, and
optional same-node transport-service refs -- as typed runtime facts (see
ADR-035). They sit under ``Node.runtime.service_manager_units`` as observed
WHAT-IS state, distinct from authored ``features`` / ``conditions`` /
``Node.services``, from process inventory (``runtime.processes``), from
container-init configuration (``runtime.container.init_process``), from
orchestrator restart policy (``runtime.operational_policy.restart``), from
sshd policy (``runtime.ssh_servers``), and from package / software / filesystem
inventory.

The surface deliberately avoids carrying raw ``systemctl``, ``journalctl``, or
backend inspector payloads. ``ExecStart`` evidence is bounded and must be
classified ``redacted`` when the underlying command carries secret arguments.
"""

from enum import Enum

from pydantic import ValidationInfo, field_validator, model_validator

from raes.runtime_vocabulary import GovernedVocabulary

from ._base import (
    SDLModel,
    is_variable_ref,
    parse_bool_or_var,
    parse_int_or_var,
)
from .runtime_values import (
    absolute_path_or_var,
    parse_runtime_enum_or_var,
    require_symbol,
)

__all__ = [
    "ServiceManagerKind",
    "ServiceManagerUnit",
    "ServiceUnitActiveState",
    "ServiceUnitEnabledState",
    "ServiceUnitExecStart",
    "ServiceUnitExecStartKind",
    "ServiceUnitKind",
    "ServiceUnitLoadState",
    "ServiceUnitResult",
]


_SUB_STATE_MAX_LEN = 64
_STATUS_TEXT_MAX_LEN = 256
_EXIT_CODE_MIN = 0
_EXIT_CODE_MAX = 255


class ServiceManagerKind(str, Enum):
    """Kind of service manager whose unit inventory is being recorded.

    Initially scoped to ``systemd``; ``other`` is the escape hatch for managers
    that have not yet been promoted to their own typed enum value (per
    ADR-035 § 5).
    """

    SYSTEMD = "systemd"
    OTHER = "other"
    UNKNOWN = "unknown"


class ServiceUnitKind(str, Enum):
    """Type of service-manager unit (systemd unit kinds with ``other`` escape)."""

    SERVICE = "service"
    SOCKET = "socket"
    TARGET = "target"
    TIMER = "timer"
    PATH = "path"
    MOUNT = "mount"
    AUTOMOUNT = "automount"
    SWAP = "swap"
    DEVICE = "device"
    SLICE = "slice"
    SCOPE = "scope"
    OTHER = "other"
    UNKNOWN = "unknown"


class ServiceUnitLoadState(str, Enum):
    """Observed unit *load* state (``systemctl list-units`` LOAD column)."""

    LOADED = "loaded"
    NOT_FOUND = "not_found"
    MASKED = "masked"
    ERROR = "error"
    MERGED = "merged"
    STUB = "stub"
    BAD_SETTING = "bad_setting"
    UNKNOWN = "unknown"
    OTHER = "other"


class ServiceUnitActiveState(str, Enum):
    """Observed unit *active* state (``systemctl list-units`` ACTIVE column)."""

    ACTIVE = "active"
    RELOADING = "reloading"
    INACTIVE = "inactive"
    FAILED = "failed"
    ACTIVATING = "activating"
    DEACTIVATING = "deactivating"
    UNKNOWN = "unknown"
    OTHER = "other"


class ServiceUnitEnabledState(str, Enum):
    """Observed unit-file enable state (``systemctl is-enabled``)."""

    ENABLED = "enabled"
    ENABLED_RUNTIME = "enabled_runtime"
    DISABLED = "disabled"
    STATIC = "static"
    ALIAS = "alias"
    MASKED = "masked"
    GENERATED = "generated"
    INDIRECT = "indirect"
    TRANSIENT = "transient"
    UNKNOWN = "unknown"
    OTHER = "other"


class ServiceUnitResult(str, Enum):
    """Observed last-run unit result class (systemd ``Result=`` values)."""

    SUCCESS = "success"
    EXIT_CODE = "exit_code"
    SIGNAL = "signal"
    TIMEOUT = "timeout"
    WATCHDOG = "watchdog"
    OOM_KILL = "oom_kill"
    CORE_DUMP = "core_dump"
    START_LIMIT_HIT = "start_limit_hit"
    RESOURCES = "resources"
    PROTOCOL = "protocol"
    OTHER = "other"
    UNKNOWN = "unknown"


class ServiceUnitExecStartKind(str, Enum):
    """How a service-manager unit's ``ExecStart`` command is carried.

    ``absolute_path`` records a concrete executable path; ``redacted`` records
    that the underlying ``ExecStart`` carries secret-bearing arguments and is
    withheld from the SDL model.
    """

    ABSOLUTE_PATH = "absolute_path"
    REDACTED = "redacted"


def _validate_unit_name(value: str) -> str:
    """Validate a native service-manager unit name (e.g. ``sshd.service``).

    Unit names are participant-visible data, not stable RAES ids, but they
    must be concrete to be useful for duplicate detection and downstream
    consumers. ``${var}`` placeholders are rejected here; the model has a
    separate stable ``unit_id`` for that role.
    """
    if not isinstance(value, str):
        raise ValueError("unit_name must be a string")
    if is_variable_ref(value):
        raise ValueError("unit_name must be a concrete string, not a variable placeholder")
    if not value.strip():
        raise ValueError("unit_name must be a non-empty string")
    if any(ch.isspace() for ch in value):
        raise ValueError(f"unit_name '{value}' must not contain whitespace")
    if "." not in value:
        raise ValueError(
            f"unit_name '{value}' must include a unit-type suffix (e.g. '.service', '.socket')",
        )
    return value


class ServiceUnitExecStart(SDLModel):
    """A typed service-manager ``ExecStart`` configuration.

    Mirrors the SSH ``ForcedCommand`` redaction discipline (ADR-031): the
    ``command_kind`` discriminates how ``command`` is interpreted, and
    ``command_redacted=True`` forces ``command`` empty and
    ``command_kind=redacted``. The model never carries raw secret-bearing
    argv -- if the underlying ``ExecStart=`` includes credentials, tokens, or
    operator-only arguments, the surface stores only the redacted shape.
    """

    command_kind: GovernedVocabulary[ServiceUnitExecStartKind] = ServiceUnitExecStartKind.ABSOLUTE_PATH
    command: str = ""
    command_redacted: bool | str = False
    description: str = ""

    @field_validator("command_kind", mode="before")
    @classmethod
    def normalize_command_kind(
        cls,
        v: ServiceUnitExecStartKind | str,
    ) -> ServiceUnitExecStartKind | str:
        return parse_runtime_enum_or_var(v, ServiceUnitExecStartKind, field_name="command_kind")

    @field_validator("command_redacted", mode="before")
    @classmethod
    def parse_command_redacted(cls, v: bool | str) -> bool | str:
        return parse_bool_or_var(v, field_name="command_redacted")

    @model_validator(mode="after")
    def validate_command_shape(self) -> "ServiceUnitExecStart":
        # Enforce literal-field invariants before deferring on variable refs --
        # otherwise a variable ``command_kind`` or ``command_redacted`` could
        # smuggle a raw secret-bearing command through the model boundary.
        kind = self.command_kind
        redacted = self.command_redacted
        kind_is_var = isinstance(kind, str) and is_variable_ref(kind)
        redacted_is_var = isinstance(redacted, str) and is_variable_ref(redacted)
        self._enforce_redaction_consistency(kind_is_var=kind_is_var, redacted_is_var=redacted_is_var)
        if not (kind_is_var or redacted_is_var or redacted is True):
            self._enforce_concrete_kind_command_shape()
        return self

    def _enforce_redaction_consistency(self, *, kind_is_var: bool, redacted_is_var: bool) -> None:
        kind = self.command_kind
        command = self.command
        redacted = self.command_redacted
        if redacted is True:
            if command != "":
                raise ValueError("redacted exec_start must omit the command value")
            if not kind_is_var and kind != ServiceUnitExecStartKind.REDACTED:
                raise ValueError("command_redacted=true requires command_kind='redacted'")
        if not kind_is_var and kind == ServiceUnitExecStartKind.REDACTED:
            if command != "":
                raise ValueError("redacted exec_start must omit the command value")
            if not redacted_is_var and redacted is not True:
                raise ValueError("command_kind='redacted' requires command_redacted=true")

    def _enforce_concrete_kind_command_shape(self) -> None:
        kind = self.command_kind
        command = self.command
        if kind == ServiceUnitExecStartKind.ABSOLUTE_PATH:
            if not command:
                raise ValueError("absolute_path exec_start requires a non-empty command")
            absolute_path_or_var(command, field_name="command")


class ServiceManagerUnit(SDLModel):
    """Observed service-manager unit state on a realized range node.

    Each record carries a stable RAES ``unit_id`` (the reference target), the
    native ``unit_name`` (e.g. ``sshd.service``), the participant-observable
    lifecycle facts captured by ``systemctl`` (load/active/sub/enabled/result),
    and bounded optional evidence: the unit-file path, an ``ExecStart``
    descriptor with explicit redaction discipline, the main PID when present,
    and an optional same-node ``Node.services[]`` ref.

    This is observed WHAT-IS state, not provisioning intent or authored
    behavior; see ADR-035 for the boundary against ``Node.services``,
    ``conditions``, ``runtime.processes``, ``runtime.container.init_process``,
    ``runtime.operational_policy``, and ``runtime.ssh_servers``.
    """

    unit_id: str
    manager_kind: GovernedVocabulary[ServiceManagerKind] = ServiceManagerKind.SYSTEMD
    unit_name: str
    unit_type: GovernedVocabulary[ServiceUnitKind] = ServiceUnitKind.OTHER
    load_state: GovernedVocabulary[ServiceUnitLoadState] = ServiceUnitLoadState.UNKNOWN
    active_state: GovernedVocabulary[ServiceUnitActiveState] = ServiceUnitActiveState.UNKNOWN
    sub_state: str = ""
    enabled_state: GovernedVocabulary[ServiceUnitEnabledState] = ServiceUnitEnabledState.UNKNOWN
    result: GovernedVocabulary[ServiceUnitResult] = ServiceUnitResult.UNKNOWN
    exit_code: int | str | None = None
    status_text: str = ""
    main_pid: int | str | None = None
    unit_file_path: str = ""
    exec_start: ServiceUnitExecStart | None = None
    service: str = ""
    description: str = ""

    @field_validator("unit_id")
    @classmethod
    def validate_unit_id(cls, v: str) -> str:
        return require_symbol(v, field_name="unit_id")

    @field_validator("unit_name")
    @classmethod
    def validate_unit_name(cls, v: str) -> str:
        return _validate_unit_name(v)

    @field_validator("manager_kind", mode="before")
    @classmethod
    def normalize_manager_kind(cls, v: ServiceManagerKind | str) -> ServiceManagerKind | str:
        return parse_runtime_enum_or_var(v, ServiceManagerKind, field_name="manager_kind")

    @field_validator("unit_type", mode="before")
    @classmethod
    def normalize_unit_type(cls, v: ServiceUnitKind | str) -> ServiceUnitKind | str:
        return parse_runtime_enum_or_var(v, ServiceUnitKind, field_name="unit_type")

    @field_validator("load_state", mode="before")
    @classmethod
    def normalize_load_state(cls, v: ServiceUnitLoadState | str) -> ServiceUnitLoadState | str:
        return parse_runtime_enum_or_var(v, ServiceUnitLoadState, field_name="load_state")

    @field_validator("active_state", mode="before")
    @classmethod
    def normalize_active_state(cls, v: ServiceUnitActiveState | str) -> ServiceUnitActiveState | str:
        return parse_runtime_enum_or_var(v, ServiceUnitActiveState, field_name="active_state")

    @field_validator("enabled_state", mode="before")
    @classmethod
    def normalize_enabled_state(cls, v: ServiceUnitEnabledState | str) -> ServiceUnitEnabledState | str:
        return parse_runtime_enum_or_var(v, ServiceUnitEnabledState, field_name="enabled_state")

    @field_validator("result", mode="before")
    @classmethod
    def normalize_result(cls, v: ServiceUnitResult | str) -> ServiceUnitResult | str:
        return parse_runtime_enum_or_var(v, ServiceUnitResult, field_name="result")

    @field_validator("exit_code", mode="before")
    @classmethod
    def parse_exit_code(cls, v: int | str | None) -> int | str | None:
        if v is None:
            return v
        return parse_int_or_var(v, minimum=_EXIT_CODE_MIN, maximum=_EXIT_CODE_MAX, field_name="exit_code")

    @field_validator("main_pid", mode="before")
    @classmethod
    def parse_main_pid(cls, v: int | str | None) -> int | str | None:
        if v is None:
            return v
        return parse_int_or_var(v, minimum=1, field_name="main_pid")

    @field_validator("unit_file_path")
    @classmethod
    def validate_unit_file_path(cls, v: str) -> str:
        return absolute_path_or_var(v, field_name="unit_file_path") if v else v

    @field_validator("service")
    @classmethod
    def validate_service(cls, v: str) -> str:
        if not v:
            return v
        if not isinstance(v, str):
            raise ValueError("service must be a string")
        if not v.strip():
            raise ValueError("service must be a non-empty string or omitted")
        return v

    @field_validator("sub_state")
    @classmethod
    def validate_sub_state(cls, v: str, info: ValidationInfo) -> str:
        return _bounded_text(v, max_len=_SUB_STATE_MAX_LEN, field_name=info.field_name)

    @field_validator("status_text")
    @classmethod
    def validate_status_text(cls, v: str, info: ValidationInfo) -> str:
        return _bounded_text(v, max_len=_STATUS_TEXT_MAX_LEN, field_name=info.field_name)

    @model_validator(mode="after")
    def validate_exit_code_consistency(self) -> "ServiceManagerUnit":
        # exit_code is meaningful only when result=exit_code (or when result is
        # a deferred variable). Recording an exit code under e.g. result=success
        # is a category error: success has no exit code attached as a fact.
        if self.exit_code is not None:
            result = self.result
            is_variable_result = isinstance(result, str) and is_variable_ref(result)
            if not is_variable_result and result != ServiceUnitResult.EXIT_CODE:
                raise ValueError(
                    f"exit_code is only valid when result='exit_code'; got result={result!r}",
                )
        return self


def _bounded_text(value: str, *, max_len: int, field_name: str) -> str:
    """Validate a bounded short string: must be a ``str`` no longer than ``max_len``."""
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string")
    if len(value) > max_len:
        raise ValueError(f"{field_name} must be <= {max_len} characters")
    return value
