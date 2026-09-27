"""Closed single-operation SEM-232 profile vocabulary and parameters."""

from typing import Literal

from pydantic import Field, StrictInt, model_validator

from .contracts.base import ContractModel, PrefixedDigestString

INPUT_CLASSES = ("plain", "transform", "declassify", "unsupported", "forbidden")
VISIBLE = (
    "crossing.request",
    "crossing.decision.permit",
    "crossing.decision.deny",
    "crossing.decision.unsupported",
    "crossing.transform",
    "crossing.declassify",
    "crossing.delivery",
    "crossing.observation",
    "crossing.replay.reject",
    "policy.cut.advance",
)
HIDDEN = (
    "internal.validate",
    "internal.resolve-policy-cut",
    "internal.resolve-capability",
    "internal.prepare-record",
    "internal.atomic-commit",
)


class CrossingDomainsModel(ContractModel):
    participant: tuple[Literal["participant-0"]]
    audience: tuple[Literal["audience-0"]]
    controller: tuple[Literal["controller-0"]]
    episode: tuple[Literal["episode-0"]]
    request_id: tuple[Literal["request-0"]]
    policy_cut: tuple[Literal["p0"], Literal["p1"]]
    input_class: tuple[
        Literal["plain"], Literal["transform"], Literal["declassify"], Literal["unsupported"], Literal["forbidden"]
    ]
    decision: tuple[
        Literal["none"],
        Literal["permit"],
        Literal["deny"],
        Literal["unsupported"],
        Literal["transform"],
        Literal["declassify"],
    ]
    replay: tuple[Literal["fresh"], Literal["same-cut"], Literal["later-cut"]]
    delivery: tuple[Literal["none"], Literal["pending"], Literal["delivered"], Literal["withheld"]]
    history_head: tuple[Literal["h0"], Literal["h1"], Literal["h2"], Literal["h3"]]


class AbstractCrossingCarrierModel(ContractModel):
    model_id: Literal["sem-230-participant-crossing-abstract"]
    revision: Literal["rev2"]
    source_path: Literal["implementations/formal/participant_crossing/abstract.py"]
    source_digest: PrefixedDigestString
    initial_state_ordinal: StrictInt = Field(ge=0, le=0)


class ConcreteCrossingCarrierModel(ContractModel):
    model_id: Literal["api-423-run-319-crossing-kernel"]
    revision: Literal["rev2"]
    source_path: Literal["implementations/formal/participant_crossing/concrete.py"]
    source_digest: PrefixedDigestString
    initial_state_ordinal: StrictInt = Field(ge=0, le=0)


class ParticipantCrossingParametersModel(ContractModel):
    kind: Literal["participant-crossing-dpbb/v1"]
    domains: CrossingDomainsModel
    left: AbstractCrossingCarrierModel
    right: ConcreteCrossingCarrierModel
    visible_labels: tuple[
        Literal["crossing.request"],
        Literal["crossing.decision.permit"],
        Literal["crossing.decision.deny"],
        Literal["crossing.decision.unsupported"],
        Literal["crossing.transform"],
        Literal["crossing.declassify"],
        Literal["crossing.delivery"],
        Literal["crossing.observation"],
        Literal["crossing.replay.reject"],
        Literal["policy.cut.advance"],
    ]
    hidden_labels: tuple[
        Literal["internal.validate"],
        Literal["internal.resolve-policy-cut"],
        Literal["internal.resolve-capability"],
        Literal["internal.prepare-record"],
        Literal["internal.atomic-commit"],
    ]
    checker_tau: Literal["internal"]
    complete_carrier: Literal[True]
    depth_or_sample_bound: None
    fresh_operations: StrictInt = Field(ge=1, le=1)
    identity_reuse: Literal["excluded"]
    order: Literal["sequential-total-order"]
    time: Literal["untimed"]
    probability: Literal["excluded"]
    concurrency: Literal["excluded"]
    controller_handoff: Literal["excluded"]
    completion: Literal["per-crossing-visible-outcome"]

    @model_validator(mode="after")
    def _independent_sources(self):
        if self.left.source_digest == self.right.source_digest:
            raise ValueError("crossing transition authorities must have independent source identities")
        return self


def validate_crossing_profile_join(profile) -> None:
    expected = {
        "profile_id": "participant-crossing-dpbb-finite-v1",
        "profile_revision": "rev2",
        "taxonomy_revision": "rev8",
        "relation_id": "divergence-preserving-branching-bisimulation",
        "left_carrier_ref": profile.parameters.left.model_id,
        "observation_projection_ref": "participant-crossing-projection",
        "observation_projection_revision": "rev1",
        "finite_analysis_scope": "declared-complete-finite-carrier",
    }
    if any(getattr(profile, key) != value for key, value in expected.items()):
        raise ValueError("crossing profile identity, projection or carrier does not match its parameters")


def crossing_profile_schema_join() -> dict:
    """Publish the relation/variant join in the existing profile schema."""
    return {
        "if": {
            "properties": {
                "parameters": {"properties": {"kind": {"const": "participant-crossing-dpbb/v1"}}, "required": ["kind"]}
            },
            "required": ["parameters"],
        },
        "then": {
            "properties": {
                key: {"const": value}
                for key, value in {
                    "profile_id": "participant-crossing-dpbb-finite-v1",
                    "profile_revision": "rev2",
                    "taxonomy_revision": "rev8",
                    "relation_id": "divergence-preserving-branching-bisimulation",
                    "left_carrier_ref": "sem-230-participant-crossing-abstract",
                    "observation_projection_ref": "participant-crossing-projection",
                    "observation_projection_revision": "rev1",
                    "finite_analysis_scope": "declared-complete-finite-carrier",
                }.items()
            }
        },
        "else": {"properties": {"relation_id": {"const": "participant-predicate-opacity"}}},
    }
