"""Observed runtime local identity inventory models for SDL nodes.

These models express the local identity database observed inside a node
asset — ``/etc/passwd`` users, ``/etc/group`` groups, and sudo/sudoers
privilege grants — as typed runtime facts (see ADR-024). They are observed
inventory, distinct from the curated top-level ``accounts`` provisioning
surface; nothing here is implicitly compiled into an account placement.
"""

from enum import Enum

from pydantic import Field, ValidationInfo, field_validator, model_validator

from raes.runtime_vocabulary import GovernedVocabulary

from ._base import (
    SDLModel,
    is_variable_ref,
    parse_bool_or_var,
    parse_int_or_var,
)
from .runtime_filesystem import RuntimeFilesystemStability
from .runtime_values import (
    absolute_path_or_var,
    coerce_string_list,
    parse_runtime_enum_or_var,
)

__all__ = [
    "RuntimeIdentityProvenance",
    "RuntimeLocalGroup",
    "RuntimeLocalIdentityInventory",
    "RuntimeLocalUser",
    "RuntimeSudoPrincipalKind",
    "RuntimeSudoRule",
]


class RuntimeIdentityProvenance(str, Enum):
    """Origin class for an observed local identity record."""

    IMAGE = "image"
    PACKAGE = "package"
    RUNTIME_CREATED = "runtime_created"
    OPERATOR = "operator"
    UNKNOWN = "unknown"
    OTHER = "other"


class RuntimeSudoPrincipalKind(str, Enum):
    """Kind of principal a sudo rule grants privilege to."""

    USER = "user"
    GROUP = "group"
    OTHER = "other"
    UNKNOWN = "unknown"


class RuntimeLocalUser(SDLModel):
    """A local user record observed in a node's identity database (/etc/passwd)."""

    username: str
    uid: int | str | None = None
    primary_gid: int | str | None = None
    primary_group: str = ""
    gecos: str = ""
    home: str = ""
    shell: str = ""
    supplemental_groups: list[str] = Field(default_factory=list)
    disabled: bool | str = False
    locked: bool | str = False
    no_login: bool | str = False
    provenance: GovernedVocabulary[RuntimeIdentityProvenance] = RuntimeIdentityProvenance.UNKNOWN
    stability: GovernedVocabulary[RuntimeFilesystemStability] = RuntimeFilesystemStability.UNKNOWN
    description: str = ""

    @field_validator("username")
    @classmethod
    def validate_username(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip():
            raise ValueError("username must be a non-empty string")
        return v

    @field_validator("uid", "primary_gid", mode="before")
    @classmethod
    def parse_identity_id(cls, v: int | str | None, info: ValidationInfo) -> int | str | None:
        return parse_int_or_var(v, minimum=0, field_name=info.field_name) if v is not None else v

    @field_validator("home", "shell")
    @classmethod
    def validate_paths(cls, v: str, info: ValidationInfo) -> str:
        return absolute_path_or_var(v, field_name=info.field_name) if v else v

    @field_validator("supplemental_groups", mode="before")
    @classmethod
    def coerce_supplemental_groups(cls, v: str | list[str] | None) -> list[str]:
        return coerce_string_list(v)

    @field_validator("disabled", "locked", "no_login", mode="before")
    @classmethod
    def parse_status_flags(cls, v: bool | str, info: ValidationInfo) -> bool | str:
        return parse_bool_or_var(v, field_name=info.field_name)

    @field_validator("provenance", mode="before")
    @classmethod
    def normalize_provenance(cls, v: RuntimeIdentityProvenance | str) -> RuntimeIdentityProvenance | str:
        return parse_runtime_enum_or_var(v, RuntimeIdentityProvenance, field_name="provenance")

    @field_validator("stability", mode="before")
    @classmethod
    def normalize_stability(cls, v: RuntimeFilesystemStability | str) -> RuntimeFilesystemStability | str:
        return parse_runtime_enum_or_var(v, RuntimeFilesystemStability, field_name="stability")


class RuntimeLocalGroup(SDLModel):
    """A local group record observed in a node's identity database (/etc/group)."""

    name: str
    gid: int | str | None = None
    members: list[str] = Field(default_factory=list)
    provenance: GovernedVocabulary[RuntimeIdentityProvenance] = RuntimeIdentityProvenance.UNKNOWN
    description: str = ""

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip():
            raise ValueError("group name must be a non-empty string")
        return v

    @field_validator("gid", mode="before")
    @classmethod
    def parse_gid(cls, v: int | str | None) -> int | str | None:
        return parse_int_or_var(v, minimum=0, field_name="gid") if v is not None else v

    @field_validator("members", mode="before")
    @classmethod
    def coerce_members(cls, v: str | list[str] | None) -> list[str]:
        return coerce_string_list(v)

    @field_validator("provenance", mode="before")
    @classmethod
    def normalize_provenance(cls, v: RuntimeIdentityProvenance | str) -> RuntimeIdentityProvenance | str:
        return parse_runtime_enum_or_var(v, RuntimeIdentityProvenance, field_name="provenance")


class RuntimeSudoRule(SDLModel):
    """An observed sudo/sudoers privilege grant.

    The portable model is the structured principal/run-as/command scope.
    ``raw_entry`` may carry the original sudoers line only as optional
    descriptive evidence; ``command_redacted`` marks a rule whose command
    scope was withheld because it carried sensitive arguments.
    """

    principal: str
    principal_kind: GovernedVocabulary[RuntimeSudoPrincipalKind] = RuntimeSudoPrincipalKind.USER
    run_as_users: list[str] = Field(default_factory=list)
    run_as_groups: list[str] = Field(default_factory=list)
    commands: list[str] = Field(default_factory=list)
    host_scope: str = ""
    nopasswd: bool | str = False
    command_redacted: bool | str = False
    raw_entry: str = ""
    description: str = ""

    @field_validator("principal")
    @classmethod
    def validate_principal(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip():
            raise ValueError("sudo principal must be a non-empty string")
        return v

    @field_validator("principal_kind", mode="before")
    @classmethod
    def normalize_principal_kind(cls, v: RuntimeSudoPrincipalKind | str) -> RuntimeSudoPrincipalKind | str:
        return parse_runtime_enum_or_var(v, RuntimeSudoPrincipalKind, field_name="principal_kind")

    @field_validator("run_as_users", "run_as_groups", "commands", mode="before")
    @classmethod
    def coerce_scope_lists(cls, v: str | list[str] | None) -> list[str]:
        return coerce_string_list(v)

    @field_validator("nopasswd", "command_redacted", mode="before")
    @classmethod
    def parse_flags(cls, v: bool | str, info: ValidationInfo) -> bool | str:
        return parse_bool_or_var(v, field_name=info.field_name)

    @model_validator(mode="after")
    def validate_redacted_commands(self) -> "RuntimeSudoRule":
        if self.command_redacted is True and self.commands:
            raise ValueError("redacted sudo rules must omit commands")
        return self


class RuntimeLocalIdentityInventory(SDLModel):
    """Observed local identity database (users, groups, sudo rules) for a node."""

    users: list[RuntimeLocalUser] = Field(default_factory=list)
    groups: list[RuntimeLocalGroup] = Field(default_factory=list)
    sudo_rules: list[RuntimeSudoRule] = Field(default_factory=list)
    description: str = ""

    @model_validator(mode="after")
    def validate_unique_identity_records(self) -> "RuntimeLocalIdentityInventory":
        seen_usernames: set[str] = set()
        for user in self.users:
            if user.username in seen_usernames:
                raise ValueError(f"Duplicate runtime local user '{user.username}'")
            seen_usernames.add(user.username)

        seen_group_names: set[str] = set()
        seen_group_gids: set[int | str] = set()
        for group in self.groups:
            if group.name in seen_group_names:
                raise ValueError(f"Duplicate runtime local group '{group.name}'")
            seen_group_names.add(group.name)
            if group.gid is not None and not is_variable_ref(group.gid):
                if group.gid in seen_group_gids:
                    raise ValueError(f"Duplicate runtime local group gid '{group.gid}'")
                seen_group_gids.add(group.gid)

        seen_sudo_keys: set[tuple[str, str, tuple[str, ...]]] = set()
        for rule in self.sudo_rules:
            key = (str(rule.principal_kind), rule.principal, tuple(rule.commands))
            if key in seen_sudo_keys:
                raise ValueError(f"Duplicate runtime sudo rule for principal '{rule.principal}'")
            seen_sudo_keys.add(key)
        return self
