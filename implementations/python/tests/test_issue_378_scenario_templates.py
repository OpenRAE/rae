"""Template validation-command rules for the example library (issue #378)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml
from test_example_library_policy import _seed_repo, _write_yaml
from tools.check_example_library import evaluate_example_library

_TEMPLATE_PATH = "examples/library/templates/scenario/template.yaml"
_MISSING = object()


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
