"""Closed workflow matrix and runner-profile expansion."""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Mapping
from itertools import product
from typing import Any

from tools.tooling_artifact_policy_common import as_list, as_mapping

_MATRIX_EXPRESSION_RE = re.compile(
    r"^\$\{\{\s*matrix\."
    r"([A-Za-z_][A-Za-z0-9_-]*(?:\.[A-Za-z_][A-Za-z0-9_-]*)*)"
    r"\s*\}\}$"
)
_MUTABLE_RUNNERS = frozenset({"ubuntu-latest", "windows-latest", "macos-latest"})
_RUNNER_PROFILES = {
    "ubuntu-22.04": "proof-ubuntu-22.04-x86_64",
    "ubuntu-24.04": "public-ubuntu-24.04-x86_64",
    "ubuntu-24.04-arm": "public-linux-arm64",
    "macos-15": "public-macos-arm64",
    "macos-15-intel": "public-macos-x86_64",
}
_MAX_MATRIX_ROWS = 256


def matrix_rows(
    job: Mapping[str, Any],
    *,
    product_values: Callable[..., Iterable[tuple[object, ...]]] = product,
) -> tuple[list[dict[str, object]], bool]:
    matrix = as_mapping(as_mapping(job.get("strategy")).get("matrix"))
    if not matrix:
        result = ([{}], False)
    else:
        axis_names = [name for name in matrix if name not in {"include", "exclude"}]
        includes, invalid = _matrix_includes(matrix, axis_names)
        if invalid:
            result = ([], True)
        elif includes is not None:
            result = (includes, False)
        else:
            result = _axis_matrix_rows(matrix, axis_names, product_values)
    return result


def _matrix_includes(
    matrix: Mapping[str, Any],
    axis_names: list[str],
) -> tuple[list[dict[str, object]] | None, bool]:
    includes = [dict(item) for item in as_list(matrix.get("include")) if isinstance(item, Mapping)]
    if len(includes) != len(as_list(matrix.get("include"))) or len(includes) > _MAX_MATRIX_ROWS:
        result: tuple[list[dict[str, object]] | None, bool] = ([], True)
    elif axis_names and includes:
        result = ([], True)
    elif includes:
        result = (includes, False)
    else:
        result = (None, False)
    return result


def _axis_matrix_rows(
    matrix: Mapping[str, Any],
    axis_names: list[str],
    product_values: Callable[..., Iterable[tuple[object, ...]]],
) -> tuple[list[dict[str, object]], bool]:
    axes, row_count = _matrix_axes(matrix, axis_names)
    excludes, invalid_excludes = _matrix_excludes(matrix)
    invalid = row_count == 0 or row_count > _MAX_MATRIX_ROWS or invalid_excludes
    if invalid:
        rows: list[dict[str, object]] = []
    else:
        candidates = [dict(zip(axis_names, values, strict=True)) for values in product_values(*axes)]
        rows = [row for row in candidates if not any(_row_matches(row, excluded) for excluded in excludes)]
    return rows, invalid


def _matrix_axes(
    matrix: Mapping[str, Any],
    axis_names: list[str],
) -> tuple[list[list[object]], int]:
    axes: list[list[object]] = []
    row_count = 1
    for name in axis_names:
        values = as_list(matrix.get(name))
        if not values:
            return [], 0
        axes.append(values)
        row_count *= len(values)
    return axes, row_count


def _matrix_excludes(matrix: Mapping[str, Any]) -> tuple[list[Mapping[object, object]], bool]:
    raw_excludes = as_list(matrix.get("exclude"))
    excludes = [item for item in raw_excludes if isinstance(item, Mapping)]
    return excludes, len(excludes) != len(raw_excludes)


def _row_matches(row: Mapping[str, object], excluded: Mapping[object, object]) -> bool:
    return all(row.get(str(name)) == value for name, value in excluded.items())


def matrix_value(value: object, row: Mapping[str, object]) -> tuple[object, bool]:
    match = _MATRIX_EXPRESSION_RE.fullmatch(value) if isinstance(value, str) and "matrix." in value else None
    if match is None:
        return value, False
    current: object = row
    for component in match.group(1).split("."):
        if not isinstance(current, Mapping) or component not in current:
            return value, True
        current = current[component]
    return current, False


def runner_profiles(
    job: Mapping[str, Any],
    *,
    product_values: Callable[..., Iterable[tuple[object, ...]]] = product,
) -> tuple[str, list[tuple[str, dict[str, object]]], bool]:
    runner = job.get("runs-on")
    if runner is None and isinstance(job.get("uses"), str):
        return "reusable-workflow", [], not str(job.get("uses")).startswith("./")
    selector = str(runner)
    rows, invalid = matrix_rows(job, product_values=product_values)
    contexts: list[tuple[str, dict[str, object]]] = []
    for row in rows:
        concrete, unresolved = matrix_value(runner, row)
        value = str(concrete)
        unresolved_runner = "matrix." in selector and _MATRIX_EXPRESSION_RE.fullmatch(selector) is None
        invalid = (
            invalid or unresolved or unresolved_runner or value in _MUTABLE_RUNNERS or value not in _RUNNER_PROFILES
        )
        if value in _RUNNER_PROFILES:
            contexts.append((_RUNNER_PROFILES[value], row))
    return selector, contexts, invalid


__all__ = ("matrix_rows", "matrix_value", "runner_profiles")
