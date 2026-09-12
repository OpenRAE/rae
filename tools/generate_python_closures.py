#!/usr/bin/env python3
"""Generate target-specific, hash-complete smoke closures from the project lock."""

from __future__ import annotations

import argparse
import hashlib
import json
import tomllib
from collections import defaultdict, deque
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from packaging.markers import Marker, default_environment
from packaging.tags import Tag, compatible_tags, cpython_tags, mac_platforms
from packaging.utils import InvalidWheelFilename, parse_wheel_filename

REPO_ROOT = Path(__file__).resolve().parents[1]
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


def _environment(python_version: str, platform: str) -> dict[str, str]:
    environment = default_environment()
    major, minor = python_version.split(".")
    machine = "aarch64" if platform.startswith("aarch64") else "x86_64"
    environment.update(
        {
            "implementation_name": "cpython",
            "platform_machine": machine,
            "platform_python_implementation": "CPython",
            "python_full_version": f"{major}.{minor}.0",
            "python_version": python_version,
            "sys_platform": "darwin" if platform.endswith("apple-darwin") else "linux",
        }
    )
    return environment


def _matches(marker: object, environment: Mapping[str, str]) -> bool:
    return not marker or isinstance(marker, str) and Marker(marker).evaluate(environment=dict(environment))


def _package_applies(package: Mapping[str, Any], environment: Mapping[str, str]) -> bool:
    markers = package.get("resolution-markers")
    return not markers or isinstance(markers, list) and any(_matches(marker, environment) for marker in markers)


def _selected_package(
    packages: Mapping[str, Sequence[Mapping[str, Any]]],
    dependency: Mapping[str, Any],
    environment: Mapping[str, str],
) -> Mapping[str, Any]:
    candidates = [
        package
        for package in packages.get(str(dependency.get("name")), ())
        if _package_applies(package, environment)
        and (not dependency.get("version") or package.get("version") == dependency.get("version"))
    ]
    if len(candidates) != 1:
        raise ValueError(f"dependency {dependency.get('name')!r} did not select exactly one locked package")
    return candidates[0]


def _locked_closure(
    lock: Mapping[str, Any],
    environment: Mapping[str, str],
    *,
    root_name: str,
    include_root_optional: bool,
    root_groups: Sequence[str] = (),
    initial_dependencies: Sequence[Mapping[str, Any]] | None = None,
) -> list[Mapping[str, Any]]:
    packages: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for package in lock.get("package", []):
        if isinstance(package, Mapping) and isinstance(package.get("name"), str):
            packages[package["name"]].append(package)
    roots = packages.get(root_name, [])
    if len(roots) != 1:
        raise ValueError(f"lock must contain exactly one {root_name} package")

    root = roots[0]
    if initial_dependencies is None:
        root_dependencies = list(root.get("dependencies", []))
        if include_root_optional:
            root_dependencies.extend(item for group in root.get("optional-dependencies", {}).values() for item in group)
        development_groups = root.get("dev-dependencies", {})
        for group in root_groups:
            dependencies = development_groups.get(group, []) if isinstance(development_groups, Mapping) else []
            if not isinstance(dependencies, list):
                raise ValueError(f"tool lock dependency group {group!r} is invalid")
            root_dependencies.extend(dependencies)
    else:
        root_dependencies = list(initial_dependencies)
    pending: deque[Mapping[str, Any]] = deque(
        dependency for dependency in root_dependencies if isinstance(dependency, Mapping)
    )
    selected: dict[str, Mapping[str, Any]] = {}
    processed_dependencies: set[str] = set()
    processed_extras: dict[str, set[str]] = defaultdict(set)
    while pending:
        dependency = pending.popleft()
        if not _matches(dependency.get("marker"), environment):
            continue
        package = _selected_package(packages, dependency, environment)
        name = str(package["name"])
        previous = selected.setdefault(name, package)
        if previous is not package and previous.get("version") != package.get("version"):
            raise ValueError(f"target closure selected multiple versions of {name}")
        if name not in processed_dependencies:
            pending.extend(item for item in package.get("dependencies", []) if isinstance(item, Mapping))
            processed_dependencies.add(name)
        requested_extras = {item for item in dependency.get("extra", []) if isinstance(item, str)} - processed_extras[
            name
        ]
        for extra in sorted(requested_extras):
            pending.extend(
                item for item in package.get("optional-dependencies", {}).get(extra, []) if isinstance(item, Mapping)
            )
        processed_extras[name].update(requested_extras)
    return [selected[name] for name in sorted(selected)]


def render_build_constraints(lock: Mapping[str, Any]) -> str:
    root = next(
        (
            package
            for package in lock.get("package", [])
            if isinstance(package, Mapping) and package.get("name") == "raes-development-tools"
        ),
        None,
    )
    if root is None:
        raise ValueError("tool lock has no project root")
    build_dependencies = root.get("dev-dependencies", {}).get("build", [])
    if not isinstance(build_dependencies, list) or not build_dependencies:
        raise ValueError("tool lock has no build dependency group")
    selected: dict[str, Mapping[str, Any]] = {}
    for python_version in ("3.11", "3.12", "3.13", "3.14"):
        for package in _locked_closure(
            lock,
            _environment(python_version, "x86_64-unknown-linux-gnu"),
            root_name="raes-development-tools",
            include_root_optional=False,
            initial_dependencies=[dependency for dependency in build_dependencies if isinstance(dependency, Mapping)],
        ):
            name = str(package["name"])
            previous = selected.setdefault(name, package)
            if previous.get("version") != package.get("version"):
                raise ValueError(f"build constraint selects multiple versions of {name}")
    lines: list[str] = []
    for name in sorted(selected):
        package = selected[name]
        artifact_values = [package.get("sdist"), *package.get("wheels", [])]
        hashes = sorted(
            {
                str(artifact["hash"])
                for artifact in artifact_values
                if isinstance(artifact, Mapping)
                and isinstance(artifact.get("hash"), str)
                and str(artifact["hash"]).startswith("sha256:")
            }
        )
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
    if not digest.startswith("sha256:"):
        raise ValueError(f"{package.get('name')} has a non-SHA256 wheel identity")
    return {
        "name": package["name"],
        "version": package["version"],
        "filename": Path(urlsplit(url).path).name,
        "url": url,
        "sha256": digest.removeprefix("sha256:"),
        "size": wheel["size"],
    }


def render_target(
    lock: Mapping[str, Any],
    lock_path: Path,
    profile_id: str,
    python_version: str,
    abi: str,
    platform: str,
    *,
    root_name: str,
    include_root_optional: bool,
    root_groups: Sequence[str] = (),
    repo_root: Path = REPO_ROOT,
) -> tuple[str, str]:
    environment = _environment(python_version, platform)
    supported = _supported_tags(python_version, abi, platform)
    artifacts = [
        _artifact(package, _select_wheel(package, supported))
        for package in _locked_closure(
            lock,
            environment,
            root_name=root_name,
            include_root_optional=include_root_optional,
            root_groups=root_groups,
        )
    ]
    requirements = "".join(
        f"{artifact['name']}=={artifact['version']} --hash=sha256:{artifact['sha256']}\n" for artifact in artifacts
    )
    manifest = {
        "schema_version": "raes-python-wheelhouse-manifest/v1",
        "python_closure_profile_id": profile_id,
        "lock_path": lock_path.relative_to(repo_root).as_posix(),
        "lock_sha256": hashlib.sha256(lock_path.read_bytes()).hexdigest(),
        "requirements_sha256": hashlib.sha256(requirements.encode()).hexdigest(),
        "artifacts": artifacts,
    }
    return requirements, json.dumps(manifest, indent=2, sort_keys=True) + "\n"


def generate(*, check: bool, repo_root: Path = REPO_ROOT) -> bool:
    changed = False
    project_lock = repo_root / "implementations" / "python" / "uv.lock"
    tool_lock = repo_root / "implementations" / "tooling" / "python" / "uv.lock"
    output_root = repo_root / "implementations" / "tooling" / "python" / "smoke"
    tool_lock_document = tomllib.loads(tool_lock.read_text(encoding="utf-8"))
    constraints_path = repo_root / "implementations" / "tooling" / "python" / "build-constraints.txt"
    constraints = render_build_constraints(tool_lock_document)
    if not constraints_path.exists() or constraints_path.read_text(encoding="utf-8") != constraints:
        changed = True
        if not check:
            constraints_path.parent.mkdir(parents=True, exist_ok=True)
            constraints_path.write_text(constraints, encoding="utf-8")
    definitions = (
        (project_lock, "raes", True, (), TARGETS),
        (tool_lock, "raes-development-tools", False, ("build",), TOOL_TARGETS),
    )
    for lock_path, root_name, include_root_optional, root_groups, targets in definitions:
        lock = tomllib.loads(lock_path.read_text(encoding="utf-8"))
        for profile_id, python_version, abi, platform in targets:
            stem = profile_id.removeprefix("public-").removesuffix("-all-extras").removesuffix("-tools")
            if root_name == "raes-development-tools":
                stem = f"tools-{stem}"
            requirements, manifest = render_target(
                lock,
                lock_path,
                profile_id,
                python_version,
                abi,
                platform,
                root_name=root_name,
                include_root_optional=include_root_optional,
                root_groups=root_groups,
                repo_root=repo_root,
            )
            for path, content in (
                (output_root / f"{stem}.txt", requirements),
                (output_root / f"{stem}.wheelhouse-manifest.json", manifest),
            ):
                if path.exists() and path.read_text(encoding="utf-8") == content:
                    continue
                changed = True
                if not check:
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text(content, encoding="utf-8")
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
