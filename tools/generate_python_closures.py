#!/usr/bin/env python3
"""Generate target-specific, hash-complete smoke closures from the project lock."""

from __future__ import annotations

import argparse
import hashlib
import json
import tomllib
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from packaging.tags import Tag, compatible_tags, cpython_tags, mac_platforms
from packaging.utils import InvalidWheelFilename, parse_wheel_filename

from tools.generate_python_closures_locks import lock_mappings, locked_closure, target_environment

REPO_ROOT = Path(__file__).resolve().parents[1]
_SHA256_PREFIX = "sha256:"
_BUILD_CONSTRAINT_PYTHON_VERSIONS = ("3.11", "3.12", "3.13", "3.14")
_TOOL_ROOT_NAME = "raes-development-tools"
TARGETS = (
    (
        "public-linux-x86_64-cp311-all-extras",
        "3.11",
        "cp311",
        "x86_64-unknown-linux-gnu",
    ),
    (
        "public-linux-x86_64-cp312-all-extras",
        "3.12",
        "cp312",
        "x86_64-unknown-linux-gnu",
    ),
    (
        "public-linux-x86_64-cp313-all-extras",
        "3.13",
        "cp313",
        "x86_64-unknown-linux-gnu",
    ),
    (
        "public-linux-x86_64-cp314-all-extras",
        "3.14",
        "cp314",
        "x86_64-unknown-linux-gnu",
    ),
    (
        "public-linux-arm64-cp314-all-extras",
        "3.14",
        "cp314",
        "aarch64-unknown-linux-gnu",
    ),
    ("public-macos-arm64-cp314-all-extras", "3.14", "cp314", "aarch64-apple-darwin"),
)
TOOL_TARGETS = (
    ("public-linux-x86_64-cp314-tools", "3.14", "cp314", "x86_64-unknown-linux-gnu"),
    ("public-linux-arm64-cp314-tools", "3.14", "cp314", "aarch64-unknown-linux-gnu"),
    ("public-macos-x86_64-cp314-tools", "3.14", "cp314", "x86_64-apple-darwin"),
    ("public-macos-arm64-cp314-tools", "3.14", "cp314", "aarch64-apple-darwin"),
)


def _build_group_dependencies(lock: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    """Resolve the reviewed build dependency group declared by the tool lock."""

    root = next(
        (
            package
            for package in lock.get("package", [])
            if isinstance(package, Mapping) and package.get("name") == _TOOL_ROOT_NAME
        ),
        None,
    )
    if root is None:
        raise ValueError("tool lock has no project root")
    dependencies = lock_mappings(root.get("dev-dependencies", {}).get("build", []))
    if not dependencies:
        raise ValueError("tool lock has no build dependency group")
    return dependencies


def _build_constraint_packages(lock: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    """Select one exact version per build dependency across every supported runtime."""

    dependencies = _build_group_dependencies(lock)
    selected: dict[str, Mapping[str, Any]] = {}
    for python_version in _BUILD_CONSTRAINT_PYTHON_VERSIONS:
        for package in locked_closure(
            lock,
            target_environment(python_version, "x86_64-unknown-linux-gnu"),
            root_name=_TOOL_ROOT_NAME,
            include_root_optional=False,
            initial_dependencies=dependencies,
        ):
            name = str(package["name"])
            if selected.setdefault(name, package).get("version") != package.get("version"):
                raise ValueError(f"build constraint selects multiple versions of {name}")
    return selected


def _sha256_artifact_hashes(package: Mapping[str, Any]) -> list[str]:
    """Collect the SHA-256 artifact identities of one locked package."""

    artifact_values = [package.get("sdist"), *package.get("wheels", [])]
    return sorted(
        {
            str(artifact["hash"])
            for artifact in artifact_values
            if isinstance(artifact, Mapping)
            and isinstance(artifact.get("hash"), str)
            and str(artifact["hash"]).startswith(_SHA256_PREFIX)
        }
    )


def render_build_constraints(lock: Mapping[str, Any]) -> str:
    """Render hash-complete build constraints for the reviewed build group."""

    selected = _build_constraint_packages(lock)
    lines: list[str] = []
    for name in sorted(selected):
        package = selected[name]
        hashes = _sha256_artifact_hashes(package)
        if not hashes:
            raise ValueError(f"build constraint {name} has no SHA-256 artifacts")
        lines.append(f"{name}=={package['version']} \\")
        for index, digest in enumerate(hashes):
            suffix = " \\" if index < len(hashes) - 1 else ""
            lines.append(f"    --hash={digest}{suffix}")
    return "\n".join(lines) + "\n"


def _platform_tags(platform: str) -> list[str]:
    if platform.endswith("apple-darwin"):
        arch = "arm64" if platform.startswith("aarch64") else "x86_64"
        return list(mac_platforms(version=(15, 0), arch=arch))
    arch = "aarch64" if platform.startswith("aarch64") else "x86_64"
    tags = [f"manylinux_2_17_{arch}", f"manylinux2014_{arch}"]
    tags.extend(f"manylinux_2_{minor}_{arch}" for minor in range(18, 40))
    tags.append(f"linux_{arch}")
    return list(dict.fromkeys(tags))


def _supported_tags(python_version: str, abi: str, platform: str) -> tuple[Tag, ...]:
    version = tuple(int(part) for part in python_version.split("."))
    platforms = _platform_tags(platform)
    return tuple(
        dict.fromkeys(
            [
                *cpython_tags(
                    python_version=version,
                    abis=[abi, "abi3", "none"],
                    platforms=platforms,
                ),
                *compatible_tags(python_version=version, interpreter=abi, platforms=platforms),
            ]
        )
    )


def _select_wheel(package: Mapping[str, Any], supported: Sequence[Tag]) -> Mapping[str, Any]:
    wheel_tags: list[tuple[Mapping[str, Any], frozenset[Tag]]] = []
    for wheel in package.get("wheels", []):
        if not isinstance(wheel, Mapping) or not isinstance(wheel.get("url"), str):
            continue
        filename = Path(urlsplit(wheel["url"]).path).name
        try:
            tags = parse_wheel_filename(filename)[3]
        except InvalidWheelFilename:
            continue
        wheel_tags.append((wheel, tags))
    for tag in supported:
        for wheel, tags in wheel_tags:
            if tag in tags:
                return wheel
    raise ValueError(f"{package.get('name')}=={package.get('version')} has no wheel for the selected target")


def _artifact(package: Mapping[str, Any], wheel: Mapping[str, Any]) -> dict[str, object]:
    url = str(wheel["url"])
    digest = str(wheel["hash"])
    if not digest.startswith(_SHA256_PREFIX):
        raise ValueError(f"{package.get('name')} has a non-SHA256 wheel identity")
    return {
        "name": package["name"],
        "version": package["version"],
        "filename": Path(urlsplit(url).path).name,
        "url": url,
        "sha256": digest.removeprefix(_SHA256_PREFIX),
        "size": wheel["size"],
    }


@dataclass(frozen=True)
class _TargetRequest:
    """One reviewed closure target and the lock root it is projected from."""

    lock: Mapping[str, Any]
    lock_path: Path
    profile_id: str
    python_version: str
    abi: str
    platform: str
    root_name: str
    include_root_optional: bool
    root_groups: Sequence[str] = ()
    repo_root: Path = REPO_ROOT


@dataclass(frozen=True)
class _LockDefinition:
    """One lock authority and the reviewed targets projected from it."""

    lock_path: Path
    root_name: str
    include_root_optional: bool
    targets: Sequence[tuple[str, str, str, str]]
    root_groups: Sequence[str] = field(default=())


def render_target(request: _TargetRequest) -> tuple[str, str]:
    """Render the pinned requirements and wheelhouse manifest for one target."""

    environment = target_environment(request.python_version, request.platform)
    supported = _supported_tags(request.python_version, request.abi, request.platform)
    artifacts = [
        _artifact(package, _select_wheel(package, supported))
        for package in locked_closure(
            request.lock,
            environment,
            root_name=request.root_name,
            include_root_optional=request.include_root_optional,
            root_groups=request.root_groups,
        )
    ]
    requirements = "".join(
        f"{artifact['name']}=={artifact['version']} --hash={_SHA256_PREFIX}{artifact['sha256']}\n"
        for artifact in artifacts
    )
    manifest = {
        "schema_version": "raes-python-wheelhouse-manifest/v1",
        "python_closure_profile_id": request.profile_id,
        "lock_path": request.lock_path.relative_to(request.repo_root).as_posix(),
        "lock_sha256": hashlib.sha256(request.lock_path.read_bytes()).hexdigest(),
        "requirements_sha256": hashlib.sha256(requirements.encode()).hexdigest(),
        "artifacts": artifacts,
    }
    return requirements, json.dumps(manifest, indent=2, sort_keys=True) + "\n"


def _write_if_changed(path: Path, content: str, *, check: bool) -> bool:
    """Report whether the content differs, writing it unless this is a check run."""

    if path.exists() and path.read_text(encoding="utf-8") == content:
        return False
    if not check:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    return True


def _projection_stem(definition: _LockDefinition, profile_id: str) -> str:
    """Name the projection files one target writes."""

    stem = profile_id.removeprefix("public-").removesuffix("-all-extras").removesuffix("-tools")
    return f"tools-{stem}" if definition.root_name == _TOOL_ROOT_NAME else stem


def _definition_changes(
    definition: _LockDefinition,
    *,
    output_root: Path,
    repo_root: Path,
    check: bool,
) -> bool:
    """Project every target of one lock authority and report whether any changed."""

    lock = tomllib.loads(definition.lock_path.read_text(encoding="utf-8"))
    changed = False
    for profile_id, python_version, abi, platform in definition.targets:
        requirements, manifest = render_target(
            _TargetRequest(
                lock=lock,
                lock_path=definition.lock_path,
                profile_id=profile_id,
                python_version=python_version,
                abi=abi,
                platform=platform,
                root_name=definition.root_name,
                include_root_optional=definition.include_root_optional,
                root_groups=definition.root_groups,
                repo_root=repo_root,
            )
        )
        stem = _projection_stem(definition, profile_id)
        for path, content in (
            (output_root / f"{stem}.txt", requirements),
            (output_root / f"{stem}.wheelhouse-manifest.json", manifest),
        ):
            changed = _write_if_changed(path, content, check=check) or changed
    return changed


def generate(*, check: bool, repo_root: Path = REPO_ROOT) -> bool:
    """Project every reviewed closure, reporting whether the tree was already current."""

    tool_root = repo_root / "implementations" / "tooling" / "python"
    tool_lock_path = tool_root / "uv.lock"
    output_root = tool_root / "smoke"
    constraints = render_build_constraints(tomllib.loads(tool_lock_path.read_text(encoding="utf-8")))
    changed = _write_if_changed(tool_root / "build-constraints.txt", constraints, check=check)
    definitions = (
        _LockDefinition(
            lock_path=repo_root / "implementations" / "python" / "uv.lock",
            root_name="raes",
            include_root_optional=True,
            targets=TARGETS,
        ),
        _LockDefinition(
            lock_path=tool_lock_path,
            root_name=_TOOL_ROOT_NAME,
            include_root_optional=False,
            targets=TOOL_TARGETS,
            root_groups=("build",),
        ),
    )
    for definition in definitions:
        changed = _definition_changes(definition, output_root=output_root, repo_root=repo_root, check=check) or changed
    return not changed


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(list(argv) if argv is not None else None)
    current = generate(check=args.check)
    if args.check and not current:
        print("Python closure projections are stale")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
