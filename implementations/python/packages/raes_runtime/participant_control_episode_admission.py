"""Admit controller authority before invoking the existing episode owner."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

    from raes_contracts.runtime_state import RuntimeSnapshot

    from .control_plane import RuntimeControlPlane


from dataclasses import replace
from uuid import uuid4

from raes_contracts.diagnostics import Diagnostic
from raes_contracts.errors import ConflictError
from raes_contracts.participant_episode import (
    ParticipantEpisodeInitializeRequest,
    ParticipantEpisodeResetRequest,
    ParticipantEpisodeRestartRequest,
)
from raes_contracts.runtime_state import ApplyResult, OperationState

from .backend_calls import _BackendCallContext, _call_backend_apply
from .participant_control_runtime import (
    CONTROL_CUT_REFUSALS,
    archived_policies,
    episode_policy_admissions,
    participant_policy_specifications,
    require_initial_authority,
    resolve_live_cut,
)
from .participant_effect_authority import participant_effect_authority


def _prepare_episode_request(plane: RuntimeControlPlane, request: object) -> object:
    if plane._mixed_control is None or not isinstance(
        request, (ParticipantEpisodeInitializeRequest, ParticipantEpisodeResetRequest, ParticipantEpisodeRestartRequest)
    ):
        return request
    return _prepare_bound_episode_request(plane, request)


def _prepare_bound_episode_request(
    plane: RuntimeControlPlane,
    request: ParticipantEpisodeInitializeRequest | ParticipantEpisodeResetRequest | ParticipantEpisodeRestartRequest,
) -> object:
    specifications = participant_policy_specifications(plane, request.participant_address)
    if not specifications:
        return request
    if len(specifications) != 1:
        raise ConflictError("episode must resolve exactly one mixed-control policy")
    request = replace(request, episode_id=request.episode_id or f"episode.{uuid4()}")
    policy = plane._mixed_control.policy(specifications[0].address, request.episode_id)
    if any(item.episode_id == request.episode_id for item in archived_policies(plane, request.participant_address)):
        raise ConflictError("mixed-control episode identity cannot be reused")
    cut = resolve_live_cut(plane, policy, None)
    require_initial_authority(policy, cut, "initial mixed-control authority is invalid")
    return request


def execute_participant_policy_call(
    plane: RuntimeControlPlane, *, method: Callable[..., ApplyResult], request: object, address: str
) -> tuple[ApplyResult, OperationState, dict[str, object] | None]:
    """Return native result, terminal knowledge and any atomically retained pin."""

    try:
        from .participant_control_action_admission import require_live_control_proposal

        require_live_control_proposal(plane, request)
        request = _prepare_episode_request(plane, request)
    except CONTROL_CUT_REFUSALS:
        return _unverified(plane, address), OperationState.FAILED, None
    return _execute_prepared_policy_call(plane, method, request, address)


def _execute_prepared_policy_call(
    plane: RuntimeControlPlane, method: Callable[..., ApplyResult], request: object, address: str
) -> tuple[ApplyResult, OperationState, dict[str, object] | None]:
    predecessor = plane._snapshot
    baseline_revision = plane._snapshot_state.revision
    with plane._mutation_authority.external_call():
        result = _call_backend_apply(
            method,
            request,
            predecessor,
            address=address,
            snapshot=predecessor,
            realization=participant_effect_authority(request, predecessor),
            call=_BackendCallContext(information_state_context_resolver=plane._information_state_context_resolver),
        )
    plane._reload_derived_state()
    if plane._snapshot_state.revision != baseline_revision:
        return _unverified(plane, address), OperationState.INDETERMINATE, None
    if not result.success:
        return result, OperationState.FAILED, None
    return _retain_episode_admissions(plane, predecessor, result, address)


def _retain_episode_admissions(
    plane: RuntimeControlPlane, predecessor: RuntimeSnapshot, result: ApplyResult, address: str
) -> tuple[ApplyResult, OperationState, dict[str, object] | None]:
    try:
        admissions = episode_policy_admissions(plane, predecessor, result.snapshot)
    except CONTROL_CUT_REFUSALS:
        # The callback ran. Preserve the current committed cut, record uncertainty
        # and retain exclusion; neither rollback nor initial authority is proved.
        return _unverified(plane, address), OperationState.INDETERMINATE, None
    return result, OperationState.SUCCEEDED, admissions


def _unverified(plane: RuntimeControlPlane, address: str) -> ApplyResult:
    return ApplyResult(
        False,
        plane._snapshot,
        diagnostics=[
            Diagnostic(
                code="runtime.participant-control.admission-unverified",
                domain="runtime",
                address=address,
                message=(
                    "Participant control authority or native effect knowledge could not be established "
                    "at the admitted cut."
                ),
            )
        ],
    )
