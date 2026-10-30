"""Static index of the package modules that the ADR-117 structural checks analyze.

The index parses each module once. It never imports or runs the analyzed code.
"""

from __future__ import annotations

import ast
import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from raes_contracts.errors import InvalidInputError

from .common import parse_python_source, safe_repo_path


@dataclass(frozen=True)
class SourceModule:
    name: str
    rel_path: str
    is_package: bool
    tree: ast.Module


@dataclass(frozen=True)
class SourceIndex:
    coverage_roots: tuple[str, ...]
    root_packages: tuple[str, ...]
    modules: Mapping[str, SourceModule]

    def is_first_party(self, dotted_name: str) -> bool:
        return dotted_name.split(".", 1)[0] in self.root_packages

    @property
    def max_package_depth(self) -> int:
        """Largest number of dots in a package name; a root package has depth 0."""

        return max((module.name.count(".") for module in self.modules.values() if module.is_package), default=0)


def build_source_index(repo_root: Path, coverage_roots: Sequence[str]) -> SourceIndex:
    """Index every module of every package directly under ``coverage_roots``.

    A package is a directory with ``__init__.py``. A directory without it is not
    part of a package, so its files are not modules. Raise ``InvalidInputError``
    for an unsafe or missing coverage root, a symbolic link to a directory, a
    file that resolves outside the repository, a duplicate root package and
    source that is not valid Python.
    """

    package_dirs: dict[str, str] = {}
    for coverage_root in coverage_roots:
        root_path = safe_repo_path(repo_root, coverage_root)
        if root_path is None or not root_path.is_dir():
            raise InvalidInputError(f"coverage root {coverage_root!r} is not a directory in the repository")
        for child in sorted(root_path.iterdir()):
            if not child.is_dir() or not (child / "__init__.py").is_file():
                continue
            if child.name in package_dirs:
                raise InvalidInputError(f"root package {child.name!r} occurs in more than one coverage root")
            package_dirs[child.name] = f"{coverage_root.strip('/')}/{child.name}"

    modules: dict[str, SourceModule] = {}
    for package_name, package_rel in sorted(package_dirs.items()):
        for rel_path in _package_files(repo_root, package_rel):
            module_name = _module_name(package_name, package_rel, rel_path)
            path = safe_repo_path(repo_root, rel_path)
            if path is None:
                raise InvalidInputError(f"{rel_path} resolves outside the repository")
            modules[module_name] = SourceModule(
                name=module_name,
                rel_path=rel_path,
                is_package=rel_path.endswith("/__init__.py"),
                tree=parse_python_source(path, rel_path),
            )
    return SourceIndex(
        coverage_roots=tuple(coverage_roots),
        root_packages=tuple(sorted(package_dirs)),
        modules=modules,
    )


def _package_files(repo_root: Path, package_rel: str) -> list[str]:
    """Return the ``.py`` files of one package tree in sorted order."""

    files: list[str] = []
    pending = [package_rel]
    while pending:
        directory_rel = pending.pop()
        directory = repo_root / directory_rel
        for entry in sorted(os.scandir(directory), key=lambda item: item.name):
            entry_rel = f"{directory_rel}/{entry.name}"
            if entry.is_dir(follow_symlinks=False):
                if entry.name == "__pycache__":
                    continue
                if (Path(entry.path) / "__init__.py").is_file():
                    pending.append(entry_rel)
                continue
            if entry.is_symlink() and Path(entry.path).is_dir():
                raise InvalidInputError(
                    f"{entry_rel} is a symbolic link to a directory; package trees must not use one"
                )
            if entry.name.endswith(".py"):
                files.append(entry_rel)
    return sorted(files)


def _module_name(package_name: str, package_rel: str, rel_path: str) -> str:
    relative = rel_path[len(package_rel) :].strip("/")
    parts = [package_name, *relative[: -len(".py")].split("/")]
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)
