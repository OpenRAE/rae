"""Public operating-system identity contract models."""

from __future__ import annotations

from pydantic import Field, model_validator

from ..controlled_vocabularies import validate_controlled_vocabulary_value
from ..operating_systems import validate_operating_system_pair
from .base import ContractModel, NonEmptyString


class ObservedOperatingSystemIdentityModel(ContractModel):
    """Typed guest-observed OS identity carried by a bound disclosure."""

    family: NonEmptyString
    distribution: NonEmptyString
    version: NonEmptyString = Field(max_length=128, pattern=r"^[!-~](?:[ -~]{0,126}[!-~])?$")

    @model_validator(mode="after")
    def _validate_vocabulary(self) -> ObservedOperatingSystemIdentityModel:

        validate_controlled_vocabulary_value("provisioner-os-families", self.family)
        validate_controlled_vocabulary_value("os-distributions", self.distribution)
        validate_operating_system_pair(self.family, self.distribution)
        return self
