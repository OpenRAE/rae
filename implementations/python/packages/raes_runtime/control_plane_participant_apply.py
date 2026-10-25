"""Validate participant backend results under their admitted effect authority."""

from __future__ import annotations

from collections.abc import Callable

from raes_contracts.contracts import ParticipantInformationStateContextResolver
from raes_contracts.runtime_state import ApplyResult, RuntimeSnapshot

from .backend_calls import _BackendCallContext, _call_backend_apply
from .participant_effect_authority import participant_effect_authority


def apply_authorized_participant_action(
    *,
    method: Callable[..., object],
    request: object,
    snapshot: RuntimeSnapshot,
    address: str,
    information_state_context_resolver: ParticipantInformationStateContextResolver | None = None,
) -> ApplyResult:
    """Invoke and validate a participant backend after durable authorization."""

    return _call_backend_apply(
        method,
        request,
        snapshot,
        address=address,
        snapshot=snapshot,
        realization=participant_effect_authority(request, snapshot),
        call=_BackendCallContext(
            information_state_context_resolver=information_state_context_resolver,
        ),
    )
