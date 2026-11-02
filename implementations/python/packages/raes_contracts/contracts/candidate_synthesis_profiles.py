"""Digest-bound transformation profiles for SDL candidate synthesis."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field, GetJsonSchemaHandler, model_validator
from pydantic.json_schema import JsonSchemaValue
from pydantic_core import CoreSchema

from raes_contracts.canonical import canonical_json_digest

from ..versions import (
    SDL_CANDIDATE_SYNTHESIS_INPUT_SCHEMA_VERSION,
    SDL_CANDIDATE_SYNTHESIS_PROFILE_SCHEMA_VERSION,
)
from .base import ContractModel, NonEmptyString, PrefixedDigestString
from .schema_invariants import add_raes_invariant

StableId = Annotated[
    str,
    Field(pattern=r"^[a-z0-9]+(?:[._-][a-z0-9]+)*$", max_length=128),
]


class CandidateSynthesisProfileCoordinateModel(ContractModel):
    """Exact coordinate for a governed, caller-supplied profile artifact."""

    profile_id: str = Field(
        pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*/v[1-9][0-9]*$",
        max_length=128,
    )
    version: NonEmptyString
    digest: PrefixedDigestString


class CandidateSynthesisProfileLimitsModel(ContractModel):
    max_assertions: Literal[4096] = 4096
    max_assumptions: Literal[1024] = 1024
    max_decisions: Literal[1024] = 1024
    max_node_identifier_length: Literal[35] = 35


class CandidateSynthesisProfileDefinitionModel(ContractModel):
    """Canonical content that binds every output-affecting profile decision."""

    schema_version: Literal[SDL_CANDIDATE_SYNTHESIS_PROFILE_SCHEMA_VERSION] = (
        SDL_CANDIDATE_SYNTHESIS_PROFILE_SCHEMA_VERSION
    )
    profile_id: Literal["concept-nodes/v1"] = "concept-nodes/v1"
    profile_version: Literal["1"] = "1"
    source_profile: Literal[SDL_CANDIDATE_SYNTHESIS_INPUT_SCHEMA_VERSION] = SDL_CANDIDATE_SYNTHESIS_INPUT_SCHEMA_VERSION
    target_profile: Literal["sdl-authoring-input/v1"] = "sdl-authoring-input/v1"
    rendering_profile: Literal["sdl-yaml/v1"] = "sdl-yaml/v1"
    canonicalization_profile: Literal["raes-sdl-canonical/v1"] = "raes-sdl-canonical/v1"
    supported_assertion_kinds: tuple[Literal["concept"], ...] = ("concept",)
    supported_node_types: tuple[Literal["compute", "switch"], ...] = ("compute", "switch")
    rule_ids: tuple[StableId, ...] = ("concept-node-emission",)
    default_ids: tuple[StableId, ...] = ()
    refusal_reason_codes: tuple[
        Literal[
            "ambiguous-ordering",
            "missing-native-semantics",
            "stale-input",
            "transformation-profile-unavailable",
            "unresolved-parameterization",
            "unsupported-relation",
        ],
        ...,
    ] = (
        "ambiguous-ordering",
        "missing-native-semantics",
        "stale-input",
        "transformation-profile-unavailable",
        "unresolved-parameterization",
        "unsupported-relation",
    )
    all_or_none: Literal[True] = True
    semantic_validation_required: Literal[True] = True
    imports_allowed: Literal[False] = False
    deterministic_order: Literal["sorted-target-ref/v1"] = "sorted-target-ref/v1"
    limits: CandidateSynthesisProfileLimitsModel = CandidateSynthesisProfileLimitsModel()
    profile_digest: PrefixedDigestString

    @model_validator(mode="after")
    def _validate_profile(self) -> CandidateSynthesisProfileDefinitionModel:
        for values, label in (
            (self.supported_assertion_kinds, "supported_assertion_kinds"),
            (self.supported_node_types, "supported_node_types"),
            (self.rule_ids, "rule_ids"),
            (self.default_ids, "default_ids"),
            (self.refusal_reason_codes, "refusal_reason_codes"),
        ):
            if values != tuple(sorted(set(values))):
                raise ValueError(f"candidate synthesis profile {label} must be sorted and unique")
        expected = canonical_json_digest(self.model_dump(mode="json", exclude={"profile_digest"}))
        if self.profile_digest != expected:
            raise ValueError("candidate synthesis profile_digest does not match the complete profile artifact")
        return self

    def coordinate(self) -> CandidateSynthesisProfileCoordinateModel:
        return CandidateSynthesisProfileCoordinateModel(
            profile_id=self.profile_id,
            version=self.profile_version,
            digest=self.profile_digest,
        )

    @classmethod
    def __get_pydantic_json_schema__(
        cls,
        core_schema: CoreSchema,
        handler: GetJsonSchemaHandler,
    ) -> JsonSchemaValue:
        schema = handler.resolve_ref_schema(handler(core_schema))
        add_raes_invariant(
            schema,
            "candidate-synthesis-complete-profile-digest",
            "The profile digest covers every output-affecting rule, default, limit, and refusal posture.",
            validator="raes_contracts.contracts.CandidateSynthesisProfileDefinitionModel.model_validate",
            inputs=[{"contract_id": "sdl-candidate-synthesis-profile-v1", "instance_path": "#"}],
        )
        return schema


__all__ = [
    "CandidateSynthesisProfileCoordinateModel",
    "CandidateSynthesisProfileDefinitionModel",
    "CandidateSynthesisProfileLimitsModel",
]
