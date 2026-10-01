#!/usr/bin/env python3
"""Reconcile the runtime dependency closure of one built distribution.

The release smoke environment installs every projected requirement and then the
candidate with `--no-deps`, so it also holds the published `dev` and `docs`
extras. Reading that environment back would describe the developer closure
rather than the distribution, which is exactly the confusion issue #1226
forbids. The closure below is reconciled from three independent sources:

* the built wheel's own `Requires-Dist` metadata, read from the archive without
  installing, importing or otherwise executing the candidate;
* the reviewed locked selection, which supplies exact versions;
* the observed installation, which proves the selection was realizable.

Any disagreement between them fails with a stable code. A dependency edge is
never silently dropped, because an omitted edge is indistinguishable from an
absent dependency once the SBOM is published.
"""

from __future__ import annotations

import zipfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from packaging.markers import Marker
from packaging.metadata import Metadata
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name
from packaging.version import InvalidVersion, Version

from tools.generate_python_closures_locks import locked_closure

# A wheel's METADATA is small; anything larger is malformed or hostile. The
# bound applies to the decompressed size so a compressed member cannot expand
# without limit.
MAX_METADATA_BYTES = 1 * 1024 * 1024


class RuntimeClosureError(Exception):
    """A reconciliation failure carrying a stable, publishable failure code."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


_ROOT_NAME = "raes"


@dataclass(frozen=True)
class ReconciledClosure:
    """One reconciled runtime closure and its dependency edges."""

    components: list[ClosureComponent] = field(default_factory=list)
    edges: dict[str, list[str]] = field(default_factory=dict)


@dataclass(frozen=True)
class ClosureComponent:
    """One reconciled runtime component of the distribution."""

    name: str
    version: str
    scope: str
    extra: str | None = None


def _metadata_member(archive: zipfile.ZipFile) -> zipfile.ZipInfo:
    candidates = [
        info
        for info in archive.infolist()
        if info.filename.endswith(".dist-info/METADATA") and info.filename.count("/") == 1
    ]
    if len(candidates) != 1:
        raise RuntimeClosureError(
            "wheel-metadata-absent",
            "wheel must contain exactly one top-level .dist-info/METADATA member",
        )
    return candidates[0]


def wheel_metadata(wheel_path: Path) -> Metadata:
    """Read one built wheel's declared metadata straight from the archive."""

    try:
        with zipfile.ZipFile(wheel_path) as archive:
            member = _metadata_member(archive)
            if member.file_size > MAX_METADATA_BYTES:
                raise RuntimeClosureError(
                    "wheel-metadata-oversized",
                    "wheel metadata exceeds the reviewed size bound",
                )
            with archive.open(member) as handle:
                payload = handle.read(MAX_METADATA_BYTES + 1)
    except (OSError, zipfile.BadZipFile) as exc:
        raise RuntimeClosureError("wheel-metadata-unreadable", "wheel archive could not be read") from exc
    if len(payload) > MAX_METADATA_BYTES:
        raise RuntimeClosureError(
            "wheel-metadata-oversized",
            "wheel metadata exceeds the reviewed size bound",
        )
    try:
        return Metadata.from_email(payload.decode("utf-8"), validate=False)
    except ValueError as exc:
        raise RuntimeClosureError("wheel-metadata-invalid", "wheel metadata could not be parsed") from exc


def _applies(requirement: Requirement, environment: Mapping[str, str], extra: str | None) -> bool:
    """Evaluate one requirement's marker for a target and optional-group context."""

    if requirement.marker is None:
        return extra is None
    return bool(requirement.marker.evaluate(environment={**environment, "extra": extra or ""}))


def _selected_extra(
    requirement: Requirement,
    environment: Mapping[str, str],
    extras: Sequence[str],
) -> tuple[bool, str | None]:
    """Classify a requirement as base, contributed by an extra, or unselected.

    This uses only the documented marker evaluation: a requirement belongs to
    the base closure when its marker holds with no extra in context, and to an
    extra when it holds only once that extra is supplied. Reading `packaging`'s
    internal marker tree to recover the extra name would couple the reviewed
    evidence to a private API.
    """

    if requirement.marker is None or _applies(requirement, environment, None):
        return True, None
    for extra in extras:
        if _applies(requirement, environment, extra):
            return True, extra
    return False, None


def _version(value: str, *, name: str, source: str) -> Version:
    try:
        return Version(value)
    except InvalidVersion as exc:
        raise RuntimeClosureError(
            "runtime-closure-invalid-version",
            f"{source} version for {name} is not a valid version",
        ) from exc


def _declared_roots(
    metadata: Metadata,
    environment: Mapping[str, str],
    extras: Sequence[str],
) -> dict[str, list[Requirement]]:
    """Group the wheel's applicable declared requirements by contributing extra."""

    roots: dict[str, list[Requirement]] = {"": []}
    for extra in extras:
        roots[extra] = []
    for requirement in metadata.requires_dist or ():
        applies, extra = _selected_extra(requirement, environment, extras)
        if applies:
            roots[extra or ""].append(requirement)
    return roots


def _resolve(
    lock: Mapping[str, Any],
    environment: Mapping[str, str],
    requirements: Sequence[Requirement],
) -> dict[str, Mapping[str, Any]]:
    """Resolve one transitive closure from explicit declared roots.

    The incumbent locked closure walker is seeded through its existing
    `initial_dependencies` seam rather than reimplemented, so marker filtering,
    extras propagation and multi-version refusal keep one definition.
    """

    if not requirements:
        return {}
    seeds: list[dict[str, Any]] = []
    for requirement in requirements:
        seed: dict[str, Any] = {"name": canonicalize_name(requirement.name)}
        if requirement.extras:
            # `uvicorn[standard]` is a declared runtime dependency whose extra
            # tree belongs to the closure. Dropping the qualifier here would
            # silently omit those packages from the published SBOM.
            seed["extra"] = sorted(requirement.extras)
        seeds.append(seed)
    try:
        packages = locked_closure(
            lock,
            environment,
            root_name=_ROOT_NAME,
            include_root_optional=False,
            initial_dependencies=seeds,
        )
    except ValueError as exc:
        raise RuntimeClosureError(
            "runtime-closure-unlocked-dependency",
            "declared dependency could not be resolved against the reviewed lock",
        ) from exc
    return {canonicalize_name(str(package["name"])): package for package in packages}


def _edges(
    selected: Mapping[str, Mapping[str, Any]],
    environment: Mapping[str, str],
) -> dict[str, list[str]]:
    """Recover the dependency edges between selected packages."""

    graph: dict[str, list[str]] = {}
    for key, package in selected.items():
        names = []
        for dependency in package.get("dependencies", []) or ():
            if not isinstance(dependency, Mapping):
                continue
            marker = dependency.get("marker")
            if isinstance(marker, str) and not Marker(marker).evaluate(environment={**environment, "extra": ""}):
                continue
            child = canonicalize_name(str(dependency.get("name", "")))
            if child in selected and child != key:
                names.append(child)
        graph[key] = sorted(dict.fromkeys(names))
    return graph


def reconcile_runtime_closure(
    metadata: Metadata,
    *,
    lock: Mapping[str, Any],
    installed_versions: Mapping[str, str],
    environment: Mapping[str, str],
    extras: Sequence[str] = (),
) -> ReconciledClosure:
    """Reconcile declared metadata, locked selection and observed installation.

    The base closure is resolved on its own so it stays identifiable
    independently of extras; each published extra is then resolved additively and
    everything it introduces is labelled with that extra rather than recorded as
    unconditional runtime.
    """

    provided = {str(value) for value in metadata.provides_extra or ()}
    unknown = sorted(set(extras) - provided)
    if unknown:
        raise RuntimeClosureError(
            "runtime-closure-unknown-extra",
            f"distribution does not publish the requested extras: {unknown}",
        )

    roots = _declared_roots(metadata, environment, extras)
    base = _resolve(lock, environment, roots[""])
    _check_roots(roots[""], base)

    selected: dict[str, tuple[Mapping[str, Any], str | None]] = {key: (package, None) for key, package in base.items()}
    for extra in extras:
        combined = _resolve(lock, environment, [*roots[""], *roots[extra]])
        _check_roots(roots[extra], combined)
        for key, package in combined.items():
            if key not in selected:
                selected[key] = (package, extra)

    installed = {canonicalize_name(name): value for name, value in installed_versions.items()}
    components = []
    for key in sorted(selected):
        package, extra = selected[key]
        components.append(
            _component(
                name=str(package["name"]),
                locked_value=str(package.get("version", "")),
                installed_value=installed.get(key),
                extra=extra,
            )
        )
    _check_specifiers(roots, {c.name: c.version for c in components})
    graph = _edges({key: package for key, (package, _extra) in selected.items()}, environment)
    return ReconciledClosure(components=components, edges=graph)


def _check_roots(
    requirements: Sequence[Requirement],
    resolved: Mapping[str, Mapping[str, Any]],
) -> None:
    for requirement in requirements:
        if canonicalize_name(requirement.name) not in resolved:
            raise RuntimeClosureError(
                "runtime-closure-unlocked-dependency",
                f"declared dependency {requirement.name} is absent from the reviewed lock",
            )


def _check_specifiers(
    roots: Mapping[str, Sequence[Requirement]],
    versions: Mapping[str, str],
) -> None:
    by_key = {canonicalize_name(name): value for name, value in versions.items()}
    for requirements in roots.values():
        for requirement in requirements:
            selected = by_key.get(canonicalize_name(requirement.name))
            if selected is None:
                continue
            version = _version(selected, name=requirement.name, source="locked")
            if requirement.specifier and not requirement.specifier.contains(version, prereleases=True):
                raise RuntimeClosureError(
                    "runtime-closure-specifier-violation",
                    f"selected version of {requirement.name} violates the declared specifier",
                )


def _component(
    *,
    name: str,
    locked_value: str,
    installed_value: str | None,
    extra: str | None,
) -> ClosureComponent:
    if installed_value is None:
        raise RuntimeClosureError(
            "runtime-closure-uninstalled-dependency",
            f"selected dependency {name} is absent from the observed installation",
        )
    locked_version = _version(locked_value, name=name, source="locked")
    installed_version = _version(installed_value, name=name, source="installed")
    if locked_version != installed_version:
        raise RuntimeClosureError(
            "runtime-closure-version-disagreement",
            f"locked and installed versions of {name} disagree",
        )
    return ClosureComponent(
        name=name,
        version=str(locked_version),
        scope="optional" if extra else "required",
        extra=extra,
    )


__all__ = [
    "MAX_METADATA_BYTES",
    "observed_installation",
    "ClosureComponent",
    "ReconciledClosure",
    "RuntimeClosureError",
    "reconcile_runtime_closure",
    "wheel_metadata",
]


def observed_installation(environment_dir: Path) -> dict[str, str]:
    """Read the versions actually installed in one environment.

    Distribution names and versions are taken from `*.dist-info` directory
    names. Nothing in the environment is imported or executed, so reading a
    candidate installation cannot run candidate code.
    """

    site_packages = sorted(environment_dir.glob("lib/python*/site-packages"))
    if not site_packages:
        site_packages = sorted(environment_dir.glob("Lib/site-packages"))
    if not site_packages:
        raise RuntimeClosureError(
            "observed-installation-absent",
            "environment has no site-packages directory to observe",
        )
    installed: dict[str, str] = {}
    for directory in site_packages:
        for dist_info in sorted(directory.glob("*.dist-info")):
            stem = dist_info.name[: -len(".dist-info")]
            name, separator, version = stem.rpartition("-")
            if not separator or not name:
                continue
            installed[canonicalize_name(name)] = version
    if not installed:
        raise RuntimeClosureError(
            "observed-installation-empty",
            "environment records no installed distributions",
        )
    return installed
