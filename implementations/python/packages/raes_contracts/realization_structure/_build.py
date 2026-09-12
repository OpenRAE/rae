"""Diagnostic result type shared by realization constraint builders."""

from __future__ import annotations

from dataclasses import dataclass

from ..diagnostics import Diagnostic
from ._common import recursive_diagnostic
from ._models import RealizationConstraintDocument, RealizationRelationStatus


@dataclass(frozen=True)
class RealizationConstraintBuildResult:
    """Result of normalization or composition without exception-shaped limits."""

    status: RealizationRelationStatus
    document: RealizationConstraintDocument | None = None
    diagnostics: tuple[Diagnostic, ...] = ()


def build_failure(
    status: RealizationRelationStatus,
    pointer: str,
    message: str,
) -> RealizationConstraintBuildResult:
    diagnostic = recursive_diagnostic(f"realization.{status.value}", pointer, message)
    return RealizationConstraintBuildResult(status=status, diagnostics=(diagnostic,))
