"""Unquoted invalid YAML timestamps are reported as invalid experiment-spec YAML (issue #1563)."""

from __future__ import annotations

from pathlib import Path

import pytest
from raes_contracts.experiment_spec import (
    ExperimentSpecValidationError,
    load_experiment_spec,
    parse_experiment_spec,
)
from raes_mcp.tools.experiment_authoring import _run_experiment_validate

_HEADER = "schema_version: experiment-authoring-input/v1\n"
_INVALID_YAML_DETAILS = "Experiment spec YAML is invalid."


@pytest.mark.parametrize(
    ("extra", "rejected"),
    [
        pytest.param("description: 2026-02-30\n", "2026-02-30", id="day-out-of-range"),
        pytest.param("description: 2026-13-01\n", "2026-13-01", id="month-out-of-range"),
        pytest.param("description: 0000-01-01\n", "0000-01-01", id="year-zero"),
        pytest.param("description: 2026-01-01 25:00:00\n", "25:00:00", id="hour-out-of-range"),
        pytest.param("description: 2026-01-01T00:00:00+99:00\n", "+99:00", id="offset-out-of-range"),
        pytest.param("a:\n  2026-02-30: x\n", "2026-02-30", id="nested-mapping-key"),
    ],
)
def test_parse_rejects_unquoted_invalid_timestamp_as_invalid_yaml(extra: str, rejected: str) -> None:
    with pytest.raises(ExperimentSpecValidationError) as excinfo:
        parse_experiment_spec(_HEADER + extra)

    exc = excinfo.value
    assert exc.code == "invalid-yaml"
    assert exc.details == _INVALID_YAML_DETAILS
    assert isinstance(exc.__cause__, ValueError)
    assert rejected not in str(exc)


def test_load_rejects_unquoted_invalid_date_with_path(tmp_path: Path) -> None:
    spec_path = tmp_path / "x.exp.yaml"
    spec_path.write_text(_HEADER + "description: 2026-02-30\n", encoding="utf-8")

    with pytest.raises(ExperimentSpecValidationError) as excinfo:
        load_experiment_spec(spec_path)

    exc = excinfo.value
    assert exc.code == "invalid-yaml"
    assert exc.path == spec_path
    assert str(exc) == f"x.exp.yaml: {_INVALID_YAML_DETAILS}"


def test_mcp_validate_reports_invalid_date_as_validation_error() -> None:
    result = _run_experiment_validate(_HEADER + "description: 2026-02-30\n")

    assert result.startswith("VALIDATION ERROR")
    assert _INVALID_YAML_DETAILS in result
    assert "2026-02-30" not in result


def test_valid_unquoted_date_still_reaches_contract_validation() -> None:
    with pytest.raises(ExperimentSpecValidationError) as excinfo:
        parse_experiment_spec(_HEADER + "description: 2026-02-28\n")

    assert excinfo.value.code == "contract-invalid"
