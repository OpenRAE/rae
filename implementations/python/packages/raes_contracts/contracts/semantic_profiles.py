"""Semantic-profile contracts."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from ..published_schemas import published_contract_ids
from ..versions import CONCEPT_FAMILIES_SCHEMA_VERSION, SEMANTIC_PROFILE_SCHEMA_VERSION
from ..vocabulary import ConceptFamilyId
from .base import ContractModel, NonEmptyString, SemanticAssumptionId, SemanticProfileId
from .catalogs import authoritative_concept_family_ids
from .manifests import ConceptBindingEntryModel
from .schema_constraints import _SEMANTIC_PROFILE_PHASE_ALLOWED_BINDING_SCOPES


class SemanticBehaviorAssumptionModel(ContractModel):
    id: SemanticAssumptionId
    statement: NonEmptyString


class SemanticProfilePhaseModel(ContractModel):
    required_contracts: list[NonEmptyString] = Field(min_length=1)
    required_concept_families: list[ConceptFamilyId] = Field(min_length=1)
    required_bindings: list[ConceptBindingEntryModel] = Field(default_factory=list)
    behavior_assumptions: list[SemanticBehaviorAssumptionModel] = Field(min_length=1)

    @model_validator(mode="after")
    def _validate_phase_assumptions(self) -> SemanticProfilePhaseModel:
        if len(self.required_contracts) != len(set(self.required_contracts)):
            raise ValueError("semantic profile required_contracts must not contain duplicates")
        if len(self.required_concept_families) != len(set(self.required_concept_families)):
            raise ValueError("semantic profile required_concept_families must not contain duplicates")

        known_contracts = published_contract_ids()
        unknown_contracts = set(self.required_contracts) - known_contracts
        if unknown_contracts:
            unknown = ", ".join(sorted(unknown_contracts))
            raise ValueError(f"semantic profile required_contracts include unknown contract ids: {unknown}")

        known_families = authoritative_concept_family_ids()
        unknown_families = set(self.required_concept_families) - known_families
        if unknown_families:
            unknown = ", ".join(sorted(unknown_families))
            raise ValueError(f"semantic profile required_concept_families include unknown families: {unknown}")

        binding_scopes = [binding.scope for binding in self.required_bindings]
        if len(binding_scopes) != len(set(binding_scopes)):
            raise ValueError("semantic profile required_bindings must not contain duplicate scopes")

        undeclared_binding_families = {
            binding.family for binding in self.required_bindings if binding.family not in self.required_concept_families
        }
        if undeclared_binding_families:
            missing = ", ".join(sorted(undeclared_binding_families))
            raise ValueError(
                f"semantic profile required_bindings must use families declared in required_concept_families: {missing}"
            )

        assumption_ids = [assumption.id for assumption in self.behavior_assumptions]
        if len(assumption_ids) != len(set(assumption_ids)):
            raise ValueError("semantic profile behavior_assumptions must not contain duplicate ids")
        return self


class SemanticProfileModel(ContractModel):
    schema_version: Literal[SEMANTIC_PROFILE_SCHEMA_VERSION] = SEMANTIC_PROFILE_SCHEMA_VERSION
    profile_id: SemanticProfileId
    title: NonEmptyString
    description: NonEmptyString
    concept_catalog_version: Literal[CONCEPT_FAMILIES_SCHEMA_VERSION]
    authoring: SemanticProfilePhaseModel
    exchange: SemanticProfilePhaseModel
    processing: SemanticProfilePhaseModel
    execution: SemanticProfilePhaseModel

    @model_validator(mode="after")
    def _validate_phase_binding_scopes(self) -> SemanticProfileModel:
        for phase_name, allowed_scopes in _SEMANTIC_PROFILE_PHASE_ALLOWED_BINDING_SCOPES.items():
            phase = getattr(self, phase_name)
            declared_scopes = {binding.scope for binding in phase.required_bindings}
            invalid_scopes = declared_scopes - allowed_scopes
            if invalid_scopes:
                invalid = ", ".join(sorted(invalid_scopes))
                if allowed_scopes:
                    allowed = ", ".join(sorted(allowed_scopes))
                    raise ValueError(
                        f"semantic profile {phase_name} required_bindings include scopes outside the governed "
                        f"{phase_name} surfaces: {invalid}; allowed scopes: {allowed}"
                    )
                raise ValueError(
                    f"semantic profile {phase_name} does not define governed required_bindings surfaces: {invalid}"
                )
        return self
