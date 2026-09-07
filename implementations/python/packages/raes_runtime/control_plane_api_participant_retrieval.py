"""HTTP routes for API-408 participant retrieval views."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Annotated, Generic, TypeVar

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from raes_contracts.contracts import (
    ParticipantContextViewModel,
    ParticipantHistoryViewModel,
    ParticipantStatusViewModel,
)

from .control_plane import RuntimeControlPlane
from .control_plane_api._offload import _control_plane_calls
from .control_plane_api._responses import _set_snapshot_revision_header
from .control_plane_security import ControlPlaneIdentity, ParticipantAudienceSubjectBinding

_NOT_FOUND_RESPONSES = {404: {"description": "Not found"}}
_GOVERNED_VIEW_RESPONSES = {
    **_NOT_FOUND_RESPONSES,
    403: {"description": "Forbidden"},
    409: {"description": "Participant projection conflict"},
}
_ViewT = TypeVar("_ViewT")


def _read_identity_dependency(request: Request) -> ControlPlaneIdentity:
    return request.app.state.control_plane_api_auth.read_identity(request)


_ReadIdentity = Annotated[ControlPlaneIdentity, Depends(_read_identity_dependency)]


@dataclass(frozen=True)
class _GovernedViewResolution(Generic[_ViewT]):
    action: str
    not_found_detail: str
    resolve: Callable[[ParticipantAudienceSubjectBinding | None, str], _ViewT | None]


@dataclass(frozen=True)
class _ParticipantContextQuery:
    view_ref: str
    episode_id: str | None
    derivation_basis_ref: str | None
    payload_ref: str | None


def _participant_context_query(
    view_ref: str,
    episode_id: str | None = None,
    derivation_basis_ref: str | None = None,
    payload_ref: str | None = None,
) -> _ParticipantContextQuery:
    return _ParticipantContextQuery(view_ref, episode_id, derivation_basis_ref, payload_ref)


_ContextQuery = Annotated[_ParticipantContextQuery, Depends(_participant_context_query)]


async def _resolved_governed_view(
    control_plane: RuntimeControlPlane,
    request: Request,
    response: Response,
    identity: ControlPlaneIdentity,
    participant_address: str,
    resolution: _GovernedViewResolution[_ViewT],
) -> _ViewT:
    """Resolve one governed participant view with the shared audit and error flow."""

    audience_binding = _require_governed_audience_candidate(control_plane, identity, participant_address)
    calls = _control_plane_calls(request)
    projection = await calls.mutate(
        _governed_view,
        lambda: control_plane._project_snapshot_read(
            lambda: resolution.resolve(audience_binding, request.headers.get("idempotency-key", ""))
        ),
    )
    view, revision = projection
    if view is None:
        raise HTTPException(status_code=404, detail=resolution.not_found_detail)
    await calls.run(
        control_plane.record_audit,
        action=resolution.action,
        identity=identity.identity,
        allowed=True,
        target=str(request.url.path),
    )
    _set_snapshot_revision_header(response, revision)
    return view


def register_participant_retrieval_routes(
    app: FastAPI,
    control_plane: RuntimeControlPlane,
) -> None:
    @app.get(
        "/participants/{participant_address}/status",
        responses=_GOVERNED_VIEW_RESPONSES,
    )
    async def get_participant_status_view(
        participant_address: str,
        request: Request,
        response: Response,
        identity: _ReadIdentity,
    ) -> ParticipantStatusViewModel:
        return await _resolved_governed_view(
            control_plane,
            request,
            response,
            identity,
            participant_address,
            _GovernedViewResolution(
                action="get_participant_status_view",
                not_found_detail=f"Unknown participant: {participant_address}",
                resolve=lambda audience_binding, idempotency_key: control_plane.get_participant_status_view(
                    participant_address,
                    identity=identity,
                    audience_binding=audience_binding,
                    idempotency_key=idempotency_key,
                ),
            ),
        )

    @app.get(
        "/participants/{participant_address}/episodes/{episode_id}/history",
        responses=_GOVERNED_VIEW_RESPONSES,
    )
    async def get_participant_history_view(
        participant_address: str,
        episode_id: str,
        request: Request,
        response: Response,
        identity: _ReadIdentity,
    ) -> ParticipantHistoryViewModel:
        return await _resolved_governed_view(
            control_plane,
            request,
            response,
            identity,
            participant_address,
            _GovernedViewResolution(
                action="get_participant_history_view",
                not_found_detail=f"Unknown participant episode: {participant_address}/{episode_id}",
                resolve=lambda audience_binding, idempotency_key: control_plane.get_participant_history_view(
                    participant_address,
                    episode_id,
                    identity=identity,
                    audience_binding=audience_binding,
                    idempotency_key=idempotency_key,
                ),
            ),
        )

    @app.get(
        "/participants/{participant_address}/context",
        responses=_GOVERNED_VIEW_RESPONSES,
    )
    async def get_participant_context_view(
        participant_address: str,
        request: Request,
        response: Response,
        identity: _ReadIdentity,
        query: _ContextQuery,
    ) -> ParticipantContextViewModel:
        return await _resolved_governed_view(
            control_plane,
            request,
            response,
            identity,
            participant_address,
            _GovernedViewResolution(
                action="get_participant_context_view",
                not_found_detail=f"Unknown participant: {participant_address}",
                resolve=lambda audience_binding, idempotency_key: control_plane.get_participant_context_view(
                    participant_address,
                    view_ref=query.view_ref,
                    episode_id=query.episode_id,
                    derivation_basis_ref=query.derivation_basis_ref,
                    payload_ref=query.payload_ref,
                    identity=identity,
                    audience_binding=audience_binding,
                    idempotency_key=idempotency_key,
                ),
            ),
        )


def _require_governed_audience_candidate(
    control_plane: RuntimeControlPlane,
    identity: ControlPlaneIdentity,
    participant_address: str,
) -> ParticipantAudienceSubjectBinding | None:
    if getattr(control_plane, "_crossing_policy_resolver", None) is None:
        return None
    matches = tuple(
        binding
        for binding in identity.participant_audience_subjects
        if binding.participant_address == participant_address
    )
    if not matches:
        raise HTTPException(status_code=403, detail="forbidden")
    if len(matches) != 1:
        raise HTTPException(status_code=409, detail="participant audience binding is ambiguous")
    return matches[0]


def _governed_view(resolve: Callable[[], _ViewT]) -> _ViewT:
    try:
        return resolve()
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail="forbidden") from exc
    except ValueError as exc:
        detail = (
            "participant view crossing evidence is unavailable"
            if str(exc) == "participant view crossing evidence is unavailable"
            else "participant projection conflict"
        )
        raise HTTPException(status_code=409, detail=detail) from exc
