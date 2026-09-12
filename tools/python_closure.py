#!/usr/bin/env python3
"""Execute reviewed Python tool, build, and installed-smoke closure profiles."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import subprocess
import sys
import tempfile
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

REPO_ROOT = Path(__file__).resolve().parents[1]
PROFILES_PATH = "implementations/tooling/profiles/development-profiles.json"
TOOL_PROJECT = REPO_ROOT / "implementations" / "tooling" / "python"
_MAX_MANIFEST_BYTES = 2 * 1024 * 1024
_ALLOWED_TOOLS = frozenset(
    {
        "check-added-large-files",
        "check-json",
        "check-merge-conflict",
        "check-yaml",
        "check-jsonschema",
        "detect-private-key",
        "end-of-file-fixer",
        "nox",
        "pre-commit",
        "python",
        "ruff",
        "trailing-whitespace-fixer",
    }
)


@dataclass(frozen=True)
class PythonClosureProfile:
    profile_id: str
    host_profile_id: str
    python_version: str
    abi: str
    platform: str
    purposes: tuple[str, ...]
    project_extras: tuple[str, ...]
    tool_groups: tuple[str, ...]
    acquisition_context_ids: tuple[str, ...]
    project_lock: Path
    tool_lock: Path
    build_constraints: Path
    smoke_requirements: Path
    wheelhouse_manifest: Path
    test_case_ids: tuple[str, ...]
    contexts: Mapping[str, Mapping[str, Any]]


def _repo_file(repo_root: Path, relative_path: object) -> Path:
    if not isinstance(relative_path, str):
        raise ValueError("Python closure authority path must be a string")
    root = repo_root.resolve()
    path = root / relative_path
    try:
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise ValueError("Python closure authority is missing") from exc
    if not resolved.is_relative_to(root):
        raise ValueError("Python closure authority must stay inside the repository")
    try:
        mode = path.lstat().st_mode
    except OSError as exc:
        raise ValueError("Python closure authority is missing") from exc
    if not stat.S_ISREG(mode) or path.is_symlink():
        raise ValueError("Python closure authority must be a regular file")
    return resolved


def _load_bounded_json_object(repo_root: Path, relative_path: object) -> dict[str, Any]:
    path = _repo_file(repo_root, relative_path)
    try:
        if path.stat().st_size > _MAX_MANIFEST_BYTES:
            raise ValueError("Python closure authority exceeds the size limit")
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("Python closure authority is not valid JSON") from exc
    if not isinstance(value, dict):
        raise ValueError("Python closure authority must be a JSON object")
    return value


def _anchor_path(path: Path) -> Path:
    """Bind a caller path to its original working directory before cwd changes."""

    return path if path.is_absolute() else Path.cwd() / path


def load_python_closure_profile(repo_root: Path, profile_id: str) -> PythonClosureProfile:
    """Load one exact closed profile after the canonical static policy passes."""

    from tools.check_tooling_artifact_policy import (
        _tracked_paths,
        evaluate_tooling_artifact_policy,
    )

    tracked_paths = _tracked_paths(repo_root)
    module_path = "tools/python_closure.py"
    if module_path not in tracked_paths and (repo_root / module_path).is_file():
        tracked_paths.append(module_path)
    failures = evaluate_tooling_artifact_policy(repo_root, tracked_paths=tracked_paths)
    if failures:
        rendered = "\n".join(item.render() for item in failures[:20])
        raise ValueError(f"development artifact policy is invalid:\n{rendered}")
    document = _load_bounded_json_object(repo_root, PROFILES_PATH)
    matches = [
        value
        for value in document.get("python_closure_profiles", [])
        if isinstance(value, Mapping) and value.get("python_closure_profile_id") == profile_id
    ]
    if len(matches) != 1:
        raise ValueError("Python closure profile must resolve to exactly one reviewed entry")
    value = matches[0]
    python = value["python"]
    contexts = {
        str(context["context_id"]): context
        for context in document.get("python_package_contexts", [])
        if isinstance(context, Mapping) and isinstance(context.get("context_id"), str)
    }
    return PythonClosureProfile(
        profile_id=profile_id,
        host_profile_id=str(value["host_profile_id"]),
        python_version=str(python["version"]),
        abi=str(python["abi"]),
        platform=str(python["platform"]),
        purposes=tuple(value["purposes"]),
        project_extras=tuple(value["project_extras"]),
        tool_groups=tuple(value["tool_groups"]),
        acquisition_context_ids=tuple(value["acquisition_context_ids"]),
        project_lock=_repo_file(repo_root, value["project_lock"]),
        tool_lock=_repo_file(repo_root, value["tool_lock"]),
        build_constraints=_repo_file(repo_root, value["build_constraints"]),
        smoke_requirements=_repo_file(repo_root, value["smoke_requirements"]),
        wheelhouse_manifest=_repo_file(repo_root, value["wheelhouse_manifest"]),
        test_case_ids=tuple(value["test_case_ids"]),
        contexts=contexts,
    )


def load_wheelhouse_manifest(profile: PythonClosureProfile) -> dict[str, Any]:
    return _load_bounded_json_object(
        profile.wheelhouse_manifest.parent,
        profile.wheelhouse_manifest.name,
    )


def verify_bootstrap_wheelhouse(
    repo_root: Path,
    profile_id: str,
    wheelhouse: Path,
    manifest_snapshot: Path,
) -> None:
    """Verify a raw kit before installing the full frozen policy environment."""

    wheelhouse = _anchor_path(wheelhouse)
    manifest_snapshot = _anchor_path(manifest_snapshot)
    profiles_path = _repo_file(repo_root, PROFILES_PATH)
    profiles = json.loads(profiles_path.read_text(encoding="utf-8"))
    matches = [
        value
        for value in profiles.get("python_closure_profiles", [])
        if isinstance(value, Mapping) and value.get("python_closure_profile_id") == profile_id
    ]
    if len(matches) != 1:
        raise ValueError("bootstrap Python closure profile must resolve exactly once")
    authority = _repo_file(repo_root, matches[0].get("wheelhouse_manifest"))
    if manifest_snapshot.is_symlink() or not manifest_snapshot.is_file():
        raise ValueError("wheelhouse manifest snapshot must be a regular file")
    snapshot = manifest_snapshot.read_bytes()
    if snapshot != authority.read_bytes():
        raise ValueError("wheelhouse manifest snapshot does not match the reviewed authority")
    manifest = json.loads(snapshot)
    lock_path = _repo_file(repo_root, manifest.get("lock_path"))
    requirements_path = _repo_file(repo_root, matches[0].get("smoke_requirements"))
    if manifest.get("python_closure_profile_id") != profile_id:
        raise ValueError("wheelhouse manifest profile identity is wrong")
    if manifest.get("lock_sha256") != hashlib.sha256(lock_path.read_bytes()).hexdigest():
        raise ValueError("wheelhouse manifest lock identity is stale")
    if manifest.get("requirements_sha256") != hashlib.sha256(requirements_path.read_bytes()).hexdigest():
        raise ValueError("wheelhouse manifest requirements identity is stale")
    verify_wheelhouse(wheelhouse, manifest)


def verify_wheelhouse(wheelhouse: Path, manifest: Mapping[str, Any]) -> None:
    """Reject a wheelhouse unless its regular files exactly match the manifest."""

    try:
        mode = wheelhouse.lstat().st_mode
    except OSError as exc:
        raise ValueError("wheelhouse is missing") from exc
    if not stat.S_ISDIR(mode) or wheelhouse.is_symlink():
        raise ValueError("wheelhouse must be a regular directory")
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        raise ValueError("wheelhouse manifest has no artifacts")
    expected: dict[str, Mapping[str, Any]] = {}
    for artifact in artifacts:
        if not isinstance(artifact, Mapping):
            raise ValueError("wheelhouse manifest artifact is invalid")
        filename = artifact.get("filename")
        if not isinstance(filename, str) or not filename or Path(filename).name != filename or filename in expected:
            raise ValueError("wheelhouse manifest filenames must be unique portable basenames")
        expected[filename] = artifact
    observed = {path.name: path for path in wheelhouse.iterdir()}
    missing = sorted(set(expected) - set(observed))
    unexpected = sorted(set(observed) - set(expected))
    if missing:
        raise ValueError(f"wheelhouse is missing {len(missing)} reviewed artifacts")
    if unexpected:
        raise ValueError(f"wheelhouse contains {len(unexpected)} unexpected artifacts")
    for filename, artifact in expected.items():
        path = observed[filename]
        mode = path.lstat().st_mode
        if path.is_symlink() or not stat.S_ISREG(mode):
            raise ValueError("wheelhouse entries must be regular files")
        if path.stat().st_size != artifact.get("size"):
            raise ValueError(f"wheelhouse artifact size mismatch: {filename}")
        if _sha256_file(path) != artifact.get("sha256"):
            raise ValueError(f"wheelhouse artifact digest mismatch: {filename}")


def closure_environment(
    profile: PythonClosureProfile,
    *,
    context_id: str,
    home: Path,
    cache_dir: Path,
    source: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Construct the profile-owned minimal environment for a uv invocation."""

    if context_id not in profile.acquisition_context_ids or context_id not in profile.contexts:
        raise ValueError("acquisition context is not admitted by the Python closure profile")
    context = profile.contexts[context_id]
    source = os.environ if source is None else source
    environment = {
        "HOME": str(home),
        "PATH": source.get("PATH", os.defpath),
        "UV_CACHE_DIR": str(cache_dir),
        "UV_KEYRING_PROVIDER": "disabled",
        "UV_PYTHON_DOWNLOADS": "never",
    }
    mode = context.get("mode")
    if mode == "offline":
        environment["UV_OFFLINE"] = "1"
    elif mode == "public":
        environment["UV_DEFAULT_INDEX"] = "https://pypi.org/simple"
        environment["UV_INDEX_STRATEGY"] = "first-index"
    elif mode == "mirror-only":
        mirror_url = source.get("RAES_PYTHON_MIRROR_URL", "")
        parsed = urlsplit(mirror_url)
        if (
            parsed.scheme != "https"
            or not parsed.netloc
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("mirror-only context requires a credential-free HTTPS mirror locator")
        environment["UV_DEFAULT_INDEX"] = mirror_url
        environment["UV_INDEX_STRATEGY"] = "first-index"
    else:
        raise ValueError("unsupported Python acquisition context")
    return environment


def frozen_tool_command(repo_root: Path, tool: str, *args: str) -> list[str]:
    if tool not in _ALLOWED_TOOLS:
        raise ValueError("tool is not present in the reviewed Python tool closure")
    return [
        "uv",
        "run",
        "--project",
        str(repo_root / "implementations" / "tooling" / "python"),
        "--frozen",
        "--no-default-groups",
        tool,
        *args,
    ]


def _run(command: Sequence[str], *, cwd: Path, environment: Mapping[str, str]) -> None:
    try:
        completed = subprocess.run(
            list(command),
            cwd=cwd,
            env=dict(environment),
            text=True,
            capture_output=True,
            timeout=900,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError("Python closure client could not execute") from exc
    if completed.returncode:
        diagnostic = (completed.stderr or completed.stdout).lower()
        if "hash" in diagnostic or "digest" in diagnostic:
            category = "artifact integrity"
        elif "auth" in diagnostic or "credential" in diagnostic or "unauthorized" in diagnostic:
            category = "authentication"
        elif "offline" in diagnostic or "not found" in diagnostic or "no matching" in diagnostic:
            category = "artifact availability"
        else:
            category = "client execution"
        raise RuntimeError(f"Python closure {category} failure (client exit code {completed.returncode})")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _candidate_digest(path: Path) -> str:
    if path.is_symlink() or not path.is_file():
        raise ValueError("candidate distribution must be a regular file")
    return _sha256_file(path)


def _assert_runtime_matches_profile(profile: PythonClosureProfile) -> None:
    selected = f"{sys.version_info.major}.{sys.version_info.minor}"
    if sys.implementation.name != "cpython" or selected != profile.python_version:
        raise ValueError("executing Python runtime does not match the reviewed closure profile")


def _build(profile: PythonClosureProfile, source: Path, out_dir: Path, *, context_id: str) -> None:
    _assert_runtime_matches_profile(profile)
    repo_root = profile.project_lock.parents[2].resolve()
    source = _anchor_path(source)
    out_dir = _anchor_path(out_dir)
    resolved_source = source.resolve(strict=True)
    resolved_out_dir = out_dir.resolve(strict=False)
    project_source = repo_root / "implementations" / "python"
    if resolved_source != project_source.resolve():
        raise ValueError("candidate build source must be the reviewed Python project")
    if resolved_out_dir.is_relative_to(repo_root):
        raise ValueError("candidate build output must be outside the checkout")
    if out_dir.is_symlink() or out_dir.exists() and any(out_dir.iterdir()):
        raise ValueError("candidate build output must be an empty non-symlink directory")
    out_dir = resolved_out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="raes-python-build-") as temporary:
        root = Path(temporary)
        environment = closure_environment(
            profile,
            context_id=context_id,
            home=root / "home",
            cache_dir=root / "cache",
        )
        base = [
            "uv",
            "build",
            "--python",
            sys.executable,
            "--build-constraints",
            str(profile.build_constraints),
            "--require-hashes",
        ]
        _run(
            [*base, "--wheel", "--out-dir", str(out_dir), str(resolved_source)],
            cwd=root,
            environment=environment,
        )
        _run(
            [*base, "--sdist", "--out-dir", str(out_dir), str(resolved_source)],
            cwd=root,
            environment=environment,
        )
        sdists = sorted(out_dir.glob("raes-*.tar.gz"))
        if len(sdists) != 1:
            raise RuntimeError("constrained build did not produce exactly one source distribution")
        _run(
            [
                *base,
                "--wheel",
                "--out-dir",
                str(out_dir / "from-sdist"),
                str(sdists[0]),
            ],
            cwd=root,
            environment=environment,
        )


def _smoke(
    profile: PythonClosureProfile,
    candidate: Path,
    environment_dir: Path,
    *,
    wheelhouse: Path | None,
    offline: bool,
) -> None:
    _assert_runtime_matches_profile(profile)
    repo_root = profile.project_lock.parents[2].resolve()
    candidate = _anchor_path(candidate)
    environment_dir = _anchor_path(environment_dir)
    wheelhouse = _anchor_path(wheelhouse) if wheelhouse is not None else None
    _candidate_digest(candidate)
    candidate = candidate.resolve(strict=True)
    resolved_environment = environment_dir.resolve(strict=False)
    if candidate.is_relative_to(repo_root):
        raise ValueError("smoke candidate must be outside the checkout")
    if resolved_environment.is_relative_to(repo_root):
        raise ValueError("smoke environment must be outside the checkout")
    if environment_dir.is_symlink() or environment_dir.exists() and any(environment_dir.iterdir()):
        raise ValueError("smoke environment must be empty and must not be a symlink")
    environment_dir = resolved_environment
    context_id = "python-offline" if offline else "python-public"
    manifest = load_wheelhouse_manifest(profile)
    if offline:
        if wheelhouse is None:
            raise ValueError("offline smoke requires a verified wheelhouse")
        verify_wheelhouse(wheelhouse, manifest)
        wheelhouse = wheelhouse.resolve(strict=True)
    with tempfile.TemporaryDirectory(prefix="raes-python-smoke-") as temporary:
        root = Path(temporary)
        environment = closure_environment(
            profile,
            context_id=context_id,
            home=root / "home",
            cache_dir=root / "cache",
        )
        _run(
            [
                "uv",
                "venv",
                "--no-project",
                "--python",
                sys.executable,
                str(environment_dir),
            ],
            cwd=root,
            environment=environment,
        )
        scripts = environment_dir / ("Scripts" if os.name == "nt" else "bin")
        python = scripts / ("python.exe" if os.name == "nt" else "python")
        install = [
            "uv",
            "pip",
            "install",
            "--python",
            str(python),
            "--requirements",
            str(profile.smoke_requirements),
            "--require-hashes",
            "--only-binary",
            ":all:",
        ]
        if offline and wheelhouse is not None:
            install.extend(["--offline", "--no-index", "--find-links", str(wheelhouse)])
        _run(install, cwd=root, environment=environment)
        _run(
            [
                "uv",
                "pip",
                "install",
                "--python",
                str(python),
                "--no-deps",
                str(candidate),
            ],
            cwd=root,
            environment=environment,
        )


def _materialize(profile: PythonClosureProfile, wheelhouse: Path) -> None:
    """Materialize exact exported wheels without granting resolver authority."""

    from tools.generate_python_closures import _platform_tags

    wheelhouse = _anchor_path(wheelhouse)
    resolved_wheelhouse = wheelhouse.resolve(strict=False)
    if wheelhouse.is_symlink() or wheelhouse.exists() and any(wheelhouse.iterdir()):
        raise ValueError("wheelhouse destination must be empty and must not be a symlink")
    wheelhouse = resolved_wheelhouse
    wheelhouse.mkdir(parents=True, exist_ok=True)
    command = [
        sys.executable,
        "-m",
        "pip",
        "download",
        "--disable-pip-version-check",
        "--no-deps",
        "--only-binary",
        ":all:",
        "--require-hashes",
        "--requirement",
        str(profile.smoke_requirements),
        "--dest",
        str(wheelhouse),
        "--python-version",
        profile.python_version.replace(".", ""),
        "--implementation",
        "cp",
        "--abi",
        profile.abi,
    ]
    for platform_tag in _platform_tags(profile.platform):
        command.extend(["--platform", platform_tag])
    with tempfile.TemporaryDirectory(prefix="raes-python-materialize-") as temporary:
        root = Path(temporary)
        environment = closure_environment(
            profile,
            context_id="python-public",
            home=root / "home",
            cache_dir=root / "cache",
        )
        environment.update(
            {
                "PIP_CONFIG_FILE": os.devnull,
                "PIP_DISABLE_PIP_VERSION_CHECK": "1",
                "PIP_INDEX_URL": "https://pypi.org/simple",
                "PIP_NO_CACHE_DIR": "1",
                "PIP_NO_INPUT": "1",
            }
        )
        _run(command, cwd=root, environment=environment)
    verify_wheelhouse(wheelhouse, load_wheelhouse_manifest(profile))


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="operation", required=True)
    for operation in (
        "bootstrap-wheelhouse-verify",
        "build",
        "manifest-show",
        "materialize",
        "smoke",
        "wheelhouse-verify",
    ):
        child = subparsers.add_parser(operation)
        child.add_argument("--profile", required=True)
        if operation == "build":
            child.add_argument("--source", type=Path, default=REPO_ROOT / "implementations" / "python")
            child.add_argument("--out-dir", type=Path, required=True)
            child.add_argument("--context", default="python-public")
        elif operation == "smoke":
            child.add_argument("--candidate", type=Path, required=True)
            child.add_argument("--environment", type=Path, required=True)
            child.add_argument("--wheelhouse", type=Path)
            child.add_argument("--offline", action="store_true")
        elif operation in {"materialize", "wheelhouse-verify"}:
            child.add_argument("--wheelhouse", type=Path, required=True)
        elif operation == "bootstrap-wheelhouse-verify":
            child.add_argument("--wheelhouse", type=Path, required=True)
            child.add_argument("--manifest-snapshot", type=Path, required=True)
    return parser.parse_args(list(argv) if argv is not None else None)


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)
    if args.operation == "bootstrap-wheelhouse-verify":
        verify_bootstrap_wheelhouse(REPO_ROOT, args.profile, args.wheelhouse, args.manifest_snapshot)
        return 0
    profile = load_python_closure_profile(REPO_ROOT, args.profile)
    if args.operation == "build":
        _build(profile, args.source, args.out_dir, context_id=args.context)
    elif args.operation == "smoke":
        _smoke(
            profile,
            args.candidate,
            args.environment,
            wheelhouse=args.wheelhouse,
            offline=args.offline,
        )
    elif args.operation == "materialize":
        _materialize(profile, args.wheelhouse)
    elif args.operation == "manifest-show":
        sys.stdout.buffer.write(profile.wheelhouse_manifest.read_bytes())
    else:
        verify_wheelhouse(args.wheelhouse, load_wheelhouse_manifest(profile))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
