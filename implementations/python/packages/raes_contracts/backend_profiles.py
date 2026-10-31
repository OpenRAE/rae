"""Helpers for loading published backend capability profiles.

Backend capability profiles live under ``contracts/profiles/backend/*.json``
and are the authority for which published contracts a backend must honor for
each profile. This module loads them through a closed-world Pydantic
``ContractModel`` so the conformance runner never re-states the
profile-to-contract mapping in code.
"""

from __future__ import annotations

import json
import re
from functools import cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, WithJsonSchema, model_validator

from raes_contracts._base import ContractModel

from .corpus import PROFILES, corpus_family_root
from .errors import InvalidInputError
from .manifest_authority import (
    BACKEND_SUPPORTED_CONTRACT_IDS,
    validate_backend_supported_contract_versions,
)
from .versions import BACKEND_PROFILE_SCHEMA_VERSION

_BACKEND_PROFILE_ID_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def backend_profiles_root() -> Path:
    return corpus_family_root(PROFILES) / "backend"


def _validate_backend_profile_id(profile_id: str) -> None:
    """Reject profile ids that don't match the published grammar.

    Applied BEFORE path construction so a caller-controlled value cannot
    contain path separators, ``..`` segments, absolute-path components, or
    anything else that would escape the configured profile root. The
    pattern matches the ``BackendProfileId`` annotation on the model so the
    pre-path check, the post-load model check, and the published schema
    enum constraint all agree.
    """

    if not isinstance(profile_id, str) or not _BACKEND_PROFILE_ID_PATTERN.fullmatch(profile_id):
        raise ValueError(
            "backend profile id must match ^[a-z0-9]+(?:-[a-z0-9]+)*$; "
            "ids that contain path separators or other characters are rejected."
        )


def backend_profile_path(profile_id: str) -> Path:
    _validate_backend_profile_id(profile_id)
    return backend_profiles_root() / f"{profile_id}.json"


BackendProfileId = Annotated[str, Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")]


class BackendProfileModel(ContractModel):
    """Published backend capability profile (closed-world)."""

    schema_version: Literal[BACKEND_PROFILE_SCHEMA_VERSION] = BACKEND_PROFILE_SCHEMA_VERSION
    profile: BackendProfileId
    required_contracts: Annotated[
        tuple[str, ...],
        Field(min_length=1),
        WithJsonSchema(
            {
                "type": "array",
                "minItems": 1,
                "uniqueItems": True,
                "items": {"type": "string", "enum": list(BACKEND_SUPPORTED_CONTRACT_IDS)},
            }
        ),
    ]

    @model_validator(mode="after")
    def _validate_required_contracts(self) -> BackendProfileModel:
        validate_backend_supported_contract_versions(self.required_contracts)
        return self


class BackendProfileIdentityError(InvalidInputError):
    """A profile artifact declares a profile id other than the requested id."""


def load_backend_profile_from_path(profile_id: str, path: Path) -> BackendProfileModel:
    """Load a backend profile from ``path`` and assert the payload identity.

    The published profile JSON's ``profile`` field must match ``profile_id``
    (the requested id, which the canonical loader resolves from the file
    stem). A mismatch indicates a swapped or mislabeled artifact and would
    otherwise let the runner drive the wrong contract set under the wrong
    name, so it is treated as a hard load failure.

    ``profile_id`` is validated against the published profile-id grammar before
    use so a caller cannot smuggle path separators or ``..`` segments into the
    constructed path. Callers that construct ``path`` themselves are
    responsible for confining it to their intended profile root.
    """

    _validate_backend_profile_id(profile_id)
    payload = json.loads(path.read_text(encoding="utf-8"))
    model = BackendProfileModel.model_validate(payload)
    if model.profile != profile_id:
        # Both ids are grammar-validated, so this message is bounded and safe to
        # surface in a conformance diagnostic. The resolved filesystem path is
        # deliberately omitted: these failures are reported into persisted
        # backend-conformance artifacts, which must not carry host paths.
        raise BackendProfileIdentityError(
            f"backend profile artifact declares profile {model.profile!r} "
            f"but was requested as {profile_id!r}; "
            "the published profile id and request id must match."
        )
    return model


@cache
def load_backend_profile(profile_id: str) -> BackendProfileModel:
    return load_backend_profile_from_path(profile_id, backend_profile_path(profile_id))


__all__ = [
    "BACKEND_SUPPORTED_CONTRACT_IDS",
    "BackendProfileIdentityError",
    "BackendProfileModel",
    "backend_profile_path",
    "backend_profiles_root",
    "load_backend_profile",
    "load_backend_profile_from_path",
]
