"""Private state activity endpoint over the existing authenticated P2 boundary."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import HTTPException, Request

from ..runtime_sequence_reference import RuntimeSequenceReference
from ._auth import _AdministrativeMutationIdentity
from ._offload import _control_plane_calls

if TYPE_CHECKING:
    from fastapi import FastAPI

    from ..control_plane import RuntimeControlPlane


def register_runtime_routes(app: FastAPI, plane: RuntimeControlPlane) -> None:
    @app.post(
        "/runtime/progress",
        responses={
            404: {"description": "Runtime execution not found or unavailable to this worker."},
            409: {"description": "Runtime execution conflicts with its admitted binding."},
            503: {"description": "Runtime execution is temporarily unavailable."},
        },
    )
    async def advance(
        reference: RuntimeSequenceReference, request: Request, identity: _AdministrativeMutationIdentity
    ) -> str:
        try:
            return await _control_plane_calls(request).mutate(plane.advance_workflow, reference, identity=identity)
        except KeyError, PermissionError:
            raise HTTPException(status_code=404, detail="runtime execution not found") from None
        except TypeError, ValueError:
            raise HTTPException(status_code=409, detail="runtime execution conflict") from None
        except RuntimeError, TimeoutError:
            raise HTTPException(status_code=503, detail="runtime execution unavailable") from None
