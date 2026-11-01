"""ACT-604 participant information reconstruction profiles: the closed profile model and its loaders."""

from __future__ import annotations

import json
from functools import cache
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator

from ..corpus import PROFILES, corpus_family_root
from ..identifiers import is_portable_identifier
from ..versions import PARTICIPANT_INFORMATION_RECONSTRUCTION_PROFILE_V1_SCHEMA_VERSION
from .base import ContractModel, NonEmptyString, PrefixedDigestString, SemanticProfileId

ParticipantInformationSourceContract = Literal[
    "participant-observation-envelope-v1",
    "participant-context-view-v1",
    "participant-shared-state-record-v1",
    "participant-behavior-history-event-stream-v1",
    "participant-episode-state-envelope-v1",
]

ParticipantInformationOrderSemantics = Literal[
    "sequence_prefix",
    "causal_frontier",
]


class ParticipantInformationReconstructionProfileModel(ContractModel):
    """One immutable, non-executable reconstruction profile declaration."""

    schema_version: Literal[PARTICIPANT_INFORMATION_RECONSTRUCTION_PROFILE_V1_SCHEMA_VERSION]
    profile_id: SemanticProfileId
    title: NonEmptyString
    description: NonEmptyString
    algorithm_id: NonEmptyString
    algorithm_version: NonEmptyString
    information_state_schema_version: NonEmptyString
    projection_version: NonEmptyString
    determinism_basis: Literal["exact_occurrence_prefix_and_proof_digest"]
    accepted_input_contracts: list[ParticipantInformationSourceContract] = Field(min_length=1)
    accepted_order_semantics: list[ParticipantInformationOrderSemantics] = Field(min_length=1)
    fixture_format: NonEmptyString
    proof_artifact_format: NonEmptyString
    normative_artifact_ref: NonEmptyString
    normative_artifact_digest: PrefixedDigestString

    @model_validator(mode="after")
    def _validate_closed_profile(self) -> ParticipantInformationReconstructionProfileModel:
        for field_name in ("accepted_input_contracts", "accepted_order_semantics"):
            values = getattr(self, field_name)
            if len(values) != len(set(values)):
                raise ValueError(f"{field_name} values must be unique")
        return self


SUPPORTED_PARTICIPANT_INFORMATION_RECONSTRUCTION_PROFILE_IDS = frozenset({"occurrence-prefix-evidence-v1"})


def participant_information_reconstruction_profiles_root() -> Path:
    return corpus_family_root(PROFILES) / "participant-information-reconstruction"


def _validate_profile_id(profile_id: str) -> None:
    if not is_portable_identifier(profile_id):
        raise ValueError(
            f"participant information reconstruction profile id {profile_id!r} must be a portable SDL identifier: "
            "1-64 lowercase ASCII letters, digits, hyphens, or underscores, starting with a letter or digit"
        )
    if profile_id not in SUPPORTED_PARTICIPANT_INFORMATION_RECONSTRUCTION_PROFILE_IDS:
        supported = ", ".join(sorted(SUPPORTED_PARTICIPANT_INFORMATION_RECONSTRUCTION_PROFILE_IDS))
        raise ValueError(
            f"unsupported participant information reconstruction profile id {profile_id!r}; supported ids: {supported}"
        )


def participant_information_reconstruction_profile_path(profile_id: str) -> Path:
    _validate_profile_id(profile_id)
    return participant_information_reconstruction_profiles_root() / f"{profile_id}.json"


def load_participant_information_reconstruction_profile_from_path(
    profile_id: str,
    path: Path,
) -> ParticipantInformationReconstructionProfileModel:
    _validate_profile_id(profile_id)
    payload = json.loads(path.read_text(encoding="utf-8"))
    profile = ParticipantInformationReconstructionProfileModel.model_validate(payload)
    if profile.profile_id != profile_id:
        raise ValueError("participant information reconstruction profile artifact identity does not match request")
    return profile


@cache
def load_participant_information_reconstruction_profile(
    profile_id: str,
) -> ParticipantInformationReconstructionProfileModel:
    return load_participant_information_reconstruction_profile_from_path(
        profile_id,
        participant_information_reconstruction_profile_path(profile_id),
    )


__all__ = (
    "SUPPORTED_PARTICIPANT_INFORMATION_RECONSTRUCTION_PROFILE_IDS",
    "load_participant_information_reconstruction_profile",
    "load_participant_information_reconstruction_profile_from_path",
    "participant_information_reconstruction_profile_path",
    "participant_information_reconstruction_profiles_root",
)


__all__ = [
    "SUPPORTED_PARTICIPANT_INFORMATION_RECONSTRUCTION_PROFILE_IDS",
    "ParticipantInformationOrderSemantics",
    "ParticipantInformationReconstructionProfileModel",
    "ParticipantInformationSourceContract",
    "load_participant_information_reconstruction_profile",
    "load_participant_information_reconstruction_profile_from_path",
    "participant_information_reconstruction_profile_path",
    "participant_information_reconstruction_profiles_root",
]
