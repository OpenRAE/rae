"""Load checked-in external authority snapshots without network access."""

from __future__ import annotations

import json

from .contracts import (
    ActivityStreamsActivityTypesSourceModel,
    AtlasTacticsSourceModel,
    AttackEnterpriseTacticsSourceModel,
    FipaCommunicativeActsSourceModel,
    NistCsfDefensiveCategorySourceModel,
)
from .corpus import CONCEPT_AUTHORITY, corpus_family_root


def load_attack_enterprise_tactics_source() -> AttackEnterpriseTacticsSourceModel:
    path = corpus_family_root(CONCEPT_AUTHORITY) / "attack-enterprise-tactics-source-v1.json"
    return AttackEnterpriseTacticsSourceModel.model_validate(json.loads(path.read_text(encoding="utf-8")))


def load_nist_csf_defensive_categories_source() -> NistCsfDefensiveCategorySourceModel:
    path = corpus_family_root(CONCEPT_AUTHORITY) / "nist-csf-defensive-categories-source-v1.json"
    return NistCsfDefensiveCategorySourceModel.model_validate(json.loads(path.read_text(encoding="utf-8")))


def load_atlas_tactics_source() -> AtlasTacticsSourceModel:
    path = corpus_family_root(CONCEPT_AUTHORITY) / "atlas-tactics-source-v1.json"
    return AtlasTacticsSourceModel.model_validate(json.loads(path.read_text(encoding="utf-8")))


def load_activitystreams_activity_types_source() -> ActivityStreamsActivityTypesSourceModel:
    path = corpus_family_root(CONCEPT_AUTHORITY) / "w3c-activitystreams-activity-types-source-v1.json"
    return ActivityStreamsActivityTypesSourceModel.model_validate(json.loads(path.read_text(encoding="utf-8")))


def load_fipa_communicative_acts_source() -> FipaCommunicativeActsSourceModel:
    path = corpus_family_root(CONCEPT_AUTHORITY) / "fipa-communicative-acts-source-v1.json"
    return FipaCommunicativeActsSourceModel.model_validate(json.loads(path.read_text(encoding="utf-8")))


__all__ = [
    "load_activitystreams_activity_types_source",
    "load_attack_enterprise_tactics_source",
    "load_atlas_tactics_source",
    "load_fipa_communicative_acts_source",
    "load_nist_csf_defensive_categories_source",
]
