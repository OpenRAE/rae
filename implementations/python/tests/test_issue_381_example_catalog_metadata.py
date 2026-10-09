"""Catalog entry metadata rules for the example library (issue #381)."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
import yaml
from test_example_library_policy import _VALID_BODY, _read_catalog, _seed_repo, _write_catalog
from tools.check_example_library import evaluate_example_library

_Mutation = Callable[[dict[str, Any]], None]
_WORKED_SDL_PATH = "examples/scenarios/worked.sdl.yaml"
_VALID_SDL = yaml.safe_dump(_VALID_BODY, sort_keys=False).encode("utf-8")


def _set(field: str, key: str, value: Any) -> _Mutation:
    def mutate(catalog: dict[str, Any]) -> None:
        catalog["surfaces"]["scenario"][field][0][key] = value

    return mutate


def _rule_ids(repo_root: Path) -> list[str]:
    return [failure.rule_id for failure in evaluate_example_library(repo_root)]


@pytest.mark.parametrize(
    ("mutation", "rule_id"),
    (
        pytest.param(
            _set("worked_examples", "validation_status", "supported"),
            "example-library-entry-status",
            id="status-outside-vocabulary",
        ),
        pytest.param(
            _set("templates", "validation_status", "guidance"),
            "example-library-entry-status",
            id="template-not-validated",
        ),
        pytest.param(
            _set("patterns", "validation_status", "validated"),
            "example-library-entry-status",
            id="pattern-claims-validation",
        ),
        pytest.param(_set("templates", "intended_user", "operator"), "example-library-entry-user", id="unknown-user"),
        pytest.param(_set("patterns", "limits", []), "example-library-entry-limits", id="empty-limits"),
        pytest.param(
            _set("patterns", "limits", "One statement."), "example-library-entry-limits", id="limits-not-a-list"
        ),
        pytest.param(_set("patterns", "sdl_sections", ["tasks"]), "example-library-entry-sections", id="not-sdl"),
        pytest.param(_set("patterns", "sdl_sections", ["name"]), "example-library-entry-sections", id="metadata-field"),
        pytest.param(
            _set("worked_examples", "sdl_sections", ["objectives", "objectives"]),
            "example-library-entry-sections",
            id="duplicate-section",
        ),
        pytest.param(
            _set("templates", "sdl_sections", ["nodes", "stories"]),
            "example-library-entry-sections",
            id="section-absent-from-template-body",
        ),
        pytest.param(
            _set("templates", "sdl_sections", ["nodes", "tasks"]),
            "example-library-entry-sections",
            id="not-sdl-on-validated-template",
        ),
        pytest.param(
            _set("worked_examples", "path", "examples/library/worked/missing.txt"),
            "example-library-path-missing",
            id="worked-example-path-missing",
        ),
    ),
)
def test_catalog_entry_violation_is_the_only_failure(tmp_path: Path, mutation: _Mutation, rule_id: str) -> None:
    repo_root = _seed_repo(tmp_path)
    catalog = _read_catalog(repo_root)
    mutation(catalog)
    _write_catalog(repo_root, catalog)

    assert _rule_ids(repo_root) == [rule_id]


@pytest.mark.parametrize(
    ("sdl_source", "sdl_sections", "expected"),
    (
        pytest.param(_VALID_SDL, ["nodes", "workflows"], [], id="valid"),
        pytest.param(_VALID_SDL, ["stories"], ["example-library-entry-sections"], id="section-absent-from-file"),
        pytest.param(
            b"name: invalid\nnodes: [not-a-map]\n",
            ["nodes"],
            ["example-library-worked-example-body"],
            id="invalid-sdl",
        ),
        pytest.param(
            b"name: advisory\nnodes:\n  vm:\n    type: compute\n",
            ["nodes"],
            ["example-library-worked-example-advisory"],
            id="advisory",
        ),
        pytest.param(b"name: \xff\n", ["nodes"], ["example-library-worked-example-body"], id="not-utf-8"),
    ),
)
def test_validated_worked_example_is_parsed_as_sdl(
    tmp_path: Path, sdl_source: bytes, sdl_sections: list[str], expected: list[str]
) -> None:
    repo_root = _seed_repo(tmp_path)
    worked_file = repo_root / _WORKED_SDL_PATH
    worked_file.parent.mkdir(parents=True)
    worked_file.write_bytes(sdl_source)
    catalog = _read_catalog(repo_root)
    catalog["surfaces"]["scenario"]["worked_examples"][0].update(
        path=_WORKED_SDL_PATH,
        validation_status="validated",
        sdl_sections=sdl_sections,
    )
    _write_catalog(repo_root, catalog)

    assert _rule_ids(repo_root) == expected
