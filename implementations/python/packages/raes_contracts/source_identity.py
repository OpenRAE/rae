"""Portable identity of the root SDL source of an analysis."""

from __future__ import annotations

import re

from pydantic import Field, model_validator

from ._base import ContractModel, PrefixedDigestString


class SourceArtifactIdentityModel(ContractModel):
    """Portable identity and exact-byte digest for the root SDL source."""

    source_id: str = Field(min_length=1, max_length=256, pattern=r"^[^\r\n]+$")
    byte_digest: PrefixedDigestString

    @model_validator(mode="after")
    def _reject_host_paths(self) -> SourceArtifactIdentityModel:
        if self.source_id.startswith(("/", "\\")) or re.match(r"^[A-Za-z]:[\\/]", self.source_id):
            raise ValueError("source_id must be portable rather than an absolute host path")
        if ".." in self.source_id.replace("\\", "/").split("/"):
            raise ValueError("source_id must not contain parent traversal")
        return self


__all__ = ["SourceArtifactIdentityModel"]
