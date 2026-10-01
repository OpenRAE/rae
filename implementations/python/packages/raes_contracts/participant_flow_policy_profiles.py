"""Hardened exact-revision loader for the published SEM-233 flow profile."""

from __future__ import annotations

from functools import cache
from pathlib import Path

from raes.identifiers import is_portable_identifier

from .contracts.participant_flow_control import (
    PARTICIPANT_BOUNDARY_FLOW_POLICY_PROFILE_REV1_DIGEST,
    ParticipantBoundaryFlowPolicyProfileModel,
)
from .corpus import PROFILES, corpus_family_root
from .json_ingress import parse_bounded_json_object

PARTICIPANT_BOUNDARY_FLOW_POLICY_PROFILE_ID = "participant-boundary-flow-policy-v1"
SUPPORTED_PARTICIPANT_BOUNDARY_FLOW_POLICY_PROFILE_IDS = frozenset({PARTICIPANT_BOUNDARY_FLOW_POLICY_PROFILE_ID})
_MAX_PROFILE_BYTES = 256 * 1024
_PROFILE_REVISION_FILENAMES = {
    (
        PARTICIPANT_BOUNDARY_FLOW_POLICY_PROFILE_ID,
        "rev1",
        PARTICIPANT_BOUNDARY_FLOW_POLICY_PROFILE_REV1_DIGEST,
    ): f"{PARTICIPANT_BOUNDARY_FLOW_POLICY_PROFILE_ID}.json",
}


def participant_boundary_flow_policy_profiles_root() -> Path:
    return corpus_family_root(PROFILES) / "participant-boundary-flow-policy"


def _validate_profile_id(profile_id: str) -> None:
    if not is_portable_identifier(profile_id):
        raise ValueError("participant boundary flow profile id must be a portable identifier")
    if profile_id not in SUPPORTED_PARTICIPANT_BOUNDARY_FLOW_POLICY_PROFILE_IDS:
        raise ValueError(f"requested participant boundary flow profile {profile_id!r} is unsupported")


def participant_boundary_flow_policy_profile_path(profile_id: str) -> Path:
    _validate_profile_id(profile_id)
    return participant_boundary_flow_policy_profiles_root() / f"{profile_id}.json"


def load_participant_boundary_flow_policy_profile_from_path(
    profile_id: str,
    path: Path,
) -> ParticipantBoundaryFlowPolicyProfileModel:
    """Load one trusted artifact path through bounded, duplicate-rejecting JSON ingress."""

    _validate_profile_id(profile_id)
    try:
        with path.open("rb") as stream:
            source = stream.read(_MAX_PROFILE_BYTES + 1)
        payload = parse_bounded_json_object(source, max_bytes=_MAX_PROFILE_BYTES)
        profile = ParticipantBoundaryFlowPolicyProfileModel.model_validate(payload)
    except (OSError, ValueError):
        raise ValueError("participant boundary flow profile JSON or contract is invalid") from None
    if profile.profile_id != profile_id:
        raise ValueError("participant boundary flow profile artifact identity does not match the request")
    return profile


@cache
def load_participant_boundary_flow_policy_profile(
    profile_id: str,
) -> ParticipantBoundaryFlowPolicyProfileModel:
    return load_participant_boundary_flow_policy_profile_from_path(
        profile_id,
        participant_boundary_flow_policy_profile_path(profile_id),
    )


@cache
def load_participant_boundary_flow_policy_profile_revision(
    profile_id: str,
    profile_revision: str,
    profile_digest: str,
) -> ParticipantBoundaryFlowPolicyProfileModel:
    """Resolve one exact immutable revision and digest; never fall back to latest."""

    _validate_profile_id(profile_id)
    revision_filename = _PROFILE_REVISION_FILENAMES.get((profile_id, profile_revision, profile_digest))
    if revision_filename is None:
        if not any(
            registered_id == profile_id and registered_revision == profile_revision
            for registered_id, registered_revision, _registered_digest in _PROFILE_REVISION_FILENAMES
        ):
            raise ValueError("participant boundary flow profile revision is unsupported")
        raise ValueError("participant boundary flow profile digest does not match")
    profile = load_participant_boundary_flow_policy_profile_from_path(
        profile_id,
        participant_boundary_flow_policy_profiles_root() / revision_filename,
    )
    if profile.profile_revision != profile_revision or profile.canonical_digest != profile_digest:
        raise ValueError("participant boundary flow profile registry entry does not match the artifact")
    return profile


__all__ = [
    "PARTICIPANT_BOUNDARY_FLOW_POLICY_PROFILE_ID",
    "PARTICIPANT_BOUNDARY_FLOW_POLICY_PROFILE_REV1_DIGEST",
    "SUPPORTED_PARTICIPANT_BOUNDARY_FLOW_POLICY_PROFILE_IDS",
    "load_participant_boundary_flow_policy_profile",
    "load_participant_boundary_flow_policy_profile_from_path",
    "load_participant_boundary_flow_policy_profile_revision",
    "participant_boundary_flow_policy_profile_path",
    "participant_boundary_flow_policy_profiles_root",
]
