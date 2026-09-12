"""Dependency-neutral base primitives for closed RAES contracts."""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field


class ContractModel(BaseModel):
    """Base model for closed-world external contracts."""

    model_config = ConfigDict(extra="forbid")


NonEmptyString = Annotated[str, Field(min_length=1)]
PrefixedDigestString = Annotated[
    str,
    Field(
        min_length=1,
        pattern=(
            r"^(?:sha256:[A-Fa-f0-9]{64}|sha384:[A-Fa-f0-9]{96}|"
            r"sha512:[A-Fa-f0-9]{128}|blake3:[A-Fa-f0-9]{64})$"
        ),
    ),
]

__all__ = ["ContractModel", "NonEmptyString", "PrefixedDigestString"]
