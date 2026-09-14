from __future__ import annotations

import subprocess
from enum import StrEnum
from pathlib import Path

from tools import verified_tool_installation as installation
from tools.maintained_client_acquisition import acquire_locked_bytes
from tools.tool_versions import OSV_SCANNER_VERSION

REPO_ROOT = Path(__file__).resolve().parents[1]

# Exit codes osv-scanner uses for scan results. Any other code (for example,
# 127 for a general error or 128 when no packages were found) is a scanner or
# setup failure, not a vulnerability result.
# See https://google.github.io/osv-scanner/output/#return-codes
OSV_CLEAN_EXIT_CODE = 0
OSV_FINDINGS_EXIT_CODE = 1


class OSVScanOutcome(StrEnum):
    CLEAN = "clean"
    FINDINGS = "findings"
    SCANNER_ERROR = "scanner-error"


def classify_osv_exit_code(exit_code: int) -> OSVScanOutcome:
    """Classify a scanner result without conflating findings with tool errors."""
    if exit_code == OSV_CLEAN_EXIT_CODE:
        return OSVScanOutcome.CLEAN
    if exit_code == OSV_FINDINGS_EXIT_CODE:
        return OSVScanOutcome.FINDINGS
    return OSVScanOutcome.SCANNER_ERROR


def osv_scanner_binary_path(repo_root: Path = REPO_ROOT, *, version: str = OSV_SCANNER_VERSION) -> Path:
    return repo_root / ".cache" / "raes-sdl" / "tooling" / "osv-scanner" / version / "osv-scanner"


def ensure_osv_scanner(
    repo_root: Path = REPO_ROOT,
    *,
    version: str = OSV_SCANNER_VERSION,
    local_input: Path | None = None,
    installation_root: Path | None = None,
    immutable_seed_root: Path | None = None,
) -> Path:
    from tools.tooling_policy_gate import (
        host_platform_id,
        load_tooling_artifact_selection,
    )

    platform_id = host_platform_id()
    selection = load_tooling_artifact_selection(
        artifact_id="osv-scanner",
        version=version,
        platform_id=platform_id,
        profile_id=f"public-{platform_id}",
    )
    if len(selection.source_urls) != 1 or len(selection.raw_manifest) != 1 or len(selection.installed_manifest) != 1:
        raise RuntimeError("osv-scanner lock selection must contain one source, raw asset, and installed binary")
    raw = selection.raw_manifest[0]
    return installation.ensure_verified_installation(
        repo_root,
        selection,
        acquire=lambda: acquire_locked_bytes(
            artifact_id="osv-scanner",
            source_url=selection.source_urls[0],
            expected=raw,
            local_input=local_input,
        ),
        materialize=installation.materialize_direct,
        legacy_path=osv_scanner_binary_path(repo_root, version=version),
        installation_root=installation_root,
        immutable_seed_root=immutable_seed_root,
    )


def run_osv_scanner(lockfile: Path, report_path: Path, *, binary: Path) -> int:
    """Scan a single lockfile and write the JSON report, returning the exit code.

    OSV-Scanner writes the machine-readable report to stdout under
    ``--format json`` and progress/logging to stderr, so redirecting stdout to
    ``report_path`` captures a clean JSON document. The caller classifies the
    result with :func:`classify_osv_exit_code` and applies repository policy.
    """
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with report_path.open("wb") as report_file:
        completed = subprocess.run(  # noqa: S603  # trusted, checksum-verified binary; fixed argv
            [
                str(binary),
                "scan",
                "source",
                "--lockfile",
                str(lockfile),
                "--format",
                "json",
            ],
            stdout=report_file,
            check=False,
        )
    return completed.returncode
