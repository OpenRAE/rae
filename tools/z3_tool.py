"""Acquire the pinned native processor solver through the existing tool policy."""

from __future__ import annotations

from pathlib import Path

from tools import verified_tool_installation as installation
from tools.maintained_client_acquisition import acquire_locked_bytes

REPO_ROOT = Path(__file__).resolve().parents[1]
Z3_VERSION = "4.16.0"


def ensure_z3(
    repo_root: Path = REPO_ROOT,
    *,
    local_input: Path | None = None,
    installation_root: Path | None = None,
) -> Path:
    """Return the reverified executable from its private installed tree."""
    from tools.tooling_policy_gate import (
        ArtifactPolicyError,
        host_platform_id,
        load_tooling_artifact_selection,
    )

    platform_id = host_platform_id()
    selection = load_tooling_artifact_selection(
        artifact_id="z3-analysis",
        version=Z3_VERSION,
        platform_id=platform_id,
        profile_id=f"public-{platform_id}",
    )
    if len(selection.source_urls) != 1 or len(selection.raw_manifest) != 1:
        raise ArtifactPolicyError("Z3 lock selection must contain one source and raw asset")
    return installation.ensure_verified_installation(
        repo_root,
        selection,
        acquire=lambda: acquire_locked_bytes(
            artifact_id="z3-analysis",
            source_url=selection.source_urls[0],
            expected=selection.raw_manifest[0],
            local_input=local_input,
        ),
        materialize=installation.materialize_zip,
        installation_root=installation_root,
    )
