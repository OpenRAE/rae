"""Authored identity-domain declarations and typed topology details.

This authoring surface is realization intent.  It is intentionally separate
from :mod:`raes.runtime_directory_identity`, which records runtime
inventory observed on a node.
"""

import re
from enum import Enum

from pydantic import ConfigDict, Field, field_validator, model_validator
from raes_contracts.domain_profiles import DomainProfileBindingModel

from ._base import SDLModel
from .profile_selections import parse_profile_or_enum
from .value_parsing import WholeFieldVariableReference, is_variable_ref

_DNS_LABEL_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?$")
_NETBIOS_NAME_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,13}[A-Za-z0-9])?$")


class IdentityDomainProfile(str, Enum):
    """Closed profiles whose controller/join semantics are realizable."""

    ACTIVE_DIRECTORY = "active_directory"


class IdentityDomain(SDLModel):
    """Scenario-scoped authored identity domain."""

    model_config = ConfigDict(
        json_schema_extra={
            "allOf": [
                {
                    "if": {"properties": {"profile": {"type": "string"}}},
                    "then": {
                        "required": ["dns_name", "netbios_name"],
                        "properties": {"dns_name": {"minLength": 1}, "netbios_name": {"minLength": 1}},
                    },
                }
            ],
        }
    )

    profile: IdentityDomainProfile | DomainProfileBindingModel | WholeFieldVariableReference
    dns_name: str = ""
    netbios_name: str = ""
    authority_account_ref: str = Field(min_length=1)

    @field_validator("profile", mode="before")
    @classmethod
    def normalize_profile(cls, value: str) -> IdentityDomainProfile | WholeFieldVariableReference:
        return parse_profile_or_enum(value, IdentityDomainProfile, field_name="profile")

    @model_validator(mode="after")
    def _selected_domain_shape(self) -> "IdentityDomain":
        if not isinstance(self.profile, DomainProfileBindingModel) and (not self.dns_name or not self.netbios_name):
            raise ValueError("Active Directory requires dns_name and netbios_name")
        return self

    @field_validator("dns_name")
    @classmethod
    def validate_dns_name(cls, value: str) -> str:
        if not value or is_variable_ref(value):
            return value
        labels = value.split(".")
        if len(value) > 253 or any(not _DNS_LABEL_RE.fullmatch(label) for label in labels):
            raise ValueError("dns_name must be a valid DNS domain name")
        return value

    @field_validator("netbios_name")
    @classmethod
    def validate_netbios_name(cls, value: str) -> str:
        if not value or is_variable_ref(value):
            return value
        if len(value) > 15 or _NETBIOS_NAME_RE.fullmatch(value) is None:
            raise ValueError("netbios_name must be a valid NetBIOS domain name of at most 15 characters")
        return value


class RelationshipDomainController(SDLModel):
    """Typed marker for a node-to-domain controller-role edge."""


class RelationshipDomainJoin(SDLModel):
    """Typed member join with explicit ordered controller candidates."""

    controller_refs: list[str] = Field(min_length=1)

    @field_validator("controller_refs")
    @classmethod
    def validate_controller_refs(cls, values: list[str]) -> list[str]:
        if any(not isinstance(value, str) or not value.strip() for value in values):
            raise ValueError("controller_refs must contain non-empty references")
        if len(values) != len(set(values)):
            raise ValueError("controller_refs must be unique")
        return values


__all__ = [
    "IdentityDomain",
    "IdentityDomainProfile",
    "RelationshipDomainController",
    "RelationshipDomainJoin",
]
