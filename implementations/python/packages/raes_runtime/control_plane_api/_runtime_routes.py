"""Private state activity endpoint over the existing authenticated P2 boundary."""

from fastapi import HTTPException, Request

from ..runtime_sequence_reference import RuntimeSequenceReference
from ._auth import _AdministrativeMutationIdentity
from ._offload import _control_plane_calls


def register_runtime_routes(app, plane):
    @app.post("/runtime/progress")
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
