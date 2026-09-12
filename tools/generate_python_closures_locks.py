#!/usr/bin/env python3
"""Resolve exact locked closures for one target environment."""

from __future__ import annotations

from collections import defaultdict, deque
from collections.abc import Mapping, Sequence
from typing import Any

from packaging.markers import Marker, default_environment


def target_environment(python_version: str, platform: str) -> dict[str, str]:
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


def lock_mappings(values: object) -> list[Mapping[str, Any]]:
    """Keep only the mapping entries of a lock list."""

    return [value for value in values if isinstance(value, Mapping)] if isinstance(values, list) else []


def _lock_packages(lock: Mapping[str, Any]) -> dict[str, list[Mapping[str, Any]]]:
    """Index every locked package by name."""

    packages: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for package in lock.get("package", []):
        if isinstance(package, Mapping) and isinstance(package.get("name"), str):
            packages[package["name"]].append(package)
    return packages


def _root_dependencies(
    root: Mapping[str, Any],
    *,
    include_root_optional: bool,
    root_groups: Sequence[str],
) -> list[Any]:
    """Collect the declared root dependencies one closure walk starts from."""

    dependencies = list(root.get("dependencies", []))
    if include_root_optional:
        dependencies.extend(item for group in root.get("optional-dependencies", {}).values() for item in group)
    development_groups = root.get("dev-dependencies", {})
    for group in root_groups:
        group_dependencies = development_groups.get(group, []) if isinstance(development_groups, Mapping) else []
        if not isinstance(group_dependencies, list):
            raise ValueError(f"tool lock dependency group {group!r} is invalid")
        dependencies.extend(group_dependencies)
    return dependencies


def _record_selection(selected: dict[str, Mapping[str, Any]], package: Mapping[str, Any]) -> str:
    """Record one selected package, refusing a second version of the same name."""

    name = str(package["name"])
    previous = selected.setdefault(name, package)
    if previous is not package and previous.get("version") != package.get("version"):
        raise ValueError(f"target closure selected multiple versions of {name}")
    return name


def _queue_requested_extras(
    pending: deque[Mapping[str, Any]],
    package: Mapping[str, Any],
    dependency: Mapping[str, Any],
    processed_extras: set[str],
) -> None:
    """Queue the optional dependencies of extras this dependency newly requests."""

    requested = {item for item in dependency.get("extra", []) if isinstance(item, str)} - processed_extras
    for extra in sorted(requested):
        pending.extend(lock_mappings(package.get("optional-dependencies", {}).get(extra, [])))
    processed_extras.update(requested)


def _resolve_closure(
    packages: Mapping[str, Sequence[Mapping[str, Any]]],
    root_dependencies: Sequence[Any],
    environment: Mapping[str, str],
) -> list[Mapping[str, Any]]:
    """Walk the marker-filtered dependency graph to one exact package set."""

    pending: deque[Mapping[str, Any]] = deque(lock_mappings(list(root_dependencies)))
    selected: dict[str, Mapping[str, Any]] = {}
    processed_dependencies: set[str] = set()
    processed_extras: dict[str, set[str]] = defaultdict(set)
    while pending:
        dependency = pending.popleft()
        if not _matches(dependency.get("marker"), environment):
            continue
        package = _selected_package(packages, dependency, environment)
        name = _record_selection(selected, package)
        if name not in processed_dependencies:
            pending.extend(lock_mappings(package.get("dependencies", [])))
            processed_dependencies.add(name)
        _queue_requested_extras(pending, package, dependency, processed_extras[name])
    return [selected[name] for name in sorted(selected)]


def locked_closure(
    lock: Mapping[str, Any],
    environment: Mapping[str, str],
    *,
    root_name: str,
    include_root_optional: bool,
    root_groups: Sequence[str] = (),
    initial_dependencies: Sequence[Mapping[str, Any]] | None = None,
) -> list[Mapping[str, Any]]:
    packages = _lock_packages(lock)
    roots = packages.get(root_name, [])
    if len(roots) != 1:
        raise ValueError(f"lock must contain exactly one {root_name} package")
    root_dependencies = (
        _root_dependencies(
            roots[0],
            include_root_optional=include_root_optional,
            root_groups=root_groups,
        )
        if initial_dependencies is None
        else list(initial_dependencies)
    )
    return _resolve_closure(packages, root_dependencies, environment)


__all__ = ("lock_mappings", "locked_closure", "target_environment")
