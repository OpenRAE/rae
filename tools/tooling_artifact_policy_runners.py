"""Matrix expansion and reviewed runner-profile resolution for workflow jobs."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from itertools import product
from typing import Any

from tools.tooling_artifact_policy_common import as_list, as_mapping

MATRIX_EXPRESSION_RE = re.compile(r"^\$\{\{\s*matrix\.([A-Za-z_][A-Za-z0-9_-]*(?:\.[A-Za-z_][A-Za-z0-9_-]*)*)\s*\}\}$")
MAX_MATRIX_ROWS = 256
_MUTABLE_RUNNERS = frozenset({"ubuntu-latest", "windows-latest", "macos-latest"})
RUNNER_PROFILES = {
    "ubuntu-22.04": "proof-ubuntu-22.04-x86_64",
    "ubuntu-24.04": "public-ubuntu-24.04-x86_64",
    "ubuntu-24.04-arm": "public-linux-arm64",
    "macos-15": "public-macos-arm64",
    "macos-15-intel": "public-macos-x86_64",
}


def _matrix_includes(matrix: Mapping[str, Any]) -> list[dict[str, object]] | None:
    """Return the include rows, or None when any is not an admitted mapping."""

    declared = as_list(matrix.get("include"))
    includes = [dict(item) for item in declared if isinstance(item, Mapping)]
    if len(includes) != len(declared) or len(includes) > MAX_MATRIX_ROWS:
        return None
    return includes


def _matrix_axes(matrix: Mapping[str, Any], axis_names: Sequence[str]) -> list[list[object]] | None:
    """Expand the declared matrix axes, or None when they are not admitted."""

    axes: list[list[object]] = []
    row_count = 1
    for name in axis_names:
        values = as_list(matrix.get(name))
        if not values:
            return None
        axes.append(values)
        row_count *= len(values)
        if row_count > MAX_MATRIX_ROWS:
            return None
    return axes


def _matrix_excludes(matrix: Mapping[str, Any]) -> list[Mapping[str, Any]] | None:
    """Return the exclude entries, or None when any is not a mapping."""

    declared = as_list(matrix.get("exclude"))
    excludes = [item for item in declared if isinstance(item, Mapping)]
    return excludes if len(excludes) == len(declared) else None


def _matrix_row_excluded(row: Mapping[str, object], excludes: Sequence[Mapping[str, Any]]) -> bool:
    """Report whether one expanded matrix row matches an exclude entry."""

    return any(all(row.get(name) == value for name, value in excluded.items()) for excluded in excludes)


def _expanded_matrix_rows(
    matrix: Mapping[str, Any],
    axis_names: Sequence[str],
) -> tuple[list[dict[str, object]], bool]:
    """Expand the cartesian product of declared axes minus the exclusions."""

    axes = _matrix_axes(matrix, axis_names)
    excludes = _matrix_excludes(matrix)
    if axes is None or excludes is None:
        return [], True
    rows = (dict(zip(axis_names, values, strict=True)) for values in product(*axes))
    return [row for row in rows if not _matrix_row_excluded(row, excludes)], False


def matrix_rows(job: Mapping[str, Any]) -> tuple[list[dict[str, object]], bool]:
    """Expand one job's matrix into concrete rows, or report it as unadmitted."""

    matrix = as_mapping(as_mapping(job.get("strategy")).get("matrix"))
    if not matrix:
        return [{}], False
    axis_names = [name for name in matrix if name not in {"include", "exclude"}]
    includes = _matrix_includes(matrix)
    if includes:
        return ([], True) if axis_names else (includes, False)
    return _expanded_matrix_rows(matrix, axis_names) if includes is not None else ([], True)


def matrix_value(value: object, row: Mapping[str, object]) -> tuple[object, bool]:
    """Resolve one matrix expression against a concrete row."""

    match = MATRIX_EXPRESSION_RE.fullmatch(value) if isinstance(value, str) and "matrix." in value else None
    if match is None:
        return value, False
    current: object = row
    for component in match.group(1).split("."):
        if not isinstance(current, Mapping) or component not in current:
            return value, True
        current = current[component]
    return current, False


def _row_runner_invalid(value: str, *, unresolved: bool, unresolved_selector: bool) -> bool:
    """Report whether one expanded runner value is outside the reviewed profiles."""

    return unresolved or unresolved_selector or value in _MUTABLE_RUNNERS or value not in RUNNER_PROFILES


def runner_profiles(job: Mapping[str, Any]) -> tuple[str, list[tuple[str, dict[str, object]]], bool]:
    """Resolve one job's runner selector to reviewed host profiles per matrix row."""

    runner = job.get("runs-on")
    if runner is None and isinstance(job.get("uses"), str):
        return "reusable-workflow", [], not str(job.get("uses")).startswith("./")
    selector = str(runner)
    rows, invalid = matrix_rows(job)
    if invalid:
        return selector, [], True
    unresolved_selector = "matrix." in selector and MATRIX_EXPRESSION_RE.fullmatch(selector) is None
    contexts: list[tuple[str, dict[str, object]]] = []
    for row in rows:
        concrete, unresolved = matrix_value(runner, row)
        value = str(concrete)
        invalid = invalid or _row_runner_invalid(
            value,
            unresolved=unresolved,
            unresolved_selector=unresolved_selector,
        )
        if value in RUNNER_PROFILES:
            contexts.append((RUNNER_PROFILES[value], row))
    return selector, contexts, invalid


def step_ref(step: Mapping[str, Any], action_name: str) -> str:
    """Name the use site one step occupies."""

    return str(step.get("id") or step.get("name") or action_name)


def concrete_inputs(
    inputs: Mapping[str, object],
    matrix_row: Mapping[str, object],
) -> tuple[dict[str, object], bool]:
    """Resolve matrix expressions in one step's inputs for a concrete row."""

    concrete: dict[str, object] = {}
    unresolved_any = False
    for name, value in inputs.items():
        concrete[name], unresolved = matrix_value(value, matrix_row)
        unresolved_any = unresolved_any or unresolved
    return concrete, unresolved_any


__all__ = (
    "MATRIX_EXPRESSION_RE",
    "MAX_MATRIX_ROWS",
    "RUNNER_PROFILES",
    "concrete_inputs",
    "matrix_rows",
    "matrix_value",
    "runner_profiles",
    "step_ref",
)
