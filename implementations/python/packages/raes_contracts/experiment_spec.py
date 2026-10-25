"""Loading helpers for authored experiment specifications.

An experiment specification is the pre-run authoring/input counterpart to the
archival experiment-core outputs (run/study/apparatus-context). Unlike SDL,
the authoring input is a single nested contract document. Its closed factorial
intent materializes condition/binding children; there is no key normalization
or cross-file resolution, so loading is a bounded,
duplicate-key/alias-rejecting safe YAML parse followed by
``ExperimentSpecModel`` validation — mirroring how the JSON fixtures under
``contracts/fixtures/experiment-core`` are checked.
"""

from __future__ import annotations

import logging
import math
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError
from yaml.composer import ComposerError
from yaml.constructor import ConstructorError
from yaml.events import AliasEvent
from yaml.nodes import MappingNode

from .contracts import ExperimentSpecModel, ExperimentTaskModel

log = logging.getLogger("raes.experiment_spec")

MAX_EXPERIMENT_SPEC_BYTES = 64 * 1024
_MAX_VALIDATION_DIAGNOSTICS = 32


class ExperimentSpecError(Exception):
    """Base exception for experiment-specification loading."""


class ExperimentSpecValidationError(ExperimentSpecError):
    """An experiment specification failed to parse or validate."""

    def __init__(self, code: str, message: str, path: Path | None = None) -> None:
        self.code = code
        self.path = path
        self.details = message
        prefix = f"{path.name}: " if path else ""
        super().__init__(f"{prefix}{message}")


class _ExperimentSpecLoader(yaml.SafeLoader):
    """Bounded authoring loader with duplicate-key and alias rejection."""

    def compose_node(self, parent: Any, index: Any) -> Any:
        if self.check_event(AliasEvent):
            raise ComposerError(None, None, "YAML aliases are not supported", self.peek_event().start_mark)
        return super().compose_node(parent, index)

    def construct_mapping(self, node: MappingNode, deep: bool = False) -> dict[object, object]:
        if not isinstance(node, MappingNode):
            raise ConstructorError(None, None, "expected a mapping node", node.start_mark)
        keys: set[object] = set()
        for key_node, _ in node.value:
            key = self.construct_object(key_node, deep=deep)
            try:
                duplicate = key in keys
            except TypeError as exc:
                raise ConstructorError(None, None, "mapping keys must be scalar", key_node.start_mark) from exc
            if duplicate:
                raise ConstructorError(None, None, "duplicate mapping key", key_node.start_mark)
            keys.add(key)
        return super().construct_mapping(node, deep=deep)


def _validate_finite_json(value: object) -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("non-finite numeric values are not supported")
    if isinstance(value, dict):
        for key, child in value.items():
            if not isinstance(key, str):
                raise ValueError("mapping keys must be strings")
            _validate_finite_json(child)
    elif isinstance(value, list):
        for child in value:
            _validate_finite_json(child)


def _safe_validation_details(exc: ValidationError) -> str:
    diagnostics: list[str] = []
    for error in exc.errors(include_url=False, include_context=False, include_input=False)[
        :_MAX_VALIDATION_DIAGNOSTICS
    ]:
        location = "/" + "/".join(str(part) for part in error["loc"])
        diagnostics.append(f"{location or '/'}: {error['type']}")
    remaining = exc.error_count() - len(diagnostics)
    if remaining > 0:
        diagnostics.append(f"{remaining} additional validation error(s) omitted")
    return "Experiment spec contract validation failed:\n" + "\n".join(diagnostics)


def _load_yaml(raw: str) -> object:
    loader = _ExperimentSpecLoader(raw)
    try:
        return loader.get_single_data()
    finally:
        loader.dispose()


def parse_experiment_spec(
    text: str, *, path: Path | None = None, task: ExperimentTaskModel | None = None
) -> ExperimentSpecModel:
    """Validate YAML and, when supplied, bind task_ref to a validated task.

    The task id must match, as must the version when task_ref declares one.
    Omitting task preserves context-free validation; no reference is fetched.
    """
    if len(text.encode("utf-8", errors="replace")) > MAX_EXPERIMENT_SPEC_BYTES:
        raise ExperimentSpecValidationError(
            "input-too-large",
            f"Experiment spec exceeds the {MAX_EXPERIMENT_SPEC_BYTES}-byte input limit.",
            path=path,
        )
    raw = text.strip()
    if not raw:
        raise ExperimentSpecValidationError("empty-input", "Experiment spec is empty.", path=path)

    try:
        payload = _load_yaml(raw)
    except ConstructorError as exc:
        code = "duplicate-key" if "duplicate mapping key" in str(exc) else "invalid-yaml"
        raise ExperimentSpecValidationError(code, "Experiment spec YAML is invalid.", path=path) from exc
    except (yaml.YAMLError, ValueError) as exc:
        raise ExperimentSpecValidationError("invalid-yaml", "Experiment spec YAML is invalid.", path=path) from exc

    if not isinstance(payload, dict):
        raise ExperimentSpecValidationError(
            "invalid-root",
            "Experiment spec must be a YAML mapping.",
            path=path,
        )
    try:
        _validate_finite_json(payload)
    except ValueError as exc:
        raise ExperimentSpecValidationError("invalid-json-value", str(exc), path=path) from exc

    try:
        spec = ExperimentSpecModel.model_validate(payload)
    except ValidationError as exc:
        raise ExperimentSpecValidationError(
            "contract-invalid",
            _safe_validation_details(exc),
            path=path,
        ) from exc
    if task is not None:
        _validate_task_reference(spec, task, path=path)
    return spec


def _validate_task_reference(spec: ExperimentSpecModel, task: ExperimentTaskModel, *, path: Path | None) -> None:
    reference = spec.task_ref
    if reference.ref_id != task.task_id or (
        reference.ref_version is not None and reference.ref_version != task.task_version
    ):
        raise ExperimentSpecValidationError(
            "task-reference-mismatch", "Experiment spec task_ref does not match the supplied task.", path=path
        )


def load_experiment_spec(path: Path, *, task: ExperimentTaskModel | None = None) -> ExperimentSpecModel:
    """Load an experiment specification, optionally checking a supplied validated task."""
    if not path.exists():
        raise FileNotFoundError(f"Experiment spec file not found: {path.name}")
    if path.stat().st_size > MAX_EXPERIMENT_SPEC_BYTES:
        raise ExperimentSpecValidationError(
            "input-too-large",
            f"Experiment spec exceeds the {MAX_EXPERIMENT_SPEC_BYTES}-byte input limit.",
            path=path,
        )

    spec = parse_experiment_spec(path.read_text(encoding="utf-8"), path=path, task=task)
    log.info("Loaded experiment spec '%s' from %s", spec.spec_id, path.name)
    return spec


def find_experiment_specs(search_dir: Path) -> list[Path]:
    """Find all authored experiment-spec files in a directory (non-recursive)."""
    if not search_dir.is_dir():
        log.debug("Experiments directory does not exist: %s", search_dir)
        return []

    paths = sorted(search_dir.glob("*.exp.yaml"))
    log.debug("Found %d experiment spec files in %s", len(paths), search_dir)
    return paths
