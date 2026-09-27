"""Per-entry apparatus admission gates for trial compilation."""

from __future__ import annotations

from raes_backend_protocols.backend_manifest import BackendManifest
from raes_backend_protocols.capabilities import ObservationCapabilities
from raes_backend_protocols.cleanup_admission import require_execution_authority_capability
from raes_contracts.contracts import TrialCleanupPlanModel
from raes_contracts.diagnostics import Diagnostic

from ..capture_admission import CaptureDemand, capture_admission_diagnostics
from .models import CompilationFailure


class CaptureAdmissionFailure(Exception):
    def __init__(self, diagnostics: tuple[Diagnostic, ...]) -> None:
        super().__init__("required capture is not supported by the admitted apparatus")
        self.diagnostics = diagnostics


def _fail(code: str, address: str, message: str) -> CompilationFailure:
    return CompilationFailure(code, address, message)


def require_capture_admission(
    demands: tuple[CaptureDemand, ...],
    observations: tuple[ObservationCapabilities | None, ...],
) -> None:
    diagnostics = [
        diagnostic for observation in observations for diagnostic in capture_admission_diagnostics(demands, observation)
    ]
    if diagnostics:
        raise CaptureAdmissionFailure(tuple(diagnostics))


def require_execution_authority(
    backends: tuple[BackendManifest, ...],
    cleanup: TrialCleanupPlanModel,
    required_guarantees: tuple[str, ...],
) -> None:
    """Every selected backend must honour the authored timeout, cleanup and retry choices.

    An entry that selects no backend has nothing that could honour them, so it is
    refused rather than admitted vacuously.
    """

    if not backends:
        raise _fail(
            "execution-authority-unsupported",
            "/execution_authority",
            "a selected backend cannot honour the admitted execution authority",
        )
    for backend in backends:
        try:
            require_execution_authority_capability(
                backend, cleanup_plan=cleanup, required_guarantees=required_guarantees
            )
        except ValueError as exc:
            raise _fail(
                "execution-authority-unsupported",
                "/execution_authority",
                "a selected backend cannot honour the admitted execution authority",
            ) from exc


__all__ = ["CaptureAdmissionFailure", "require_capture_admission", "require_execution_authority"]
