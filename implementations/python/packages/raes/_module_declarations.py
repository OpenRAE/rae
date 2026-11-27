"""Authored module descriptors and import declarations."""

from pydantic import Field, field_validator, model_validator
from raes_contracts.identifiers import (
    PortableIdentifier,
    require_module_identifier,
    require_portable_identifier,
)
from raes_contracts.sdl_model import SDLModel

# Resolved import provenance bounds both the requested and the module version to this length.
_MAX_VERSION_LENGTH = 256


def _require_version_text(value: str, *, field_name: str) -> str:
    """Reject a blank or overlong version, which resolved import provenance cannot record."""
    if not value.strip():
        raise ValueError(f"{field_name} must not be blank")
    if len(value) > _MAX_VERSION_LENGTH:
        raise ValueError(f"{field_name} must be at most {_MAX_VERSION_LENGTH} characters")
    return value


class ModuleDescriptor(SDLModel):
    """Published module metadata for SDL composition."""

    id: str
    version: str
    parameters: list[PortableIdentifier] = Field(default_factory=list)
    exports: dict[str, list[str]] = Field(default_factory=dict)
    description: str = ""

    @field_validator("version")
    @classmethod
    def _validate_version(cls, value: str) -> str:
        return _require_version_text(value, field_name="module.version")

    @model_validator(mode="after")
    def validate_descriptor(self) -> ModuleDescriptor:
        require_module_identifier(self.id)
        if len(self.parameters) != len(set(self.parameters)):
            raise ValueError("module.parameters must be unique")
        for section, names in self.exports.items():
            if len(names) != len(set(names)):
                raise ValueError(f"module.exports.{section} entries must be unique")
        return self


class ImportDecl(SDLModel):
    """A module import expanded before full semantic validation."""

    source: str = ""
    path: str = ""
    namespace: str = ""
    version: str = "*"
    parameters: dict[PortableIdentifier, object] = Field(default_factory=dict)
    digest: str = ""

    @field_validator("version")
    @classmethod
    def _validate_version_constraint(cls, value: str) -> str:
        from packaging.specifiers import InvalidSpecifier

        from .module_registry._digests import _normalize_exact_or_range

        _require_version_text(value, field_name="import version")
        try:
            _normalize_exact_or_range(value)
        except InvalidSpecifier as exc:
            raise ValueError("import version must be an exact version, '*', or a valid version range") from exc
        return value

    @model_validator(mode="after")
    def validate_source_fields(self) -> ImportDecl:
        if not self.source and not self.path:
            raise ValueError("Import requires either 'source' or deprecated 'path'")
        if self.source and self.path:
            raise ValueError("Import may specify only one of 'source' or 'path'")
        if not self.namespace:
            raise ValueError("Import requires an explicit namespace")
        require_portable_identifier(self.namespace, field_name="namespace")
        return self

    @property
    def normalized_source(self) -> str:
        if self.source:
            return self.source
        return f"local:{self.path}"
