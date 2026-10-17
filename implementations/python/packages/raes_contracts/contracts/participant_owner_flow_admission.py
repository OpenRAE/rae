"""Finite IFC admission uses API-424's existing obligations and support relation."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .participant_control_results import ControlOwnerSecurityFactModel
from .participant_control_support_v2 import ControlSupportAssessmentV2Model
from .participant_owner_flow import OWNER_FLOW_OBLIGATION_IDS, OWNER_FLOW_PROFILE_ID

if TYPE_CHECKING:
    from .participant_control_applicability import ParticipantControlRequestV2Model, ParticipantControlSelectionV2Model
    from .participant_control_invocation import ControlMechanismResultV2Model


def validate_owner_flow_selection(selection: ParticipantControlSelectionV2Model) -> None:
    bindings = {binding.instance_id: binding for binding in selection.bindings}
    selected = {profile for binding in selection.bindings for profile in binding.profiles}
    owner_profiles = {profile for profile in selected if profile.ref == OWNER_FLOW_PROFILE_ID}
    for profile in owner_profiles:
        obligations = [item for item in selection.obligations if item.profile == profile]
        if {item.obligation_id for item in obligations} != OWNER_FLOW_OBLIGATION_IDS:
            raise ValueError("owner flow profile requires both exact profile-owned obligations")
        if any(item.required_kind != "ifc-fact" or not item.admitted_support for item in obligations):
            raise ValueError("owner flow obligations require IFC facts and admitted support promises")
    for obligation in selection.obligations:
        for promise in obligation.admitted_support:
            binding = bindings.get(promise.instance_id)
            if binding is None or obligation.profile not in binding.profiles:
                raise ValueError("admitted support promise must resolve its exact profile and instance")
            # Reuse the published CA-04 relation; the trusted resolver still
            # establishes constraint/coverage evidence before release.
            relation = {
                "exact": "exact",
                "bounded": "bounded-compatible",
                "disclosed_weak": "disclosed-weak-compatible",
            }[promise.effective_level]
            ControlSupportAssessmentV2Model(
                obligation_id=obligation.obligation_id,
                instance_id=promise.instance_id,
                required_strength=obligation.required_strength,
                required_constraints=obligation.constraints,
                effective_support=promise,
                relation=relation,
                evidence=promise.evidence,
            )


def validate_owner_flow_result_coverage(
    request: ParticipantControlRequestV2Model, results: tuple[ControlMechanismResultV2Model, ...]
) -> None:
    """A different selected domain cannot discharge an owner obligation."""
    obligations = {item.obligation_id: item for item in request.selection.obligations}
    outputs = {item.slot_id: item for item in results}
    for coverage in request.applicability.coverage:
        obligation = obligations[coverage.obligation_id]
        if coverage.status != "applies" or obligation.profile.ref != OWNER_FLOW_PROFILE_ID:
            continue
        for slot_id in coverage.slot_ids:
            result = outputs[slot_id]
            if result.status == "resolved" and (
                not isinstance(result.payload, ControlOwnerSecurityFactModel)
                or result.payload.profile != obligation.profile
            ):
                raise ValueError("owner flow obligation requires its exact profile fact")
