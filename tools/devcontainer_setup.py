#!/usr/bin/env python3
"""Prepare a development container checkout in one idempotent, fail-closed step.

The dev-container lifecycle runs this once the checkout is mounted, so a
contributor opens the repository and starts work. It composes the reviewed
routes and adds no acquisition of its own: the locked uv and CPython payloads
come from `tools.bootstrap_profile`, the project environments from the frozen
`uv.lock` files, and the generic CLI tools from their verified installers.

The cache volume is disposable and never trusted. Every run re-verifies each
cached archive against the lock, fetches only what is missing or wrong, and
rebuilds the installed clients in a staging directory that atomically replaces
the previous kit, so a tampered or interrupted cache cannot leak into use.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any, TypeVar

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

PYTHON_LINK_NAME = "current"
_TOOLING_PROJECT = "implementations/tooling/python"
_Result = TypeVar("_Result")
_PROJECTS = (
    ("implementations/python", ("--all-extras", "--frozen")),
    (_TOOLING_PROJECT, ("--frozen", "--no-default-groups")),
)
_SUBPROCESS_TIMEOUT_SECONDS = 1800


class DevcontainerSetupError(RuntimeError):
    """A setup step failed; the message is safe to show to the contributor."""


def default_kit_root() -> Path:
    cache_home = os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")
    return Path(cache_home) / "raes-bootstrap"


def container_host_profile_id(repo_root: Path, platform_id: str) -> str:
    """Return the one reviewed container host profile qualified for this platform."""

    from tools.check_tooling_artifact_policy import (
        PROFILES_PATH,
        evaluate_tooling_artifact_policy,
    )
    from tools.policy.common import load_bounded_json_object
    from tools.tooling_artifact_policy_common import (
        MAX_JSON_BYTES,
        normalize_platform_id,
    )

    failures = evaluate_tooling_artifact_policy(repo_root)
    if failures:
        rendered = "\n".join(item.render() for item in failures)
        raise DevcontainerSetupError(f"the development artifact policy is invalid:\n{rendered}")
    profiles = load_bounded_json_object(repo_root, PROFILES_PATH, max_bytes=MAX_JSON_BYTES)
    matches = [
        str(host["host_profile_id"])
        for host in profiles.get("host_profiles", [])
        if isinstance(host, Mapping)
        and isinstance(host.get("base_image_artifact_ref"), str)
        and normalize_platform_id(str(host.get("platform_id", ""))) == normalize_platform_id(platform_id)
    ]
    if len(matches) != 1:
        raise DevcontainerSetupError(f"no reviewed development container profile is qualified for {platform_id}")
    return matches[0]


def _payload_ids(artifacts: Sequence[Mapping[str, Any]]) -> tuple[str, str]:
    """Identify the locked CPython and uv payloads by their installed identity, not by name."""

    by_implementation: dict[str, str] = {}
    for artifact in artifacts:
        identity = artifact.get("platform", {}).get("installed_identity", {})
        if isinstance(identity, Mapping) and identity.get("implementation") in {
            "CPython",
            "uv",
        }:
            by_implementation[str(identity["implementation"])] = str(artifact["artifact_id"])
    if set(by_implementation) != {"CPython", "uv"}:
        raise DevcontainerSetupError("the container host profile must select exactly one CPython and one uv payload")
    return by_implementation["CPython"], by_implementation["uv"]


def _verified_archive(path: Path, raw: Mapping[str, Any]) -> bool:
    if not path.is_file() or path.is_symlink() or path.stat().st_size != raw["size"]:
        return False
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest() == raw["sha256"]


def prepare_kit(host_profile_id: str, kit_root: Path) -> dict[str, str]:
    """Rebuild the verified uv and CPython clients, reusing only archives that still verify."""

    from tools import bootstrap_profile
    from tools.tooling_policy_gate import (
        load_tooling_host_profile_selection_with_current_interpreter,
    )

    selection = load_tooling_host_profile_selection_with_current_interpreter(host_profile_id)
    artifacts = {str(item["artifact_id"]): item for item in selection["artifacts"]}
    python_id, uv_id = _payload_ids(list(artifacts.values()))
    kit_root.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".raes-bootstrap-staging-", dir=kit_root.parent))
    try:
        missing: list[str] = []
        for artifact_id in (python_id, uv_id):
            raw = artifacts[artifact_id]["platform"]["raw_manifest"][0]
            relative = Path("archives") / artifact_id / raw["path"]
            if _verified_archive(kit_root / relative, raw):
                (staging / relative).parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(kit_root / relative, staging / relative)
            else:
                missing.append(artifact_id)
        if missing:
            bootstrap_profile.fetch_offline_kit_payloads(host_profile_id, staging, missing)
        bootstrap_profile.install_offline_uv_payload(host_profile_id, staging, uv_id)
        python = bootstrap_profile.install_offline_python_payload(host_profile_id, staging, python_id)
        (staging / "python" / PYTHON_LINK_NAME).symlink_to(Path(python["path"]).name, target_is_directory=True)
        previous = kit_root.with_name(f".{kit_root.name}-previous")
        shutil.rmtree(previous, ignore_errors=True)
        if kit_root.exists() or kit_root.is_symlink():
            kit_root.rename(previous)
        staging.rename(kit_root)
        shutil.rmtree(previous, ignore_errors=True)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return {
        "host_profile_id": host_profile_id,
        "python": python_id,
        "uv": uv_id,
        "fetched": ",".join(missing),
    }


def _run(argv: Sequence[str], repo_root: Path, environment: Mapping[str, str]) -> None:
    try:
        completed = subprocess.run(  # noqa: S603 - fixed argv built from reviewed constants
            list(argv),
            cwd=repo_root,
            env=dict(environment),
            stdin=subprocess.DEVNULL,
            check=False,
            timeout=_SUBPROCESS_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise DevcontainerSetupError(f"`{' '.join(argv[:3])}` could not run") from exc
    if completed.returncode != 0:
        raise DevcontainerSetupError(f"`{' '.join(argv)}` failed with exit code {completed.returncode}")


def sync_projects(repo_root: Path, kit_root: Path) -> None:
    uv = kit_root / "bin" / "uv"
    environment = {
        **os.environ,
        "UV_PYTHON": str(kit_root / "python" / PYTHON_LINK_NAME / "bin" / "python3"),
        "UV_PYTHON_DOWNLOADS": "never",
    }
    for project, options in _PROJECTS:
        _run([str(uv), "sync", "--project", project, *options], repo_root, environment)


def install_generic_tools(repo_root: Path, kit_root: Path) -> None:
    """Verify generic tools inside the frozen tooling environment that supplies filelock."""

    _run(
        [
            str(kit_root / "bin" / "uv"),
            "run",
            "--project",
            _TOOLING_PROJECT,
            "--frozen",
            "--no-default-groups",
            "python",
            "-m",
            "tools.bootstrap_profile",
            "generic-tools",
        ],
        repo_root,
        {**os.environ, "UV_PYTHON_DOWNLOADS": "never"},
    )


def install_git_hooks(repo_root: Path, kit_root: Path) -> str:
    """Install the repository's pre-commit and pre-push hooks unless the checkout cannot hold them."""

    git_dir = subprocess.run(  # noqa: S603 - fixed argv
        ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
        check=False,
        timeout=60,
    )
    common_dir = Path(git_dir.stdout.strip()) if git_dir.returncode == 0 else None
    if common_dir is None or not common_dir.is_dir():
        return "skipped: the checkout's git directory is not inside the container"
    environment = {**os.environ, "UV_PYTHON_DOWNLOADS": "never"}
    _run(
        [
            str(kit_root / "bin" / "uv"),
            "run",
            "--project",
            _TOOLING_PROJECT,
            "--frozen",
            "--no-default-groups",
            "pre-commit",
            "install",
        ],
        repo_root,
        environment,
    )
    return "installed"


def setup(repo_root: Path = REPO_ROOT, *, kit_root: Path | None = None) -> None:
    from tools.tooling_policy_gate import host_platform_id

    kit_root = kit_root or default_kit_root()
    platform_id = host_platform_id()
    print(f"RAES development container setup ({platform_id})", flush=True)
    host_profile_id = _step(
        "Resolving the reviewed container profile",
        lambda: container_host_profile_id(repo_root, platform_id),
    )
    _step(
        "Verifying locked uv and CPython",
        lambda: prepare_kit(host_profile_id, kit_root),
    )
    _step(
        "Syncing the locked project environments",
        lambda: sync_projects(repo_root, kit_root),
    )
    _step(
        "Verifying locked Conftest, Gitleaks, OSV-Scanner, and Vale",
        lambda: install_generic_tools(repo_root, kit_root),
    )
    hooks = _step("Installing git hooks", lambda: install_git_hooks(repo_root, kit_root))
    print(
        f"Ready. Git hooks: {hooks}. Run `nox -l` to list checks; `nox -s verify-changed` before pushing.",
        flush=True,
    )


def _step(label: str, action: Callable[[], _Result]) -> _Result:
    print(f"==> {label}", flush=True)
    return action()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.parse_args(argv)
    try:
        setup()
    # DevcontainerSetupError is a RuntimeError; policy and installer refusals raise ValueError.
    except (RuntimeError, ValueError) as exc:
        print(f"devcontainer-setup: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
