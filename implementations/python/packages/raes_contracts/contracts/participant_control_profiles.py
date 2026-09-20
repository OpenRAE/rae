"""Closed wire projection of SEM-235's published teaching-influence profile."""

from typing import Literal

from pydantic import ConfigDict

from .._canonical import canonical_json_digest
from ..corpus import PROFILES, corpus_family_root
from ..json_ingress import parse_bounded_json_object
from .base import ContractModel
from .participant_flow_control import PARTICIPANT_BOUNDARY_FLOW_POLICY_PROFILE_REV1_DIGEST


class ParticipantControlTeachingProfileModel(ContractModel):
    model_config = ConfigDict(frozen=True)
    schema_version: Literal["participant-control-teaching-profile/v1"]
    profile_id: Literal["teaching-influence"]
    profile_revision: Literal["rev1"]
    semantic_revision: Literal["sem-235/rev1"]
    domain: Literal["teaching-influence-domain/rev1"]
    tokens: tuple[Literal["coached-hint"], Literal["worked-example"]]
    order: Literal["subset"]
    join: Literal["union"]
    unknown_source: Literal["unknown"]
    memory: Literal["retain-across-episodes"]
    release: Literal["none"]
    sinks: tuple[Literal["practice-action"], Literal["teaching-observation"]]
    trigger_rule: Literal["hint-followup/1"]


def load_teaching_influence_profile() -> ParticipantControlTeachingProfileModel:
    # Constant packaged path, bounded read before decode; no provider-selected I/O.
    path = corpus_family_root(PROFILES) / "participant-control" / "teaching-influence-rev1.json"
    try:
        with path.open("rb") as stream:
            source = stream.read(16385)
        return ParticipantControlTeachingProfileModel.model_validate(parse_bounded_json_object(source, max_bytes=16384))
    except (OSError, ValueError):
        raise ValueError("published teaching influence profile is invalid") from None


def validate_control_profile_reference(profile) -> None:
    if profile.revision != "rev1":
        raise ValueError("participant control profile revision is unsupported")
    if profile.ref == "teaching-influence":
        expected = canonical_json_digest(load_teaching_influence_profile().model_dump(mode="json"))
    elif profile.ref == "participant-boundary-flow-policy-v1":
        expected = PARTICIPANT_BOUNDARY_FLOW_POLICY_PROFILE_REV1_DIGEST
    else:
        raise ValueError("participant control profile identity is unsupported")
    if profile.digest != expected:
        raise ValueError("participant control profile digest does not match its revision")
