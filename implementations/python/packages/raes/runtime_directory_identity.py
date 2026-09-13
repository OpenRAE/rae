"""Directory/domain identity authority runtime inventory models.

These models express participant-observable identity authority state attached
to a runtime node: directories, domains, realms, identity providers, IAM
tenants, subjects, policy facts, and membership/trust relationships. They are
observed runtime facts, not top-level scenario account provisioning requests.
"""

from enum import Enum
from typing import Any

from pydantic import Field, ValidationInfo, field_validator, model_validator

from raes.runtime_vocabulary import GovernedVocabulary

from ._base import SDLModel, parse_int_or_var
from .runtime_filesystem import RuntimeSensitivityClassification
from .runtime_values import (
    coerce_string_list,
    enforce_observed_value_redaction,
    parse_optional_bool_or_var,
    parse_runtime_enum_or_var,
    reject_duplicates,
    require_non_empty,
    require_symbol,
)

__all__ = [
    "RuntimeIdentityAttribute",
    "RuntimeIdentityAuthority",
    "RuntimeIdentityAuthorityKind",
    "RuntimeIdentityAuthorityProtocol",
    "RuntimeIdentityAuthorityService",
    "RuntimeIdentityPolicy",
    "RuntimeIdentityPolicyKind",
    "RuntimeIdentityRecordOrigin",
    "RuntimeIdentityRelationship",
    "RuntimeIdentityRelationshipKind",
    "RuntimeIdentitySubject",
    "RuntimeIdentitySubjectKind",
]

_REDACTED_SENSITIVITIES = (
    RuntimeSensitivityClassification.REDACTED,
    RuntimeSensitivityClassification.OPERATOR_SECRET,
)
_DUPLICATE_IDENTITY_TEMPLATE = "Duplicate runtime identity {label} '{value}' in {container_label}"


class RuntimeIdentityAuthorityKind(str, Enum):
    """Portable kind of identity authority represented by the inventory."""

    DIRECTORY = "directory"
    DOMAIN = "domain"
    KERBEROS_REALM = "kerberos_realm"
    IDENTITY_PROVIDER = "identity_provider"
    CLOUD_IAM = "cloud_iam"
    AUTHORIZATION_SYSTEM = "authorization_system"
    OTHER = "other"
    UNKNOWN = "unknown"


class RuntimeIdentityAuthorityProtocol(str, Enum):
    """Protocol or API family exposed by an identity authority service."""

    LDAP = "ldap"
    LDAPS = "ldaps"
    KERBEROS = "kerberos"
    SAML = "saml"
    OIDC = "oidc"
    OAUTH2 = "oauth2"
    SCIM = "scim"
    AD_DS_RPC = "ad_ds_rpc"
    GRAPH_API = "graph_api"
    OTHER = "other"
    UNKNOWN = "unknown"


class RuntimeIdentitySubjectKind(str, Enum):
    """Portable subject/principal kind within an identity authority."""

    USER = "user"
    GROUP = "group"
    COMPUTER = "computer"
    DEVICE = "device"
    SERVICE_ACCOUNT = "service_account"
    SERVICE_PRINCIPAL = "service_principal"
    ROLE = "role"
    APPLICATION = "application"
    ORGANIZATIONAL_UNIT = "organizational_unit"
    OTHER = "other"
    UNKNOWN = "unknown"


class RuntimeIdentityRelationshipKind(str, Enum):
    """Portable relationship kind between authority-local identity objects."""

    MEMBER_OF = "member_of"
    HAS_MEMBER = "has_member"
    TRUSTS = "trusts"
    FEDERATES_WITH = "federates_with"
    MANAGES = "manages"
    OWNS = "owns"
    DELEGATED_ADMIN = "delegated_admin"
    SYNCS_FROM = "syncs_from"
    ASSOCIATED = "associated"
    OTHER = "other"
    UNKNOWN = "unknown"


class RuntimeIdentityPolicyKind(str, Enum):
    """Portable policy family attached to an identity authority."""

    PASSWORD = "password"  # noqa: S105
    LOCKOUT = "lockout"
    KERBEROS = "kerberos"
    ACCESS = "access"
    CONDITIONAL_ACCESS = "conditional_access"
    MFA = "mfa"
    GROUP_POLICY = "group_policy"
    TRUST = "trust"
    OTHER = "other"
    UNKNOWN = "unknown"


class RuntimeIdentityRecordOrigin(str, Enum):
    """Origin class for an observed identity authority record."""

    BUILT_IN = "built_in"
    DIRECTORY = "directory"
    SYNCHRONIZED = "synchronized"
    FEDERATED = "federated"
    PROVISIONED = "provisioned"
    RUNTIME_CREATED = "runtime_created"
    OPERATOR = "operator"
    UNKNOWN = "unknown"
    OTHER = "other"


def _reject_duplicate_local_ref_ids(authority: "RuntimeIdentityAuthority") -> None:
    seen: dict[str, str] = {}
    entries: list[tuple[str, str]] = [("identity_authority_id", authority.identity_authority_id)]
    entries.extend(("service_id", service.service_id) for service in authority.services)
    entries.extend(("subject_id", subject.subject_id) for subject in authority.subjects)
    entries.extend(("policy_id", policy.policy_id) for policy in authority.policies)
    entries.extend(("relationship_id", relationship.relationship_id) for relationship in authority.relationships)

    for label, value in entries:
        prior = seen.get(value)
        if prior is not None:
            raise ValueError(
                f"Duplicate runtime identity stable id '{value}' in identity authority "
                f"'{authority.identity_authority_id}' across {prior} and {label}"
            )
        seen[value] = label


class RuntimeIdentityAttribute(SDLModel):
    """Observed identity attribute or bounded setting.

    Secret-bearing names must not carry raw values. This keeps directory
    passwords, Kerberos keys, keytabs, tokens, and client secrets out of
    fixtures, diagnostics, schemas, and generated runtime artifacts.
    """

    name: str
    values: list[str] = Field(default_factory=list)
    value_classification: GovernedVocabulary[RuntimeSensitivityClassification] = (
        RuntimeSensitivityClassification.UNKNOWN
    )
    origin: GovernedVocabulary[RuntimeIdentityRecordOrigin] = RuntimeIdentityRecordOrigin.UNKNOWN
    provenance: GovernedVocabulary[RuntimeIdentityRecordOrigin] = RuntimeIdentityRecordOrigin.UNKNOWN
    description: str = ""

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        return require_non_empty(v, field_name="identity attribute name")

    @field_validator("values", mode="before")
    @classmethod
    def coerce_values(cls, v: Any) -> list[str]:
        return coerce_string_list(v)

    @field_validator("values")
    @classmethod
    def validate_values(cls, v: list[str]) -> list[str]:
        for value in v:
            if not isinstance(value, str) or not value.strip():
                raise ValueError("identity attribute values must be non-empty strings")
        if len(v) != len(set(v)):
            raise ValueError("Duplicate runtime identity attribute value")
        return v

    @field_validator("value_classification", mode="before")
    @classmethod
    def normalize_value_classification(
        cls,
        v: RuntimeSensitivityClassification | str,
    ) -> RuntimeSensitivityClassification | str:
        return parse_runtime_enum_or_var(v, RuntimeSensitivityClassification, field_name="value_classification")

    @field_validator("origin", mode="before")
    @classmethod
    def normalize_origin(cls, v: RuntimeIdentityRecordOrigin | str) -> RuntimeIdentityRecordOrigin | str:
        return parse_runtime_enum_or_var(v, RuntimeIdentityRecordOrigin, field_name="origin")

    @field_validator("provenance", mode="before")
    @classmethod
    def normalize_provenance(cls, v: RuntimeIdentityRecordOrigin | str) -> RuntimeIdentityRecordOrigin | str:
        return parse_runtime_enum_or_var(v, RuntimeIdentityRecordOrigin, field_name="provenance")

    @model_validator(mode="after")
    def align_origin_and_provenance(self) -> "RuntimeIdentityAttribute":
        if (
            self.origin == RuntimeIdentityRecordOrigin.UNKNOWN
            and self.provenance != RuntimeIdentityRecordOrigin.UNKNOWN
        ):
            self.origin = self.provenance
        elif (
            self.provenance != RuntimeIdentityRecordOrigin.UNKNOWN
            and self.origin != RuntimeIdentityRecordOrigin.UNKNOWN
            and self.provenance != self.origin
        ):
            raise ValueError("origin and provenance must describe the same runtime identity record origin")
        return self

    @model_validator(mode="after")
    def validate_redacted_values(self) -> "RuntimeIdentityAttribute":
        enforce_observed_value_redaction(
            owner_label=f"identity attribute '{self.name}'",
            value=self.values,
            classification=self.value_classification,
            redacted_classifications=_REDACTED_SENSITIVITIES,
            raw_value_label="raw values",
        )
        return self


class RuntimeIdentityAuthorityService(SDLModel):
    """A protocol/API endpoint associated with an identity authority."""

    service_id: str
    service: str = ""
    protocol: GovernedVocabulary[RuntimeIdentityAuthorityProtocol] = RuntimeIdentityAuthorityProtocol.OTHER
    address: str = ""
    port: int | str | None = None
    description: str = ""

    @field_validator("service_id")
    @classmethod
    def validate_service_id(cls, v: str) -> str:
        return require_symbol(v, field_name="service_id")

    @field_validator("protocol", mode="before")
    @classmethod
    def normalize_protocol(
        cls,
        v: RuntimeIdentityAuthorityProtocol | str,
    ) -> RuntimeIdentityAuthorityProtocol | str:
        return parse_runtime_enum_or_var(v, RuntimeIdentityAuthorityProtocol, field_name="protocol")

    @field_validator("port", mode="before")
    @classmethod
    def parse_port(cls, v: int | str | None) -> int | str | None:
        return parse_int_or_var(v, minimum=1, maximum=65535, field_name="port") if v is not None else v


class RuntimeIdentitySubject(SDLModel):
    """An authority-local user, group, device, role, or service principal."""

    subject_id: str
    kind: GovernedVocabulary[RuntimeIdentitySubjectKind] = RuntimeIdentitySubjectKind.OTHER
    name: str
    display_name: str = ""
    principal_name: str = ""
    distinguished_name: str = ""
    domain: str = ""
    enabled: bool | str | None = None
    origin: GovernedVocabulary[RuntimeIdentityRecordOrigin] = RuntimeIdentityRecordOrigin.UNKNOWN
    service_principal_names: list[str] = Field(default_factory=list)
    attributes: list[RuntimeIdentityAttribute] = Field(default_factory=list)
    description: str = ""

    @field_validator("subject_id")
    @classmethod
    def validate_subject_id(cls, v: str) -> str:
        return require_symbol(v, field_name="subject_id")

    @field_validator("kind", mode="before")
    @classmethod
    def normalize_kind(cls, v: RuntimeIdentitySubjectKind | str) -> RuntimeIdentitySubjectKind | str:
        return parse_runtime_enum_or_var(v, RuntimeIdentitySubjectKind, field_name="kind")

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        return require_non_empty(v, field_name="identity subject name")

    @field_validator("enabled", mode="before")
    @classmethod
    def parse_enabled(cls, v: bool | str | None) -> bool | str | None:
        return parse_optional_bool_or_var(v, field_name="enabled")

    @field_validator("origin", mode="before")
    @classmethod
    def normalize_origin(cls, v: RuntimeIdentityRecordOrigin | str) -> RuntimeIdentityRecordOrigin | str:
        return parse_runtime_enum_or_var(v, RuntimeIdentityRecordOrigin, field_name="origin")

    @field_validator("service_principal_names", mode="before")
    @classmethod
    def coerce_service_principal_names(cls, v: Any) -> list[str]:
        return coerce_string_list(v)

    @model_validator(mode="after")
    def validate_subject(self) -> "RuntimeIdentitySubject":
        reject_duplicates(
            self.service_principal_names,
            label="service_principal_name",
            container_label=f"subject '{self.subject_id}'",
            duplicate_template=_DUPLICATE_IDENTITY_TEMPLATE,
        )
        reject_duplicates(
            (attribute.name for attribute in self.attributes),
            label="attribute",
            container_label=f"subject '{self.subject_id}'",
            duplicate_template=_DUPLICATE_IDENTITY_TEMPLATE,
        )
        return self


class RuntimeIdentityPolicy(SDLModel):
    """Observed identity authority policy or bounded policy setting group."""

    policy_id: str
    policy_kind: GovernedVocabulary[RuntimeIdentityPolicyKind] = RuntimeIdentityPolicyKind.OTHER
    name: str = ""
    applies_to_refs: list[str] = Field(default_factory=list)
    settings: list[RuntimeIdentityAttribute] = Field(default_factory=list)
    description: str = ""

    @field_validator("policy_id")
    @classmethod
    def validate_policy_id(cls, v: str) -> str:
        return require_symbol(v, field_name="policy_id")

    @field_validator("policy_kind", mode="before")
    @classmethod
    def normalize_policy_kind(cls, v: RuntimeIdentityPolicyKind | str) -> RuntimeIdentityPolicyKind | str:
        return parse_runtime_enum_or_var(v, RuntimeIdentityPolicyKind, field_name="policy_kind")

    @field_validator("applies_to_refs", mode="before")
    @classmethod
    def coerce_applies_to_refs(cls, v: Any) -> list[str]:
        return coerce_string_list(v)

    @model_validator(mode="after")
    def validate_policy(self) -> "RuntimeIdentityPolicy":
        reject_duplicates(
            self.applies_to_refs,
            label="policy applies_to_ref",
            container_label=f"policy '{self.policy_id}'",
            duplicate_template=_DUPLICATE_IDENTITY_TEMPLATE,
        )
        reject_duplicates(
            (setting.name for setting in self.settings),
            label="policy setting",
            container_label=f"policy '{self.policy_id}'",
            duplicate_template=_DUPLICATE_IDENTITY_TEMPLATE,
        )
        return self


class RuntimeIdentityRelationship(SDLModel):
    """Observed membership, trust, federation, or delegation relationship."""

    relationship_id: str
    relationship_type: GovernedVocabulary[RuntimeIdentityRelationshipKind] = RuntimeIdentityRelationshipKind.OTHER
    source_ref: str
    target_ref: str = ""
    external_target: str = ""
    description: str = ""

    @field_validator("relationship_id")
    @classmethod
    def validate_relationship_id(cls, v: str) -> str:
        return require_symbol(v, field_name="relationship_id")

    @field_validator("relationship_type", mode="before")
    @classmethod
    def normalize_relationship_type(
        cls,
        v: RuntimeIdentityRelationshipKind | str,
    ) -> RuntimeIdentityRelationshipKind | str:
        return parse_runtime_enum_or_var(v, RuntimeIdentityRelationshipKind, field_name="relationship_type")

    @field_validator("source_ref")
    @classmethod
    def validate_source_ref(cls, v: str) -> str:
        return require_non_empty(v, field_name="source_ref")

    @field_validator("target_ref", "external_target")
    @classmethod
    def validate_optional_targets(cls, v: str, info: ValidationInfo) -> str:
        return require_non_empty(v, field_name=info.field_name) if v else v

    @model_validator(mode="after")
    def validate_relationship_target(self) -> "RuntimeIdentityRelationship":
        if bool(self.target_ref) == bool(self.external_target):
            raise ValueError("identity relationships require exactly one of target_ref or external_target")
        return self


class RuntimeIdentityAuthority(SDLModel):
    """A node-scoped identity authority inventory."""

    identity_authority_id: str
    kind: GovernedVocabulary[RuntimeIdentityAuthorityKind] = RuntimeIdentityAuthorityKind.OTHER
    name: str = ""
    namespace: str = ""
    domain_name: str = ""
    realm: str = ""
    issuer: str = ""
    tenant_id: str = ""
    base_dn: str = ""
    description: str = ""
    services: list[RuntimeIdentityAuthorityService] = Field(default_factory=list)
    subjects: list[RuntimeIdentitySubject] = Field(default_factory=list)
    policies: list[RuntimeIdentityPolicy] = Field(default_factory=list)
    relationships: list[RuntimeIdentityRelationship] = Field(default_factory=list)

    @field_validator("identity_authority_id")
    @classmethod
    def validate_identity_authority_id(cls, v: str) -> str:
        return require_symbol(v, field_name="identity_authority_id")

    @field_validator("kind", mode="before")
    @classmethod
    def normalize_kind(cls, v: RuntimeIdentityAuthorityKind | str) -> RuntimeIdentityAuthorityKind | str:
        return parse_runtime_enum_or_var(v, RuntimeIdentityAuthorityKind, field_name="kind")

    @model_validator(mode="after")
    def validate_authority(self) -> "RuntimeIdentityAuthority":
        container = f"identity authority '{self.identity_authority_id}'"
        reject_duplicates(
            (service.service_id for service in self.services),
            label="service_id",
            container_label=container,
            duplicate_template=_DUPLICATE_IDENTITY_TEMPLATE,
        )
        reject_duplicates(
            (subject.subject_id for subject in self.subjects),
            label="subject_id",
            container_label=container,
            duplicate_template=_DUPLICATE_IDENTITY_TEMPLATE,
        )
        reject_duplicates(
            (policy.policy_id for policy in self.policies),
            label="policy_id",
            container_label=container,
            duplicate_template=_DUPLICATE_IDENTITY_TEMPLATE,
        )
        reject_duplicates(
            (relationship.relationship_id for relationship in self.relationships),
            label="relationship_id",
            container_label=container,
            duplicate_template=_DUPLICATE_IDENTITY_TEMPLATE,
        )
        _reject_duplicate_local_ref_ids(self)
        return self
