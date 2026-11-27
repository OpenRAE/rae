"""Integrate the released documentation package with existing verified tools."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

from tools import verified_tool_installation as installation
from tools.maintained_client_acquisition import acquire_locked_bytes
from tools.tool_versions import DOC_TOOLS_VERSION, STE_VERSION
from tools.tooling_policy_gate import (
    ArtifactPolicyError,
    host_platform_id,
    load_tooling_artifact_selection,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


def _ensure_dependency(repo_root: Path, artifact_id: str, version: str, local_input: Path | None) -> Path:
    platform_id = host_platform_id()
    selection = load_tooling_artifact_selection(
        artifact_id=artifact_id,
        version=version,
        platform_id=platform_id,
        profile_id=f"public-{platform_id}",
    )
    if len(selection.source_urls) != 1 or len(selection.raw_manifest) != 1:
        raise ArtifactPolicyError("Documentation dependency selection must contain one source and raw asset")
    return installation.ensure_verified_installation(
        repo_root,
        selection,
        acquire=lambda: acquire_locked_bytes(
            artifact_id=artifact_id,
            source_url=selection.source_urls[0],
            expected=selection.raw_manifest[0],
            local_input=local_input,
        ),
        materialize=installation.materialize_tar_gz,
    )


def ensure_doc_tools(repo_root: Path = REPO_ROOT, *, local_input: Path | None = None) -> Path:
    """Return the admitted package directory, including unchanged skill and notices."""
    wrapper = _ensure_dependency(repo_root, "doc-tools", DOC_TOOLS_VERSION, local_input)
    return wrapper.parent.parent


def ensure_ste(repo_root: Path = REPO_ROOT, *, local_input: Path | None = None) -> Path:
    """Return ste-cli after checking its complete installed identity."""
    return _ensure_dependency(repo_root, "ste-cli", STE_VERSION, local_input)


def sync_doc_tools_styles(repo_root: Path, vale: Path, package: Path) -> None:
    """Install the verified shared rules through Vale's local package interface."""
    with tempfile.TemporaryDirectory(prefix="raes-vale-package-") as directory:
        # Vale keeps source modes. Stage writable copies so a later sync can replace them.
        style = Path(directory) / "DocTools"
        style.mkdir()
        for rule in (package / "vale/DocTools").glob("*.yml"):
            shutil.copyfile(rule, style / rule.name)
        config = Path(directory) / ".vale.ini"
        config.write_text(f"StylesPath = {repo_root / 'styles'}\nPackages = {style}\n")
        try:
            subprocess.run(
                [str(vale), "--no-global", f"--config={config}", "sync"],
                cwd=repo_root,
                stdin=subprocess.DEVNULL,
                capture_output=True,
                check=True,
                timeout=180,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise installation.ToolInstallationError("tool-installation: documentation-style-sync-failed") from exc
