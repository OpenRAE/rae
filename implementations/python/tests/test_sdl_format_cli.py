"""Tests for canonical SDL formatting and migration CLI surfaces."""

from __future__ import annotations

import pytest
import raes_cli.sdl as sdl_commands
from raes import format_sdl_source
from raes_cli.main import app
from raes_contracts.errors import ConflictError, OperationalError
from typer.testing import CliRunner

SECRET = "sentinel-registry-token-1678"
_REGISTRY_FAILURE = "a module registry, cache or layout operation failed (OperationalError)"


def test_format_api_migrates_fields_and_expands_shorthands() -> None:
    result = format_sdl_source(
        """\
Name: migrate-me
Nodes:
  web-app:
    Type: VM
    roles: {admin: operator}
infrastructure:
  web-app: 1
"""
    )

    assert result.content.startswith("name: migrate-me\nnodes:\n  web-app:\n    type: compute\n")
    assert "username: operator" in result.content
    assert "count: 1" in result.content
    assert "concern: compute-substrate" in result.content
    assert "value: virtual-machine" in result.content
    assert [item.code for item in result.diagnostics] == [
        "sdl.noncanonical_field",
        "sdl.noncanonical_field",
        "sdl.noncanonical_field",
        "sdl.legacy_node_type_vm",
    ]


def test_format_cli_supports_stdout_write_and_check(tmp_path) -> None:
    source = tmp_path / "scenario.yaml"
    source.write_text("Name: cli-format\n", encoding="utf-8")
    runner = CliRunner()

    stdout_result = runner.invoke(app, ["sdl", "format", str(source)])
    assert stdout_result.exit_code == 0
    assert "name: cli-format" in stdout_result.stdout
    assert "sdl.noncanonical_field" in stdout_result.stderr
    assert source.read_text(encoding="utf-8") == "Name: cli-format\n"

    check_result = runner.invoke(app, ["sdl", "format", str(source), "--check"])
    assert check_result.exit_code == 1

    write_result = runner.invoke(app, ["sdl", "format", str(source), "--write"])
    assert write_result.exit_code == 0
    assert source.read_text(encoding="utf-8") == "name: cli-format\n"

    clean_check = runner.invoke(app, ["sdl", "format", str(source), "--check"])
    assert clean_check.exit_code == 0


@pytest.mark.parametrize(
    ("command", "patched", "error", "expected"),
    [
        ("format", "format_sdl_source", OperationalError, _REGISTRY_FAILURE),
        ("resolve", "resolve_lock_records", OperationalError, _REGISTRY_FAILURE),
        ("verify-imports", "load_lockfile", OperationalError, _REGISTRY_FAILURE),
        ("publish", "publish_module_to_oci_layout", OperationalError, _REGISTRY_FAILURE),
        (
            "publish",
            "publish_module_to_oci_layout",
            ConflictError,
            "conflicts with the existing layout (ConflictError)",
        ),
    ],
)
def test_sdl_commands_report_expected_failures_on_stderr_without_values(
    tmp_path, monkeypatch, command, patched, error, expected
) -> None:
    source = tmp_path / "scenario.yaml"
    source.write_text("name: probe\n", encoding="utf-8")

    def _fail(*_args, **_kwargs):
        raise error(f"Failed to fetch OCI metadata from https://user:{SECRET}@registry.example/v2")

    monkeypatch.setattr(sdl_commands, patched, _fail)
    result = CliRunner().invoke(app, ["sdl", command, str(source)])

    # An expected failure exits 1 with one value-free line, not 70 from the application boundary.
    assert result.exit_code == 1
    assert isinstance(result.exception, SystemExit)
    assert result.stdout == ""
    assert result.stderr.count("\n") == 1
    assert expected in result.stderr
    assert SECRET not in result.output


def test_sdl_resolve_reports_a_malformed_import_declaration_without_values(tmp_path) -> None:
    source = tmp_path / "scenario.yaml"
    source.write_text(f"name: probe\nimports:\n  - source: local:{SECRET}.yaml\n", encoding="utf-8")

    result = CliRunner().invoke(app, ["sdl", "resolve", str(source)])

    assert result.exit_code == 1
    assert "the input was rejected (ValidationError)" in result.stderr
    assert SECRET not in result.output
    assert not (tmp_path / "raes.lock.json").exists()
