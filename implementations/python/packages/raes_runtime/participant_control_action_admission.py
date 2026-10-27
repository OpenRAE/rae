"""Recheck linked mixed-control permission at independent action admission."""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from raes_contracts.contracts import ParticipantControlOccurrenceModel
    from raes_contracts.contracts.participant_control_occurrence_v2 import (
        ParticipantApprovalOccurrenceV2Model,
        ParticipantControlOccurrenceV2Model,
    )
    from raes_contracts.contracts.participant_control_occurrence_v2_policy import (
        ParticipantControlOccurrencePolicyModel,
    )
    from raes_contracts.contracts.participant_control_occurrence_v2_state import (
        ParticipantControlEpisodeStateV2,
        ParticipantControlProducedTargetV2,
    )
    from raes_contracts.runtime_state import ApplyResult

    from .control_plane import RuntimeControlPlane


from raes_contracts.contracts.participant_control import ParticipantControlTargetKind
from raes_contracts.contracts.participant_control_occurrence_v2 import parse_participant_control_occurrence
from raes_contracts.participant_binding import ParticipantActionAdmissionRequest

from .participant_control_runtime import admitted_policy, resolve_owner_cut
from .participant_control_targets import archived_control_targets


def linked_action_refusal(plane: RuntimeControlPlane, request: object) -> ApplyResult | None:
    """Return a bounded native failure before any linked effect is dispatched."""

    from raes_contracts.diagnostics import Diagnostic
    from raes_contracts.runtime_state import ApplyResult

    try:
        require_live_control_proposal(plane, request)
    except (ValueError, PermissionError, TimeoutError):
        return ApplyResult(
            False,
            plane._snapshot,
            diagnostics=[
                Diagnostic(
                    code="runtime.participant-control.action-not-authorized",
                    domain="runtime",
                    address=request.participant_address,
                    message="The linked control proposal does not authorize action admission at the current cut.",
                )
            ],
        )
    return None


def require_live_control_proposal(plane: RuntimeControlPlane, request: object) -> None:
    """A selection cannot revive a cancelled, superseded or denied proposal."""

    if (
        not isinstance(request, ParticipantActionAdmissionRequest)
        or request.validated_selection is None
        or plane._mixed_control is None
    ):
        return
    participant = request.participant_address
    state = plane._snapshot.participant_episode_results.get(participant, {})
    episode = state.get("episode_id")
    from .participant_control_archive_projection import control_archive_projection
    from .participant_control_runtime import archived_policies

    targets = archived_control_targets(plane, participant)
    archive = control_archive_projection(
        plane, participant, policies=archived_policies(plane, participant), targets=targets
    )
    proposal_ref = request.validated_selection.proposal_ref
    if archive.proposal_episodes.get(proposal_ref, set()) - {episode}:
        raise ValueError("linked control proposal belongs to an ended episode")
    if archive.lineages.get(episode) != "2.0.0":
        return
    policy = admitted_policy(plane, participant, episode)
    prefix = archive.episodes[episode]
    history = tuple(prefix.records.values())
    proposal = prefix.state.produced(ParticipantControlTargetKind.PROPOSAL, proposal_ref)
    if proposal is None:
        return
    approval = _require_eligible_approval(request, state, prefix.state, proposal, history)
    _require_action_cut(plane, request, policy, prefix.state.state_ref, approval)


def _current_control_history(
    plane: RuntimeControlPlane, participant: str, episode: str | None, proposal_ref: str
) -> list[ParticipantControlOccurrenceModel | ParticipantControlOccurrenceV2Model]:
    archive = [
        parse_participant_control_occurrence(payload)
        for payload in plane._snapshot.participant_control_history.get(participant, ())
    ]
    if any(
        record.occurrence.disposition == "accepted"
        and record.occurrence.kind == "proposal"
        and record.occurrence.proposal_id == proposal_ref
        and record.episode_id != episode
        for record in archive
    ):
        raise ValueError("linked control proposal belongs to an ended episode")
    return [record for record in archive if record.episode_id == episode]


def _require_eligible_approval(
    request: ParticipantActionAdmissionRequest,
    state: dict[str, object],
    folded: ParticipantControlEpisodeStateV2,
    proposal: ParticipantControlProducedTargetV2,
    history: Sequence[ParticipantControlOccurrenceModel | ParticipantControlOccurrenceV2Model],
) -> ParticipantApprovalOccurrenceV2Model:
    lifecycle = folded.lifecycle(proposal.record_event_id)
    if state.get("status") != "running" or lifecycle.superseded or lifecycle.replaced:
        raise ValueError("linked control proposal is no longer eligible")
    decisions = _live_decisions(history, folded, proposal.target_ref)
    if len(decisions) != 1:
        raise ValueError("linked proposal requires one live approval")
    proposed = next(record.occurrence for record in history if record.event_id == proposal.record_event_id)
    if proposed.action_contract_ref != request.action_contract_address:
        raise ValueError("linked proposal action contract changed")
    return decisions[0].occurrence


def _live_decisions(
    history: Sequence[ParticipantControlOccurrenceModel | ParticipantControlOccurrenceV2Model],
    folded: ParticipantControlEpisodeStateV2,
    proposal_ref: str,
) -> list[ParticipantControlOccurrenceModel | ParticipantControlOccurrenceV2Model]:
    return [
        record
        for record in history
        if record.occurrence.disposition == "accepted"
        and record.occurrence.kind == "approval"
        and record.occurrence.proposal_ref == proposal_ref
        and not folded.lifecycle(record.event_id).superseded
    ]


def _require_action_cut(
    plane: RuntimeControlPlane,
    request: ParticipantActionAdmissionRequest,
    policy: ParticipantControlOccurrencePolicyModel,
    state_ref: str,
    approval: ParticipantApprovalOccurrenceV2Model,
) -> None:
    method = getattr(plane._mixed_control.resolver, "resolve_action_cut", None)
    if not callable(method):
        raise ValueError("linked proposal has no admitted action-cut owner")
    cut = resolve_owner_cut(plane, policy, request, method)
    current = policy.state(state_ref)
    if (
        cut.request_ref != request.action_instance_id
        or not {*approval.authority_basis_refs, *current.authority_basis_refs} <= set(cut.active_authority_basis_refs)
        or not set(approval.controlled_scope_refs) <= set(cut.authorized_scope_refs)
        or not approval.valid_from_order <= cut.effective_order <= approval.valid_until_order
        or not current.valid_from_order <= cut.effective_order <= current.valid_until_order
    ):
        raise ValueError("linked approval is not valid at action admission")
