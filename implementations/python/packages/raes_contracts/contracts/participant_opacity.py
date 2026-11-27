"""Portable bounded participant-opacity runtime-enforcement contracts."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from raes_contracts.behavioral_claims import BehavioralClaimBindingModel
from raes_contracts.canonical import canonical_json_digest

from .base import ContractModel, NonEmptyString, PrefixedDigestString

ParticipantOpacityObservationChannel = Literal[
    "participant-state",
    "payload",
    "decision",
    "action-availability",
    "delivery",
    "retry",
    "latency",
    "order",
    "policy-release",
]


class ParticipantOpacityObservationSurfaceModel(ContractModel):
    """One concrete observer-visible surface in a runtime opacity inventory."""

    surface_ref: NonEmptyString
    profile_channel: ParticipantOpacityObservationChannel
    owner_ref: NonEmptyString
    disposition: Literal["mediated", "unreachable", "unsupported"]
    occurrence_treatment: Literal["observable", "hidden", "not-applicable"]
    content_treatment: Literal["projected", "hidden", "not-applicable"]
    projection_ref: NonEmptyString
    projection_revision: NonEmptyString
    order_basis_ref: NonEmptyString
    order_basis_revision: NonEmptyString
    opportunity_basis_ref: NonEmptyString | None = None
    opportunity_basis_revision: NonEmptyString | None = None
    timing_bucket_ref: NonEmptyString | None = None
    timing_bucket_revision: NonEmptyString | None = None
    limitation_ref: NonEmptyString | None = None

    @model_validator(mode="after")
    def _validate_optional_coordinates(self) -> ParticipantOpacityObservationSurfaceModel:
        pairs = (
            (
                self.opportunity_basis_ref,
                self.opportunity_basis_revision,
                "opportunity basis",
            ),
            (
                self.timing_bucket_ref,
                self.timing_bucket_revision,
                "timing bucket",
            ),
        )
        for reference, revision, label in pairs:
            if (reference is None) != (revision is None):
                raise ValueError(f"participant opacity {label} ref and revision must be supplied together")
        if self.disposition == "unsupported" and self.limitation_ref is None:
            raise ValueError("unsupported participant opacity surfaces require a limitation ref")
        return self


class ParticipantOpacityObservationInventoryModel(ContractModel):
    """Closed concrete inventory for every channel claimed by one profile."""

    inventory_ref: NonEmptyString
    inventory_revision: NonEmptyString
    observer_ref: NonEmptyString
    audience_ref: NonEmptyString
    surfaces: tuple[ParticipantOpacityObservationSurfaceModel, ...] = Field(
        min_length=1,
        max_length=64,
    )

    @model_validator(mode="after")
    def _validate_unique_surfaces(self) -> ParticipantOpacityObservationInventoryModel:
        refs = tuple(surface.surface_ref for surface in self.surfaces)
        if len(refs) != len(set(refs)):
            raise ValueError("participant opacity observation surface refs must be unique")
        return self

    @property
    def canonical_digest(self) -> str:
        """Bind the exact closed inventory independently of runtime state."""

        return canonical_json_digest(self.model_dump(mode="json"))


class ParticipantOpacityRuntimeEnforcementBindingModel(ContractModel):
    """Safe finite runtime-enforcement binding owned by an API-423 decision."""

    taxonomy_id: Literal["raes-behavioral-relations"]
    taxonomy_revision: NonEmptyString
    relation_id: Literal["participant-predicate-opacity"]
    profile_id: NonEmptyString
    profile_revision: NonEmptyString
    profile_digest: PrefixedDigestString
    predicate_ref: NonEmptyString
    predicate_revision: NonEmptyString
    carrier_ref: NonEmptyString
    carrier_digest: PrefixedDigestString
    materializer_ref: NonEmptyString
    materializer_revision: NonEmptyString
    materializer_digest: PrefixedDigestString
    observation_inventory_ref: NonEmptyString
    observation_inventory_revision: NonEmptyString
    observation_inventory_digest: PrefixedDigestString
    enforcement_rule_ref: NonEmptyString
    enforcement_rule_revision: NonEmptyString
    enforcement_rule_digest: PrefixedDigestString
    state_cut_ref: NonEmptyString
    state_cut_revision: NonEmptyString
    memory_ref: NonEmptyString
    memory_revision: NonEmptyString
    release_ref: NonEmptyString
    release_revision: NonEmptyString
    assurance_axis: Literal["runtime-enforcement"]
    claim: BehavioralClaimBindingModel
    evidence_refs: list[NonEmptyString] = Field(min_length=1)
    limitations: list[NonEmptyString] = Field(min_length=1)
    explicit_non_claims: list[NonEmptyString] = Field(min_length=1)

    @model_validator(mode="after")
    def _validate_local_binding(self) -> ParticipantOpacityRuntimeEnforcementBindingModel:
        if self.claim.assurance_axis != self.assurance_axis:
            raise ValueError("participant opacity runtime claim assurance axis must match the decision binding")
        if self.claim.assurance_status != "enforced" or self.claim.evidence_scope != "finite":
            raise ValueError("participant opacity runtime claims must use enforced finite evidence")
        if self.claim.quantifier_scope not in {"single-artifact", "finite-cases"}:
            raise ValueError("participant opacity runtime claims must remain finitely quantified")
        return self


class ParticipantOpacityRuntimeSupportModel(ContractModel):
    """Trusted in-process support joined to one compact durable binding."""

    binding: ParticipantOpacityRuntimeEnforcementBindingModel
    observation_inventory: ParticipantOpacityObservationInventoryModel
    predicate_positive_case_ref: NonEmptyString
    predicate_negative_case_ref: NonEmptyString
    initial_information_digest: PrefixedDigestString
    normalized_observation_digest: PrefixedDigestString

    @model_validator(mode="after")
    def _validate_inventory_binding(self) -> ParticipantOpacityRuntimeSupportModel:
        identity = (
            self.observation_inventory.inventory_ref,
            self.observation_inventory.inventory_revision,
            self.observation_inventory.canonical_digest,
        )
        expected = (
            self.binding.observation_inventory_ref,
            self.binding.observation_inventory_revision,
            self.binding.observation_inventory_digest,
        )
        if identity != expected:
            raise ValueError("participant opacity runtime support inventory does not match its durable binding")
        if self.predicate_positive_case_ref == self.predicate_negative_case_ref:
            raise ValueError("participant opacity runtime support requires distinct secret and nonsecret cases")
        return self


__all__ = [
    "ParticipantOpacityObservationChannel",
    "ParticipantOpacityObservationInventoryModel",
    "ParticipantOpacityObservationSurfaceModel",
    "ParticipantOpacityRuntimeEnforcementBindingModel",
    "ParticipantOpacityRuntimeSupportModel",
]
