"""Exact corpus-backed profile loading with bounded regular-file ingress."""

from __future__ import annotations

import os
import stat
from functools import cache
from pathlib import Path
from typing import TYPE_CHECKING

from raes.identifiers import is_portable_identifier

if TYPE_CHECKING:
    from .behavioral_relation_profiles import BehavioralRelationProfileModel
from .corpus import PROFILES, corpus_family_root
from .json_ingress import parse_bounded_json_object

_MAX_PROFILE_BYTES = 256 * 1024
SUPPORTED_BEHAVIORAL_RELATION_PROFILE_IDS = frozenset(
    {
        "participant-opacity-baseline-v1",
        "participant-opacity-runtime-reference-v1",
        "participant-opacity-theorem-v1",
        "participant-crossing-dpbb-finite-v1",
    }
)


def behavioral_relation_profiles_root() -> Path:
    return corpus_family_root(PROFILES) / "behavioral-relation"


def _validate_profile_id(profile_id: str) -> None:
    if not is_portable_identifier(profile_id):
        raise ValueError("requested behavioral relation profile id must be a portable identifier")
    if profile_id not in SUPPORTED_BEHAVIORAL_RELATION_PROFILE_IDS:
        raise ValueError("requested behavioral relation profile is unsupported")


def behavioral_relation_profile_path(profile_id: str) -> Path:
    _validate_profile_id(profile_id)
    return behavioral_relation_profiles_root() / f"{profile_id}.json"


def load_behavioral_relation_profile_from_path(
    profile_id: str,
    path: Path,
) -> BehavioralRelationProfileModel:
    """Load one trusted profile path after strict bounded JSON ingress."""

    from .behavioral_relation_profiles import BehavioralRelationProfileModel

    _validate_profile_id(profile_id)
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(descriptor, "rb") as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                raise ValueError("profile must be a regular file")
            content = stream.read(_MAX_PROFILE_BYTES + 1)
        payload = parse_bounded_json_object(
            content,
            max_bytes=_MAX_PROFILE_BYTES,
        )
        profile = BehavioralRelationProfileModel.model_validate(payload)
    except (OSError, ValueError):
        raise ValueError("behavioral relation profile JSON or contract is invalid") from None
    if profile.profile_id != profile_id:
        raise ValueError("behavioral relation profile artifact identity does not match the requested profile")
    return profile


@cache
def load_behavioral_relation_profile(
    profile_id: str,
) -> BehavioralRelationProfileModel:
    return load_behavioral_relation_profile_from_path(
        profile_id,
        behavioral_relation_profile_path(profile_id),
    )


_HISTORICAL_PROFILE_PATHS = {
    (
        "participant-opacity-baseline-v1",
        "sem-231/rev2",
    ): behavioral_relation_profiles_root() / "history" / "participant-opacity-baseline-v1-sem-231-rev2.json",
    (
        "participant-opacity-runtime-reference-v1",
        "sem-231/runtime-rev1",
    ): behavioral_relation_profiles_root()
    / "history"
    / "participant-opacity-runtime-reference-v1-sem-231-runtime-rev1.json",
}


@cache
def load_behavioral_relation_profile_revision(
    profile_id: str,
    profile_revision: str,
) -> BehavioralRelationProfileModel:
    """Resolve an exact immutable profile revision for evidence replay."""

    _validate_profile_id(profile_id)
    historical_path = _HISTORICAL_PROFILE_PATHS.get((profile_id, profile_revision))
    if historical_path is not None:
        profile = load_behavioral_relation_profile_from_path(profile_id, historical_path)
        if profile.profile_revision != profile_revision:
            raise ValueError("historical behavioral relation profile revision does not match its registry entry")
        return profile
    current = load_behavioral_relation_profile(profile_id)
    if current.profile_revision == profile_revision:
        return current
    raise ValueError("requested behavioral relation profile revision is unsupported")
