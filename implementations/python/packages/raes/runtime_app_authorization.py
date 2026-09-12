"""Application-internal authorization (RBAC) runtime inventory models.

This shared primitive types an application's *internal* role-based access
control store: principals, roles, resource-scoped permission grants, role
mappings, and tenants. It is deliberately **not** a wire-protocol directory
(that stays ``identity_authorities``); its defining addition over a directory
is the resource-scoped permission grant (role -> actions -> resource pattern),
anchored by RBAC96 / ANSI INCITS 359 permission-assignment and NIST SP 800-162
resource-scoping.

Principal credentials are never stored as raw values. A principal carries a
``credential_classification`` (``none`` / ``redacted`` / ``operator_secret``)
and the model has no field that can hold a raw bcrypt hash, API key, or
password.
"""

from enum import Enum

from pydantic import Field, field_validator, model_validator

from raes.runtime_vocabulary import GovernedVocabulary

from ._base import SDLModel
from .runtime_values import (
    coerce_string_list,
    is_variable_ref,
    parse_optional_bool_or_var,
    parse_runtime_enum_or_var,
    require_symbol,
)

__all__ = [
    "RuntimeAppAuthorization",
    "RuntimeAppAuthorizationCredentialClassification",
    "RuntimeAppAuthorizationGrant",
    "RuntimeAppAuthorizationGrantEffect",
    "RuntimeAppAuthorizationPrincipal",
    "RuntimeAppAuthorizationPrincipalKind",
    "RuntimeAppAuthorizationResourceVocabulary",
    "RuntimeAppAuthorizationRole",
    "RuntimeAppAuthorizationRoleMapping",
    "RuntimeAppAuthorizationTenant",
]


class RuntimeAppAuthorizationResourceVocabulary(str, Enum):
    """Open spine discriminator for the resource space an RBAC store governs.

    Tier placement (storage RBAC vs presentation RBAC) is derived from which
    spine references the authorization, not declared here. Open taxonomy:
    carries both ``unknown`` and ``other``.
    """

    INDEX_PATTERN = "index_pattern"
    CQL_RESOURCE = "cql_resource"
    REDIS_ACL = "redis_acl"
    APP_RESOURCE = "app_resource"
    UNKNOWN = "unknown"
    OTHER = "other"


class RuntimeAppAuthorizationPrincipalKind(str, Enum):
    """Open taxonomy of authorization principal kinds.

    Carries both ``unknown`` and ``other`` (extensible real-world vocab).
    """

    USER = "user"
    SERVICE_ACCOUNT = "service_account"
    API_KEY = "api_key"
    BACKEND_ROLE = "backend_role"
    UNKNOWN = "unknown"
    OTHER = "other"


class RuntimeAppAuthorizationCredentialClassification(str, Enum):
    """Closed posture vocabulary for a principal credential.

    The raw credential value MUST NOT be recorded; the principal model has no
    field that can hold one. This vocabulary is the only credential
    representation in the surface. Closed structural vocab: no ``unknown`` /
    ``other``.
    """

    NONE = "none"
    REDACTED = "redacted"
    OPERATOR_SECRET = "operator_secret"  # noqa: S105


class RuntimeAppAuthorizationGrantEffect(str, Enum):
    """Closed allow/deny effect for a permission grant.

    Closed structural vocab: no ``unknown`` / ``other``.
    """

    ALLOW = "allow"
    DENY = "deny"


class RuntimeAppAuthorizationPrincipal(SDLModel):
    """A user, service account, API key, or backend role known to the store.

    No raw secret is ever carried: the credential posture is recorded purely
    via :attr:`credential_classification`.
    """

    principal_id: str
    kind: GovernedVocabulary[RuntimeAppAuthorizationPrincipalKind] = RuntimeAppAuthorizationPrincipalKind.UNKNOWN
    name: str = ""
    reserved: bool | str | None = None
    hidden: bool | str | None = None
    credential_classification: GovernedVocabulary[RuntimeAppAuthorizationCredentialClassification] = (
        RuntimeAppAuthorizationCredentialClassification.NONE
    )
    backend_roles: list[str] = Field(default_factory=list)
    description: str = ""

    @field_validator("principal_id")
    @classmethod
    def validate_principal_id(cls, v: str) -> str:
        return require_symbol(v, field_name="principal_id")

    @field_validator("kind", mode="before")
    @classmethod
    def normalize_kind(cls, v: RuntimeAppAuthorizationPrincipalKind | str) -> object:
        return parse_runtime_enum_or_var(v, RuntimeAppAuthorizationPrincipalKind, field_name="kind")

    @field_validator("credential_classification", mode="before")
    @classmethod
    def normalize_credential_classification(
        cls,
        v: RuntimeAppAuthorizationCredentialClassification | str,
    ) -> object:
        return parse_runtime_enum_or_var(
            v,
            RuntimeAppAuthorizationCredentialClassification,
            field_name="credential_classification",
        )

    @field_validator("reserved", "hidden", mode="before")
    @classmethod
    def parse_optional_bools(cls, v: object) -> bool | str | None:
        return parse_optional_bool_or_var(v, field_name="reserved/hidden")

    @field_validator("backend_roles", mode="before")
    @classmethod
    def coerce_backend_roles(cls, v: object) -> object:
        return coerce_string_list(v)

    @model_validator(mode="after")
    def validate_principal(self) -> "RuntimeAppAuthorizationPrincipal":
        _reject_duplicate_values(self.backend_roles, field_name="backend_roles", owner=self.principal_id)
        return self


class RuntimeAppAuthorizationRole(SDLModel):
    """A named role defined within the application authorization store."""

    role_id: str
    name: str = ""
    description: str = ""

    @field_validator("role_id")
    @classmethod
    def validate_role_id(cls, v: str) -> str:
        return require_symbol(v, field_name="role_id")


class RuntimeAppAuthorizationGrant(SDLModel):
    """A resource-scoped permission grant (role -> actions -> resource pattern).

    ``resource_kind`` is the single author-settable source of truth for the
    resource vocabulary; the owning authorization's ``resource_vocabulary`` is
    the declared set validated against these grants.
    """

    grant_id: str
    role_ref: str = ""
    resource_kind: GovernedVocabulary[RuntimeAppAuthorizationResourceVocabulary] = (
        RuntimeAppAuthorizationResourceVocabulary.UNKNOWN
    )
    actions: list[str] = Field(default_factory=list)
    resource_patterns: list[str] = Field(default_factory=list)
    effect: GovernedVocabulary[RuntimeAppAuthorizationGrantEffect] = RuntimeAppAuthorizationGrantEffect.ALLOW
    description: str = ""

    @field_validator("grant_id")
    @classmethod
    def validate_grant_id(cls, v: str) -> str:
        return require_symbol(v, field_name="grant_id")

    @field_validator("resource_kind", mode="before")
    @classmethod
    def normalize_resource_kind(cls, v: RuntimeAppAuthorizationResourceVocabulary | str) -> object:
        return parse_runtime_enum_or_var(v, RuntimeAppAuthorizationResourceVocabulary, field_name="resource_kind")

    @field_validator("effect", mode="before")
    @classmethod
    def normalize_effect(cls, v: RuntimeAppAuthorizationGrantEffect | str) -> object:
        return parse_runtime_enum_or_var(v, RuntimeAppAuthorizationGrantEffect, field_name="effect")

    @field_validator("actions", "resource_patterns", mode="before")
    @classmethod
    def coerce_lists(cls, v: object) -> object:
        return coerce_string_list(v)

    @model_validator(mode="after")
    def validate_grant(self) -> "RuntimeAppAuthorizationGrant":
        _reject_duplicate_values(self.actions, field_name="actions", owner=self.grant_id)
        _reject_duplicate_values(self.resource_patterns, field_name="resource_patterns", owner=self.grant_id)
        return self


class RuntimeAppAuthorizationRoleMapping(SDLModel):
    """A mapping that binds backend roles, users, or hosts onto a local role."""

    mapping_id: str
    role_ref: str = ""
    backend_roles: list[str] = Field(default_factory=list)
    users: list[str] = Field(default_factory=list)
    hosts: list[str] = Field(default_factory=list)
    description: str = ""

    @field_validator("mapping_id")
    @classmethod
    def validate_mapping_id(cls, v: str) -> str:
        return require_symbol(v, field_name="mapping_id")

    @field_validator("backend_roles", "users", "hosts", mode="before")
    @classmethod
    def coerce_lists(cls, v: object) -> object:
        return coerce_string_list(v)

    @model_validator(mode="after")
    def validate_role_mapping(self) -> "RuntimeAppAuthorizationRoleMapping":
        _reject_duplicate_values(self.backend_roles, field_name="backend_roles", owner=self.mapping_id)
        _reject_duplicate_values(self.users, field_name="users", owner=self.mapping_id)
        _reject_duplicate_values(self.hosts, field_name="hosts", owner=self.mapping_id)
        return self


class RuntimeAppAuthorizationTenant(SDLModel):
    """A tenant/namespace scope within the application authorization store."""

    tenant_id: str
    name: str = ""
    description: str = ""

    @field_validator("tenant_id")
    @classmethod
    def validate_tenant_id(cls, v: str) -> str:
        return require_symbol(v, field_name="tenant_id")


class RuntimeAppAuthorization(SDLModel):
    """Application-internal RBAC store inventory for a single owning spine."""

    app_authorization_id: str
    resource_vocabulary: GovernedVocabulary[RuntimeAppAuthorizationResourceVocabulary] = (
        RuntimeAppAuthorizationResourceVocabulary.UNKNOWN
    )
    auth_enabled: bool | str | None = None
    name: str = ""
    principals: list[RuntimeAppAuthorizationPrincipal] = Field(default_factory=list)
    roles: list[RuntimeAppAuthorizationRole] = Field(default_factory=list)
    permission_grants: list[RuntimeAppAuthorizationGrant] = Field(default_factory=list)
    role_mappings: list[RuntimeAppAuthorizationRoleMapping] = Field(default_factory=list)
    tenants: list[RuntimeAppAuthorizationTenant] = Field(default_factory=list)
    description: str = ""

    @field_validator("app_authorization_id")
    @classmethod
    def validate_app_authorization_id(cls, v: str) -> str:
        return require_symbol(v, field_name="app_authorization_id")

    @field_validator("resource_vocabulary", mode="before")
    @classmethod
    def normalize_resource_vocabulary(cls, v: RuntimeAppAuthorizationResourceVocabulary | str) -> object:
        return parse_runtime_enum_or_var(v, RuntimeAppAuthorizationResourceVocabulary, field_name="resource_vocabulary")

    @field_validator("auth_enabled", mode="before")
    @classmethod
    def parse_auth_enabled(cls, v: object) -> bool | str | None:
        return parse_optional_bool_or_var(v, field_name="auth_enabled")

    @model_validator(mode="after")
    def validate_app_authorization(self) -> "RuntimeAppAuthorization":
        _reject_duplicate_local_ref_ids(self)
        self._require_grants_for_resource_vocabulary()
        return self

    def _require_grants_for_resource_vocabulary(self) -> None:
        """An authorization that declares a concrete vocabulary must use it.

        If :attr:`resource_vocabulary` is a concrete (non-``unknown``) enum
        member, at least one permission grant must carry a matching
        ``resource_kind``. A declared-but-unused vocabulary is rejected. A
        ``${var}`` placeholder or the open ``unknown`` sentinel is exempt
        (nothing concrete is being asserted).
        """
        vocab = self.resource_vocabulary
        if is_variable_ref(vocab):
            return
        if vocab is RuntimeAppAuthorizationResourceVocabulary.UNKNOWN:
            return
        for grant in self.permission_grants:
            if grant.resource_kind == vocab:
                return
        raise ValueError(
            "app_authorization declares a resource_vocabulary but no permission_grant has a matching resource_kind"
        )


def _reject_duplicate_values(values: list[object], *, field_name: str, owner: str) -> None:
    seen: set[object] = set()
    for value in values:
        if value in seen:
            raise ValueError(f"Duplicate runtime app authorization {field_name} entry on '{owner}'")
        seen.add(value)


def _reject_duplicate_local_ref_ids(authorization: RuntimeAppAuthorization) -> None:
    entries: list[tuple[str, str]] = [("app_authorization_id", authorization.app_authorization_id)]
    for label, collection_name in (
        ("principal_id", "principals"),
        ("role_id", "roles"),
        ("grant_id", "permission_grants"),
        ("mapping_id", "role_mappings"),
        ("tenant_id", "tenants"),
    ):
        entries.extend((label, getattr(item, label)) for item in getattr(authorization, collection_name))

    seen: dict[str, str] = {}
    for label, value in entries:
        prior = seen.get(value)
        if prior is not None:
            raise ValueError(
                f"Duplicate runtime app authorization stable id '{value}' in authorization "
                f"'{authorization.app_authorization_id}' across {prior} and {label}"
            )
        seen[value] = label
