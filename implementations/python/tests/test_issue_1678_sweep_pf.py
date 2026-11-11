"""Area PF input failures stay refusals after the narrowed handlers (ADR-116, issue #1678).

Each case feeds input that once reached a broad handler. The narrowed handler must
still return the same refusal, and an unrelated defect must still propagate.
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from dataclasses import replace

import pytest
from raes_contracts.diagnostics import DiagnosticModel, Severity

SENTINEL = "sentinel-pf-1678-value"
DEFECT = "SENTINEL-DEFECT-DETAIL"
# The interpreter refuses to convert an integer literal with more than 4300 digits.
_TOO_MANY_DIGITS = "9" * 5000
_TOO_DEEP = "[" * 200_000 + "]" * 200_000


# --- Authoring-path comparison: the path output is untrusted input -----------------------------------------


def _authoring_case(case_id: str):
    from raes_conformance.authoring_adapters import load_authoring_vectors, reference_authoring_output

    vector = next(item for item in load_authoring_vectors() if item.case_id == case_id)
    return vector, reference_authoring_output(vector)


def _parse_diagnostic_output(**changes: object):
    vector, output = _authoring_case("duplicate-key")
    return vector, output, replace(output, diagnostics=(replace(output.diagnostics[0], **changes),))


def _unpaired_surrogate_pointer():
    return _parse_diagnostic_output(pointer="/\udc80" + SENTINEL)


def _unpaired_surrogate_message():
    return _parse_diagnostic_output(message="\udc80" + SENTINEL)


def _unhashable_severity():
    return _parse_diagnostic_output(severity=["error"])


def _absent_diagnostic_collection():
    vector, output = _authoring_case("duplicate-key")
    return vector, output, replace(output, diagnostics=None)


def _non_text_output_source():
    vector, output = _authoring_case("strict-source")
    return vector, output, replace(output, output_source=output.output_source.encode("utf-8"))


def _unserializable_diagnostic_carrier():
    vector, output = _authoring_case("strict-source")
    carrier = DiagnosticModel.model_construct(
        code=object(), domain="sdl", address="", message=SENTINEL, severity=Severity.WARNING
    )
    return vector, output, replace(output, diagnostics=(carrier,))


def _unserializable_transformation_report():
    vector, output = _authoring_case("rename-node")
    report = output.transformation_report
    forged = type(report).model_construct(**{**dict(report), "derivation_digest": object()})
    return vector, output, replace(output, transformation_report=forged)


@pytest.mark.parametrize(
    "build",
    [
        _unpaired_surrogate_pointer,
        _unpaired_surrogate_message,
        _unhashable_severity,
        _absent_diagnostic_collection,
        _non_text_output_source,
        _unserializable_diagnostic_carrier,
        _unserializable_transformation_report,
    ],
)
def test_malformed_authoring_path_output_is_an_invalid_side(build) -> None:
    from raes_conformance.authoring_adapters import compare_authoring_paths

    vector, output, malformed = build()
    report = compare_authoring_paths(vector, output, malformed).report

    assert "right-invalid" in report.reason_codes
    assert report.right is None
    assert not report.conformant
    assert SENTINEL not in report.model_dump_json()


def test_authoring_observation_defect_still_propagates(monkeypatch: pytest.MonkeyPatch) -> None:
    from raes_conformance import _authoring_observations
    from raes_conformance.authoring_adapters import compare_authoring_paths

    def defect(_items: object) -> str:
        raise ValueError(DEFECT)

    vector, output = _authoring_case("duplicate-key")
    monkeypatch.setattr(_authoring_observations, "canonical_json_digest", defect)
    with pytest.raises(ValueError, match=DEFECT):
        compare_authoring_paths(vector, output, output)


# --- Participant control manifest support ------------------------------------------------------------------


def test_participant_control_manifest_without_a_canonical_form_is_unresolved() -> None:
    from participant_control_contract_fixtures import evaluation_payload
    from raes_backend_protocols.participant_control_admission import resolve_participant_control_support
    from raes_contracts.contracts.participant_control_composition import ParticipantControlEvaluationModel
    from raes_contracts.errors import ConflictError
    from test_api_424_capability_admission import manifest_with_modular_support

    # RFC 8785 refuses an unpaired surrogate, so this manifest has no digest that can match the declaration.
    manifest = replace(manifest_with_modular_support(), constraints={"note": "\udc80" + SENTINEL})
    record = ParticipantControlEvaluationModel.model_validate(evaluation_payload())

    with pytest.raises(ConflictError, match="participant control manifest support is unresolved") as refused:
        resolve_participant_control_support(manifest, record.support[0])
    assert SENTINEL not in str(refused.value)


def test_participant_control_digest_defect_still_propagates(monkeypatch: pytest.MonkeyPatch) -> None:
    from participant_control_contract_fixtures import evaluation_payload
    from raes_backend_protocols import participant_control_admission
    from raes_contracts.contracts.participant_control_composition import ParticipantControlEvaluationModel
    from test_api_424_capability_admission import manifest_with_modular_support

    def defect(_record: object) -> str:
        raise ValueError(DEFECT)

    monkeypatch.setattr(participant_control_admission, "control_digest", defect)
    record = ParticipantControlEvaluationModel.model_validate(evaluation_payload())
    manifest = manifest_with_modular_support()
    with pytest.raises(ValueError, match=DEFECT):
        participant_control_admission.resolve_participant_control_support(manifest, record.support[0])


# --- Live conformance: participant execution readback isolates the backend ---------------------------------


def test_failing_participant_execution_readback_is_a_sanitized_diagnostic(caplog: pytest.LogCaptureFixture) -> None:
    from implementations.python.tests.test_dsl_437_benign_participant_execution import (
        _autonomous_manifest,
        _NativeParticipantRuntime,
    )
    from implementations.python.tests.test_issue_898_participant_execution_control import (
        _two_green_participant_scenario,
    )
    from raes_backend_stubs.stubs import create_stub_target
    from raes_conformance.conformance.profiles import BackendCapabilityProfile
    from raes_conformance.conformance.target_probes import _target_adapter_cases
    from raes_processor.compiler import compile_runtime_model

    class _FailingReadbackRuntime(_NativeParticipantRuntime):
        def execution_state(self, execution_scope_ref, snapshot):
            raise ValueError(f"backend readback detail {SENTINEL}")

    target = replace(
        create_stub_target(),
        manifest=_autonomous_manifest(compile_runtime_model(_two_green_participant_scenario())),
        participant_runtime=_FailingReadbackRuntime(),
    )

    with caplog.at_level(logging.ERROR, logger="raes_conformance"):
        cases = _target_adapter_cases(target, BackendCapabilityProfile.FULL_REMOTE_CONTROL_PLANE)

    start = next(case for case in cases if case.name == "participant-execution-start")
    assert start.passed is False
    assert [item.code for item in start.diagnostics] == ["conformance.participant-execution-readback-missing"]
    assert all(SENTINEL not in item.message for case in cases for item in case.diagnostics)
    records = [record for record in caplog.records if record.name.endswith("participant_execution_probes")]
    assert records
    for record in records:
        assert SENTINEL not in record.getMessage()
        assert SENTINEL not in (record.exc_text or "")
        assert "ForeignCodeFailure" in (record.exc_text or "")
        assert "ValueError" not in (record.exc_text or "")


# --- JSON ingress: decoder limits are invalid JSON, not unexpected failures --------------------------------


@pytest.mark.parametrize("document", ['{"identity": ' + _TOO_MANY_DIGITS + "}", _TOO_DEEP], ids=["digits", "depth"])
def test_plan_manifest_beyond_the_decoder_limits_is_a_bad_parameter(tmp_path, document: str) -> None:
    from paths import EXAMPLES_DIR
    from raes_cli.main import app
    from typer.testing import CliRunner

    manifest = tmp_path / "manifest.json"
    manifest.write_text(document, encoding="utf-8")
    scenario = EXAMPLES_DIR / "techvault-defensive-min.sdl.yaml"

    result = CliRunner().invoke(
        app, ["processor", "plan", str(scenario), "--manifest", str(manifest), "--format", "json"]
    )

    assert result.exit_code == 2
    assert result.exception is None or isinstance(result.exception, SystemExit)
    assert "manifest is not valid JSON" in result.stderr
    assert result.stdout.strip() == ""


@pytest.mark.parametrize("document", ['{"profile": ' + _TOO_MANY_DIGITS + "}", _TOO_DEEP], ids=["digits", "depth"])
def test_exploit_path_input_beyond_the_decoder_limits_is_rejected(tmp_path, document: str) -> None:
    from raes_processor.exploit_path import ExploitPathOperationalError, analyze_exploit_path_file

    source = tmp_path / "input.json"
    source.write_text(document, encoding="utf-8")

    with pytest.raises(ExploitPathOperationalError, match="input is not valid UTF-8 JSON"):
        analyze_exploit_path_file(source)


def _tool_text(tool: str, arguments: dict[str, str]) -> str:
    from raes_mcp.server import create_server

    result = asyncio.run(create_server().call_tool(tool, arguments))
    return result[0][0].text


_MINIMAL_SDL = "name: probe\n"


def test_mcp_parameters_beyond_the_decoder_limits_are_invalid_json() -> None:
    # The tool byte limit refuses a document deep enough to exhaust the decoder stack before it is decoded.
    document = '{"count": ' + _TOO_MANY_DIGITS + "}"
    instantiated = _tool_text("sdl_instantiate", {"sdl_content": _MINIMAL_SDL, "parameters_json": document})
    assert instantiated.startswith("Invalid JSON in parameters_json")

    compiled = json.loads(_tool_text("sdl_compile", {"sdl_content": _MINIMAL_SDL, "parameters_json": document}))
    assert compiled["status"] == "invalid"
    assert compiled["stage"] == "parameter_parsing"


@pytest.mark.parametrize("document", [_TOO_MANY_DIGITS, _TOO_DEEP], ids=["digits", "depth"])
def test_mcp_edit_value_beyond_the_decoder_limits_is_invalid_json(document: str) -> None:
    result = json.loads(
        _tool_text(
            "sdl_apply_edit",
            {"sdl_content": _MINIMAL_SDL, "operation": "set", "pointer": "/name", "value_json": document},
        )
    )

    assert result["status"] == "invalid"
    assert result["diagnostics"][0]["code"] == "sdl.edit"
    assert result["diagnostics"][0]["message"].startswith("Invalid JSON in value_json")


# --- Pointer tokens: only ASCII digits name an array index ------------------------------------------------

# int() refuses the superscript digit that str.isdigit() accepts, and refuses a token beyond the digit limit.
_NON_INDEX_TOKENS = pytest.mark.parametrize("token", ["²", _TOO_MANY_DIGITS], ids=["superscript", "digits"])


@_NON_INDEX_TOKENS
def test_authority_pointer_with_a_non_index_token_names_no_value(token: str) -> None:
    from raes_processor.planner.realization_authority import _MISSING, _pointer_value

    assert _pointer_value({"limits": [10, 20]}, f"/limits/{token}") is _MISSING
    assert _pointer_value({"limits": [10, 20]}, "/limits/1") == 20


def test_authority_pointer_does_not_read_a_unicode_digit_as_an_index() -> None:
    from raes_processor.planner.realization_authority import _MISSING, _pointer_value

    # int() accepts the Arabic-Indic digit one, but RFC 6901 array indices are ASCII digits.
    assert _pointer_value({"limits": [10, 20]}, "/limits/١") is _MISSING


def _constrained_process_limit_scenario(token: str):
    from raes import instantiate_scenario, parse_sdl
    from test_issue_1066_runtime_resource_limits import _scenario

    source = _scenario(
        """
        - resource: open_file_descriptors
          soft: ${soft_limit}
          hard: 65536
          subject: {name: search}
          scope: subtree
        """,
        variables="""
        variables:
          soft_limit:
            type: integer
            default: 32768
            allowed_values: [16384, 32768, 65536]
        """,
    )
    scenario = instantiate_scenario(parse_sdl(source))
    provenance = scenario.instantiation_provenance
    constraints = tuple(
        item.model_copy(
            update={"field_pointer": item.field_pointer.replace("/process_limits/0/", f"/process_limits/{token}/")}
        )
        for item in provenance.capability_constraints
    )
    return scenario.model_copy(
        update={"instantiation_provenance": provenance.model_copy(update={"capability_constraints": constraints})}
    )


@_NON_INDEX_TOKENS
def test_process_limit_constraint_with_a_non_index_token_is_not_bound(token: str) -> None:
    from raes_processor.compiler.realization_concern_bounds import _compiled_process_resource_limits

    field_pointer = "/nodes/worker/runtime/operational_policy/resource_limits/process_limits"
    authored = [
        {
            "resource": "open_file_descriptors",
            "soft": 32768,
            "hard": 65536,
            "subject": {"name": "search"},
            "scope": "subtree",
        }
    ]

    bound, demands = _compiled_process_resource_limits(
        _constrained_process_limit_scenario("0"), field_pointer=field_pointer, authored_value=authored
    )
    assert [item.leaf for item in bound] == ["soft"]
    unbound, same_demands = _compiled_process_resource_limits(
        _constrained_process_limit_scenario(token), field_pointer=field_pointer, authored_value=authored
    )
    assert unbound == ()
    assert same_demands == demands


@pytest.mark.parametrize("key", ["١٢٣", "¹²"], ids=["arabic-indic", "superscript"])
def test_attacker_named_unicode_digit_location_is_redacted(key: str) -> None:
    from pydantic import ValidationError
    from raes_conformance.conformance.diagnostics import sanitized_failure_message

    payload = {"code": "test.code", "domain": "sdl", "address": "", "message": "m", "severity": "warning", key: 1}
    with pytest.raises(ValidationError) as rejected:
        DiagnosticModel.model_validate(payload)

    message = sanitized_failure_message(rejected.value)
    assert "extra_forbidden" in message
    assert key not in message
    assert "<field>" in message


# --- Backend conformance fixture suite: an undecodable fixture is an invalid payload ------------------------

_UNDECODABLE_FIXTURES = pytest.mark.parametrize(
    ("document", "reason"),
    [
        (b"{not json", "payload is not valid JSON"),
        (b"\xff\xfe{}", "payload is not valid UTF-8"),
        (b'{"receipt": ' + _TOO_MANY_DIGITS.encode() + b"}", "payload exceeds the JSON decoder limits"),
        (_TOO_DEEP.encode(), "payload exceeds the JSON decoder limits"),
    ],
    ids=["syntax", "utf8", "digits", "depth"],
)


def _fixture_tree(tmp_path):
    """Return a fixture tree for one required contract and the backend profile tree that requires it."""

    profiles = tmp_path / "profiles"
    profiles.mkdir()
    profile = {
        "schema_version": "backend-profile/v1",
        "profile": "provisioning-only",
        "required_contracts": ["operation-receipt-v1"],
    }
    (profiles / "provisioning-only.json").write_text(json.dumps(profile), encoding="utf-8")
    fixtures = tmp_path / "fixtures"
    (fixtures / "operation-receipt-v1" / "valid").mkdir(parents=True)
    return fixtures, profiles


def _fixture_corpus(tmp_path, document: bytes, *, directory: str):
    fixtures, profiles = _fixture_tree(tmp_path)
    target = fixtures / "operation-receipt-v1" / directory
    target.mkdir(exist_ok=True)
    (target / "undecodable.json").write_bytes(document)
    return fixtures, profiles


def _backend_command(fixtures, profiles) -> list[str]:
    return [
        "raes",
        "conformance",
        "backend",
        "--profile",
        "provisioning-only",
        "--fixtures-root",
        str(fixtures),
        "--profiles-root",
        str(profiles),
    ]


@pytest.fixture
def restore_root_logging():
    # The application entry point configures logging; keep the root logger of the other tests unchanged.
    root = logging.getLogger()
    handlers = list(root.handlers)
    level = root.level
    yield
    for handler in list(root.handlers):
        if handler not in handlers:
            root.removeHandler(handler)
    root.setLevel(level)


@_UNDECODABLE_FIXTURES
@pytest.mark.parametrize("directory", ["valid", "invalid"])
def test_undecodable_fixture_gets_the_invalid_payload_refusal(tmp_path, document, reason, directory) -> None:
    from raes_conformance.conformance.fixture_suite import run_fixture_suite

    fixtures, profiles = _fixture_corpus(tmp_path, document, directory=directory)

    report = run_fixture_suite(profile="provisioning-only", root=fixtures, profiles_root=profiles)

    [case] = report.cases
    assert (case.name, case.valid) == ("undecodable", directory == "valid")
    assert [(item.code, item.address, item.message) for item in case.diagnostics] == [
        (
            "conformance.schema-invalid",
            "operation-receipt-v1",
            f"operation-receipt-v1 failed contract validation: {reason}",
        )
    ]
    # A valid fixture fails, while an invalid fixture passes its expected rejection.
    assert case.passed is (directory == "invalid")
    # An invalid-only corpus has no positive coverage, so ASR-526 keeps the aggregate incomplete.
    assert report.passed is False
    assert bool(report.diagnostics) is (directory == "invalid")
    if directory == "invalid":
        assert report.diagnostics[0].code == "conformance.fixture-missing"


def test_backend_conformance_command_reports_an_undecodable_fixture(tmp_path) -> None:
    from raes_cli.main import app
    from typer.testing import CliRunner

    fixtures, profiles = _fixture_corpus(tmp_path, b"{not json", directory="valid")

    result = CliRunner().invoke(
        app,
        [
            "conformance",
            "backend",
            "--profile",
            "provisioning-only",
            "--fixtures-root",
            str(fixtures),
            "--profiles-root",
            str(profiles),
        ],
    )

    assert result.exit_code == 1
    assert result.exception is None or isinstance(result.exception, SystemExit)
    report = json.loads(result.stdout)
    assert report["passed"] is False
    assert [diagnostic["code"] for case in report["cases"] for diagnostic in case["diagnostics"]] == [
        "conformance.schema-invalid"
    ]


@pytest.mark.parametrize("directory", ["valid", "invalid"])
def test_unreadable_fixture_fails_the_whole_conformance_command(
    tmp_path, monkeypatch, capsys, restore_root_logging, directory
) -> None:
    import raes_cli.entrypoint as cli_entrypoint

    fixtures, profiles = _fixture_tree(tmp_path)
    # A directory named like a fixture file cannot be read as one, in either fixture directory.
    (fixtures / "operation-receipt-v1" / directory / "x.json").mkdir(parents=True)
    monkeypatch.setattr(sys, "argv", _backend_command(fixtures, profiles))

    with pytest.raises(SystemExit) as exited:
        cli_entrypoint.main()

    captured = capsys.readouterr()
    assert exited.value.code == 1
    assert captured.out == ""
    assert captured.err == "error: the conformance fixture corpus could not be read\n"
    assert str(tmp_path) not in captured.out + captured.err


def test_unreadable_fixture_is_an_operational_failure_without_host_detail(tmp_path) -> None:
    from raes_conformance.conformance.fixture_suite import run_fixture_suite
    from raes_contracts.errors import OperationalError

    fixtures, profiles = _fixture_tree(tmp_path)
    (fixtures / "operation-receipt-v1" / "valid" / "x.json").mkdir()

    with pytest.raises(OperationalError) as failed:
        run_fixture_suite(profile="provisioning-only", root=fixtures, profiles_root=profiles)

    assert str(failed.value) == "conformance fixture could not be read"
    assert isinstance(failed.value.__cause__, OSError)


def test_fixture_suite_defect_is_not_a_corpus_read_failure(tmp_path, monkeypatch, capsys, restore_root_logging) -> None:
    import raes_cli.entrypoint as cli_entrypoint
    from raes_conformance.conformance import fixture_suite

    def defect(_contract_name: str, _payload: object) -> list[object]:
        raise ValueError(DEFECT)

    fixtures, profiles = _fixture_corpus(tmp_path, b"{}", directory="valid")
    monkeypatch.setattr(fixture_suite, "_fixture_case_diagnostics", defect)
    with pytest.raises(ValueError, match=DEFECT):
        fixture_suite.run_fixture_suite(profile="provisioning-only", root=fixtures, profiles_root=profiles)

    monkeypatch.setattr(sys, "argv", _backend_command(fixtures, profiles))
    with pytest.raises(SystemExit) as exited:
        cli_entrypoint.main()

    # The application boundary reports the defect as an unexpected failure, not as a corpus read failure.
    captured = capsys.readouterr()
    assert exited.value.code == 70
    assert "could not be read" not in captured.err
    assert DEFECT not in captured.out + captured.err


def _unloadable_profile(tmp_path, kind: str):
    fixtures, profiles = _fixture_tree(tmp_path)
    profile = profiles / "provisioning-only.json"
    profile.unlink()
    if kind == "directory":
        profile.mkdir()
    else:
        profile.write_text(_TOO_DEEP, encoding="utf-8")
    return fixtures, profiles


@pytest.mark.parametrize(("kind", "reason"), [("directory", "IsADirectoryError"), ("depth", "RecursionError")])
def test_unloadable_backend_profile_is_a_profile_load_diagnostic(tmp_path, kind: str, reason: str) -> None:
    from raes_cli.main import app
    from typer.testing import CliRunner

    fixtures, profiles = _unloadable_profile(tmp_path, kind)

    result = CliRunner().invoke(app, _backend_command(fixtures, profiles)[1:])

    assert result.exit_code == 1
    assert result.exception is None or isinstance(result.exception, SystemExit)
    report = json.loads(result.stdout)
    assert report["passed"] is False
    assert [(item["code"], item["message"]) for item in report["diagnostics"]] == [
        (
            "conformance.profile-load-failed",
            f"Failed to load published backend profile 'provisioning-only': rejected by {reason}",
        )
    ]
    assert str(tmp_path) not in result.output


def test_backend_profile_loader_defect_still_propagates(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    from raes_conformance.conformance import profiles as profile_module
    from raes_conformance.conformance.fixture_suite import run_fixture_suite

    def defect(*_args: object, **_kwargs: object) -> frozenset[str]:
        raise KeyError(DEFECT)

    fixtures, profiles = _fixture_tree(tmp_path)
    monkeypatch.setattr(profile_module, "required_contracts", defect)

    with pytest.raises(KeyError, match=DEFECT):
        run_fixture_suite(profile="provisioning-only", root=fixtures, profiles_root=profiles)


# --- Participant temporal probe: only the contract owners' refusals become guarantee failures ---------------


def _temporal_fixture():
    from implementations.python.tests._act_614_temporal_fixtures import (
        _bound_deadline_payload,
        _temporal_target,
        _TemporalEvidenceRuntime,
    )

    return _temporal_target(_bound_deadline_payload(), _TemporalEvidenceRuntime())


def _guarantee_failures(case) -> list[str]:
    return [
        item.message for item in case.diagnostics if item.code == "conformance.participant-temporal-guarantee-failed"
    ]


def test_temporal_probe_refuses_an_invalid_stochastic_control_set() -> None:
    from raes_conformance.conformance.participant_temporal_probes import participant_temporal_scenario_case
    from raes_contracts.contracts import ExperimentStochasticControlModel

    control = ExperimentStochasticControlModel.model_validate({"control_id": SENTINEL, "role": "agent-policy"})
    scenario, target = _temporal_fixture()

    # The runtime configuration refuses an agent-policy control without an executable binding with ValueError.
    case = participant_temporal_scenario_case(target, scenario, stochastic_controls=(control,))

    assert not case.passed
    assert _guarantee_failures(case) == ["rejected by ValueError"]
    assert SENTINEL not in repr(case)
    assert target.participant_runtime.native_actions == []


def test_temporal_probe_refuses_invalid_temporal_evidence(monkeypatch: pytest.MonkeyPatch) -> None:
    from raes_conformance.conformance import participant_temporal_probes as probes

    def refuse(_snapshot: object) -> None:
        raise ValueError(SENTINEL)

    monkeypatch.setattr(probes, "require_participant_temporal_history", refuse)
    scenario, target = _temporal_fixture()

    case = probes.participant_temporal_scenario_case(target, scenario)

    assert not case.passed
    assert _guarantee_failures(case) == ["rejected by ValueError"]
    assert SENTINEL not in repr(case)
    assert case.cleanup_verified is None


def test_temporal_probe_defect_is_not_a_guarantee_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    from raes_conformance.conformance import participant_temporal_probes as probes

    def defect(_plan: object) -> set[str]:
        raise ValueError(DEFECT)

    monkeypatch.setattr(probes, "_required_temporal_contract_digests", defect)
    scenario, target = _temporal_fixture()

    with pytest.raises(ValueError, match=DEFECT):
        probes.participant_temporal_scenario_case(target, scenario)


# The profile-load diagnostic quotes only the typed identity refusal, never interpreter text (ADR-116 rule E7).


def test_profile_load_diagnostic_does_not_quote_an_untyped_value_error(tmp_path):
    from raes_conformance.conformance import BackendCapabilityProfile, run_fixture_suite

    backend_dir = tmp_path / "backend"
    backend_dir.mkdir()
    (backend_dir / "provisioning-only.json").write_text('{"profile": ' + "7" * 5000 + "}", encoding="utf-8")

    report = run_fixture_suite(profile=BackendCapabilityProfile.PROVISIONING_ONLY, profiles_root=backend_dir)

    [diagnostic] = [item for item in report.diagnostics if item.code == "conformance.profile-load-failed"]
    assert "rejected by ValueError" in diagnostic.message
    assert "limit" not in diagnostic.message


def test_profile_identity_refusal_is_typed_and_keeps_its_safe_text(tmp_path):
    from raes_contracts.backend_profiles import BackendProfileIdentityError, load_backend_profile_from_path
    from raes_contracts.errors import InvalidInputError

    path = tmp_path / "provisioning-only.json"
    path.write_text(
        json.dumps({"profile": "full-remote-control-plane", "required_contracts": ["backend-manifest-v2"]}),
        encoding="utf-8",
    )

    with pytest.raises(BackendProfileIdentityError, match="full-remote-control-plane") as refused:
        load_backend_profile_from_path("provisioning-only", path)
    assert isinstance(refused.value, InvalidInputError)
    assert str(tmp_path) not in str(refused.value)
