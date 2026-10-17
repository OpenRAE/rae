"""Recheck linked mixed-control permission at independent action admission."""

from raes_contracts.contracts.participant_control import ParticipantControlTargetKind
from raes_contracts.contracts.participant_control_occurrence_v2 import parse_participant_control_occurrence
from raes_contracts.contracts.participant_control_occurrence_v2_validation import fold_participant_control_episode_v2
from raes_contracts.participant_binding import ParticipantActionAdmissionRequest

from .participant_control_runtime import admitted_policy, resolve_owner_cut
from .participant_control_targets import archived_control_targets


def linked_action_refusal(plane, request):
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


def require_live_control_proposal(plane, request):
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
    archive = [
        parse_participant_control_occurrence(payload)
        for payload in plane._snapshot.participant_control_history.get(participant, ())
    ]
    if any(
        record.occurrence.disposition == "accepted"
        and record.occurrence.kind == "proposal"
        and record.occurrence.proposal_id == request.validated_selection.proposal_ref
        and record.episode_id != episode
        for record in archive
    ):
        raise ValueError("linked control proposal belongs to an ended episode")
    history = [record for record in archive if record.episode_id == episode]
    if not history or history[0].schema_version != "2.0.0":
        return
    policy = admitted_policy(plane, participant, episode)
    fold = fold_participant_control_episode_v2(
        history, policy=policy, available_targets=archived_control_targets(plane, participant)
    )
    if fold.violation is not None:
        raise ValueError("linked control history is unverifiable")
    proposal = fold.state.produced(ParticipantControlTargetKind.PROPOSAL, request.validated_selection.proposal_ref)
    if proposal is None:
        return
    lifecycle = fold.state.lifecycle(proposal.record_event_id)
    if state.get("status") != "running" or lifecycle.superseded or lifecycle.replaced:
        raise ValueError("linked control proposal is no longer eligible")
    decisions = [
        record
        for record in history
        if record.occurrence.disposition == "accepted"
        and record.occurrence.kind == "approval"
        and record.occurrence.proposal_ref == proposal.target_ref
        and not fold.state.lifecycle(record.event_id).superseded
    ]
    if len(decisions) != 1:
        raise ValueError("linked proposal requires one live approval")
    approval = decisions[0].occurrence
    proposed = next(record.occurrence for record in history if record.event_id == proposal.record_event_id)
    if proposed.action_contract_ref != request.action_contract_address:
        raise ValueError("linked proposal action contract changed")
    method = getattr(plane._mixed_control.resolver, "resolve_action_cut", None)
    if not callable(method):
        raise ValueError("linked proposal has no admitted action-cut owner")
    cut = resolve_owner_cut(plane, policy, request, method)
    current = policy.state(fold.state.state_ref)
    if (
        cut.request_ref != request.action_instance_id
        or not set([*approval.authority_basis_refs, *current.authority_basis_refs])
        <= set(cut.active_authority_basis_refs)
        or not set(approval.controlled_scope_refs) <= set(cut.authorized_scope_refs)
        or not approval.valid_from_order <= cut.effective_order <= approval.valid_until_order
        or not current.valid_from_order <= cut.effective_order <= current.valid_until_order
    ):
        raise ValueError("linked approval is not valid at action admission")
