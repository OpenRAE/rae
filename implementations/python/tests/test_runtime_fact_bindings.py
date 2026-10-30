"""SCE-002/SCE-004 typed runtime fact binding behavior."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError
from raes_conformance.conformance import validate_contract_payload
from raes_contracts.contracts import schema_bundle
from raes_contracts.contracts.runtime_facts import (
    RuntimeFactAbsenceDisposition,
    RuntimeFactAudience,
    RuntimeFactBindingDisposition,
    RuntimeFactBindingPlaneModel,
    RuntimeFactBindingRequestModel,
    RuntimeFactBindingSelectionModel,
    RuntimeFactDeclarationModel,
    RuntimeFactScopeKind,
    RuntimeFactScopeModel,
    RuntimeFactSensitivity,
    RuntimeFactSinkModel,
    RuntimeFactSourceKind,
    RuntimeFactValueType,
    RuntimeFactVersionModel,
    RuntimeFactVisibilityModel,
)
from raes_contracts.errors import ConflictError
from raes_runtime.runtime_fact_bindings import (
    RuntimeFactActionDisposition,
    RuntimeFactBindingAdmission,
    RuntimeFactBindingPlane,
    RuntimeFactDispatchCommand,
)


def _host_declaration() -> RuntimeFactDeclarationModel:
    return RuntimeFactDeclarationModel(
        fact_id="fact.observed-host",
        value_type=RuntimeFactValueType.STRING,
        source_kind=RuntimeFactSourceKind.OBSERVATION,
        sensitivity=RuntimeFactSensitivity.INTERNAL,
        visibility=RuntimeFactVisibilityModel(
            participant_addresses=["participant.behavior.red-agent"],
            workflow_addresses=["workflow.main"],
        ),
        authority_refs=["policy.runtime-facts"],
    )


def _host_version(*, version_id: str = "fact-version.host.1", sequence: int = 1) -> RuntimeFactVersionModel:
    return RuntimeFactVersionModel(
        fact_id="fact.observed-host",
        version_id=version_id,
        sequence=sequence,
        value_type=RuntimeFactValueType.STRING,
        source_kind=RuntimeFactSourceKind.OBSERVATION,
        sensitivity=RuntimeFactSensitivity.INTERNAL,
        scope=RuntimeFactScopeModel(
            kind=RuntimeFactScopeKind.EPISODE,
            run_id="run-791",
            participant_address="participant.behavior.red-agent",
            episode_id="episode-1",
        ),
        observed_at="2026-07-20T03:00:00Z",
        value="10.0.0.23",
        confidence=1.0,
        evidence_refs=["evidence.network-scan.1"],
        provenance_refs=["observation.network-scan.1"],
    )


def _host_sink() -> RuntimeFactSinkModel:
    return RuntimeFactSinkModel(
        sink_id="sink.scan-target",
        action_contract_address="participant.action-contract.scan",
        target_field="input.target.host",
        value_type=RuntimeFactValueType.STRING,
        allowed_source_kinds=[RuntimeFactSourceKind.OBSERVATION],
        allowed_scope_kinds=[RuntimeFactScopeKind.EPISODE],
        allowed_sensitivities=[RuntimeFactSensitivity.INTERNAL],
        max_age_seconds=300,
        authority_refs=["policy.runtime-facts"],
        audience=RuntimeFactAudience.PARTICIPANT,
        absence_disposition=RuntimeFactAbsenceDisposition.FAIL,
    )


def _host_request() -> RuntimeFactBindingRequestModel:
    return RuntimeFactBindingRequestModel(
        run_id="run-791",
        participant_address="participant.behavior.red-agent",
        episode_id="episode-1",
        workflow_address="workflow.main",
        action_instance_id="scan-0001",
        action_contract_address="participant.action-contract.scan",
    )


def _admission(
    request: RuntimeFactBindingRequestModel,
    *,
    sink: RuntimeFactSinkModel | None = None,
    candidate_fact_ids: list[str] | None = None,
    authority_refs: frozenset[str] = frozenset({"policy.runtime-facts"}),
    requested_at: str = "2026-07-20T03:02:00Z",
) -> RuntimeFactBindingAdmission:
    return RuntimeFactBindingAdmission(
        run_id=request.run_id,
        participant_address=request.participant_address,
        episode_id=request.episode_id,
        workflow_address=request.workflow_address,
        action_instance_id=request.action_instance_id,
        action_contract_address=request.action_contract_address,
        requested_at=requested_at,
        authority_refs=authority_refs,
        selections=(
            RuntimeFactBindingSelectionModel(
                sink=_host_sink() if sink is None else sink,
                candidate_fact_ids=["fact.observed-host"] if candidate_fact_ids is None else candidate_fact_ids,
            ),
        ),
    )


def _capture_dispatch(
    captured: dict[str, object],
    *,
    secret_resolver=None,
):
    def dispatch(command: RuntimeFactDispatchCommand) -> None:
        command.dispatch(
            secret_resolver=secret_resolver,
            send=lambda inputs: captured.update(inputs),
        )

    return dispatch


def test_typed_runtime_fact_binds_to_declared_action_sink_with_safe_provenance() -> None:
    request = _host_request()
    dispatched: dict[str, object] = {}
    plane = RuntimeFactBindingPlane(
        admissions=[_admission(request)],
        action_dispatcher=_capture_dispatch(dispatched),
    )
    plane.declare(_host_declaration())
    plane.append(_host_version())

    result = plane.bind_action_inputs(request)

    assert result.accepted is True
    assert result.action_disposition is RuntimeFactActionDisposition.BOUND
    assert dispatched == {"input.target.host": "10.0.0.23"}
    assert not hasattr(result, "inputs")
    assert result.diagnostics == ()
    assert len(result.events) == 1
    event = result.events[0]
    assert event.fact_version_id == "fact-version.host.1"
    assert event.action_instance_id == "scan-0001"
    assert event.evidence_refs == ["evidence.network-scan.1"]
    assert event.provenance_refs == ["observation.network-scan.1"]
    assert "value" not in event.model_dump(mode="json")


def test_fact_history_is_append_only_and_monotonic() -> None:
    plane = RuntimeFactBindingPlane()
    plane.declare(_host_declaration())
    first = _host_version()
    plane.append(first)

    with pytest.raises(ConflictError, match="version_id"):
        plane.append(first)
    invalid_sequence = _host_version(version_id="fact-version.host.3", sequence=3)
    with pytest.raises(ConflictError, match="sequence"):
        plane.append(invalid_sequence)

    second = _host_version(version_id="fact-version.host.2", sequence=2)
    plane.append(second)
    assert plane.history("fact.observed-host") == (first, second)


def test_binding_selects_latest_fact_observed_no_later_than_trusted_admission() -> None:
    request = _host_request()
    dispatched: dict[str, object] = {}
    plane = RuntimeFactBindingPlane(
        admissions=[_admission(request)],
        action_dispatcher=_capture_dispatch(dispatched),
    )
    plane.declare(_host_declaration())
    plane.append(_host_version())
    plane.append(
        _host_version(version_id="fact-version.host.2", sequence=2).model_copy(
            update={
                "observed_at": "2026-07-20T03:05:00Z",
                "value": "10.0.0.99",
            }
        )
    )

    result = plane.bind_action_inputs(request)

    assert result.accepted is True
    assert result.events[0].fact_version_id == "fact-version.host.1"
    assert dispatched == {"input.target.host": "10.0.0.23"}


@pytest.mark.parametrize(
    ("absence_disposition", "expected"),
    [
        (RuntimeFactAbsenceDisposition.BLOCK, RuntimeFactActionDisposition.BLOCKED),
        (RuntimeFactAbsenceDisposition.FAIL, RuntimeFactActionDisposition.FAILED),
        (RuntimeFactAbsenceDisposition.INAPPLICABLE, RuntimeFactActionDisposition.INAPPLICABLE),
    ],
)
def test_missing_fact_honors_compiled_sink_absence_behavior(
    absence_disposition: RuntimeFactAbsenceDisposition,
    expected: RuntimeFactActionDisposition,
) -> None:
    sink = _host_sink().model_copy(update={"absence_disposition": absence_disposition})
    request = _host_request()
    plane = RuntimeFactBindingPlane(admissions=[_admission(request, sink=sink, candidate_fact_ids=["fact.missing"])])

    result = plane.bind_action_inputs(request)

    assert result.accepted is False
    assert result.action_disposition is expected
    assert result.events[0].disposition is RuntimeFactBindingDisposition.ABSENT


@pytest.mark.parametrize(
    ("requested_at", "authority_refs", "expected"),
    [
        (
            "2026-07-20T03:10:00Z",
            frozenset({"policy.runtime-facts"}),
            RuntimeFactBindingDisposition.STALE,
        ),
        (
            "2026-07-20T03:02:00Z",
            frozenset({"policy.other"}),
            RuntimeFactBindingDisposition.UNAUTHORIZED,
        ),
    ],
)
def test_stale_and_unauthorized_facts_fail_closed_with_explicit_disposition(
    requested_at: str,
    authority_refs: frozenset[str],
    expected: RuntimeFactBindingDisposition,
) -> None:
    request = _host_request()
    plane = RuntimeFactBindingPlane(
        admissions=[
            _admission(
                request,
                authority_refs=authority_refs,
                requested_at=requested_at,
            )
        ]
    )
    plane.declare(_host_declaration())
    plane.append(_host_version())

    result = plane.bind_action_inputs(request)

    assert result.accepted is False
    assert result.events[0].disposition is expected
    if expected is RuntimeFactBindingDisposition.UNAUTHORIZED:
        assert result.events[0].fact_id is None
    assert result.diagnostics[0].code == f"runtime.fact-binding.{expected.value}"


def test_missing_and_ambiguous_candidates_do_not_fall_back() -> None:
    first_declaration = _host_declaration()
    second_declaration = first_declaration.model_copy(update={"fact_id": "fact.observed-host.secondary"})
    missing_request = _host_request()
    ambiguous_request = _host_request().model_copy(update={"action_instance_id": "scan-0002"})
    plane = RuntimeFactBindingPlane(
        admissions=[
            _admission(missing_request, candidate_fact_ids=["fact.missing"]),
            _admission(
                ambiguous_request,
                candidate_fact_ids=[first_declaration.fact_id, second_declaration.fact_id],
            ),
        ]
    )
    plane.declare(first_declaration)
    plane.declare(second_declaration)
    plane.append(_host_version())
    plane.append(
        _host_version().model_copy(
            update={
                "fact_id": second_declaration.fact_id,
                "version_id": "fact-version.host.secondary.1",
            }
        )
    )

    missing = plane.bind_action_inputs(missing_request)
    ambiguous = plane.bind_action_inputs(ambiguous_request)

    assert missing.events[0].disposition is RuntimeFactBindingDisposition.ABSENT
    assert ambiguous.events[0].disposition is RuntimeFactBindingDisposition.AMBIGUOUS


def test_wrong_type_scope_and_unsupported_source_are_distinct_failures() -> None:
    request = _host_request()
    wrong_type_sink = _host_sink().model_copy(update={"value_type": RuntimeFactValueType.INTEGER})
    plane = RuntimeFactBindingPlane(
        admissions=[_admission(request, sink=wrong_type_sink)],
        supported_source_kinds={RuntimeFactSourceKind.OBSERVATION},
    )
    plane.declare(_host_declaration())
    plane.append(_host_version())

    wrong_scope_version = _host_version().model_copy(
        update={
            "version_id": "fact-version.host.cross-participant.1",
            "scope": RuntimeFactScopeModel(
                kind=RuntimeFactScopeKind.EPISODE,
                run_id="run-791",
                participant_address="participant.behavior.blue-agent",
                episode_id="episode-1",
            ),
        }
    )

    wrong_type = plane.bind_action_inputs(request)
    plane = RuntimeFactBindingPlane(
        admissions=[_admission(request)],
        supported_source_kinds={RuntimeFactSourceKind.OBSERVATION},
    )
    plane.declare(_host_declaration())
    plane.append(wrong_scope_version)
    wrong_scope = plane.bind_action_inputs(_host_request())
    unsupported = RuntimeFactBindingPlane(
        admissions=[_admission(request)],
        supported_source_kinds={RuntimeFactSourceKind.TOOL_RESULT},
    )
    unsupported.declare(_host_declaration())
    unsupported.append(_host_version())
    unsupported_result = unsupported.bind_action_inputs(_host_request())

    assert wrong_type.events[0].disposition is RuntimeFactBindingDisposition.WRONG_TYPE
    assert wrong_scope.events[0].disposition is RuntimeFactBindingDisposition.ABSENT
    assert wrong_scope.events[0].fact_id is None
    assert unsupported_result.events[0].disposition is RuntimeFactBindingDisposition.UNSUPPORTED


def _secret_declaration() -> RuntimeFactDeclarationModel:
    return RuntimeFactDeclarationModel(
        fact_id="fact.credential-handle",
        value_type=RuntimeFactValueType.STRING,
        source_kind=RuntimeFactSourceKind.SECRET_REFERENCE,
        sensitivity=RuntimeFactSensitivity.SECRET,
        visibility=RuntimeFactVisibilityModel(
            participant_addresses=["participant.behavior.red-agent"],
            workflow_addresses=["workflow.main"],
        ),
        authority_refs=["policy.runtime-secrets"],
    )


def _secret_version() -> RuntimeFactVersionModel:
    return RuntimeFactVersionModel(
        fact_id="fact.credential-handle",
        version_id="fact-version.credential.1",
        sequence=1,
        value_type=RuntimeFactValueType.STRING,
        source_kind=RuntimeFactSourceKind.SECRET_REFERENCE,
        sensitivity=RuntimeFactSensitivity.SECRET,
        scope=RuntimeFactScopeModel(
            kind=RuntimeFactScopeKind.EPISODE,
            run_id="run-791",
            participant_address="participant.behavior.red-agent",
            episode_id="episode-1",
        ),
        observed_at="2026-07-20T03:00:00Z",
        secret_ref="secret://runtime/credential/scan",
        confidence=1.0,
        evidence_refs=["evidence.credential-discovery.1"],
        provenance_refs=["observation.credential-discovery.1"],
    )


def _secret_sink() -> RuntimeFactSinkModel:
    return RuntimeFactSinkModel(
        sink_id="sink.scan-credential",
        action_contract_address="participant.action-contract.scan",
        target_field="input.credential",
        value_type=RuntimeFactValueType.STRING,
        allowed_source_kinds=[RuntimeFactSourceKind.SECRET_REFERENCE],
        allowed_scope_kinds=[RuntimeFactScopeKind.EPISODE],
        allowed_sensitivities=[RuntimeFactSensitivity.SECRET],
        max_age_seconds=300,
        authority_refs=["policy.runtime-secrets"],
        audience=RuntimeFactAudience.PROTECTED_SINK,
        absence_disposition=RuntimeFactAbsenceDisposition.FAIL,
    )


def _secret_request() -> RuntimeFactBindingRequestModel:
    return RuntimeFactBindingRequestModel(
        run_id="run-791",
        participant_address="participant.behavior.red-agent",
        episode_id="episode-1",
        workflow_address="workflow.main",
        action_instance_id="scan-0001",
        action_contract_address="participant.action-contract.scan",
    )


def _secret_admission(request: RuntimeFactBindingRequestModel) -> RuntimeFactBindingAdmission:
    return RuntimeFactBindingAdmission(
        run_id=request.run_id,
        participant_address=request.participant_address,
        episode_id=request.episode_id,
        workflow_address=request.workflow_address,
        action_instance_id=request.action_instance_id,
        action_contract_address=request.action_contract_address,
        requested_at="2026-07-20T03:02:00Z",
        authority_refs=frozenset({"policy.runtime-secrets"}),
        selections=(
            RuntimeFactBindingSelectionModel(
                sink=_secret_sink(),
                candidate_fact_ids=["fact.credential-handle"],
            ),
        ),
    )


def test_secret_reference_resolves_only_inside_trusted_dispatch_and_never_enters_evidence() -> None:
    request = _secret_request()
    dispatched: dict[str, object] = {}
    plane = RuntimeFactBindingPlane(
        admissions=[_secret_admission(request)],
        action_dispatcher=_capture_dispatch(
            dispatched,
            secret_resolver=lambda ref: "super-secret-value",
        ),
    )
    plane.declare(_secret_declaration())
    plane.append(_secret_version())

    result = plane.bind_action_inputs(request)

    assert result.accepted is True
    assert dispatched == {"input.credential": "super-secret-value"}
    assert not hasattr(result, "inputs")
    event_payload = result.events[0].model_dump(mode="json")
    assert "secret://runtime/credential/scan" not in str(event_payload)
    assert "super-secret-value" not in str(event_payload)
    assert event_payload["redacted"] is True


def test_resolved_secret_must_match_the_declared_sink_type() -> None:
    request = _secret_request()
    plane = RuntimeFactBindingPlane(
        admissions=[_secret_admission(request)],
        action_dispatcher=_capture_dispatch({}, secret_resolver=lambda ref: 123),
    )
    plane.declare(_secret_declaration())
    plane.append(_secret_version())

    result = plane.bind_action_inputs(request)

    assert result.accepted is False
    assert result.events[0].disposition is RuntimeFactBindingDisposition.WRONG_TYPE


def test_unavailable_secret_resolver_fails_closed_without_leaking_reference() -> None:
    request = _secret_request()
    plane = RuntimeFactBindingPlane(
        admissions=[_secret_admission(request)],
        action_dispatcher=_capture_dispatch({}),
    )
    plane.declare(_secret_declaration())
    plane.append(_secret_version())

    result = plane.bind_action_inputs(request)

    assert result.accepted is False
    assert result.events[0].disposition is RuntimeFactBindingDisposition.SECRET_UNAVAILABLE
    assert "secret://runtime/credential/scan" not in result.diagnostics[0].message


def test_participant_and_workflow_fact_projections_are_scope_bound_and_secret_redacted() -> None:
    plane = RuntimeFactBindingPlane()
    plane.declare(_host_declaration())
    plane.append(_host_version())
    plane.declare(_secret_declaration())
    plane.append(_secret_version())

    participant_view = plane.project_for_participant(
        run_id="run-791",
        participant_address="participant.behavior.red-agent",
        episode_id="episode-1",
    )
    other_participant_view = plane.project_for_participant(
        run_id="run-791",
        participant_address="participant.behavior.blue-agent",
        episode_id="episode-1",
    )
    workflow_view = plane.project_for_workflow(run_id="run-791", workflow_address="workflow.main")

    assert [item.fact_id for item in participant_view] == ["fact.credential-handle", "fact.observed-host"]
    secret_projection = participant_view[0]
    assert secret_projection.value is None
    assert secret_projection.redacted is True
    assert secret_projection.secret_reference_present is True
    assert other_participant_view == ()
    assert [item.fact_id for item in workflow_view] == ["fact.credential-handle", "fact.observed-host"]


def test_binding_history_is_append_only_and_action_instance_cannot_be_rebound() -> None:
    request = _host_request()
    plane = RuntimeFactBindingPlane(
        admissions=[_admission(request)],
        action_dispatcher=_capture_dispatch({}),
    )
    plane.declare(_host_declaration())
    plane.append(_host_version())
    result = plane.bind_action_inputs(request)

    assert plane.binding_history() == result.events
    with pytest.raises(ConflictError, match="action_instance_id"):
        plane.bind_action_inputs(request)


def test_fact_contracts_reject_identity_rewrites_and_inconsistent_secret_posture() -> None:
    invalid_sink = _host_sink().model_dump(mode="json")
    invalid_sink["target_field"] = "scenario.identity"
    with pytest.raises(ValidationError, match="run-local action input"):
        RuntimeFactSinkModel.model_validate(invalid_sink)

    invalid_declaration = _secret_declaration().model_dump(mode="json")
    invalid_declaration["source_kind"] = "observation"
    with pytest.raises(ValidationError, match="secret_reference"):
        RuntimeFactDeclarationModel.model_validate(invalid_declaration)


def test_runtime_fact_contract_schema_and_fixtures_are_closed_and_conformant() -> None:
    contract_id = "runtime-fact-binding-plane-v1"
    schema = schema_bundle()[contract_id]
    assert schema["additionalProperties"] is False
    validator = Draft202012Validator(schema)
    fixture_root = Path(__file__).resolve().parents[3] / "contracts" / "fixtures" / "participant-runtime" / contract_id

    for path in sorted((fixture_root / "valid").glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert list(validator.iter_errors(payload)) == []
        RuntimeFactBindingPlaneModel.model_validate(payload)

    invalid_paths = sorted((fixture_root / "invalid").glob("*.json"))
    assert invalid_paths
    for path in invalid_paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert list(validator.iter_errors(payload))
        with pytest.raises(ValidationError):
            RuntimeFactBindingPlaneModel.model_validate(payload)


def test_runtime_fact_plane_rejects_dangling_binding_provenance() -> None:
    fixture_path = (
        Path(__file__).resolve().parents[3]
        / "contracts"
        / "fixtures"
        / "participant-runtime"
        / "runtime-fact-binding-plane-v1"
        / "valid"
        / "observation-to-action.json"
    )
    payload = json.loads(fixture_path.read_text(encoding="utf-8"))
    payload["events"][0]["fact_version_id"] = "fact-version.missing"

    with pytest.raises(ValidationError, match="fact_version_id"):
        RuntimeFactBindingPlaneModel.model_validate(payload)

    schema = schema_bundle()["runtime-fact-binding-plane-v1"]
    invariant_ids = {item["id"] for item in schema.get("x-raes-invariants", [])}
    assert "runtime-fact-binding-references-resolve" in invariant_ids


def test_runtime_fact_plane_rejects_forged_event_metadata_for_resolved_version() -> None:
    fixture_path = (
        Path(__file__).resolve().parents[3]
        / "contracts"
        / "fixtures"
        / "participant-runtime"
        / "runtime-fact-binding-plane-v1"
        / "valid"
        / "observation-to-action.json"
    )
    payload = json.loads(fixture_path.read_text(encoding="utf-8"))
    payload["events"][0]["sensitivity"] = "public"
    payload["events"][0]["evidence_refs"] = ["evidence.forged"]

    with pytest.raises(ValidationError, match="binding event metadata must match"):
        RuntimeFactBindingPlaneModel.model_validate(payload)


def test_runtime_fact_plane_rejects_forged_unredacted_secret_projection() -> None:
    fixture_path = (
        Path(__file__).resolve().parents[3]
        / "contracts"
        / "fixtures"
        / "participant-runtime"
        / "runtime-fact-binding-plane-v1"
        / "valid"
        / "secret-reference.json"
    )
    payload = json.loads(fixture_path.read_text(encoding="utf-8"))
    projection = payload["projections"][0]
    projection.update(
        {
            "source_kind": "observation",
            "sensitivity": "internal",
            "value": "exposed-secret",
            "redacted": False,
            "secret_reference_present": False,
        }
    )

    with pytest.raises(ValidationError, match="projection metadata must match"):
        RuntimeFactBindingPlaneModel.model_validate(payload)


def test_runtime_fact_conformance_fixtures_cover_failure_secret_and_cross_participant_cases() -> None:
    fixture_root = (
        Path(__file__).resolve().parents[3]
        / "contracts"
        / "fixtures"
        / "participant-runtime"
        / "runtime-fact-binding-plane-v1"
        / "valid"
    )
    failure_payload = json.loads((fixture_root / "failure-dispositions.json").read_text(encoding="utf-8"))
    secret_payload = json.loads((fixture_root / "secret-reference.json").read_text(encoding="utf-8"))

    dispositions = {event["disposition"] for event in failure_payload["events"]}
    assert dispositions >= {
        "absent",
        "stale",
        "ambiguous",
        "unauthorized",
        "unsupported",
        "wrong_scope",
    }
    assert any(event["participant_address"] == "participant.behavior.other" for event in failure_payload["events"])
    assert secret_payload["versions"][0].get("value") is None
    assert secret_payload["projections"][0]["redacted"] is True
    assert secret_payload["projections"][0].get("value") is None


def test_runtime_fact_contract_is_registered_with_the_conformance_boundary() -> None:
    fixture_root = (
        Path(__file__).resolve().parents[3]
        / "contracts"
        / "fixtures"
        / "participant-runtime"
        / "runtime-fact-binding-plane-v1"
    )
    valid = json.loads((fixture_root / "valid" / "observation-to-action.json").read_text(encoding="utf-8"))
    invalid = json.loads((fixture_root / "invalid" / "additional-property.json").read_text(encoding="utf-8"))

    assert validate_contract_payload("runtime-fact-binding-plane-v1", valid) == ()
    diagnostics = validate_contract_payload("runtime-fact-binding-plane-v1", invalid)
    assert [diagnostic.code for diagnostic in diagnostics] == ["conformance.schema-invalid"]


def test_binding_request_cannot_supply_sinks_candidates_or_authority() -> None:
    invalid_request = {
        "run_id": "run-791",
        "participant_address": "participant.behavior.red-agent",
        "episode_id": "episode-1",
        "workflow_address": "workflow.main",
        "action_instance_id": "scan-0001",
        "action_contract_address": "participant.action-contract.scan",
        "authority_refs": ["policy.runtime-secrets"],
        "selections": [
            {
                "sink": _secret_sink().model_dump(mode="json"),
                "candidate_fact_ids": ["fact.credential-handle"],
            }
        ],
    }
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        RuntimeFactBindingRequestModel.model_validate(invalid_request)


def test_secret_resolution_stays_inside_trusted_dispatch_and_result_is_value_free() -> None:
    request = _secret_request()
    admission = _secret_admission(request)
    dispatched: dict[str, object] = {}

    def dispatch(command: RuntimeFactDispatchCommand) -> None:
        command.dispatch(
            secret_resolver=lambda ref: "super-secret-value",
            send=lambda inputs: dispatched.update(inputs),
        )

    plane = RuntimeFactBindingPlane(admissions=[admission], action_dispatcher=dispatch)
    plane.declare(_secret_declaration())
    plane.append(_secret_version())

    result = plane.bind_action_inputs(request)

    assert result.accepted is True
    assert not hasattr(result, "inputs")
    assert dispatched == {"input.credential": "super-secret-value"}
    assert "super-secret-value" not in repr(result)


def test_unadmitted_or_wrong_scope_requests_expose_no_fact_metadata() -> None:
    admitted_request = _host_request()
    admission = _admission(admitted_request)
    plane = RuntimeFactBindingPlane(
        admissions=[admission],
        action_dispatcher=lambda command: command.dispatch(send=lambda inputs: None),
    )
    plane.declare(_host_declaration())
    plane.append(
        _host_version().model_copy(
            update={
                "scope": RuntimeFactScopeModel(
                    kind=RuntimeFactScopeKind.EPISODE,
                    run_id="run-791",
                    participant_address="participant.behavior.blue-agent",
                    episode_id="episode-1",
                )
            }
        )
    )

    wrong_scope = plane.bind_action_inputs(admitted_request)
    forged_request = admitted_request.model_copy(update={"action_instance_id": "scan-forged"})
    unadmitted = plane.bind_action_inputs(forged_request)

    assert wrong_scope.events[0].disposition is RuntimeFactBindingDisposition.ABSENT
    assert wrong_scope.events[0].fact_id is None
    assert wrong_scope.events[0].fact_version_id is None
    assert unadmitted.events == ()
    assert unadmitted.diagnostics[0].code == "runtime.fact-binding.unauthorized"
