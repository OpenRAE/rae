"""Participant feature-support declaration contracts."""

from __future__ import annotations

import re

from pydantic import Field, GetJsonSchemaHandler, model_validator
from pydantic.json_schema import JsonSchemaValue
from pydantic_core import CoreSchema

from ..controlled_vocabularies import load_controlled_vocabulary_catalog
from ..manifest_authority import PARTICIPANT_RUNTIME_EVIDENCE_REQUIRED_FEATURES
from ..vocabulary import ParticipantFeatureSupportLevel
from .base import ContractModel, NonEmptyString
from .validators import validate_unique_string_values

_PARTICIPANT_FEATURE_SUPPORT_VOCABULARY_IDS = (
    "participant-runtime-behavior-features",
    "participant-runtime-interaction-features",
)


def _validate_participant_feature_support_term(feature: str) -> None:

    catalog = load_controlled_vocabulary_catalog()
    for vocabulary_id in _PARTICIPANT_FEATURE_SUPPORT_VOCABULARY_IDS:
        definition = catalog.vocabularies[vocabulary_id]
        if feature in definition.terms:
            return
        if definition.extension_pattern is not None and re.fullmatch(definition.extension_pattern, feature):
            return
    joined = ", ".join(_PARTICIPANT_FEATURE_SUPPORT_VOCABULARY_IDS)
    raise ValueError(
        f"feature_support feature '{feature}' is not a governed term of {joined} "
        "and does not match the governed extension pattern"
    )


class ParticipantFeatureSupportModel(ContractModel):
    """API-407 per-feature participant runtime support declaration."""

    feature: NonEmptyString
    support_level: ParticipantFeatureSupportLevel
    constraint_refs: list[NonEmptyString] = Field(default_factory=list)
    limitation_refs: list[NonEmptyString] = Field(default_factory=list)
    disclosure_refs: list[NonEmptyString] = Field(default_factory=list)
    evidence_refs: list[NonEmptyString] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_feature_support_declaration(self) -> ParticipantFeatureSupportModel:
        _validate_participant_feature_support_term(self.feature)
        validate_unique_string_values("constraint_refs", self.constraint_refs)
        validate_unique_string_values("limitation_refs", self.limitation_refs)
        validate_unique_string_values("disclosure_refs", self.disclosure_refs)
        validate_unique_string_values("evidence_refs", self.evidence_refs)
        if self.support_level != ParticipantFeatureSupportLevel.EXACT and not self.disclosure_refs:
            raise ValueError(
                f"feature_support entry '{self.feature}' declares support_level "
                f"'{self.support_level.value}' below 'exact' and must carry at least one disclosure_refs entry"
            )
        if self.feature in PARTICIPANT_RUNTIME_EVIDENCE_REQUIRED_FEATURES:
            if self.support_level != ParticipantFeatureSupportLevel.EXACT and not self.limitation_refs:
                raise ValueError(f"feature_support entry '{self.feature}' below 'exact' must carry limitation_refs")
            if self.support_level == ParticipantFeatureSupportLevel.BOUNDED and not self.constraint_refs:
                raise ValueError(
                    f"feature_support entry '{self.feature}' with bounded support must carry constraint_refs"
                )
            if self.support_level != ParticipantFeatureSupportLevel.UNSUPPORTED and not self.evidence_refs:
                raise ValueError(
                    f"feature_support entry '{self.feature}' with positive support must carry evidence_refs"
                )
        return self

    @classmethod
    def __get_pydantic_json_schema__(
        cls,
        core_schema: CoreSchema,
        handler: GetJsonSchemaHandler,
    ) -> JsonSchemaValue:
        json_schema = handler(core_schema)
        json_schema = handler.resolve_ref_schema(json_schema)
        below_exact = [
            level.value for level in ParticipantFeatureSupportLevel if level != ParticipantFeatureSupportLevel.EXACT
        ]
        json_schema.setdefault("allOf", []).append(
            {
                "if": {
                    "properties": {"support_level": {"enum": below_exact}},
                    "required": ["support_level"],
                },
                "then": {
                    "required": ["disclosure_refs"],
                    "properties": {"disclosure_refs": {"minItems": 1}},
                },
            }
        )
        policy_features = sorted(PARTICIPANT_RUNTIME_EVIDENCE_REQUIRED_FEATURES)
        json_schema["allOf"].extend(
            [
                {
                    "if": {
                        "properties": {
                            "feature": {"enum": policy_features},
                            "support_level": {"enum": below_exact},
                        },
                        "required": ["feature", "support_level"],
                    },
                    "then": {
                        "required": ["limitation_refs"],
                        "properties": {"limitation_refs": {"minItems": 1}},
                    },
                },
                {
                    "if": {
                        "properties": {
                            "feature": {"enum": policy_features},
                            "support_level": {"const": ParticipantFeatureSupportLevel.BOUNDED.value},
                        },
                        "required": ["feature", "support_level"],
                    },
                    "then": {
                        "required": ["constraint_refs"],
                        "properties": {"constraint_refs": {"minItems": 1}},
                    },
                },
                {
                    "if": {
                        "properties": {
                            "feature": {"enum": policy_features},
                            "support_level": {
                                "enum": [
                                    ParticipantFeatureSupportLevel.DISCLOSED_WEAK.value,
                                    ParticipantFeatureSupportLevel.BOUNDED.value,
                                    ParticipantFeatureSupportLevel.EXACT.value,
                                ]
                            },
                        },
                        "required": ["feature", "support_level"],
                    },
                    "then": {
                        "required": ["evidence_refs"],
                        "properties": {"evidence_refs": {"minItems": 1}},
                    },
                },
            ]
        )
        return json_schema
