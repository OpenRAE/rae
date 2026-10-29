"""Tests for the ``raes processor plan`` plan-inspection CLI (issue #609)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import raes_cli.processor as processor_commands
import yaml
from paths import EXAMPLES_DIR
from raes._errors import (
    SDLInstantiationError,
    SDLParseDiagnostic,
    SDLParseError,
    SDLSourcePosition,
    SDLSourceRange,
    SDLValidationError,
)
from raes_backend_protocols.manifest import BackendManifestInvalidError, backend_manifest_payload
from raes_backend_stubs.manifest import create_stub_manifest
from raes_cli.main import app
from raes_cli.processor import _sdl_error_summary
from raes_contracts.contracts import (
    EvaluationPlanModel,
    OrchestrationPlanModel,
    ProvisioningPlanModel,
)
from raes_contracts.errors import InvalidInputError, OperationalError
from typer.testing import CliRunner

_SCENARIO = EXAMPLES_DIR / "techvault-defensive-min.sdl.yaml"
_ENVELOPE_IDENTITY = {
    "contract_id": "realization-envelope-v1",
    "envelope_id": "example-envelope",
    "schema_version": "realization-envelope/v1",
    "digest": "sha256:" + "0" * 64,
    "configuration_digest": "sha256:" + "1" * 64,
}


def _invoke(*args: str):
    return CliRunner().invoke(app, ["processor", "plan", *args])


def _scenario_supported_by_default_manifest(tmp_path: Path) -> Path:
    payload = yaml.safe_load(_SCENARIO.read_text(encoding="utf-8"))
    for node in payload["nodes"].values():
        node.pop("os", None)
        node.pop("os_distribution", None)
        node.pop("os_version", None)
    # The dry-run stub deliberately does not claim independent runtime-environment
    # readback. Keep these generic CLI contract tests on its supported surface;
    # issue #1074 and issue #1078 cover generated environment delivery and the
    # fail-closed realization diagnostic directly.
    payload["nodes"]["wazuh-dashboard"].pop("runtime", None)
    payload["generated_artifacts"].pop("wazuh-dashboard-api-token")
    path = tmp_path / _SCENARIO.name
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    return path


def test_plan_default_manifest_emits_contract_json(tmp_path: Path) -> None:
    result = _invoke(str(_scenario_supported_by_default_manifest(tmp_path)), "--format", "json")

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert set(payload) == {"scenario_name", "provisioning", "orchestration", "evaluation", "diagnostics"}
    assert payload["scenario_name"] == "techvault-defensive-min"

    # Each domain member independently validates against its published plan contract
    # -- the same models that admit contracts/fixtures/plans/*.
    ProvisioningPlanModel.model_validate(payload["provisioning"])
    OrchestrationPlanModel.model_validate(payload["orchestration"])
    EvaluationPlanModel.model_validate(payload["evaluation"])
    provisioning_ops = payload["provisioning"]["operations"]
    assert provisioning_ops, "expected provisioning operations for defensive-min"
    # Operation payload content -- the field real backends consume -- survives
    # end-to-end through the CLI, not just the operations list being non-empty.
    assert any(op["payload"] for op in provisioning_ops)


def test_plan_output_is_deterministic(tmp_path: Path) -> None:
    scenario = _scenario_supported_by_default_manifest(tmp_path)
    first = _invoke(str(scenario), "--format", "json")
    second = _invoke(str(scenario), "--format", "json")

    assert first.exit_code == 0
    assert first.stdout == second.stdout


def test_plan_accepts_supplied_backend_manifest(tmp_path: Path) -> None:
    manifest_file = tmp_path / "stub-manifest.json"
    manifest_file.write_text(json.dumps(backend_manifest_payload(create_stub_manifest())), encoding="utf-8")

    result = _invoke(
        str(_scenario_supported_by_default_manifest(tmp_path)), "--manifest", str(manifest_file), "--format", "json"
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    ProvisioningPlanModel.model_validate(payload["provisioning"])


def test_plan_emits_full_json_and_nonzero_exit_on_error_diagnostics(tmp_path: Path) -> None:
    payload = backend_manifest_payload(create_stub_manifest())
    # A manifest that cannot provision compute resources turns its compute nodes into a
    # capability gap: the planner reports error diagnostics rather than raising.
    payload["capabilities"]["provisioner"]["supported_node_types"] = ["switch"]
    manifest_file = tmp_path / "no-vm-manifest.json"
    manifest_file.write_text(json.dumps(payload), encoding="utf-8")

    result = _invoke(
        str(_scenario_supported_by_default_manifest(tmp_path)), "--manifest", str(manifest_file), "--format", "json"
    )

    assert result.exit_code == 1
    emitted = json.loads(result.stdout)  # the full plan is still emitted
    error_codes = {diagnostic["code"] for diagnostic in emitted["diagnostics"] if diagnostic["severity"] == "error"}
    assert "provisioner.unsupported-node-type" in error_codes


def test_plan_invalid_sdl_fails_without_partial_json(tmp_path: Path) -> None:
    bad = tmp_path / "broken.sdl.yaml"
    bad.write_text("name: [unclosed\n", encoding="utf-8")

    result = _invoke(str(bad), "--format", "json")

    assert result.exit_code == 1
    assert result.stdout.strip() == ""
    assert "could not compile" in result.stderr
    # Sanitized single-line summary, not a raw multi-line exception dump.
    assert result.stderr.count("\n") <= 1
    assert "Traceback" not in result.stderr


def test_sdl_error_summary_redacts_message_and_source() -> None:
    source = Path("scenario.sdl.yaml")
    parse_error = SDLParseError(
        "boom SECRETMARKER",
        diagnostics=[
            SDLParseDiagnostic(
                code="sdl.duplicate-key",
                message="rejected value SECRETMARKER",
                pointer="/nodes",
                primary_range=SDLSourceRange(SDLSourcePosition(3, 5), SDLSourcePosition(3, 9)),
            )
        ],
    )
    parse_summary = _sdl_error_summary(source, parse_error)
    assert "SECRETMARKER" not in parse_summary
    assert "sdl.duplicate-key@3:5" in parse_summary

    validation_summary = _sdl_error_summary(
        source, SDLValidationError(errors=["undefined node SECRETMARKER", "bad ref SECRETMARKER"])
    )
    assert "SECRETMARKER" not in validation_summary
    assert "2 SDL validation errors" in validation_summary

    instantiation_summary = _sdl_error_summary(source, SDLInstantiationError(errors=["unbound parameter SECRETMARKER"]))
    assert "SECRETMARKER" not in instantiation_summary
    assert "1 SDL instantiation error" in instantiation_summary


def test_plan_invalid_manifest_does_not_leak_rejected_value(tmp_path: Path) -> None:
    payload = backend_manifest_payload(create_stub_manifest())
    # A rejected controlled-vocabulary value must not escape into stderr/logs.
    payload["capabilities"]["provisioner"]["supported_node_types"] = ["ZZLEAKMARKER99"]
    manifest_file = tmp_path / "leaky-manifest.json"
    manifest_file.write_text(json.dumps(payload), encoding="utf-8")

    result = _invoke(
        str(_scenario_supported_by_default_manifest(tmp_path)), "--manifest", str(manifest_file), "--format", "json"
    )

    assert result.exit_code != 0
    assert result.stdout.strip() == ""
    assert "ZZLEAKMARKER99" not in result.stderr
    assert "backend-manifest-v2" in result.stderr


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (InvalidInputError, "SDL compilation failed (InvalidInputError)"),
        (OperationalError, "an SDL module import could not be fetched or cached (OperationalError)"),
    ],
)
def test_plan_reports_compiler_and_import_failures_without_values(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, error: type[Exception], expected: str
) -> None:
    def _refuse(*_args: object, **_kwargs: object) -> None:
        raise error("observation scope does not resolve: SECRETMARKER")

    monkeypatch.setattr(processor_commands, "run_reference_processor", _refuse)
    result = _invoke(str(_scenario_supported_by_default_manifest(tmp_path)), "--format", "json")

    assert result.exit_code == 1
    assert result.stdout.strip() == ""
    assert expected in result.stderr
    assert result.stderr.count("\n") <= 1
    assert "SECRETMARKER" not in result.output


def test_plan_manifest_rejected_by_capability_validation_is_a_bad_parameter(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _reject(_model: object) -> None:
        raise BackendManifestInvalidError("backend manifest was rejected by backend capability validation")

    monkeypatch.setattr(processor_commands, "backend_manifest_from_v2_model", _reject)
    manifest_file = tmp_path / "manifest.json"
    manifest_file.write_text(json.dumps(backend_manifest_payload(create_stub_manifest())), encoding="utf-8")

    result = _invoke(
        str(_scenario_supported_by_default_manifest(tmp_path)), "--manifest", str(manifest_file), "--format", "json"
    )

    assert result.exit_code == 2
    assert result.stdout.strip() == ""
    assert "rejected by backend capability validation" in result.stderr


def test_plan_manifest_with_realization_envelope_fails_closed(tmp_path: Path) -> None:
    payload = backend_manifest_payload(create_stub_manifest())
    payload["supported_contract_versions"].append("realization-envelope-v1")
    payload["realization_envelope"] = dict(_ENVELOPE_IDENTITY)
    manifest_file = tmp_path / "envelope-manifest.json"
    manifest_file.write_text(json.dumps(payload), encoding="utf-8")

    result = _invoke(
        str(_scenario_supported_by_default_manifest(tmp_path)), "--manifest", str(manifest_file), "--format", "json"
    )

    assert result.exit_code != 0
    assert result.stdout.strip() == ""
    assert "realization envelope" in result.stderr


def test_plan_rejects_non_json_manifest(tmp_path: Path) -> None:
    manifest_file = tmp_path / "not-json.json"
    manifest_file.write_text("this is not json", encoding="utf-8")

    result = _invoke(
        str(_scenario_supported_by_default_manifest(tmp_path)), "--manifest", str(manifest_file), "--format", "json"
    )

    assert result.exit_code != 0
    assert result.stdout.strip() == ""


def test_plan_requires_explicit_format(tmp_path: Path) -> None:
    result = _invoke(str(_scenario_supported_by_default_manifest(tmp_path)))

    assert result.exit_code != 0
