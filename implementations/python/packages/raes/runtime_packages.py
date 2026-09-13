"""Typed runtime package and third-party repository declarations."""

from __future__ import annotations

import re
from typing import Annotated, Literal
from urllib.parse import urlsplit

from pydantic import Field, GetJsonSchemaHandler, WithJsonSchema, field_validator, model_validator
from pydantic.json_schema import JsonSchemaValue
from pydantic_core import CoreSchema
from raes_contracts.uri_safety import validate_safe_absolute_uri

from ._base import VARIABLE_REFERENCE_SCHEMA_MARKER, VARIABLE_TOKEN_PATTERN, SDLModel, is_variable_ref
from .architectures import PackageArchitectureString, normalize_architecture

_HTTPS_URI_OR_VARIABLE_PATTERN = rf"^(?:https://[^\s#]+|{VARIABLE_TOKEN_PATTERN})$"
_SHA256_OR_VARIABLE_PATTERN = rf"^(?:sha256:[a-f0-9]{{64}}|{VARIABLE_TOKEN_PATTERN})$"
_APT_SUITE_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9.+_~:-]{0,127}$"
_APT_COMPONENT_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9.+_~-]{0,127}$"
_APT_PACKAGE_NAME_PATTERN = r"^[a-z0-9][a-z0-9+.-]{0,127}$"
_APT_PACKAGE_VERSION_PATTERN = r"^[0-9][A-Za-z0-9.+:~_-]{0,255}$"

HttpsUriOrVariable = Annotated[
    str,
    Field(min_length=1, max_length=2048, pattern=_HTTPS_URI_OR_VARIABLE_PATTERN),
    WithJsonSchema(
        {
            "anyOf": [
                {
                    "type": "string",
                    "minLength": 1,
                    "maxLength": 2048,
                    "pattern": r"^https://[^\s#]+$",
                    "not": {
                        "anyOf": [
                            {"pattern": r"^https://[^/?#]*@"},
                            {
                                "pattern": (
                                    r"[?&](?:access_token|api_key|apikey|auth|credential|key|password|"
                                    r"secret|sig|signature|token)(?:=|&|$)"
                                )
                            },
                        ]
                    },
                },
                {
                    "type": "string",
                    "pattern": rf"^{VARIABLE_TOKEN_PATTERN}$",
                    VARIABLE_REFERENCE_SCHEMA_MARKER: True,
                },
            ]
        }
    ),
]
Sha256DigestOrVariable = Annotated[
    str,
    Field(pattern=_SHA256_OR_VARIABLE_PATTERN),
]
AptSuiteToken = Annotated[str, Field(min_length=1, max_length=128, pattern=_APT_SUITE_PATTERN)]
AptComponentToken = Annotated[str, Field(min_length=1, max_length=128, pattern=_APT_COMPONENT_PATTERN)]


def _validate_https_uri(value: object, *, field_name: str) -> object:
    """Validate an inert public HTTPS URI without dereferencing it."""

    if is_variable_ref(value):
        return value
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string")
    validate_safe_absolute_uri(value, field_name=field_name, forbid_fragment=True)
    if urlsplit(value).scheme.casefold() != "https":
        raise ValueError(f"{field_name} must use HTTPS")
    return value


def _is_safe_apt_token(value: object, pattern: str) -> bool:
    return is_variable_ref(value) or isinstance(value, str) and re.fullmatch(pattern, value, re.ASCII) is not None


class RuntimePackageRepositorySigningKey(SDLModel):
    """Exact public OpenPGP key bytes trusted by one package repository."""

    uri: HttpsUriOrVariable = Field(
        description="Credential-free HTTPS location of the public signing-key bytes.",
    )
    format: Literal["openpgp-ascii-armored", "openpgp-binary"]
    digest: Sha256DigestOrVariable = Field(
        description="Canonical SHA-256 digest of the exact public signing-key bytes.",
    )

    @field_validator("uri", mode="before")
    @classmethod
    def validate_uri(cls, value: object) -> object:
        return _validate_https_uri(value, field_name="signing key uri")


class RuntimeAptPackageRepository(SDLModel):
    """Version 1 portable binary APT repository and dedicated trust binding."""

    repository_profile: Literal["apt"]
    profile_version: Literal["1"]
    uri: HttpsUriOrVariable = Field(
        description="Credential-free HTTPS base URI of the binary APT repository.",
    )
    suite: AptSuiteToken
    components: list[AptComponentToken] = Field(
        min_length=1,
        max_length=32,
        json_schema_extra={"uniqueItems": True},
    )
    signing_key: RuntimePackageRepositorySigningKey

    @field_validator("uri", mode="before")
    @classmethod
    def validate_uri(cls, value: object) -> object:
        return _validate_https_uri(value, field_name="repository uri")

    @field_validator("suite", mode="before")
    @classmethod
    def validate_suite(cls, value: object) -> object:
        if not _is_safe_apt_token(value, _APT_SUITE_PATTERN):
            raise ValueError("suite must be a bounded APT token")
        return value

    @field_validator("components", mode="before")
    @classmethod
    def validate_components(cls, value: object) -> object:
        if not isinstance(value, list) or not value:
            raise ValueError("components must contain at least one APT component")
        if any(not _is_safe_apt_token(component, _APT_COMPONENT_PATTERN) for component in value):
            raise ValueError("component must be a bounded APT token")
        if len(value) != len(set(value)):
            raise ValueError("components must not contain duplicates")
        return sorted(value)


# This compatibility profile retains its fixed final-state meaning. New
# acquisition semantics use component domain-profile refinements instead.
RuntimePackageRepository = Annotated[
    RuntimeAptPackageRepository,
    Field(discriminator="repository_profile"),
]


class RuntimePackage(SDLModel):
    """An exact package required in a runtime image or node.

    ``repository`` is absent for ordinary target-configured repositories. When
    present, it is required final node state and stays within the existing
    ``runtime-packages`` realization concern.
    """

    manager: str = Field(description="Package manager identity used by the target node.")
    name: str = Field(description="Package name interpreted by the selected package manager.")
    version: str = Field(description="Exact package version interpreted by the selected package manager.")
    architecture: PackageArchitectureString = ""
    source: str = Field(
        default="",
        description="Opaque package source or provenance label; never a repository declaration or executable value.",
    )
    purl: str = Field(
        default="",
        description="Package URL identity metadata; never a repository locator, trust binding, or acquisition command.",
    )
    repository: RuntimePackageRepository | None = Field(
        default=None,
        description="Closed third-party repository profile; absence selects the target's ordinary configured sources.",
    )

    @field_validator("architecture", mode="before")
    @classmethod
    def normalize_package_architecture(cls, value: object) -> object:
        """Normalize a populated package architecture to a canonical token."""

        if value is None or value == "":
            return value
        normalized = normalize_architecture(value)
        return normalized.value if hasattr(normalized, "value") else normalized

    @model_validator(mode="after")
    def validate_repository_package(self) -> RuntimePackage:
        if self.repository is None:
            return self
        if self.manager != self.repository.repository_profile:
            raise ValueError("repository profile 'apt' requires package manager 'apt'")
        if not _is_safe_apt_token(self.name, _APT_PACKAGE_NAME_PATTERN):
            raise ValueError("package name must be a bounded APT token")
        if not _is_safe_apt_token(self.version, _APT_PACKAGE_VERSION_PATTERN):
            raise ValueError("package version must be a bounded APT token")
        return self

    @classmethod
    def __get_pydantic_json_schema__(
        cls,
        core_schema: CoreSchema,
        handler: GetJsonSchemaHandler,
    ) -> JsonSchemaValue:
        schema = handler.resolve_ref_schema(handler(core_schema))
        schema.setdefault("allOf", []).append(
            {
                "if": {
                    "required": ["repository"],
                    "properties": {"repository": {"not": {"type": "null"}}},
                },
                "then": {
                    "properties": {
                        "manager": {"const": "apt"},
                        "name": {
                            "anyOf": [
                                {"pattern": _APT_PACKAGE_NAME_PATTERN},
                                {"pattern": rf"^{VARIABLE_TOKEN_PATTERN}$"},
                            ]
                        },
                        "version": {
                            "anyOf": [
                                {"pattern": _APT_PACKAGE_VERSION_PATTERN},
                                {"pattern": rf"^{VARIABLE_TOKEN_PATTERN}$"},
                            ]
                        },
                    }
                },
            }
        )
        return schema


__all__ = [
    "RuntimeAptPackageRepository",
    "RuntimePackage",
    "RuntimePackageRepository",
    "RuntimePackageRepositorySigningKey",
]
