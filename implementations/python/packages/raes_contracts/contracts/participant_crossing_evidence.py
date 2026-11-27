"""Caller evidence metadata without operation identity or execution authority."""

from pydantic import Field

from .base import ContractModel, NonEmptyString


class ParticipantCrossingEvidence(ContractModel):
    """Caller-owned evidence metadata with no incumbent-operation coordinates."""

    audience_scope_ref: NonEmptyString
    required_evidence_refs: list[NonEmptyString] = Field(min_length=1)
    provenance_refs: list[NonEmptyString] = Field(min_length=1)
    evidence_refs: list[NonEmptyString] = Field(min_length=1)
    object_marking_refs: list[NonEmptyString] = Field(min_length=1)
    authorization_scope: NonEmptyString
    loss_and_limitations: list[NonEmptyString] = Field(min_length=1)
