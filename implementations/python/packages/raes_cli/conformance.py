"""Backend conformance commands exposed through ``raes conformance backend``."""

from __future__ import annotations

import json
from pathlib import Path

import typer
from raes_conformance.conformance import (
    BackendCapabilityProfile,
    BackendConformanceReport,
    backend_conformance_report_payload,
    run_fixture_suite,
)
from raes_contracts.errors import OperationalError

_DEFAULT_PROFILE_ID = BackendCapabilityProfile.ORCHESTRATION_EVALUATION.value
_KNOWN_PROFILE_HINT = ", ".join(sorted(profile.value for profile in BackendCapabilityProfile))

app = typer.Typer(help="Backend conformance suite and fixture corpus.")


def _report_payload(report: BackendConformanceReport) -> dict[str, object]:
    return backend_conformance_report_payload(report)


@app.command("backend")
def backend(
    profile: str = typer.Option(
        _DEFAULT_PROFILE_ID,
        "--profile",
        help=(
            "Backend profile id to validate. Resolves against the JSON corpus under "
            "--profiles-root (defaults to contracts/profiles/backend). Known runtime "
            f"surfaces: {_KNOWN_PROFILE_HINT}. Other ids load as long as their JSON "
            "exists in the corpus, so adding a new published profile does not require "
            "a Python-side enum edit."
        ),
    ),
    fixtures_root: Path | None = typer.Option(
        None,
        "--fixtures-root",
        help="Override the fixtures tree (defaults to contracts/fixtures).",
    ),
    profiles_root: Path | None = typer.Option(
        None,
        "--profiles-root",
        help="Override the backend profile tree (defaults to contracts/profiles/backend).",
    ),
) -> None:
    """Run the published backend conformance fixture suite for ``profile``.

    Reads the profile-to-contract requirements from
    ``contracts/profiles/backend/<profile>.json`` and the fixture corpus
    from ``contracts/fixtures/`` (or the supplied overrides). Exits non-zero
    when any case or top-level diagnostic fails so CI gates can wire it in.
    A missing/malformed/mislabeled profile JSON surfaces as a structured
    ``conformance.profile-load-failed`` diagnostic in the report. A fixture
    file that cannot be read fails the command with exit status 1 and no report.
    """

    try:
        report = run_fixture_suite(profile=profile, root=fixtures_root, profiles_root=profiles_root)
    except OperationalError as exc:
        # The line names the failure kind only; host paths and OS error text stay out of the output.
        typer.echo("error: the conformance fixture corpus could not be read", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(json.dumps(_report_payload(report), indent=2))
    if not report.passed:
        raise typer.Exit(code=1)
