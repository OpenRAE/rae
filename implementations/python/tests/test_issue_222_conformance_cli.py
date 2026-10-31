"""JSON/text parity at the installed command interface."""

import json

from raes_cli.main import app
from typer.testing import CliRunner


def test_backend_text_and_json_agree_on_missing_corpus(tmp_path):
    runner = CliRunner()
    args = ["conformance", "backend", "--profile", "provisioning-only", "--fixtures-root", str(tmp_path)]
    machine = runner.invoke(app, args)
    human = runner.invoke(app, [*args, "--format", "text"])
    assert machine.exit_code == human.exit_code == 1
    payload = json.loads(machine.output)
    assert payload["summary"]["achieved_profile"] is None
    assert "achieved: none" in human.output
    for diag in payload["diagnostics"]:
        assert diag["code"] in human.output


def test_processor_cli_uses_same_result_and_exit_status_in_both_formats():
    runner = CliRunner()
    machine = runner.invoke(app, ["conformance", "processor"])
    human = runner.invoke(app, ["conformance", "processor", "--format", "text"])
    assert machine.exit_code == human.exit_code == 0, machine.output + human.output
    payload = json.loads(machine.output)
    assert payload["subject_kind"] == "processor"
    assert "processor conformance: passed" in human.output
    assert payload["profile"] in human.output
    assert "native conformance: false" in human.output


def test_processor_cli_reports_unverified_support_and_invalid_format():
    runner = CliRunner()
    machine = runner.invoke(app, ["conformance", "processor", "--feature", "runtime-control-plane"])
    human = runner.invoke(app, ["conformance", "processor", "--feature", "runtime-control-plane", "--format", "text"])
    assert machine.exit_code == human.exit_code == 1
    assert json.loads(machine.output)["unsupported_capability_gaps"] == ["runtime-control-plane"]
    assert "runtime-control-plane" in human.output
    assert runner.invoke(app, ["conformance", "backend", "--format", "html"]).exit_code == 2
