"""Lightweight installed-console entry point for the RAES CLI."""

from __future__ import annotations

import sys
from importlib.metadata import PackageNotFoundError, version

_NOT_INSTALLED_VERSION = "0.0.0+unknown"
_VERSION_ARGUMENTS = frozenset({"--version", "-V"})
_UNEXPECTED_FAILURE_STATUS = 70


def _distribution_version() -> str:
    """Return the governed distribution version or its honest sentinel."""

    try:
        return version("raes")
    except PackageNotFoundError:
        return _NOT_INSTALLED_VERSION


def main() -> None:
    """Run the command graph inside the shared application boundary.

    Exact version probes return before the command graph and the logging
    utilities are imported. An unexpected exception produces one value-free
    log record on standard error and exit status 70, the status that the
    command contract documents for a failure sanitized at the CLI boundary
    (ADR-116).
    """

    arguments = sys.argv[1:]
    if len(arguments) == 1 and arguments[0] in _VERSION_ARGUMENTS:
        print(f"raes {_distribution_version()}")
        return

    from raes_contracts.operational_logging import run_application

    from raes_cli.main import app

    status = run_application(app, unexpected_status=_UNEXPECTED_FAILURE_STATUS)
    if status:
        raise SystemExit(status)
