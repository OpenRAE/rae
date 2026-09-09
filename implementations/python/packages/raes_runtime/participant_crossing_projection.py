"""Stable participant projection subjects across provider snapshot revisions."""

from __future__ import annotations

_SNAPSHOT_REVISION_REF_PREFIX = "runtime.snapshot.revision."
_INVALID_REVISION_PATH = "runtime-owned projection revision path is invalid"

RuntimeRevisionPath = tuple[str | int, ...]
_RevisionContainer = dict[str, object] | list[object]


def stable_projection_subject(
    payload: dict[str, object],
    runtime_owned_revision_paths: tuple[RuntimeRevisionPath, ...],
) -> dict[str, object]:
    """Normalize only runtime-owned provider revision evidence paths."""

    paths = ((("source_snapshot_ref",), False), *((path, True) for path in runtime_owned_revision_paths))
    for path, required in paths:
        container, leaf = _revision_path_parent(payload, path)
        value = _revision_path_value(container, leaf)
        if _is_snapshot_revision_ref(value):
            _set_revision_path_value(container, leaf, f"{_SNAPSHOT_REVISION_REF_PREFIX}observed")
        elif required:
            raise RuntimeError(_INVALID_REVISION_PATH)
    return payload


def _revision_path_parent(
    payload: dict[str, object],
    path: RuntimeRevisionPath,
) -> tuple[_RevisionContainer, str | int]:
    container: _RevisionContainer = payload
    for segment in path[:-1]:
        nested = _revision_path_value(container, segment)
        if not isinstance(nested, (dict, list)):
            raise RuntimeError(_INVALID_REVISION_PATH)
        container = nested
    return container, path[-1]


def _revision_path_value(container: _RevisionContainer, segment: str | int) -> object:
    if isinstance(container, dict) and isinstance(segment, str):
        return container[segment]
    if isinstance(container, list) and isinstance(segment, int):
        return container[segment]
    raise RuntimeError(_INVALID_REVISION_PATH)


def _set_revision_path_value(
    container: _RevisionContainer,
    segment: str | int,
    value: str,
) -> None:
    if isinstance(container, dict) and isinstance(segment, str):
        container[segment] = value
        return
    if isinstance(container, list) and isinstance(segment, int):
        container[segment] = value
        return
    raise RuntimeError(_INVALID_REVISION_PATH)


def _is_snapshot_revision_ref(value: object) -> bool:
    if not isinstance(value, str) or not value.startswith(_SNAPSHOT_REVISION_REF_PREFIX):
        return False
    return value.removeprefix(_SNAPSHOT_REVISION_REF_PREFIX).isdigit()
