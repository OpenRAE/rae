"""Behavioral contract for the human-facing RAES semantic CLI."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from paths import REPO_ROOT
from raes_cli.main import app
from typer.testing import CliRunner

_SDL = """\
name: semantic-cli
nodes:
  network:
    type: switch
"""


def _write_sdl(tmp_path: Path) -> Path:
    source = tmp_path / "scenario.sdl.yaml"
    source.write_text(_SDL, encoding="utf-8")
    return source


def test_semantic_help_lists_required_operations() -> None:
    result = CliRunner().invoke(app, ["semantic", "--help"])

    assert result.exit_code == 0, result.output
    for operation in ("parse", "validate", "normalize", "resolve", "compile", "transform", "inspect", "conformance"):
        assert operation in result.output


@pytest.mark.parametrize(
    ("operation", "extra", "exit_code", "status", "phase"),
    [
        ("parse", [], 0, "success", "parsed-authoring"),
        ("validate", [], 0, "success", "validated-authoring"),
        ("normalize", [], 0, "success", "normalized-authoring"),
        ("resolve", [], 0, "success", "resolved-references"),
        ("compile", [], 0, "success", "compiled-runtime-summary"),
        ("transform", ["--transform", "canonical"], 0, "success", "transformed"),
        ("inspect", [], 0, "success", "inspection"),
        ("conformance", [], 3, "unsupported", None),
    ],
)
def test_sdl_operations_emit_one_deterministic_typed_json_result(
    tmp_path: Path,
    operation: str,
    extra: list[str],
    exit_code: int,
    status: str,
    phase: str | None,
) -> None:
    source = _write_sdl(tmp_path)
    argv = [
        "semantic",
        operation,
        str(source),
        "--contract",
        "sdl-yaml/v1",
        "--output",
        "json",
        *extra,
    ]

    first = CliRunner().invoke(app, argv)
    second = CliRunner().invoke(app, argv)

    assert first.exit_code == exit_code, first.output
    assert first.stdout == second.stdout
    assert first.stderr == ""
    assert first.stdout.endswith("\n")
    payload = json.loads(first.stdout)
    assert payload["operation"] == operation
    assert payload["status"] == status
    assert payload["contract_id"] == "sdl-yaml/v1"
    assert payload["source_format"] == "sdl-yaml/v1"
    assert payload["migration_policy"] == "reject"
    assert payload["diagnostics"] == []
    if phase is not None:
        assert payload["payload"]["phase"] == phase


def test_sdl_resolve_and_inspect_have_distinct_phase_results(tmp_path: Path) -> None:
    source = _write_sdl(tmp_path)
    runner = CliRunner()
    common = [str(source), "--contract", "sdl-yaml/v1", "--output", "json"]

    resolve_payload = json.loads(runner.invoke(app, ["semantic", "resolve", *common]).stdout)["payload"]
    inspect_payload = json.loads(runner.invoke(app, ["semantic", "inspect", *common]).stdout)["payload"]

    assert resolve_payload["phase"] == "resolved-references"
    assert resolve_payload["reference_bindings"]
    assert "declarations" not in resolve_payload
    assert inspect_payload["phase"] == "inspection"
    assert inspect_payload["declarations"]
    assert "reference_bindings" not in inspect_payload


def test_file_and_stdin_share_the_same_semantic_result(tmp_path: Path) -> None:
    source = _write_sdl(tmp_path)
    runner = CliRunner()
    common = [
        "--contract",
        "sdl-yaml/v1",
        "--output",
        "json",
    ]

    file_result = runner.invoke(app, ["semantic", "validate", str(source), *common])
    stdin_result = runner.invoke(app, ["semantic", "validate", "-", *common], input=_SDL)

    assert file_result.exit_code == stdin_result.exit_code == 0
    file_payload = json.loads(file_result.stdout)
    stdin_payload = json.loads(stdin_result.stdout)
    assert file_payload == stdin_payload


def test_portable_contract_conformance_reuses_the_owning_registry() -> None:
    source = REPO_ROOT / "contracts" / "fixtures" / "control-plane" / "operation-status-v1" / "valid" / "succeeded.json"

    result = CliRunner().invoke(
        app,
        [
            "semantic",
            "conformance",
            str(source),
            "--contract",
            "operation-status-v1",
            "--output",
            "json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["status"] == "success"
    assert payload["contract_id"] == "operation-status-v1"
    assert payload["validation_strength"] == "semantic"
    assert payload["payload"]["phase"] == "contract-conformance"
    assert payload["payload"]["passed"] is True


def test_portable_operations_keep_distinct_phase_contracts() -> None:
    source = REPO_ROOT / "contracts" / "fixtures" / "control-plane" / "operation-status-v1" / "valid" / "succeeded.json"
    runner = CliRunner()
    common = [str(source), "--contract", "operation-status-v1", "--output", "json"]

    parse_result = runner.invoke(app, ["semantic", "parse", *common])
    validate_result = runner.invoke(app, ["semantic", "validate", *common])
    inspect_result = runner.invoke(app, ["semantic", "inspect", *common])

    assert parse_result.exit_code == 3
    assert json.loads(parse_result.stdout)["status"] == "unsupported"
    assert json.loads(validate_result.stdout)["payload"]["phase"] == "contract-admission"
    assert json.loads(validate_result.stdout)["payload"]["admitted"] is True
    inspection = json.loads(inspect_result.stdout)["payload"]
    assert inspection["phase"] == "inspection"
    assert inspection["members"]
    assert "admitted" not in inspection


@pytest.mark.parametrize(
    ("operation", "phase", "outcome_field"),
    [
        ("validate", "contract-admission", "admitted"),
        ("inspect", "inspection", None),
        ("conformance", "contract-conformance", "passed"),
    ],
)
def test_portable_operations_reject_invalid_registered_contract_payload(
    operation: str,
    phase: str,
    outcome_field: str | None,
) -> None:
    source = (
        REPO_ROOT
        / "contracts"
        / "fixtures"
        / "control-plane"
        / "operation-status-v1"
        / "invalid"
        / "unknown-extra.json"
    )

    result = CliRunner().invoke(
        app,
        [
            "semantic",
            operation,
            str(source),
            "--contract",
            "operation-status-v1",
            "--output",
            "json",
        ],
    )

    assert result.exit_code == 1, result.output
    payload = json.loads(result.stdout)
    assert payload["status"] == "invalid"
    assert payload["diagnostics"]
    assert payload["payload"]["phase"] == phase
    if outcome_field is not None:
        assert payload["payload"][outcome_field] is False


def test_portable_event_stream_accepts_array_root_from_stdin() -> None:
    source = (
        REPO_ROOT
        / "contracts"
        / "fixtures"
        / "control-plane"
        / "workflow-history-event-stream-v1"
        / "valid"
        / "started.json"
    )

    result = CliRunner().invoke(
        app,
        [
            "semantic",
            "validate",
            "-",
            "--contract",
            "workflow-history-event-stream-v1",
            "--output",
            "json",
        ],
        input=source.read_text(encoding="utf-8"),
    )

    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["payload"]["root_type"] == "array"


def test_invalid_input_is_value_free_and_uses_exit_one(tmp_path: Path) -> None:
    marker = "SECRET-MARKER"
    source = tmp_path / f"{marker}.yaml"
    source.write_text(f"name: [{marker}\n", encoding="utf-8")

    result = CliRunner().invoke(
        app,
        [
            "semantic",
            "validate",
            str(source),
            "--contract",
            "sdl-yaml/v1",
            "--output",
            "json",
        ],
    )

    assert result.exit_code == 1
    assert marker not in result.stdout
    assert marker not in result.stderr
    assert "Traceback" not in result.output
    payload = json.loads(result.stdout)
    assert payload["status"] == "invalid"
    assert payload["diagnostics"]


def test_unknown_contract_is_usage_error_exit_two(tmp_path: Path) -> None:
    source = _write_sdl(tmp_path)

    result = CliRunner().invoke(
        app,
        [
            "semantic",
            "validate",
            str(source),
            "--contract",
            "unknown-contract-v1",
            "--output",
            "json",
        ],
    )

    assert result.exit_code == 2
    assert "unknown-contract-v1" not in result.output


def test_unsupported_contract_operation_uses_exit_three() -> None:
    source = REPO_ROOT / "contracts" / "fixtures" / "control-plane" / "operation-status-v1" / "valid" / "succeeded.json"

    result = CliRunner().invoke(
        app,
        [
            "semantic",
            "normalize",
            str(source),
            "--contract",
            "operation-status-v1",
            "--output",
            "json",
        ],
    )

    assert result.exit_code == 3
    assert json.loads(result.stdout)["status"] == "unsupported"


def test_bounded_input_failure_uses_exit_four(tmp_path: Path) -> None:
    result = CliRunner().invoke(
        app,
        [
            "semantic",
            "validate",
            str(tmp_path / "missing.sdl.yaml"),
            "--contract",
            "sdl-yaml/v1",
            "--output",
            "json",
        ],
    )

    assert result.exit_code == 4
    assert json.loads(result.stdout)["status"] == "operational"


def test_unexpected_failure_is_sanitized_and_uses_exit_seventy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _write_sdl(tmp_path)

    def _unexpected(*args: object, **kwargs: object) -> None:
        del args, kwargs
        raise RuntimeError("SECRET-MARKER")

    monkeypatch.setattr("raes_cli._semantic_sdl.parse_sdl", _unexpected)
    result = CliRunner().invoke(
        app,
        [
            "semantic",
            "validate",
            str(source),
            "--contract",
            "sdl-yaml/v1",
            "--output",
            "json",
        ],
    )

    assert result.exit_code == 70
    assert "SECRET-MARKER" not in result.output
    assert json.loads(result.stdout)["status"] == "internal"


def test_effective_migration_profile_is_explicit_in_result(tmp_path: Path) -> None:
    source = tmp_path / "legacy.sdl.yaml"
    source.write_text("Name: migrated\n", encoding="utf-8")

    result = CliRunner().invoke(
        app,
        [
            "semantic",
            "normalize",
            str(source),
            "--contract",
            "sdl-yaml/v1",
            "--migration-policy",
            "accept",
            "--output",
            "json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["migration_policy"] == "accept"
    assert payload["normalization_profile"] == "raes-sdl-semantic/v2"
    assert payload["diagnostics"][0]["code"] == "sdl.noncanonical_field"


def test_semantic_operations_are_offline_and_read_only(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = _write_sdl(tmp_path)
    before = sorted(path.relative_to(tmp_path) for path in tmp_path.rglob("*"))
    before_contents = {path.relative_to(tmp_path): path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()}

    def _network_forbidden(*args: object, **kwargs: object) -> None:
        del args, kwargs
        raise AssertionError("semantic CLI attempted network access")

    monkeypatch.setattr("socket.create_connection", _network_forbidden)
    result = CliRunner().invoke(
        app,
        [
            "semantic",
            "resolve",
            str(source),
            "--contract",
            "sdl-yaml/v1",
            "--output",
            "json",
        ],
    )

    assert result.exit_code == 0, result.output
    after = sorted(path.relative_to(tmp_path) for path in tmp_path.rglob("*"))
    assert after == before
    after_contents = {path.relative_to(tmp_path): path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()}
    assert after_contents == before_contents
