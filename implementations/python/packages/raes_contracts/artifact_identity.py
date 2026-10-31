"""Provider-neutral artifact identity and mechanism profiles.

Authored artifact requirements and realized artifact disclosures share these
models.
"""

from __future__ import annotations

import re
from typing import Annotated

from pydantic import Field, GetJsonSchemaHandler, model_validator
from pydantic.json_schema import JsonSchemaValue
from pydantic_core import CoreSchema

from .digests import SHA256_DIGEST_PATTERN
from .sdl_model import SDLModel

ARTIFACT_EXTENSION_MECHANISM_PATTERN = re.compile(r"^x-[a-z0-9]+(?:-[a-z0-9]+)*:[a-z0-9]+(?:-[a-z0-9]+)*$")
PORTABLE_ARTIFACT_MECHANISMS = frozenset(
    {
        "exact-artifact",
        "backend-owned-artifact",
        "published-candidate",
        "dynamic-composition",
        "materialization-specification",
    }
)
ARTIFACT_IDENTIFIER_PATTERN = r"^[a-zA-Z0-9][a-zA-Z0-9._:/@+-]*$"


class ArtifactIdentity(SDLModel):
    """Immutable provider-neutral identity for one artifact payload."""

    artifact_id: Annotated[str, Field(min_length=1, max_length=256, pattern=ARTIFACT_IDENTIFIER_PATTERN)]
    version: Annotated[str, Field(min_length=1, max_length=256)]
    digest: Annotated[str, Field(pattern=SHA256_DIGEST_PATTERN)]
    media_type: Annotated[str, Field(min_length=1, max_length=256)]


class ArtifactMechanismProfile(SDLModel):
    """Versioned portable mechanism profile.

    Portable mechanisms use the governed base names above or a namespaced
    ``x-<authority>:<term>`` extension. The profile digest binds the exact
    mechanism contract without making the mechanism set a closed union.
    """

    mechanism: Annotated[str, Field(min_length=1, max_length=128)]
    profile: Annotated[str, Field(min_length=1, max_length=256, pattern=ARTIFACT_IDENTIFIER_PATTERN)]
    version: Annotated[str, Field(min_length=1, max_length=128)]
    digest: Annotated[str, Field(pattern=SHA256_DIGEST_PATTERN)]

    @model_validator(mode="after")
    def validate_mechanism(self) -> ArtifactMechanismProfile:
        if (
            self.mechanism not in PORTABLE_ARTIFACT_MECHANISMS
            and ARTIFACT_EXTENSION_MECHANISM_PATTERN.fullmatch(self.mechanism) is None
        ):
            raise ValueError("mechanism must be a portable base mechanism or a governed x-<authority>:<term> extension")
        return self

    @classmethod
    def __get_pydantic_json_schema__(
        cls,
        core_schema: CoreSchema,
        handler: GetJsonSchemaHandler,
    ) -> JsonSchemaValue:
        json_schema = handler.resolve_ref_schema(handler(core_schema))
        json_schema["properties"]["mechanism"]["anyOf"] = [
            {"enum": sorted(PORTABLE_ARTIFACT_MECHANISMS)},
            {"pattern": ARTIFACT_EXTENSION_MECHANISM_PATTERN.pattern},
        ]
        return json_schema


__all__ = [
    "ARTIFACT_EXTENSION_MECHANISM_PATTERN",
    "ARTIFACT_IDENTIFIER_PATTERN",
    "PORTABLE_ARTIFACT_MECHANISMS",
    "ArtifactIdentity",
    "ArtifactMechanismProfile",
]
