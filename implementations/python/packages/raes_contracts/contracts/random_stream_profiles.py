"""Helpers for loading published random-stream profile declarations.

Random-stream profiles live under ``contracts/profiles/random-stream/*.json``
(ADR-009/019/061 normative corpus). Mirrors ``semantic_profiles.py``, but
hardened per the EXP-718 preflight's "Normative profile and corpus gate":
the profile id is validated against ``raes``'s portable-identifier
grammar *before* any path is constructed, and unsupported ids are rejected
explicitly rather than allowed to 404 (or path-traverse) through the corpus
loader.
"""

from __future__ import annotations

import json
from functools import cache
from pathlib import Path

from raes_contracts.contracts.random_stream import RandomStreamProfileModel
from raes_contracts.identifiers import is_portable_identifier

from ..corpus import PROFILES, corpus_family_root

# The closed set of profile ids this reference implementation dispatches.
# Adding a newly accepted profile means adding its published artifact under
# ``contracts/profiles/random-stream/`` *and* its id here -- there is no
# dynamic plugin, "latest" alias, or version-range fallback (EXP-718
# preflight, "One Profile And One Stateless API").
SUPPORTED_RANDOM_STREAM_PROFILE_IDS = frozenset({"blake3-xof-participant-v1", "blake3-xof-v1"})


def random_stream_profiles_root() -> Path:
    return corpus_family_root(PROFILES) / "random-stream"


def _validate_random_stream_profile_id(profile_id: str) -> None:
    """Reject unknown or unsupported profile ids BEFORE any path is built.

    Two independent gates: the id must be a portable SDL identifier (so it
    cannot contain path separators, ``..`` segments, or absolute-path
    components), and it must be one of the profiles this implementation
    actually publishes and dispatches.
    """

    if not is_portable_identifier(profile_id):
        raise ValueError(
            f"random stream profile id {profile_id!r} must be a portable SDL identifier: "
            "1-64 lowercase ASCII letters, digits, hyphens, or underscores, starting with a letter or digit"
        )
    if profile_id not in SUPPORTED_RANDOM_STREAM_PROFILE_IDS:
        supported = ", ".join(sorted(SUPPORTED_RANDOM_STREAM_PROFILE_IDS))
        raise ValueError(f"unsupported random stream profile id {profile_id!r}; supported ids: {supported}")


def random_stream_profile_path(profile_id: str) -> Path:
    _validate_random_stream_profile_id(profile_id)
    return random_stream_profiles_root() / f"{profile_id}.json"


def load_random_stream_profile_from_path(profile_id: str, path: Path) -> RandomStreamProfileModel:
    """Load a random-stream profile from ``path`` and assert the payload identity.

    The published profile JSON's ``profile_id`` field must match the
    requested ``profile_id``; a mismatch is a swapped/mislabeled artifact and
    is treated as a hard load failure rather than silently trusting the file
    contents.
    """

    _validate_random_stream_profile_id(profile_id)
    payload = json.loads(path.read_text(encoding="utf-8"))
    model = RandomStreamProfileModel.model_validate(payload)
    if model.profile_id != profile_id:
        # Host paths stay out of the message (E7), as in the backend profile loader.
        raise ValueError(
            "random stream profile artifact declares profile_id "
            f"{model.profile_id!r} but was requested as {profile_id!r}; "
            "the published profile id and request id must match."
        )
    return model


@cache
def load_random_stream_profile(profile_id: str) -> RandomStreamProfileModel:
    return load_random_stream_profile_from_path(profile_id, random_stream_profile_path(profile_id))


__all__ = [
    "SUPPORTED_RANDOM_STREAM_PROFILE_IDS",
    "load_random_stream_profile",
    "load_random_stream_profile_from_path",
    "random_stream_profile_path",
    "random_stream_profiles_root",
]
