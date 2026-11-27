"""ADR-114's published finite owner universe and independently resolved bindings.

The fixed reader names are semantic principal references. Trusted operator
resolution binds an exact sink to those principals; profile data grants no
authority. This module neither loads code nor executes release operations.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, ClassVar, Literal

from pydantic import ConfigDict, Field

from ..canonical import canonical_json_digest
from .base import ContractModel, NonEmptyString
from .participant_flow_control_context import (
    ParticipantFlowControlValidationContext,
    ParticipantFlowSinkCoordinate,
)
from .participant_flow_control_context import (
    ParticipantFlowObligationAuthorityCoordinate as _ParticipantFlowObligationAuthorityCoordinate,
)
from .participant_flow_control_context import (
    ParticipantOwnerFlowSinkResolution as _ParticipantOwnerFlowSinkResolution,
)
from .participant_flow_control_semantics import ParticipantBoundaryFlowPolicyProfileModel

if TYPE_CHECKING:
    from .participant_flow_control import ParticipantFlowControlRelationModel
    from .participant_flow_control_semantics import ParticipantEffectiveFlowLabelModel, ParticipantFlowRelease

OWNER_FLOW_PROFILE_ID = "participant-owner-flow-policy-v1"
OWNER_FLOW_PROFILE_DIGEST = "sha256:0a7872665ca0cf435bddcd0d6a39b89d20a8f5f6a5e8ca8abdf1d4f77da774df"
OWNER_FLOW_OBLIGATION_IDS = frozenset({"ifc-owner-a", "ifc-owner-b"})


class ParticipantOwnerFlowClauseModel(ContractModel):
    model_config = ConfigDict(frozen=True)
    owner_ref: Literal["owner:a", "owner:b"]
    confidentiality_obligation_ref: NonEmptyString
    untrusted_integrity_obligation_ref: NonEmptyString
    endorsed_integrity_obligation_ref: NonEmptyString
    reader_refs: tuple[Literal["reader:alice", "reader:bob", "reader:carol"], ...] = Field(min_length=1, max_length=3)


class ParticipantOwnerFlowPolicyProfileModel(ParticipantBoundaryFlowPolicyProfileModel):
    """One exact publication; shape-valid modifications remain unpublished."""

    _published_digest: ClassVar[str] = OWNER_FLOW_PROFILE_DIGEST
    schema_version: Literal["participant-owner-flow-policy/v1"] = "participant-owner-flow-policy/v1"
    profile_id: Literal["participant-owner-flow-policy-v1"]
    variability_revision: Literal["ifc-profile-variability/rev1"]
    memory: Literal["retain-across-episodes"]
    owner_clauses: tuple[ParticipantOwnerFlowClauseModel, ...] = Field(min_length=2, max_length=2)


def validate_owner_flow_context(
    document: ParticipantFlowControlRelationModel,
    profile: ParticipantOwnerFlowPolicyProfileModel,
    context: ParticipantFlowControlValidationContext,
) -> None:
    """Reuse the incumbent graph and gates; validate only the new owner relations."""

    _validate_owner_releases(document, profile, context)
    _validate_owner_sinks(document, profile, context)


def _discharged_owner_obligations(
    release: ParticipantFlowRelease,
    confidentiality: Mapping[str, str],
    integrity: Mapping[str, ParticipantOwnerFlowClauseModel],
) -> list[tuple[str, str | None]]:
    if release.kind == "declassification":
        return [(token, confidentiality.get(token)) for token in release.removed_confidentiality_obligation_refs]
    discharged: list[tuple[str, str | None]] = []
    for replacement in release.integrity_obligation_replacements:
        clause = integrity.get(replacement.source_obligation_ref)
        if clause is None or replacement.result_obligation_ref != clause.endorsed_integrity_obligation_ref:
            raise ValueError("owner endorsement replacement must retain its exact owner")
        discharged.append((replacement.source_obligation_ref, clause.owner_ref))
    return discharged


def _validate_owner_releases(
    document: ParticipantFlowControlRelationModel,
    profile: ParticipantOwnerFlowPolicyProfileModel,
    context: ParticipantFlowControlValidationContext,
) -> None:
    confidentiality = {clause.confidentiality_obligation_ref: clause.owner_ref for clause in profile.owner_clauses}
    integrity = {clause.untrusted_integrity_obligation_ref: clause for clause in profile.owner_clauses}
    for release in document.releases:
        digest = canonical_json_digest(release.model_dump(mode="json"))
        for token, owner in _discharged_owner_obligations(release, confidentiality, integrity):
            if (
                owner is None
                or _ParticipantFlowObligationAuthorityCoordinate(digest, owner, token)
                not in context.owner_release_authorities
            ):
                raise ValueError("owner release authority must cover each exact discharged obligation")


def _require_owner_sink_resolution(sink: object, known_readers: frozenset[str]) -> _ParticipantOwnerFlowSinkResolution:
    if (
        not isinstance(sink, _ParticipantOwnerFlowSinkResolution)
        or type(sink.accepts_untrusted_integrity) is not bool
        or type(sink.readers) is not frozenset
        or not sink.readers
        or not sink.readers <= known_readers
    ):
        raise ValueError("owner flow sink must resolve exact known reader principals and integrity posture")
    return sink


def _expected_owner_sink_results(
    label: ParticipantEffectiveFlowLabelModel,
    sink: _ParticipantOwnerFlowSinkResolution,
    clauses: Mapping[str, frozenset[str]],
    endorsed: set[str],
) -> tuple[str, str]:
    if label.resolution_status != "resolved":
        status = "unsupported" if label.resolution_status == "unsupported" else "unresolved"
        return status, status
    confidentiality = all(sink.readers <= clauses[token] for token in label.confidentiality_obligation_refs)
    integrity = sink.accepts_untrusted_integrity or set(label.integrity_obligation_refs) <= endorsed
    return "satisfied" if confidentiality else "deny", "satisfied" if integrity else "deny"


def _validate_owner_sinks(
    document: ParticipantFlowControlRelationModel,
    profile: ParticipantOwnerFlowPolicyProfileModel,
    context: ParticipantFlowControlValidationContext,
) -> None:
    labels = {label.label_id: label for label in document.labels}
    clauses = {clause.confidentiality_obligation_ref: frozenset(clause.reader_refs) for clause in profile.owner_clauses}
    endorsed = {clause.endorsed_integrity_obligation_ref for clause in profile.owner_clauses}
    known_readers = frozenset().union(*(clause.reader_refs for clause in profile.owner_clauses))
    for decision in document.sink_decisions:
        coordinate = ParticipantFlowSinkCoordinate(**decision.sink.model_dump(mode="python"))
        sink = _require_owner_sink_resolution(context.owner_sink_resolutions.get(coordinate), known_readers)
        expected = _expected_owner_sink_results(labels[decision.label_ref], sink, clauses, endorsed)
        if (decision.confidentiality_result, decision.integrity_result) != expected:
            raise ValueError("owner flow sink coordinate result differs from the published relation")
