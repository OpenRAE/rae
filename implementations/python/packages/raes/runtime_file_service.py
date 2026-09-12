"""Runtime file-service inventory models for SDL nodes.

These models express the participant-observable file-sharing surface of a
node (see ADR-037): node-scoped services that publish file-like resources
over a protocol family — initially SMB/Samba, with a deliberate seam for
NFS, FTP/SFTP, WebDAV, and object-store APIs. They are observation
metadata attached to ``Node.runtime``; they never mutate ``Node.services``,
``runtime.network.published_ports``, top-level ``accounts``,
``runtime.local_identity``, or ``runtime.identity_authorities``.

The portable shape factors share/resource identity, service-local
principals, authorization rules, and observed access outcomes into
distinct records so vendor ACLs (POSIX, Windows DACL, NFSv4 ACE,
Zanzibar) are not smuggled in as the canonical RAES rule language.
Service-local principals carry only a credential-strength classification
(``RuntimeFileServiceCredentialClassification``); raw passwords, hashes,
keys, and other secret material are unrepresentable in this surface per
ADR-037 §4 and the redaction gate.
"""

from enum import Enum
from typing import Any

from pydantic import Field, ValidationInfo, field_validator, model_validator

from raes.runtime_vocabulary import GovernedVocabulary

from ._base import SDLModel
from .runtime_filesystem import RuntimeSensitivityClassification
from .runtime_values import (
    absolute_path_or_var,
    coerce_string_list,
    parse_optional_bool_or_var,
    parse_runtime_enum_or_var,
    require_non_empty,
    require_symbol,
)

__all__ = [
    "RuntimeFileService",
    "RuntimeFileServiceAccessAction",
    "RuntimeFileServiceAccessBasis",
    "RuntimeFileServiceAccessEffect",
    "RuntimeFileServiceAccessObservation",
    "RuntimeFileServiceAccessOutcome",
    "RuntimeFileServiceAccessRule",
    "RuntimeFileServiceCredentialClassification",
    "RuntimeFileServicePrincipal",
    "RuntimeFileServicePrincipalKind",
    "RuntimeFileServicePrincipalStatus",
    "RuntimeFileServicePrincipalOrigin",
    "RuntimeFileServiceProtocol",
    "RuntimeFileServiceShare",
    "RuntimeFileShareKind",
]


class RuntimeFileServiceProtocol(str, Enum):
    """Portable protocol family for an observed runtime file service."""

    SMB = "smb"
    CIFS = "cifs"
    NFS = "nfs"
    AFP = "afp"
    FTP = "ftp"
    SFTP = "sftp"
    WEBDAV = "webdav"
    OBJECT_STORE = "object_store"
    OTHER = "other"
    UNKNOWN = "unknown"


class RuntimeFileShareKind(str, Enum):
    """Observed kind of a published file-service share/resource."""

    DISK = "disk"
    IPC = "ipc"
    PRINTER = "printer"
    OTHER = "other"
    UNKNOWN = "unknown"


class RuntimeFileServicePrincipalKind(str, Enum):
    """Portable kind of a service-local principal in a file service."""

    USER = "user"
    GROUP = "group"
    MACHINE = "machine"
    ALIAS = "alias"
    GUEST = "guest"
    ANONYMOUS = "anonymous"
    SERVICE_ACCOUNT = "service_account"
    OTHER = "other"
    UNKNOWN = "unknown"


class RuntimeFileServicePrincipalStatus(str, Enum):
    """Observed account status for a service-local principal."""

    ENABLED = "enabled"
    DISABLED = "disabled"
    LOCKED = "locked"
    NO_LOGIN = "no_login"
    UNKNOWN = "unknown"
    OTHER = "other"


class RuntimeFileServicePrincipalOrigin(str, Enum):
    """Origin/provenance class for a service-local principal record."""

    BUILT_IN = "built_in"
    PROVISIONED = "provisioned"
    SYNCHRONIZED = "synchronized"
    RUNTIME_CREATED = "runtime_created"
    OPERATOR = "operator"
    UNKNOWN = "unknown"
    OTHER = "other"


class RuntimeFileServiceCredentialClassification(str, Enum):
    """Semantic classification of a service-local credential.

    The raw credential value MUST NOT be recorded; the principal model
    has no field that can hold one. This vocabulary is the only credential
    representation in the file-service surface — it describes the
    strength/posture of the credential as observed (or its absence) so
    downstream consumers can reason about exposure without leaking secret
    material into fixtures, schemas, diagnostics, or logs.
    """

    NO_CREDENTIAL = "no_credential"
    WEAK = "weak"
    DEFAULT_OR_TRIVIAL = "default_or_trivial"
    STRONG = "strong"
    REDACTED = "redacted"
    UNKNOWN = "unknown"
    OTHER = "other"


class RuntimeFileServiceAccessAction(str, Enum):
    """Portable action vocabulary for file-service access policy/observations."""

    BROWSE = "browse"
    LIST = "list"
    READ = "read"
    WRITE = "write"
    CREATE = "create"
    DELETE = "delete"
    EXECUTE = "execute"
    ADMINISTER = "administer"
    OTHER = "other"
    UNKNOWN = "unknown"


class RuntimeFileServiceAccessEffect(str, Enum):
    """Portable effect for an authored or computed file-service access rule."""

    ALLOW = "allow"
    DENY = "deny"
    NOT_APPLICABLE = "not_applicable"
    UNKNOWN = "unknown"
    OTHER = "other"


class RuntimeFileServiceAccessBasis(str, Enum):
    """Basis/provenance for an access claim or observation."""

    SHARE_CONFIG = "share_config"
    PASSDB = "passdb"
    FILESYSTEM_ACL = "filesystem_acl"
    DIRECTORY_POLICY = "directory_policy"
    OBSERVED_PROBE = "observed_probe"
    COMPUTED = "computed"
    UNKNOWN = "unknown"
    OTHER = "other"


class RuntimeFileServiceAccessOutcome(str, Enum):
    """Observed outcome class for a per-share access probe."""

    ALLOWED = "allowed"
    DENIED = "denied"
    ERROR = "error"
    NOT_OBSERVED = "not_observed"
    UNKNOWN = "unknown"
    OTHER = "other"


def _reject_duplicate_local_ref_ids(service: "RuntimeFileService") -> None:
    seen: dict[str, str] = {}
    entries: list[tuple[str, str]] = [("file_service_id", service.file_service_id)]
    entries.extend(("share_id", share.share_id) for share in service.shares)
    entries.extend(("principal_id", principal.principal_id) for principal in service.principals)
    entries.extend(("rule_id", rule.rule_id) for rule in service.access_rules)
    entries.extend(("observation_id", observation.observation_id) for observation in service.access_observations)

    for label, value in entries:
        prior = seen.get(value)
        if prior is not None:
            raise ValueError(
                f"Duplicate runtime file-service stable id '{value}' in service "
                f"'{service.file_service_id}' across {prior} and {label}"
            )
        seen[value] = label


class RuntimeFileServiceShare(SDLModel):
    """A published share/resource on a runtime file service."""

    share_id: str
    name: str
    kind: GovernedVocabulary[RuntimeFileShareKind] = RuntimeFileShareKind.DISK
    backing_path: str = ""
    comment: str = ""
    read_only: bool | str | None = None
    browseable: bool | str | None = None
    guest_ok: bool | str | None = None
    valid_users: list[str] = Field(default_factory=list)
    valid_groups: list[str] = Field(default_factory=list)
    invalid_users: list[str] = Field(default_factory=list)
    write_users: list[str] = Field(default_factory=list)
    description: str = ""

    @field_validator("share_id")
    @classmethod
    def validate_share_id(cls, v: str) -> str:
        return require_symbol(v, field_name="share_id")

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        return require_non_empty(v, field_name="share name")

    @field_validator("kind", mode="before")
    @classmethod
    def normalize_kind(cls, v: RuntimeFileShareKind | str) -> RuntimeFileShareKind | str:
        return parse_runtime_enum_or_var(v, RuntimeFileShareKind, field_name="kind")

    @field_validator("backing_path")
    @classmethod
    def validate_backing_path(cls, v: str) -> str:
        if not v:
            return v
        return absolute_path_or_var(v, field_name="backing_path")

    @field_validator("read_only", "browseable", "guest_ok", mode="before")
    @classmethod
    def parse_share_bool(cls, v: bool | str | None, info: ValidationInfo) -> bool | str | None:
        return parse_optional_bool_or_var(v, field_name=info.field_name)

    @field_validator(
        "valid_users",
        "valid_groups",
        "invalid_users",
        "write_users",
        mode="before",
    )
    @classmethod
    def coerce_user_lists(cls, v: Any) -> list[str]:
        return coerce_string_list(v)


class RuntimeFileServicePrincipal(SDLModel):
    """A service-local principal (Samba passdb-style account or group).

    Service-local principals are NOT promoted to top-level ``accounts``,
    ``runtime.local_identity``, or ``runtime.identity_authorities``.
    Optional ``local_user_ref`` and ``directory_subject_ref`` carry refs to
    those surfaces when a mapping is observed.

    Raw credential material (passwords, NT/LM hashes, Kerberos keys, private
    keys, bearer tokens, captured credentials) is unrepresentable on this
    record per ADR-037 §4 and the secret-handling gate; only
    ``credential_classification`` is carried, so the field surface itself
    cannot smuggle a secret into models, schemas, fixtures, diagnostics, or
    snapshots.
    """

    principal_id: str
    kind: GovernedVocabulary[RuntimeFileServicePrincipalKind] = RuntimeFileServicePrincipalKind.OTHER
    name: str
    external_id: str = ""
    status: GovernedVocabulary[RuntimeFileServicePrincipalStatus] = RuntimeFileServicePrincipalStatus.UNKNOWN
    credential_classification: GovernedVocabulary[RuntimeFileServiceCredentialClassification] = (
        RuntimeFileServiceCredentialClassification.UNKNOWN
    )
    origin: GovernedVocabulary[RuntimeFileServicePrincipalOrigin] = RuntimeFileServicePrincipalOrigin.UNKNOWN
    local_user_ref: str = ""
    directory_subject_ref: str = ""
    description: str = ""

    @field_validator("principal_id")
    @classmethod
    def validate_principal_id(cls, v: str) -> str:
        return require_symbol(v, field_name="principal_id")

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        return require_non_empty(v, field_name="principal name")

    @field_validator("kind", mode="before")
    @classmethod
    def normalize_kind(cls, v: RuntimeFileServicePrincipalKind | str) -> RuntimeFileServicePrincipalKind | str:
        return parse_runtime_enum_or_var(v, RuntimeFileServicePrincipalKind, field_name="kind")

    @field_validator("status", mode="before")
    @classmethod
    def normalize_status(
        cls,
        v: RuntimeFileServicePrincipalStatus | str,
    ) -> RuntimeFileServicePrincipalStatus | str:
        return parse_runtime_enum_or_var(v, RuntimeFileServicePrincipalStatus, field_name="status")

    @field_validator("credential_classification", mode="before")
    @classmethod
    def normalize_credential_classification(
        cls,
        v: RuntimeFileServiceCredentialClassification | str,
    ) -> RuntimeFileServiceCredentialClassification | str:
        return parse_runtime_enum_or_var(
            v,
            RuntimeFileServiceCredentialClassification,
            field_name="credential_classification",
        )

    @field_validator("origin", mode="before")
    @classmethod
    def normalize_origin(
        cls,
        v: RuntimeFileServicePrincipalOrigin | str,
    ) -> RuntimeFileServicePrincipalOrigin | str:
        return parse_runtime_enum_or_var(
            v,
            RuntimeFileServicePrincipalOrigin,
            field_name="origin",
        )


class RuntimeFileServiceAccessRule(SDLModel):
    """An authored or computed access rule for a file-service resource."""

    rule_id: str
    subject_ref: str
    resource_ref: str
    action: GovernedVocabulary[RuntimeFileServiceAccessAction] = RuntimeFileServiceAccessAction.OTHER
    effect: GovernedVocabulary[RuntimeFileServiceAccessEffect] = RuntimeFileServiceAccessEffect.UNKNOWN
    basis: GovernedVocabulary[RuntimeFileServiceAccessBasis] = RuntimeFileServiceAccessBasis.UNKNOWN
    description: str = ""

    @field_validator("rule_id")
    @classmethod
    def validate_rule_id(cls, v: str) -> str:
        return require_symbol(v, field_name="rule_id")

    @field_validator("subject_ref", "resource_ref")
    @classmethod
    def validate_refs(cls, v: str, info: ValidationInfo) -> str:
        return require_non_empty(v, field_name=info.field_name)

    @field_validator("action", mode="before")
    @classmethod
    def normalize_action(cls, v: RuntimeFileServiceAccessAction | str) -> RuntimeFileServiceAccessAction | str:
        return parse_runtime_enum_or_var(v, RuntimeFileServiceAccessAction, field_name="action")

    @field_validator("effect", mode="before")
    @classmethod
    def normalize_effect(cls, v: RuntimeFileServiceAccessEffect | str) -> RuntimeFileServiceAccessEffect | str:
        return parse_runtime_enum_or_var(v, RuntimeFileServiceAccessEffect, field_name="effect")

    @field_validator("basis", mode="before")
    @classmethod
    def normalize_basis(cls, v: RuntimeFileServiceAccessBasis | str) -> RuntimeFileServiceAccessBasis | str:
        return parse_runtime_enum_or_var(v, RuntimeFileServiceAccessBasis, field_name="basis")


class RuntimeFileServiceAccessObservation(SDLModel):
    """An observed probe outcome against a file-service resource.

    Observations are evidence; they support but do not overwrite authored
    or configured policy.
    """

    observation_id: str
    subject_ref: str
    resource_ref: str
    action: GovernedVocabulary[RuntimeFileServiceAccessAction] = RuntimeFileServiceAccessAction.OTHER
    outcome: GovernedVocabulary[RuntimeFileServiceAccessOutcome] = RuntimeFileServiceAccessOutcome.UNKNOWN
    basis: GovernedVocabulary[RuntimeFileServiceAccessBasis] = RuntimeFileServiceAccessBasis.OBSERVED_PROBE
    sensitivity: GovernedVocabulary[RuntimeSensitivityClassification] = RuntimeSensitivityClassification.UNKNOWN
    description: str = ""

    @field_validator("observation_id")
    @classmethod
    def validate_observation_id(cls, v: str) -> str:
        return require_symbol(v, field_name="observation_id")

    @field_validator("subject_ref", "resource_ref")
    @classmethod
    def validate_refs(cls, v: str, info: ValidationInfo) -> str:
        return require_non_empty(v, field_name=info.field_name)

    @field_validator("action", mode="before")
    @classmethod
    def normalize_action(cls, v: RuntimeFileServiceAccessAction | str) -> RuntimeFileServiceAccessAction | str:
        return parse_runtime_enum_or_var(v, RuntimeFileServiceAccessAction, field_name="action")

    @field_validator("outcome", mode="before")
    @classmethod
    def normalize_outcome(
        cls,
        v: RuntimeFileServiceAccessOutcome | str,
    ) -> RuntimeFileServiceAccessOutcome | str:
        return parse_runtime_enum_or_var(v, RuntimeFileServiceAccessOutcome, field_name="outcome")

    @field_validator("basis", mode="before")
    @classmethod
    def normalize_basis(cls, v: RuntimeFileServiceAccessBasis | str) -> RuntimeFileServiceAccessBasis | str:
        return parse_runtime_enum_or_var(v, RuntimeFileServiceAccessBasis, field_name="basis")

    @field_validator("sensitivity", mode="before")
    @classmethod
    def normalize_sensitivity(
        cls,
        v: RuntimeSensitivityClassification | str,
    ) -> RuntimeSensitivityClassification | str:
        return parse_runtime_enum_or_var(v, RuntimeSensitivityClassification, field_name="sensitivity")


class RuntimeFileService(SDLModel):
    """A node-scoped runtime file-service inventory.

    ``service`` references the owning same-node ``Node.services[].name``
    (bare name or qualified ``nodes.<node>.services.<name>``).
    """

    file_service_id: str
    service: str = ""
    protocol: GovernedVocabulary[RuntimeFileServiceProtocol] = RuntimeFileServiceProtocol.OTHER
    backend: str = ""
    description: str = ""
    shares: list[RuntimeFileServiceShare] = Field(default_factory=list)
    principals: list[RuntimeFileServicePrincipal] = Field(default_factory=list)
    access_rules: list[RuntimeFileServiceAccessRule] = Field(default_factory=list)
    access_observations: list[RuntimeFileServiceAccessObservation] = Field(default_factory=list)

    @field_validator("file_service_id")
    @classmethod
    def validate_file_service_id(cls, v: str) -> str:
        return require_symbol(v, field_name="file_service_id")

    @field_validator("protocol", mode="before")
    @classmethod
    def normalize_protocol(cls, v: RuntimeFileServiceProtocol | str) -> RuntimeFileServiceProtocol | str:
        return parse_runtime_enum_or_var(v, RuntimeFileServiceProtocol, field_name="protocol")

    @model_validator(mode="after")
    def validate_service(self) -> "RuntimeFileService":
        for label, attr in (
            ("share_id", "shares"),
            ("principal_id", "principals"),
            ("rule_id", "access_rules"),
            ("observation_id", "access_observations"),
        ):
            seen: set[str] = set()
            for item in getattr(self, attr):
                key = getattr(item, label)
                if key in seen:
                    raise ValueError(
                        f"Duplicate runtime file-service {label} '{key}' in service '{self.file_service_id}'"
                    )
                seen.add(key)
        _reject_duplicate_local_ref_ids(self)
        return self
