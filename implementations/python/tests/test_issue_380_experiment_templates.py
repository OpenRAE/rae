"""Experiment authoring-input templates in the example library (issue #380)."""

from __future__ import annotations

import copy
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
import yaml
from test_example_library_policy import _VALID_BODY, _read_catalog, _seed_repo, _write_catalog, _write_yaml
from tools.check_example_library import evaluate_example_library

_EXPERIMENT_CONTRACT = "experiment-authoring-input-v1"
_EXPERIMENT_BODY: dict[str, Any] = {
    "schema_version": "experiment-authoring-input/v1",
    "spec_id": "policy-test-spec",
    "spec_version": "1.0.0",
    "title": "Policy test spec",
    "description": "Experiment template body for policy tests.",
    "task_ref": {"ref_kind": "task", "ref_id": "task-policy-test"},
    "run_plan": {
        "episode_control": {"turn_order": "sequential", "termination_rule": "End each episode after one step."},
        "target_run_count": 1,
    },
}


@dataclass(frozen=True)
class _Library:
    """The seeded catalog and one surface's template file, loaded for editing."""

    catalog: dict[str, Any]
    template: dict[str, Any]
    surface: str = "run"

    def entry(self, surface: str | None = None, field: str = "templates") -> dict[str, Any]:
        return self.catalog["surfaces"][surface or self.surface][field][0]


_Mutation = Callable[[_Library], None]


def _apply(repo_root: Path, mutate: _Mutation, surface: str = "run") -> None:
    template_path = repo_root / f"examples/library/templates/{surface}/template.yaml"
    template = yaml.safe_load(template_path.read_text(encoding="utf-8"))
    library = _Library(_read_catalog(repo_root), template, surface)
    mutate(library)
    _write_catalog(repo_root, library.catalog)
    _write_yaml(template_path, library.template)


def _as_experiment_template(library: _Library) -> None:
    entry = library.entry()
    entry.update(contract=_EXPERIMENT_CONTRACT, intended_user="experiment-author")
    del entry["sdl_sections"]
    library.template["body"] = copy.deepcopy(_EXPERIMENT_BODY)


def _seed_experiment_repo(tmp_path: Path) -> Path:
    repo_root = _seed_repo(tmp_path)
    _apply(repo_root, _as_experiment_template)
    return repo_root


def _set_entry(key: str, value: Any, surface: str = "run", field: str = "templates") -> _Mutation:
    def mutate(library: _Library) -> None:
        library.entry(surface, field)[key] = value

    return mutate


def _drop_task_ref(library: _Library) -> None:
    del library.template["body"]["task_ref"]


def _sdl_body(library: _Library) -> None:
    library.template["body"] = copy.deepcopy(_VALID_BODY)


def _drop_contract(library: _Library) -> None:
    entry = library.entry()
    del entry["contract"]
    entry.update(intended_user="sdl-author", sdl_sections=["objectives"])


def test_experiment_template_passes(tmp_path: Path) -> None:
    assert evaluate_example_library(_seed_experiment_repo(tmp_path)) == []


@pytest.mark.parametrize(
    ("mutation", "rule_id"),
    (
        pytest.param(
            _set_entry("contract", _EXPERIMENT_CONTRACT, field="worked_examples"),
            "example-library-entry-contract",
            id="contract-on-worked-example",
        ),
        pytest.param(_set_entry("contract", "experiment-run-v1"), "example-library-entry-contract", id="unknown"),
        pytest.param(_set_entry("sdl_sections", ["objectives"]), "example-library-entry-sections", id="sections"),
        pytest.param(_set_entry("intended_user", "sdl-author"), "example-library-entry-user", id="sdl-author"),
        pytest.param(
            _set_entry("intended_user", "experiment-author", surface="scenario"),
            "example-library-entry-user",
            id="experiment-author-on-sdl",
        ),
        pytest.param(_drop_task_ref, "example-library-template-body", id="invalid-experiment-body"),
        pytest.param(_sdl_body, "example-library-template-body", id="sdl-body-under-experiment-contract"),
        pytest.param(_drop_contract, "example-library-template-body", id="experiment-body-without-contract"),
    ),
)
def test_experiment_template_violation_is_the_only_failure(tmp_path: Path, mutation: _Mutation, rule_id: str) -> None:
    repo_root = _seed_experiment_repo(tmp_path)
    _apply(repo_root, mutation)

    assert [failure.rule_id for failure in evaluate_example_library(repo_root)] == [rule_id]


@pytest.mark.parametrize(
    ("surface", "rule_ids"),
    (
        pytest.param("study", [], id="study"),
        *(
            pytest.param(surface, ["example-library-entry-contract"], id=surface)
            for surface in ("scenario", "workflow", "participant_behavior", "task")
        ),
    ),
)
def test_experiment_contract_is_limited_to_run_and_study_templates(
    tmp_path: Path, surface: str, rule_ids: list[str]
) -> None:
    repo_root = _seed_repo(tmp_path)
    _apply(repo_root, _as_experiment_template, surface=surface)

    assert [failure.rule_id for failure in evaluate_example_library(repo_root)] == rule_ids
