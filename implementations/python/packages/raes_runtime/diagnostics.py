"""Shared runtime diagnostic helpers."""

from __future__ import annotations

from raes_contracts.diagnostics import Diagnostic


def _has_error_diagnostic(diagnostics: list[Diagnostic]) -> bool:
    return any(diagnostic.is_error for diagnostic in diagnostics)


def _failure_diagnostic(code: str, address: str, message: str) -> Diagnostic:
    return Diagnostic(
        code=code,
        domain="runtime",
        address=address,
        message=message,
    )
