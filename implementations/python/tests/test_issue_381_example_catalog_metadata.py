"""Catalog entry metadata rules for the example library (issue #381)."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
import yaml
from raes import SDLParseError, load_sdl_fragment
from test_example_library_policy import _VALID_BODY, _read_catalog, _seed_repo, _write_catalog
from tools import example_library_checks
from tools.check_example_library import evaluate_example_library
from tools.example_library_checks import sdl_body_source

_Mutation = Callable[[dict[str, Any]], None]
_WORKED_SDL_PATH = "examples/scenarios/worked.sdl.yaml"
_VALID_SDL = yaml.safe_dump(_VALID_BODY, sort_keys=False).encode("utf-8")


def _set(field: str, key: str, value: Any) -> _Mutation:
    def mutate(catalog: dict[str, Any]) -> None:
        catalog["surfaces"]["scenario"][field][0][key] = value

    return mutate


def _rule_ids(repo_root: Path) -> list[str]:
    return [failure.rule_id for failure in evaluate_example_library(repo_root)]


def _seed_worked_sdl(tmp_path: Path, sdl_source: bytes, sections_by_surface: dict[str, list[str]]) -> Path:
    """Point each named surface's worked example at one validated SDL file."""
    repo_root = _seed_repo(tmp_path)
    worked_file = repo_root / _WORKED_SDL_PATH
    worked_file.parent.mkdir(parents=True)
    worked_file.write_bytes(sdl_source)
    catalog = _read_catalog(repo_root)
    for surface, sdl_sections in sections_by_surface.items():
        catalog["surfaces"][surface]["worked_examples"][0].update(
            path=_WORKED_SDL_PATH,
            validation_status="validated",
            sdl_sections=sdl_sections,
        )
    _write_catalog(repo_root, catalog)
    return repo_root


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
        # sdl-yaml/v1 resolves plain scalars with YAML 1.2 Core, so these are strings.
        pytest.param(
            _VALID_SDL + b"description: 2026-02-30\n", ["nodes", "workflows"], [], id="core-date-spelling-is-a-string"
        ),
        pytest.param(_VALID_SDL + b"description: =\n", ["nodes", "workflows"], [], id="core-equals-sign-is-a-string"),
        pytest.param(
            _VALID_SDL + b"description: 2026-02-30\n",
            ["stories"],
            ["example-library-entry-sections"],
            id="core-date-spelling-section-absent",
        ),
    ),
)
def test_validated_worked_example_is_parsed_as_sdl(
    tmp_path: Path, sdl_source: bytes, sdl_sections: list[str], expected: list[str]
) -> None:
    assert _rule_ids(_seed_worked_sdl(tmp_path, sdl_source, {"scenario": sdl_sections})) == expected


def test_absent_section_failure_names_the_catalog_entry(tmp_path: Path) -> None:
    # Two entries share one file, as the hospital and satcom worked examples do in the catalog.
    repo_root = _seed_worked_sdl(tmp_path, _VALID_SDL, {"scenario": ["nodes"], "run": ["stories"]})

    failures = evaluate_example_library(repo_root)

    assert [failure.rule_id for failure in failures] == ["example-library-entry-sections"]
    assert "run-worked" in failures[0].message


_TEMPLATE_PATH = "examples/library/templates/scenario/template.yaml"
_BODY_NAME_LINE = "  name: scenario-template\n"


@pytest.mark.parametrize(
    ("old", "new", "expected", "diagnostic"),
    (
        pytest.param(
            _BODY_NAME_LINE,
            _BODY_NAME_LINE + "  description: First.\n  description: Second.\n",
            ["example-library-parse"],
            "sdl.mapping_key_conflict",
            id="duplicate-body-key",
        ),
        pytest.param(
            "      type: compute\n",
            "      <<: {type: compute}\n",
            ["example-library-parse"],
            "sdl.noncanonical_merge",
            id="merge-key",
        ),
        pytest.param(
            _BODY_NAME_LINE,
            "  name: !!str scenario-template\n",
            ["example-library-parse"],
            "Explicit YAML tags",
            id="explicit-tag",
        ),
        # sdl-yaml/v1 accepts an acyclic alias within its limits, as parse_sdl does.
        pytest.param(
            _BODY_NAME_LINE,
            "  name: &shared scenario-template\n  description: *shared\n",
            [],
            "",
            id="acyclic-alias-accepted",
        ),
        # YAML 1.2 Core reads this as a string; yaml.safe_load raises ValueError on it.
        pytest.param(_BODY_NAME_LINE, _BODY_NAME_LINE + "  description: 2026-02-30\n", [], "", id="core-date-spelling"),
        # sdl-yaml/v1 keeps this quoted value a string; yaml.safe_dump writes it unquoted, which reads back as an int.
        pytest.param(
            "      interval: 30\n",
            "      interval: '0o36'\n",
            ["example-library-template-body"],
            "interval must be an integer",
            id="quoted-octal-string",
        ),
        # parse_sdl accepts this text; a surrogate-pair escape of the emoji would read back as two lone surrogates.
        pytest.param(
            _BODY_NAME_LINE, _BODY_NAME_LINE + "  description: smile \U0001f600\n", [], "", id="non-bmp-character"
        ),
        # YAML escapes for characters the sdl-yaml/v1 reader rejects or reads as line breaks when written raw.
        pytest.param(
            _BODY_NAME_LINE,
            _BODY_NAME_LINE + '  description: "\\x7f \\x85 \\x9f \\L \\P \\uFFFE \\uFFFF"\n',
            [],
            "",
            id="yaml-special-characters",
        ),
    ),
)
def test_template_file_is_read_with_the_sdl_yaml_loader(
    tmp_path: Path, old: str, new: str, expected: list[str], diagnostic: str
) -> None:
    repo_root = _seed_repo(tmp_path)
    template_file = repo_root / _TEMPLATE_PATH
    source = template_file.read_text(encoding="utf-8")
    assert source.count(old) == 1
    template_file.write_text(source.replace(old, new), encoding="utf-8")

    failures = evaluate_example_library(repo_root)

    assert [failure.rule_id for failure in failures] == expected
    assert all(diagnostic in failure.message and failure.path == _TEMPLATE_PATH for failure in failures)


@pytest.mark.parametrize(
    "character",
    (
        pytest.param("\U0001f600", id="non-bmp"),
        pytest.param("\x7f", id="delete"),
        pytest.param("\x80", id="first-c1-control"),
        pytest.param("\x85", id="next-line"),
        pytest.param("\x9f", id="last-c1-control"),
        pytest.param("\u2028", id="line-separator"),
        pytest.param("\u2029", id="paragraph-separator"),
        pytest.param("\ufeff", id="byte-order-mark"),
        pytest.param("\ufffe", id="noncharacter-fffe"),
        pytest.param("\uffff", id="noncharacter-ffff"),
    ),
)
def test_template_body_source_reads_back_as_the_loaded_body(character: str) -> None:
    # Spaces around the character catch the line folding that a raw NEL, U+2028, or U+2029 gets.
    body = {"name": "scenario-template", "description": f" a {character} b "}

    assert load_sdl_fragment(sdl_body_source(body)) == body


def test_invalid_template_sdl_is_reported_as_a_policy_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    def reject(_source: str) -> None:
        raise SDLParseError("template body is not a mapping")

    monkeypatch.setattr(example_library_checks, "parse_sdl", reject)

    failures = example_library_checks.check_template_body({}, dict(_VALID_BODY), "template.yaml")

    assert [failure.rule_id for failure in failures] == ["example-library-template-body"]
    assert "template body is not a mapping" in failures[0].message


def test_a_parser_defect_is_not_reported_as_invalid_sdl(monkeypatch: pytest.MonkeyPatch) -> None:
    # A defect in the parser must reach the boundary as a failure, never pass as an authoring finding.
    def defect(_source: str) -> None:
        raise KeyError("secret-sentinel")

    monkeypatch.setattr(example_library_checks, "parse_sdl", defect)

    with pytest.raises(KeyError, match="secret-sentinel"):
        example_library_checks.check_template_body({}, dict(_VALID_BODY), "template.yaml")
