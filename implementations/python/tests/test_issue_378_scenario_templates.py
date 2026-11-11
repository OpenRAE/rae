"""Template validation-command rules for the example library (issue #378)."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import pytest
import yaml
from test_example_library_policy import _seed_repo, _write_yaml
from tools.check_example_library import evaluate_example_library

_TEMPLATE_PATH = "examples/library/templates/scenario/template.yaml"
_MISSING = object()
_REPO_ROOT = Path(__file__).resolve().parents[3]
_CATALOG = yaml.safe_load((_REPO_ROOT / "examples/library/catalog.yaml").read_text(encoding="utf-8"))
_CATALOG_PATHS = [
    entry["path"]
    for surface in _CATALOG["surfaces"].values()
    for field in ("worked_examples", "templates", "patterns")
    for entry in surface[field]
]
_SHIPPED_TEMPLATES = sorted(
    entry["path"] for surface in _CATALOG["surfaces"].values() for entry in surface["templates"]
)
_BODY_LINE = "\nbody:\n"


@pytest.mark.parametrize(
    ("validation", "rule_id"),
    (
        pytest.param(_MISSING, "example-library-template-field", id="missing"),
        pytest.param([], "example-library-template-validation", id="empty"),
        pytest.param("python tools/check_example_library.py", "example-library-template-validation", id="not-a-list"),
        pytest.param(
            ["python tools/check_example_library.py"], "example-library-template-validation", id="step-not-a-mapping"
        ),
        pytest.param(
            [{"command": "raes semantic validate x.sdl.yaml"}], "example-library-template-validation", id="no-expected"
        ),
        pytest.param(
            [{"command": "  ", "expected": "exits 0"}], "example-library-template-validation", id="blank-command"
        ),
    ),
)
def test_template_validation_violation_is_the_only_failure(tmp_path: Path, validation: Any, rule_id: str) -> None:
    repo_root = _seed_repo(tmp_path)
    template_path = repo_root / _TEMPLATE_PATH
    template = yaml.safe_load(template_path.read_text(encoding="utf-8"))
    if validation is _MISSING:
        del template["validation"]
    else:
        template["validation"] = validation
    _write_yaml(template_path, template)

    assert [failure.rule_id for failure in evaluate_example_library(repo_root)] == [rule_id]


def _copy_library(tmp_path: Path) -> Path:
    """Copy examples/ and every catalog path outside it, such as the sem-208 test module.

    The copy marks worked examples as guidance, so the gate checks only that
    they exist and does not spend most of its time parsing them.
    """
    shutil.copytree(_REPO_ROOT / "examples", tmp_path / "examples")
    for relative in _CATALOG_PATHS:
        if not (tmp_path / relative).exists():
            (tmp_path / relative).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(_REPO_ROOT / relative, tmp_path / relative)
    catalog = yaml.safe_load((tmp_path / "examples/library/catalog.yaml").read_text(encoding="utf-8"))
    for surface in catalog["surfaces"].values():
        for entry in surface["worked_examples"]:
            entry["validation_status"] = "guidance"
    _write_yaml(tmp_path / "examples/library/catalog.yaml", catalog)
    return tmp_path


@pytest.mark.parametrize("template_path", _SHIPPED_TEMPLATES)
def test_shipped_template_with_a_duplicate_body_key_fails_the_gate(tmp_path: Path, template_path: str) -> None:
    # Each template's gate step says that the gate rejects duplicate keys.
    repo_root = _copy_library(tmp_path)
    template_file = repo_root / template_path
    source = template_file.read_text(encoding="utf-8")
    assert source.count(_BODY_LINE) == 1
    duplicated = _BODY_LINE + "  description: First.\n  description: Second.\n"
    template_file.write_text(source.replace(_BODY_LINE, duplicated), encoding="utf-8")

    failures = evaluate_example_library(repo_root)

    assert [(failure.rule_id, failure.path) for failure in failures] == [("example-library-parse", template_path)]
