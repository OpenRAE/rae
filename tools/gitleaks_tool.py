from __future__ import annotations

from pathlib import Path

from tools import verified_tool_installation as installation
from tools.maintained_client_acquisition import acquire_locked_bytes
from tools.tool_versions import GITLEAKS_VERSION

REPO_ROOT = Path(__file__).resolve().parents[1]


def gitleaks_binary_path(repo_root: Path = REPO_ROOT, *, version: str = GITLEAKS_VERSION) -> Path:
    return repo_root / ".cache" / "raes-sdl" / "tooling" / "gitleaks" / version / "gitleaks"


def ensure_gitleaks(
    repo_root: Path = REPO_ROOT,
    *,
    version: str = GITLEAKS_VERSION,
    local_input: Path | None = None,
    installation_root: Path | None = None,
) -> Path:
    from tools.tooling_policy_gate import (
        host_platform_id,
        load_tooling_artifact_selection,
    )

    platform_id = host_platform_id()
    selection = load_tooling_artifact_selection(
        artifact_id="gitleaks",
        version=version,
        platform_id=platform_id,
        profile_id=f"public-{platform_id}",
    )
    if len(selection.source_urls) != 1 or len(selection.raw_manifest) != 1 or len(selection.installed_manifest) != 1:
        raise RuntimeError("gitleaks lock selection must contain one source, raw asset, and installed binary")
    raw = selection.raw_manifest[0]
    return installation.ensure_verified_installation(
        repo_root,
        selection,
        acquire=lambda: acquire_locked_bytes(
            artifact_id="gitleaks",
            source_url=selection.source_urls[0],
            expected=raw,
            local_input=local_input,
        ),
        materialize=installation.materialize_tar_gz,
        legacy_path=gitleaks_binary_path(repo_root, version=version),
        installation_root=installation_root,
    )
