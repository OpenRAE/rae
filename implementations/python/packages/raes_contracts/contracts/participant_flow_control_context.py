"""Trusted non-wire context records for SEM-233 flow-control validation."""

from __future__ import annotations

from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from .participant_control import (
    ParticipantControlDeclarationModel,
    ParticipantControlOccurrenceModel,
    ParticipantControlTargetContextModel,
)
from .participant_crossing import (
    ParticipantCrossingOccurrenceModel,
    ParticipantCrossingPolicyReferenceModel,
    ParticipantCrossingSubjectReferenceModel,
)
from .participant_flow_control import (
    ParticipantBoundaryFlowPolicyProfileModel,
    ParticipantEffectiveFlowLabelModel,
    ParticipantFlowFinalDisposition,
    ParticipantFlowPolicyCutReferenceModel,
    ParticipantFlowReleaseKind,
    ParticipantFlowSinkKind,
)
from .runtime_facts import RuntimeFactBindingPlaneModel

if TYPE_CHECKING:
    from raes_contracts.contracts.participant_action_admission import ParticipantActionAdmissionRequest

    from ..participant_action_arguments import ParticipantValidatedActionSelection

FlowProfileKey = tuple[str, str]
ActionSelectionKey = tuple[str, str]


@dataclass(frozen=True)
class ParticipantFlowReleaseAuthorityCoordinate:
    """Exact coordinate over which one release authority was resolved."""

    kind: ParticipantFlowReleaseKind
    authority_basis_ref: str
    authority_revision: str
    sink_ref: str
    destination_ref: str
    audience_scope_ref: str


@dataclass(frozen=True)
class ParticipantFlowSinkCoordinate:
    """Exact final sink identity resolved from trusted state."""

    sink_kind: ParticipantFlowSinkKind
    sink_ref: str
    destination_ref: str
    audience_scope_ref: str


@dataclass(frozen=True)
class ParticipantFlowObligationAuthorityCoordinate:
    """Independently authorized owner/clause for the complete exact release."""

    release_digest: str
    owner_ref: str
    obligation_ref: str


@dataclass(frozen=True)
class ParticipantOwnerFlowSinkResolution:
    """Trusted principal resolution and policy posture of one exact final sink."""

    readers: frozenset[str]
    accepts_untrusted_integrity: bool


@dataclass(frozen=True)
class ParticipantFlowActionAdmissionResolution:
    """Trusted action-admission decision at one exact participant sink scope."""

    action_admission_ref: str
    participant_address: str
    episode_id: str
    action_contract_address: str
    action_instance_id: str
    sink: ParticipantFlowSinkCoordinate
    disposition: ParticipantFlowFinalDisposition


@dataclass(frozen=True)
class ParticipantFlowCapabilityResolution:
    """Trusted capability decision at one exact participant sink scope."""

    capability_resolution_ref: str
    participant_address: str
    episode_id: str
    sink: ParticipantFlowSinkCoordinate
    disposition: ParticipantFlowFinalDisposition


@dataclass(frozen=True)
class ParticipantFlowHistoryHeadResolution:
    """Trusted history-head freshness decision at one exact participant sink scope."""

    participant_address: str
    episode_id: str
    sink: ParticipantFlowSinkCoordinate
    history_head_refs: tuple[str, ...]
    disposition: ParticipantFlowFinalDisposition


@dataclass(frozen=True)
class ParticipantFlowControlValidationContext:
    """Trusted non-wire indexes required to validate one SEM-233 relation."""

    profiles: Mapping[FlowProfileKey, ParticipantBoundaryFlowPolicyProfileModel]
    source_labels: Mapping[str, ParticipantEffectiveFlowLabelModel]
    policy_cuts: Mapping[str, ParticipantFlowPolicyCutReferenceModel]
    release_authorities: Collection[ParticipantFlowReleaseAuthorityCoordinate]
    known_sinks: Collection[ParticipantFlowSinkCoordinate]
    runtime_fact_planes: Mapping[str, RuntimeFactBindingPlaneModel]
    action_selections: Mapping[ActionSelectionKey, ParticipantValidatedActionSelection]
    action_admissions: Mapping[str, ParticipantActionAdmissionRequest]
    action_admission_resolutions: Mapping[str, ParticipantFlowActionAdmissionResolution]
    capability_resolutions: Mapping[str, ParticipantFlowCapabilityResolution]
    history_head_resolutions: Collection[ParticipantFlowHistoryHeadResolution]
    control_records: Sequence[ParticipantControlOccurrenceModel]
    control_declarations: Sequence[ParticipantControlDeclarationModel]
    control_known_targets: Sequence[ParticipantControlTargetContextModel]
    crossing_records: Sequence[ParticipantCrossingOccurrenceModel]
    crossing_subjects: Sequence[ParticipantCrossingSubjectReferenceModel]
    crossing_policies: Sequence[ParticipantCrossingPolicyReferenceModel]
    known_evidence_refs: Collection[str]
    known_authority_refs: Collection[str]
    owner_release_authorities: Collection[ParticipantFlowObligationAuthorityCoordinate] = ()
    owner_sink_resolutions: Mapping[ParticipantFlowSinkCoordinate, ParticipantOwnerFlowSinkResolution] = field(
        default_factory=dict
    )
