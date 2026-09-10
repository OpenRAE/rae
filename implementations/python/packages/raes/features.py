"""Feature models — software deployed onto VMs.

Features are composable configuration units (Service, Configuration,
or Artifact) with dependency graphs. The validator detects cycles.
"""

from enum import Enum

from pydantic import Field, field_validator

from ._base import normalize_enum_value
from ._classification_guard import LegacyClassificationGuard
from ._source import Source


class FeatureType(str, Enum):
    """Kind of feature deployed to a compute node."""

    SERVICE = "service"
    CONFIGURATION = "configuration"
    ARTIFACT = "artifact"


class Feature(LegacyClassificationGuard):
    """A software artifact, service, or configuration deployed to a compute node."""

    legacy_classification_fields = ("vulnerabilities",)

    name: str = ""
    type: FeatureType = Field(alias="type")
    source: Source | None = None

    @field_validator("type", mode="before")
    @classmethod
    def normalize_type(cls, v: str) -> str:
        return normalize_enum_value(v)

    dependencies: list[str] = Field(default_factory=list)
    destination: str = ""
    description: str = ""
    environment: list[str] = Field(default_factory=list)
