#!/usr/bin/env python3
"""Execute reviewed Python tool, build, and installed-smoke closure profiles."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path

from tools.python_closure_profiles import (
    REPO_ROOT,
    PythonClosureProfile,
    assert_runtime_matches_profile,
    closure_environment,
    load_python_closure_profile,
    load_wheelhouse_manifest,
)
from tools.python_closure_wheelhouse import (
    candidate_digest,
    operator_path,
    require_empty_destination,
    verify_bootstrap_wheelhouse,
    verify_wheelhouse,
)

_CLIENT_FAILURE_CATEGORIES = (
    ("artifact integrity", ("hash", "digest")),
    ("authentication", ("auth", "credential", "unauthorized")),
    ("artifact availability", ("offline", "not found", "no matching")),
)


def _client_failure_category(diagnostic: str) -> str:
    for category, markers in _CLIENT_FAILURE_CATEGORIES:
        if any(marker in diagnostic for marker in markers):
            return category
    return "client execution"


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
        category = _client_failure_category((completed.stderr or completed.stdout).lower())
        raise RuntimeError(f"Python closure {category} failure (client exit code {completed.returncode})")


def _build(profile: PythonClosureProfile, source: Path, out_dir: Path, *, context_id: str) -> None:
    assert_runtime_matches_profile(profile)
    repo_root = profile.project_lock.parents[2].resolve()
    source = operator_path(source, purpose="candidate build source")
    out_dir = operator_path(out_dir, purpose="candidate build output")
    project_source = repo_root / "implementations" / "python"
    if source != project_source.resolve():
        raise ValueError("candidate build source must be the reviewed Python project")
    if out_dir.is_relative_to(repo_root):
        raise ValueError("candidate build output must be outside the checkout")
    require_empty_destination(out_dir, "candidate build output")
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
            [*base, "--wheel", "--out-dir", str(out_dir), str(source)],
            cwd=root,
            environment=environment,
        )
        _run(
            [*base, "--sdist", "--out-dir", str(out_dir), str(source)],
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


def _admitted_smoke_paths(
    repo_root: Path,
    candidate: Path,
    environment_dir: Path,
    wheelhouse: Path | None,
) -> tuple[Path, Path, Path | None]:
    """Admit every operator-supplied smoke path before any artifact is read."""

    candidate = operator_path(candidate, purpose="smoke candidate")
    environment_dir = operator_path(environment_dir, purpose="smoke environment")
    wheelhouse = None if wheelhouse is None else operator_path(wheelhouse, purpose="smoke wheelhouse")
    if candidate.is_relative_to(repo_root):
        raise ValueError("smoke candidate must be outside the checkout")
    if environment_dir.is_relative_to(repo_root):
        raise ValueError("smoke environment must be outside the checkout")
    candidate_digest(candidate)
    require_empty_destination(environment_dir, "smoke environment")
    return candidate, environment_dir, wheelhouse


def _smoke(
    profile: PythonClosureProfile,
    candidate: Path,
    environment_dir: Path,
    *,
    wheelhouse: Path | None,
    offline: bool,
) -> None:
    assert_runtime_matches_profile(profile)
    repo_root = profile.project_lock.parents[2].resolve()
    candidate, environment_dir, wheelhouse = _admitted_smoke_paths(
        repo_root,
        candidate,
        environment_dir,
        wheelhouse,
    )
    context_id = "python-offline" if offline else "python-public"
    if offline:
        if wheelhouse is None:
            raise ValueError("offline smoke requires a verified wheelhouse")
        verify_wheelhouse(wheelhouse, load_wheelhouse_manifest(profile))
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

    wheelhouse = operator_path(wheelhouse, purpose="wheelhouse destination")
    require_empty_destination(wheelhouse, "wheelhouse destination")
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


def _dispatch(args: argparse.Namespace) -> None:
    if args.operation == "bootstrap-wheelhouse-verify":
        verify_bootstrap_wheelhouse(REPO_ROOT, args.profile, args.wheelhouse, args.manifest_snapshot)
        return
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
        admitted = operator_path(args.wheelhouse, purpose="wheelhouse")
        verify_wheelhouse(admitted, load_wheelhouse_manifest(profile))


def main(argv: Iterable[str] | None = None) -> int:
    _dispatch(parse_args(argv))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
