"""Task-contract admission and supplied-task binding for experiment plans."""

from __future__ import annotations

import json
from functools import partial
from pathlib import Path

import pytest
from paths import REPO_ROOT
from raes_cli.main import app
from raes_conformance.conformance import validate_contract_payload
from raes_contracts.contracts import ExperimentTaskModel
from raes_contracts.experiment_spec import (
    ExperimentSpecValidationError,
    load_experiment_spec,
    parse_experiment_spec,
)
from typer.testing import CliRunner

_FIXTURES = REPO_ROOT / "contracts/fixtures/experiment-core"
_TASK = _FIXTURES / "experiment-task-v1/valid/reference.json"
_SPEC = _FIXTURES / "experiment-authoring-input-v1/valid/reference.json"


@pytest.mark.parametrize("valid", [True, False])
def test_task_contract_validation_reaches_the_cli(tmp_path: Path, valid: bool) -> None:
    fixture = _TASK if valid else _FIXTURES / "experiment-task-v1/invalid/scenario-ref-is-run.json"
    payload = json.loads(fixture.read_text())
    source = tmp_path / "task.json"
    source.write_text(json.dumps(payload))

    diagnostics = validate_contract_payload("experiment-task-v1", payload)
    result = CliRunner().invoke(
        app, ["semantic", "validate", "--contract", "experiment-task-v1", str(source), "--output", "json"]
    )

    assert bool(diagnostics) is not valid
    assert result.exit_code == (0 if valid else 1), result.output
    assert json.loads(result.stdout)["status"] == ("success" if valid else "invalid")


@pytest.mark.parametrize("loader", ["parse", "load"])
@pytest.mark.parametrize("reference", ["exact", "id-only", "wrong-id", "wrong-version"])
def test_supplied_task_is_bound_by_id_and_declared_version(tmp_path: Path, loader: str, reference: str) -> None:
    task = ExperimentTaskModel.model_validate_json(_TASK.read_text())
    payload = json.loads(_SPEC.read_text())
    payload["task_ref"] = {"ref_kind": "task", "ref_id": task.task_id, "ref_version": task.task_version}
    if reference == "id-only":
        del payload["task_ref"]["ref_version"]
    elif reference == "wrong-id":
        payload["task_ref"]["ref_id"] = "another-task"
    elif reference == "wrong-version":
        payload["task_ref"]["ref_version"] = "2.0.0"
    source = tmp_path / "plan.exp.yaml"
    source.write_text(json.dumps(payload))

    def load():
        if loader == "parse":
            return parse_experiment_spec(source.read_text(), path=source, task=task)
        return load_experiment_spec(source, task=task)

    if reference.startswith("wrong"):
        with pytest.raises(ExperimentSpecValidationError) as caught:
            load()
        assert caught.value.code == "task-reference-mismatch"
        assert caught.value.path == source
        assert "another-task" not in str(caught.value)
    else:
        assert load().task_ref.ref_id == task.task_id


def test_task_is_optional_and_unresolved_references_remain_descriptive() -> None:
    payload = json.loads(_SPEC.read_text())
    payload["task_ref"]["ref_id"] = "not-acquired"
    assert parse_experiment_spec(json.dumps(payload)).task_ref.ref_id == "not-acquired"


@pytest.mark.parametrize("loader", ["parse", "load"])
def test_invalid_date_raises_a_validation_error(tmp_path: Path, loader: str) -> None:
    source = tmp_path / "invalid.exp.yaml"
    source.write_text("schema_version: experiment-authoring-input/v1\ndescription: 2026-02-30\n")
    operation = (
        partial(parse_experiment_spec, source.read_text(), path=source)
        if loader == "parse"
        else partial(load_experiment_spec, source)
    )
    with pytest.raises(ExperimentSpecValidationError) as caught:
        operation()
    assert caught.value.code == "invalid-yaml"
    assert caught.value.path == source
