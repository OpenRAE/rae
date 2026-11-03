"""Governed validation-profile taxonomy contract and canonical loader."""

from __future__ import annotations

from functools import cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, model_validator

from raes_contracts._base import ContractModel, NonEmptyString

from .corpus import PROFILES, corpus_family_root
from .versions import VALIDATION_PROFILE_CATALOG_SCHEMA_VERSION

TermId = Annotated[
    str,
    Field(
        pattern=(
            r"^(?:[a-z][a-z0-9_]*|"
            r"x-[a-z][a-z0-9-]*:[a-z][a-z0-9_-]*)$"
        )
    ),
]
ProfileId = Annotated[str, Field(pattern=r"^[a-z][a-z0-9-]*$")]
ProfileVersion = Annotated[str, Field(pattern=r"^v[1-9][0-9]*$")]
CatalogVersion = Annotated[str, Field(pattern=r"^v[1-9][0-9]*$")]


class ValidationStrengthDefinitionModel(ContractModel):
    strength_id: TermId
    rank: int = Field(ge=1)
    definition: NonEmptyString


class ValidationSubjectKindDefinitionModel(ContractModel):
    subject_kind: TermId
    definition: NonEmptyString


class ValidationGateKindDefinitionModel(ContractModel):
    gate_kind: TermId
    definition: NonEmptyString


class ValidationLimitationCategoryDefinitionModel(ContractModel):
    limitation_category: TermId
    definition: NonEmptyString


class ValidationProfileDefinitionModel(ContractModel):
    profile_id: ProfileId
    profile_version: ProfileVersion
    title: NonEmptyString
    intended_subject_kinds: list[TermId] = Field(min_length=1)
    minimum_strength: TermId
    required_gate_kinds: list[TermId] = Field(min_length=1)
    optional_gate_kinds: list[TermId] = Field(default_factory=list)
    evidence_expectations: list[NonEmptyString] = Field(min_length=1)
    diagnostic_expectations: list[NonEmptyString] = Field(min_length=1)
    limitation_categories: list[TermId] = Field(min_length=1)
    extension_terms_allowed: bool = False

    @model_validator(mode="after")
    def validate_local_sets(self) -> ValidationProfileDefinitionModel:
        list_fields = (
            "intended_subject_kinds",
            "required_gate_kinds",
            "optional_gate_kinds",
            "limitation_categories",
        )
        for field_name in list_fields:
            values = getattr(self, field_name)
            if len(values) != len(set(values)):
                raise ValueError(f"{field_name.replace('_', ' ')} must be unique")
        overlap = sorted(set(self.required_gate_kinds) & set(self.optional_gate_kinds))
        if overlap:
            raise ValueError(f"required and optional gate kinds must be disjoint: {overlap}")
        referenced_terms = (
            *self.intended_subject_kinds,
            self.minimum_strength,
            *self.required_gate_kinds,
            *self.optional_gate_kinds,
            *self.limitation_categories,
        )
        if not self.extension_terms_allowed and any(term.startswith("x-") for term in referenced_terms):
            raise ValueError("extension terms require extension_terms_allowed=true")
        return self


class ValidationProfileCatalogModel(ContractModel):
    schema_version: Literal[VALIDATION_PROFILE_CATALOG_SCHEMA_VERSION] = VALIDATION_PROFILE_CATALOG_SCHEMA_VERSION
    profile_family: Literal["raes-validation"] = "raes-validation"
    catalog_version: CatalogVersion
    strengths: list[ValidationStrengthDefinitionModel] = Field(min_length=1)
    subject_kinds: list[ValidationSubjectKindDefinitionModel] = Field(min_length=1)
    gate_kinds: list[ValidationGateKindDefinitionModel] = Field(min_length=1)
    limitation_categories: list[ValidationLimitationCategoryDefinitionModel] = Field(min_length=1)
    profiles: list[ValidationProfileDefinitionModel] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_catalog_references(self) -> ValidationProfileCatalogModel:
        strength_ids = self._unique_term_ids(
            "strength ids",
            [item.strength_id for item in self.strengths],
        )
        ranks = [item.rank for item in self.strengths]
        if len(ranks) != len(set(ranks)):
            raise ValueError("strength ranks must be unique")
        if set(ranks) != set(range(1, len(ranks) + 1)):
            raise ValueError("strength ranks must be contiguous from 1")

        subject_ids = self._unique_term_ids(
            "subject kind ids",
            [item.subject_kind for item in self.subject_kinds],
        )
        gate_ids = self._unique_term_ids(
            "gate kind ids",
            [item.gate_kind for item in self.gate_kinds],
        )
        limitation_ids = self._unique_term_ids(
            "limitation category ids",
            [item.limitation_category for item in self.limitation_categories],
        )
        identities = [(profile.profile_id, profile.profile_version) for profile in self.profiles]
        if len(identities) != len(set(identities)):
            raise ValueError("profile identities must be unique")

        for profile in self.profiles:
            self._require_resolved(
                profile,
                "strength",
                [profile.minimum_strength],
                strength_ids,
            )
            self._require_resolved(
                profile,
                "subject kinds",
                profile.intended_subject_kinds,
                subject_ids,
            )
            self._require_resolved(
                profile,
                "gate kinds",
                [*profile.required_gate_kinds, *profile.optional_gate_kinds],
                gate_ids,
            )
            self._require_resolved(
                profile,
                "limitation categories",
                profile.limitation_categories,
                limitation_ids,
            )
        return self

    @staticmethod
    def _unique_term_ids(label: str, values: list[str]) -> set[str]:
        if len(values) != len(set(values)):
            raise ValueError(f"{label} must be unique")
        return set(values)

    @staticmethod
    def _require_resolved(
        profile: ValidationProfileDefinitionModel,
        label: str,
        referenced: list[str],
        declared: set[str],
    ) -> None:
        missing = sorted(set(referenced) - declared)
        if missing:
            raise ValueError(f"profile {profile.profile_id!r} references unknown {label}: {missing}")


def validation_profiles_root() -> Path:
    """Return the canonical validation-profile corpus directory."""

    return corpus_family_root(PROFILES) / "validation"


@cache
def load_validation_profile_catalog() -> ValidationProfileCatalogModel:
    """Load and validate the packaged canonical validation-profile catalog."""

    path = validation_profiles_root() / "validation-profile-catalog-v1.json"
    return ValidationProfileCatalogModel.model_validate_json(path.read_text(encoding="utf-8"))


def select_validation_profile(
    profile_id: str,
    profile_version: str,
    *,
    subject_kind: str,
) -> ValidationProfileDefinitionModel:
    """Select one exact profile identity that declares the subject kind."""

    for profile in load_validation_profile_catalog().profiles:
        if profile.profile_id == profile_id and profile.profile_version == profile_version:
            if subject_kind not in profile.intended_subject_kinds:
                raise ValueError(
                    f"validation profile {profile_id!r} version "
                    f"{profile_version!r} does not declare subject kind "
                    f"{subject_kind!r}"
                )
            return profile
    raise ValueError(f"unknown validation profile {profile_id!r} version {profile_version!r}")


__all__ = [
    "ValidationGateKindDefinitionModel",
    "ValidationLimitationCategoryDefinitionModel",
    "ValidationProfileCatalogModel",
    "ValidationProfileDefinitionModel",
    "ValidationStrengthDefinitionModel",
    "ValidationSubjectKindDefinitionModel",
    "load_validation_profile_catalog",
    "select_validation_profile",
    "validation_profiles_root",
]
