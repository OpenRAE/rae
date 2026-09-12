"""Observed SSH server configuration models for SDL nodes.

These models express the participant-observable sshd policy that materially
changes a node's login surface (``ForceCommand``, ``AcceptEnv``, ``Match``
rules) as typed runtime facts (see ADR-031). They sit under
``Node.runtime.ssh_servers`` as observed service configuration, distinct
from transport-binding ``Node.services``, curated top-level ``accounts``,
``runtime.local_identity`` inventory, ``runtime.environment`` values, and
``runtime.applications`` HTTP route inventory.

The surface deliberately avoids carrying raw ``sshd_config`` text, session
identifier values, or per-session environment values; ``AcceptEnv`` records
the allowed name allowlist only, and a forced command that wraps secrets
must be modeled with ``command_redacted=True``.
"""

from enum import Enum

from pydantic import Field, ValidationInfo, field_validator, model_validator

from raes.runtime_vocabulary import GovernedVocabulary

from ._base import (
    SDLModel,
    is_variable_ref,
    parse_bool_or_var,
)
from .runtime_values import (
    absolute_path_or_var,
    coerce_string_list,
    parse_optional_bool_or_var,
    parse_runtime_enum_or_var,
)

__all__ = [
    "RuntimeSshServer",
    "SshForcedCommand",
    "SshForcedCommandKind",
    "SshMatchCriterion",
    "SshMatchCriterionKind",
    "SshMatchRule",
]


class SshForcedCommandKind(str, Enum):
    """Kind of forced command an sshd ``ForceCommand`` directive carries."""

    ABSOLUTE_PATH = "absolute_path"
    INTERNAL_SFTP = "internal_sftp"
    REDACTED = "redacted"


class SshMatchCriterionKind(str, Enum):
    """OpenSSH ``Match`` criterion kinds.

    ``LOCAL_USER`` is the explicit "match this concrete account" form that
    semantic validation may cross-check against ``runtime.local_identity``
    when that inventory is present. ``USER`` is the looser pattern form
    (wildcards, comma-separated lists) and is not cross-checked.
    """

    USER = "user"
    GROUP = "group"
    HOST = "host"
    ADDRESS = "address"
    LOCAL_USER = "local_user"
    LOCAL_PORT = "local_port"
    RDOMAIN = "rdomain"
    ALL = "all"


def _check_accept_env_literal_shape(raw: str) -> None:
    """Raise if a concrete (non-variable) ``AcceptEnv`` entry is malformed."""
    if raw == "" or raw.strip() == "":
        raise ValueError("accept_env entries must be non-empty")
    if any(ch.isspace() for ch in raw):
        raise ValueError(f"accept_env entry '{raw}' must not contain whitespace")
    if "=" in raw:
        raise ValueError(f"accept_env entry '{raw}' must not contain '=' (names only, not assignments)")


def _validate_accept_env_entries(values: list[str]) -> list[str]:
    """Validate an ``AcceptEnv`` allowlist of environment-variable names/patterns.

    ``AcceptEnv`` entries are names or patterns, not assignments. Reject
    non-strings, empty entries, entries containing whitespace, entries
    containing ``=``, and case-sensitive duplicates. Variable refs
    (``${var}``) are passed through unchanged but still deduplicated.
    """
    seen: set[str] = set()
    out: list[str] = []
    for raw in values:
        if not isinstance(raw, str):
            raise ValueError("accept_env entries must be strings")
        if not is_variable_ref(raw):
            _check_accept_env_literal_shape(raw)
        if raw in seen:
            raise ValueError(f"Duplicate accept_env entry '{raw}'")
        seen.add(raw)
        out.append(raw)
    return out


def _validate_stable_identifier(value: str, *, field_name: str) -> str:
    """Reject empty, whitespace-only, and variable-ref symbol-defining identifiers."""
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string")
    if is_variable_ref(value):
        raise ValueError(f"{field_name} must be a stable identifier, not a variable reference")
    if not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value


class SshForcedCommand(SDLModel):
    """A typed sshd ``ForceCommand`` configuration.

    The ``command_kind`` discriminates how ``command`` is interpreted:

    - ``absolute_path``: a concrete executable path (or ``${var}``) starting
      with ``/``. Validated via ``absolute_path_or_var``.
    - ``internal_sftp``: the sshd-internal sftp subsystem; ``command`` must
      equal the literal ``"internal-sftp"``.
    - ``redacted``: the underlying command is withheld from the SDL model
      because it carries secrets, session identifiers, or operator-only
      arguments; ``command`` must be empty and ``command_redacted`` must
      be true.
    """

    command_kind: GovernedVocabulary[SshForcedCommandKind] = SshForcedCommandKind.ABSOLUTE_PATH
    command: str = ""
    command_redacted: bool | str = False
    description: str = ""

    @field_validator("command_kind", mode="before")
    @classmethod
    def normalize_command_kind(cls, v: SshForcedCommandKind | str) -> SshForcedCommandKind | str:
        return parse_runtime_enum_or_var(v, SshForcedCommandKind, field_name="command_kind")

    @field_validator("command_redacted", mode="before")
    @classmethod
    def parse_command_redacted(cls, v: bool | str) -> bool | str:
        return parse_bool_or_var(v, field_name="command_redacted")

    @model_validator(mode="after")
    def validate_command_shape(self) -> "SshForcedCommand":
        # Enforce every invariant that is knowable from the literal fields
        # BEFORE deferring variable-dependent checks. Otherwise a variable
        # ``command_kind`` or ``command_redacted`` can be used to smuggle
        # a raw secret-bearing command through the model boundary.
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
                raise ValueError("redacted forced command must omit the command value")
            if not kind_is_var and kind != SshForcedCommandKind.REDACTED:
                raise ValueError("command_redacted=true requires command_kind='redacted'")
        if not kind_is_var and kind == SshForcedCommandKind.REDACTED:
            if command != "":
                raise ValueError("redacted forced command must omit the command value")
            if not redacted_is_var and redacted is not True:
                raise ValueError("command_kind='redacted' requires command_redacted=true")

    def _enforce_concrete_kind_command_shape(self) -> None:
        kind = self.command_kind
        command = self.command
        if kind == SshForcedCommandKind.ABSOLUTE_PATH:
            if not command:
                raise ValueError("absolute_path forced command requires a non-empty command")
            absolute_path_or_var(command, field_name="command")
        elif kind == SshForcedCommandKind.INTERNAL_SFTP and command != "internal-sftp":
            raise ValueError("internal_sftp forced command must equal 'internal-sftp'")


class SshMatchCriterion(SDLModel):
    """A single sshd ``Match`` criterion (one ``kind`` + one ``pattern``)."""

    kind: GovernedVocabulary[SshMatchCriterionKind]
    pattern: str

    @field_validator("kind", mode="before")
    @classmethod
    def normalize_kind(cls, v: SshMatchCriterionKind | str) -> SshMatchCriterionKind | str:
        return parse_runtime_enum_or_var(v, SshMatchCriterionKind, field_name="kind")

    @field_validator("pattern")
    @classmethod
    def validate_pattern(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip():
            raise ValueError("match criterion pattern must be a non-empty string")
        return v


class _SshDirectiveBundle(SDLModel):
    """Shared sshd directive fields used by both the server config and per-rule overrides.

    Concrete sshd directives — ``AcceptEnv``, ``AllowUsers`` /
    ``DenyUsers`` / ``AllowGroups`` / ``DenyGroups``,
    ``AuthenticationMethods``, ``PasswordAuthentication`` /
    ``PubkeyAuthentication`` / ``PermitTTY``, ``ChrootDirectory``, and
    ``AuthorizedKeysFile`` — apply identically at the global scope
    (``RuntimeSshServer``) and inside a ``Match`` rule
    (``SshMatchRule``). Centralising the field declarations and their
    validators here keeps the two surfaces in lockstep and removes the
    structural duplication SonarCloud flags when the same block is
    repeated verbatim across both classes.
    """

    forced_command: SshForcedCommand | None = None
    accept_env: list[str] = Field(default_factory=list)
    allow_users: list[str] = Field(default_factory=list)
    deny_users: list[str] = Field(default_factory=list)
    allow_groups: list[str] = Field(default_factory=list)
    deny_groups: list[str] = Field(default_factory=list)
    authentication_methods: list[str] = Field(default_factory=list)
    password_authentication: bool | str | None = None
    pubkey_authentication: bool | str | None = None
    permit_tty: bool | str | None = None
    chroot_directory: str = ""
    authorized_keys_file: str = ""
    description: str = ""

    @field_validator(
        "accept_env",
        "allow_users",
        "deny_users",
        "allow_groups",
        "deny_groups",
        "authentication_methods",
        mode="before",
    )
    @classmethod
    def _coerce_string_lists(cls, v: str | list[str] | None) -> list[str]:
        return coerce_string_list(v)

    @field_validator("accept_env")
    @classmethod
    def _validate_accept_env(cls, v: list[str]) -> list[str]:
        return _validate_accept_env_entries(v)

    @field_validator(
        "password_authentication",
        "pubkey_authentication",
        "permit_tty",
        mode="before",
    )
    @classmethod
    def _parse_optional_bool_fields(cls, v: bool | str | None, info: ValidationInfo) -> bool | str | None:
        return parse_optional_bool_or_var(v, field_name=info.field_name)

    @field_validator("chroot_directory", "authorized_keys_file")
    @classmethod
    def _validate_path_fields(cls, v: str, info: ValidationInfo) -> str:
        return absolute_path_or_var(v, field_name=info.field_name) if v else v


class SshMatchRule(_SshDirectiveBundle):
    """A scoped sshd ``Match`` rule.

    ``criteria`` is the ordered conjunction of one-or-more match criteria
    (``Match User kali`` is one criterion; ``Match User kali Address 10.0.0.0/8``
    is two). Per-rule sshd directives override the surrounding global
    directives for sessions that match all listed criteria.
    """

    match_id: str
    criteria: list[SshMatchCriterion] = Field(default_factory=list)

    @field_validator("match_id")
    @classmethod
    def validate_match_id(cls, v: str) -> str:
        return _validate_stable_identifier(v, field_name="match_id")

    @model_validator(mode="after")
    def validate_criteria(self) -> "SshMatchRule":
        if not self.criteria:
            raise ValueError("match rule criteria must include at least one criterion")
        seen: set[tuple[object, str]] = set()
        for crit in self.criteria:
            key = (crit.kind, crit.pattern)
            if key in seen:
                raise ValueError(
                    f"Duplicate match criterion ({crit.kind}, '{crit.pattern}') within rule '{self.match_id}'"
                )
            seen.add(key)
        return self


def _criteria_fingerprint(rule: SshMatchRule) -> tuple[tuple[object, str], ...]:
    """A hashable fingerprint of a rule's criteria for duplicate detection."""
    return tuple((crit.kind, crit.pattern) for crit in rule.criteria)


class RuntimeSshServer(_SshDirectiveBundle):
    """A scoped sshd server configuration observed on a node.

    Each configuration carries a stable ``ssh_server_id`` and an explicit
    ``service`` reference pointing at the owning same-node service (bare
    name or ``nodes.<node>.services.<name>`` form). Global sshd directives
    sit at the top level; scoped overrides live in ``match_rules``.

    The configuration is the SDL surface for participant-observable sshd
    policy. It is not a backend sshd-payload dump and must not embed raw
    ``sshd_config`` text, raw ``sshd -T`` output, container inspect
    payloads, session transcripts, or environment values.
    """

    ssh_server_id: str
    service: str
    match_rules: list[SshMatchRule] = Field(default_factory=list)

    @field_validator("ssh_server_id")
    @classmethod
    def validate_ssh_server_id(cls, v: str) -> str:
        return _validate_stable_identifier(v, field_name="ssh_server_id")

    @field_validator("service")
    @classmethod
    def validate_service(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip():
            raise ValueError("service must be a non-empty string")
        return v

    @model_validator(mode="after")
    def validate_match_rules_unique(self) -> "RuntimeSshServer":
        seen_ids: set[str] = set()
        seen_fingerprints: set[tuple[tuple[object, str], ...]] = set()
        for rule in self.match_rules:
            if rule.match_id in seen_ids:
                raise ValueError(f"Duplicate ssh match_id '{rule.match_id}'")
            seen_ids.add(rule.match_id)
            fingerprint = _criteria_fingerprint(rule)
            if fingerprint in seen_fingerprints:
                raise ValueError(
                    f"Duplicate ssh match rule criteria {list(fingerprint)} in server '{self.ssh_server_id}'"
                )
            seen_fingerprints.add(fingerprint)
        return self
