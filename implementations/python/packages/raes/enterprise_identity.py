"""Authored enterprise identity intent above individual identity domains."""

from enum import Enum

from pydantic import Field, field_validator
from raes_contracts.domain_profiles import DomainProfileBindingModel

from ._base import SDLModel
from .profile_selections import parse_profile_or_enum
from .value_parsing import WholeFieldVariableReference, parse_enum_or_var


class IdentityFacadeProtocol(str, Enum):
    """Challenge-facing identity protocol exposed by an authored facade."""

    OIDC = "oidc"


class IdentityForest(SDLModel):
    """A forest with explicit root and complete authored domain membership."""

    root_domain_ref: str = Field(min_length=1)
    domain_refs: list[str] = Field(min_length=1)

    @field_validator("domain_refs")
    @classmethod
    def validate_domain_refs(cls, values: list[str]) -> list[str]:
        if any(not value.strip() for value in values):
            raise ValueError("domain_refs must contain non-empty references")
        if len(values) != len(set(values)):
            raise ValueError("domain_refs must be unique")
        return values


class IdentityFacade(SDLModel):
    """Authored IdP facade identified through an existing logical service."""

    service_ref: str = Field(min_length=1)
    protocol: IdentityFacadeProtocol | DomainProfileBindingModel | WholeFieldVariableReference

    @field_validator("protocol", mode="before")
    @classmethod
    def normalize_protocol(cls, value: str) -> IdentityFacadeProtocol | WholeFieldVariableReference:
        return parse_profile_or_enum(value, IdentityFacadeProtocol, field_name="protocol")


class ForestTrustType(str, Enum):
    """Closed forest-to-forest trust profiles."""

    FOREST = "forest"


class ForestTrustDirection(str, Enum):
    """Authority direction for one forest trust edge."""

    ONE_WAY_OUTBOUND = "one_way_outbound"
    ONE_WAY_INBOUND = "one_way_inbound"
    BIDIRECTIONAL = "bidirectional"


class RelationshipForestTrust(SDLModel):
    """Typed forest trust detail; relationship endpoints own forest identity."""

    trust_type: ForestTrustType | DomainProfileBindingModel | WholeFieldVariableReference
    direction: ForestTrustDirection | WholeFieldVariableReference

    @field_validator("trust_type", mode="before")
    @classmethod
    def normalize_trust_type(cls, value: str) -> ForestTrustType | WholeFieldVariableReference:
        return parse_profile_or_enum(value, ForestTrustType, field_name="trust_type")

    @field_validator("direction", mode="before")
    @classmethod
    def normalize_direction(cls, value: str) -> ForestTrustDirection | WholeFieldVariableReference:
        return parse_enum_or_var(value, ForestTrustDirection, field_name="direction")


class FederationDirection(str, Enum):
    """Portable direction for workforce authority federation."""

    AUTHORITY_TO_FACADE = "authority_to_facade"


class FederationProtocol(str, Enum):
    """Portable directory-to-facade synchronization protocols."""

    LDAP_TLS = "ldap_tls"
    SCIM = "scim"


class FederationMappingIntent(str, Enum):
    """Portable outcome of identity mapping without provider mapper syntax."""

    GROUPS_TO_ROLES = "groups_to_roles"


class TenantClaimOwner(str, Enum):
    """Authority allowed to issue the server-controlled tenant claim."""

    FACADE = "facade"


class RelationshipIdentityFederation(SDLModel):
    """Typed human-authority-to-IdP-facade federation intent."""

    direction: FederationDirection | WholeFieldVariableReference
    protocol: FederationProtocol | DomainProfileBindingModel | WholeFieldVariableReference
    mapping_intent: FederationMappingIntent | DomainProfileBindingModel | WholeFieldVariableReference
    tenant_claim_name: str = Field(min_length=1)
    tenant_claim_owner: TenantClaimOwner | WholeFieldVariableReference

    @field_validator("direction", mode="before")
    @classmethod
    def normalize_direction(cls, value: str) -> FederationDirection | WholeFieldVariableReference:
        return parse_enum_or_var(value, FederationDirection, field_name="direction")

    @field_validator("protocol", mode="before")
    @classmethod
    def normalize_protocol(cls, value: str) -> FederationProtocol | WholeFieldVariableReference:
        return parse_profile_or_enum(value, FederationProtocol, field_name="protocol")

    @field_validator("mapping_intent", mode="before")
    @classmethod
    def normalize_mapping_intent(cls, value: str) -> FederationMappingIntent | WholeFieldVariableReference:
        return parse_profile_or_enum(value, FederationMappingIntent, field_name="mapping_intent")

    @field_validator("tenant_claim_owner", mode="before")
    @classmethod
    def normalize_claim_owner(cls, value: str) -> TenantClaimOwner | WholeFieldVariableReference:
        return parse_enum_or_var(value, TenantClaimOwner, field_name="tenant_claim_owner")


__all__ = [
    "FederationDirection",
    "FederationMappingIntent",
    "FederationProtocol",
    "ForestTrustDirection",
    "ForestTrustType",
    "IdentityFacade",
    "IdentityFacadeProtocol",
    "IdentityForest",
    "RelationshipForestTrust",
    "RelationshipIdentityFederation",
    "TenantClaimOwner",
]
