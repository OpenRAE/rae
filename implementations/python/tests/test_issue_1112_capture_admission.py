"""Issue #1112: capture capability admission and emitted-evidence proof."""

from __future__ import annotations

import hashlib
import io
import json
import textwrap
from dataclasses import replace

import pytest
from paths import REPO_ROOT
from pydantic import ValidationError
from raes import parse_sdl
from raes_backend_protocols.capabilities import ObservationCaptureOffer
from raes_backend_protocols.manifest import backend_manifest_from_v2_model, backend_manifest_v2_model
from raes_backend_stubs.stubs import create_stub_manifest, create_stub_target
from raes_contracts.contracts import (
    BackendManifestV2Model,
    ExperimentCaptureSpecModel,
    ExperimentEvidenceRecordModel,
    ExperimentRunEvidenceInputs,
    ExperimentRunModel,
    ExperimentStudyModel,
    ExperimentTaskModel,
    ObservationCaptureOfferModel,
    validate_experiment_run_against_task,
    validate_experiment_study_against_tasks_and_runs,
)
from raes_contracts.evidence_satisfaction import validate_experiment_run_evidence
from raes_processor.compiler import compile_runtime_model
from raes_processor.planner import plan
from raes_reference_backend.manifest import create_reference_backend_manifest
from raes_runtime.control_plane import RuntimeControlPlane

FIXTURES = REPO_ROOT / "contracts" / "fixtures" / "experiment-core"
EVENT_STREAM_FIXTURE = (
    REPO_ROOT
    / "contracts"
    / "fixtures"
    / "control-plane"
    / "participant-behavior-history-event-stream-v1"
    / "valid"
    / "terminal-observation.json"
)


def _capture_scenario(
    *,
    channel: str = "log",
    output_contract: str = "participant-behavior-history-event-stream-v1",
    scope_declaration: str = "scope: run",
):
    return parse_sdl(
        textwrap.dedent(
            f"""
            name: capture-admission
            nodes:
              vm:
                type: compute
                source: ubuntu:24.04
                resources: {{ram: 1 gib, cpu: 1}}
                conditions: {{health: ops}}
                roles: {{ops: operator}}
            content:
              setup:
                type: file
                target: vm
                path: /opt/setup.sh
            evidence_requirements:
              attacker-action-log:
                description: Capture every attacker action used by evaluation.
                source_class: participant_action
                {scope_declaration}
                window: task
                channel: {channel}
                artifact_role: observation
                media_types: [application/json]
                sensitivity: plain
                redaction: none
                integrity: checksum
                retention: study_lifetime
                loss_disclosure: required
                output_contract: {output_contract}
                field_selectors: [/0, /0/action_contract_address]
            conditions:
              health: {{command: /bin/true, interval: 15}}
            propositions:
              health:
                description: The governed VM has declared runtime state.
                subjects: [nodes.vm]
                basis: declared_state
                predicate: {{kind: presence, property: runtime, semantic_ref: urn:raes:declared-property:runtime, operator: exists}}
            assertions:
              pre-health: {{proposition: health, role: precondition, polarity: positive}}
              post-health: {{proposition: health, role: postcondition, polarity: positive}}
            events:
              kickoff: {{assertions: [pre-health]}}
            scripts:
              timeline: {{start_time: 0, end_time: 60, speed: 1, events: {{kickoff: 10}}}}
            stories:
              main: {{scripts: [timeline]}}
            """
        )
    )


def _offer(**updates: object) -> ObservationCaptureOffer:
    fields: dict[str, object] = {
        "offer_id": "participant-action-log-json",
        "offer_version": "1.0.0",
        "output_contract": "participant-behavior-history-event-stream-v1",
        "field_selectors": ("", "/0", "/0/action_contract_address"),
        "artifact_roles": frozenset({"observation"}),
        "media_types": frozenset({"application/json"}),
        "capture_kind": "log",
        "source_classes": frozenset({"participant_action"}),
        "source_refs": frozenset(),
        "scopes": frozenset({"run"}),
        "scope_refs": frozenset(),
        "channel_kinds": frozenset({"backend-log"}),
        "channel_refs": frozenset(),
        "window_kinds": frozenset({"task"}),
        "integrity_modes": frozenset({"checksum"}),
        "sensitivity": "plain",
        "availability": "available",
        "fidelity": "complete",
        "disclosure": "full",
        "retention_policy_refs": frozenset({"study_lifetime"}),
        "export_policy": "not-required",
    }
    fields.update(updates)
    return ObservationCaptureOffer(**fields)


def _manifest_with_offers(*offers: ObservationCaptureOffer):
    base = create_stub_manifest()
    assert base.observation is not None
    observation = replace(base.observation, capture_offers=tuple(offers))
    return replace(base, capabilities=replace(base.capabilities, observation=observation))


def test_manifest_capture_offers_are_closed_and_round_trip() -> None:
    offer = _offer()
    manifest = _manifest_with_offers(offer)

    model = backend_manifest_v2_model(manifest)
    assert model.capabilities.observation is not None
    assert model.capabilities.observation.capture_offers[0] == ObservationCaptureOfferModel(**offer.to_payload())
    assert backend_manifest_from_v2_model(model) == manifest

    payload = model.model_dump(mode="json")
    payload["capabilities"]["observation"]["capture_offers"][0]["unknown"] = True
    with pytest.raises(ValidationError, match="unknown"):
        BackendManifestV2Model.model_validate(payload)


@pytest.mark.parametrize(
    ("offer_update", "failed_dimension"),
    [
        ({"availability": "unsupported"}, "availability"),
        ({"availability": "unavailable"}, "availability"),
        ({"fidelity": "lossy"}, "fidelity"),
        ({"disclosure": "redacted", "redaction_policy": "redact_sensitive"}, "disclosure"),
        ({"disclosure": "withheld", "redaction_policy": "redact_sensitive"}, "disclosure"),
        ({"channel_kinds": frozenset({"packet-capture"})}, "channel"),
        ({"field_selectors": ("/0/action_contract_address",)}, "field-selector"),
    ],
)
def test_planner_rejects_every_unmet_capture_dimension_before_execution(
    offer_update: dict[str, object],
    failed_dimension: str,
) -> None:
    execution_plan = plan(
        compile_runtime_model(_capture_scenario()),
        _manifest_with_offers(_offer(**offer_update)),
    )

    assert not execution_plan.is_valid
    capture_diagnostics = [diagnostic for diagnostic in execution_plan.diagnostics if diagnostic.domain == "capture"]
    assert capture_diagnostics
    assert any(failed_dimension in diagnostic.code for diagnostic in capture_diagnostics)


def test_planner_reports_all_unmet_capture_requirements_deterministically() -> None:
    scenario = _capture_scenario()
    payload = scenario.model_dump(mode="python", by_alias=True)
    payload["evidence_requirements"]["availability-series"] = {
        **payload["evidence_requirements"]["attacker-action-log"],
        "description": "Capture the availability series.",
        "channel": "metric",
        "output_contract": "experiment-evidence-record-v1",
        "field_selectors": ["/samples"],
    }
    compiled = compile_runtime_model(scenario.__class__.model_validate(payload))
    execution_plan = plan(compiled, _manifest_with_offers())

    assert not execution_plan.is_valid
    assert [
        (diagnostic.address, diagnostic.code)
        for diagnostic in execution_plan.diagnostics
        if diagnostic.domain == "capture"
    ] == [
        ("evidence_requirements.attacker-action-log", "capture.offer-missing"),
        ("evidence_requirements.availability-series", "capture.offer-missing"),
    ]


def test_matching_capture_offer_admits_and_precise_installation_does_not_create_capture_demand() -> None:
    admitted = plan(compile_runtime_model(_capture_scenario()), _manifest_with_offers(_offer()))
    assert not [diagnostic for diagnostic in admitted.diagnostics if diagnostic.domain == "capture"]

    scenario_without_capture = parse_sdl(
        textwrap.dedent(
            """
            name: exact-installation-only
            nodes:
              vm:
                type: compute
                source:
                  name: ubuntu-server
                  version: 24.04.1
                resources: {ram: 1 gib, cpu: 1}
                runtime:
                  packages:
                    - {manager: apt, name: openssl, version: 3.0.13}
            """
        )
    )
    no_capture_plan = plan(compile_runtime_model(scenario_without_capture), _manifest_with_offers())
    assert not [diagnostic for diagnostic in no_capture_plan.diagnostics if diagnostic.domain == "capture"]


def test_sdl_capture_spec_references_fail_closed_when_the_payload_is_unavailable() -> None:
    scenario = _capture_scenario()
    payload = scenario.model_dump(mode="python", by_alias=True)
    requirement = payload["evidence_requirements"]["attacker-action-log"]
    requirement["capture_spec_ref"] = "capture-techvault-evidence-v1"
    requirement["capture_requirement_ref"] = "auth-log-evidence"

    execution_plan = plan(
        compile_runtime_model(scenario.__class__.model_validate(payload)),
        _manifest_with_offers(_offer()),
    )

    assert any(diagnostic.code == "capture.reference-unresolved" for diagnostic in execution_plan.diagnostics)

    requirement["capture_requirement_ref"] = ""
    with pytest.raises(ValidationError, match="must be declared together"):
        scenario.__class__.model_validate(payload)


def test_capture_offer_binds_the_exact_redaction_policy() -> None:
    payload = _capture_scenario().model_dump(mode="python", by_alias=True)
    payload["evidence_requirements"]["attacker-action-log"]["redaction"] = "redact_secrets"
    scenario = _capture_scenario().__class__.model_validate(payload)
    mismatch = plan(
        compile_runtime_model(scenario),
        _manifest_with_offers(_offer(disclosure="redacted", redaction_policy="redact_sensitive")),
    )
    admitted = plan(
        compile_runtime_model(scenario),
        _manifest_with_offers(_offer(disclosure="redacted", redaction_policy="redact_secrets")),
    )

    assert any(diagnostic.code == "capture.redaction-policy-mismatch" for diagnostic in mismatch.diagnostics)
    assert not any(diagnostic.code == "capture.redaction-policy-mismatch" for diagnostic in admitted.diagnostics)


def _fixture(contract: str) -> dict[str, object]:
    path = FIXTURES / contract / "valid" / "reference.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _evidence_bundle(
    payload: bytes | None = None,
    *,
    output_contract: str = "participant-behavior-history-event-stream-v1",
    field_selectors: list[str] | None = None,
    media_type: str = "application/json",
):
    if payload is None:
        payload = EVENT_STREAM_FIXTURE.read_bytes()
    checksum = hashlib.sha256(payload).hexdigest()
    task_payload = _fixture("experiment-task-v1")
    run_payload = _fixture("experiment-run-v1")
    capture_payload = _fixture("experiment-capture-spec-v1")
    record_payload = _fixture("experiment-evidence-record-v1")

    capture_payload["capture_requirements"] = {
        "auth-log-evidence": {
            **next(iter(capture_payload["capture_requirements"].values())),
            "requirement_id": "auth-log-evidence",
            "output_contract": output_contract,
            "field_selectors": field_selectors or ["/0/action_contract_address"],
            "expected_media_types": [media_type],
        }
    }
    record_payload["capture_requirement_ref"] = "auth-log-evidence"
    record_payload["output_contract"] = output_contract
    record_payload["raw_content"] = {
        "content_uri": "runs/run-techvault-001/evaluation-history.json",
        "content_checksum": {"algorithm": "sha256", "value": checksum},
    }
    run_payload["evidence_artifacts"][0].update(
        artifact_id="auth-log-evidence",
        uri="runs/run-techvault-001/evaluation-history.json",
        media_type=media_type,
        size_bytes=len(payload),
        checksum={"algorithm": "sha256", "value": checksum},
        satisfies_refs=[],
    )
    run_payload["result_summaries"]["foothold-achieved-result"]["evidence_refs"][0]["ref_id"] = "auth-log-evidence"
    return (
        ExperimentTaskModel.model_validate(task_payload),
        ExperimentRunModel.model_validate(run_payload),
        ExperimentCaptureSpecModel.model_validate(capture_payload),
        ExperimentEvidenceRecordModel.model_validate(record_payload),
        payload,
    )


def _validate_evidence_bundle(
    task: ExperimentTaskModel,
    run: ExperimentRunModel,
    capture_spec: ExperimentCaptureSpecModel,
    evidence_record: ExperimentEvidenceRecordModel,
    payload: bytes,
    *,
    artifact_id: str = "auth-log-evidence",
) -> None:
    validate_experiment_run_evidence(
        task,
        run,
        capture_specs={capture_spec.capture_spec_id: capture_spec},
        evidence_records={evidence_record.evidence_record_id: evidence_record},
        artifact_readers={artifact_id: io.BytesIO(payload)},
    )


def test_post_run_validation_requires_emitted_bytes_and_promised_fields() -> None:
    task, run, capture_spec, evidence_record, payload = _evidence_bundle()

    _validate_evidence_bundle(task, run, capture_spec, evidence_record, payload)

    missing_task, missing_run, missing_spec, missing_record, missing_payload = _evidence_bundle(
        field_selectors=["/0/not-present"]
    )
    with pytest.raises(ValueError, match="field selector"):
        _validate_evidence_bundle(missing_task, missing_run, missing_spec, missing_record, missing_payload)


@pytest.mark.parametrize(
    "captured_at",
    ["2026-05-26T00:09:59Z", "2026-05-26T00:40:01Z"],
)
def test_post_run_validation_rejects_evidence_outside_the_capture_window(captured_at: str) -> None:
    task, run, capture_spec, evidence_record, payload = _evidence_bundle()
    evidence_record = evidence_record.model_copy(update={"captured_at": captured_at})

    with pytest.raises(ValueError, match="capture window"):
        _validate_evidence_bundle(task, run, capture_spec, evidence_record, payload)


def test_post_run_validation_rejects_an_unprovable_trigger_window() -> None:
    task, run, capture_spec, evidence_record, payload = _evidence_bundle()
    spec_payload = capture_spec.model_dump(mode="json")
    spec_payload["capture_windows"][0] = {
        "window_id": "run-window",
        "window_kind": "event",
        "trigger_ref": {"ref_kind": "other", "ref_id": "capture-start"},
    }
    capture_spec = ExperimentCaptureSpecModel.model_validate(spec_payload)

    with pytest.raises(ValueError, match="timing cannot be proved"):
        _validate_evidence_bundle(task, run, capture_spec, evidence_record, payload)


def test_authoritative_task_run_validation_requires_and_consumes_content_inputs() -> None:
    task, run, capture_spec, evidence_record, payload = _evidence_bundle()
    with pytest.raises(ValueError, match="content-backed evidence inputs"):
        validate_experiment_run_against_task(task, run)

    invalid_evidence = ExperimentRunEvidenceInputs(
        capture_specs={capture_spec.capture_spec_id: capture_spec},
        evidence_records={evidence_record.evidence_record_id: evidence_record},
        artifact_readers={"auth-log-evidence": io.BytesIO(b"x" * len(payload))},
    )
    with pytest.raises(ValueError, match="checksum"):
        validate_experiment_run_against_task(task, run, evidence=invalid_evidence)

    validate_experiment_run_against_task(
        task,
        run,
        evidence=ExperimentRunEvidenceInputs(
            capture_specs={capture_spec.capture_spec_id: capture_spec},
            evidence_records={evidence_record.evidence_record_id: evidence_record},
            artifact_readers={"auth-log-evidence": io.BytesIO(payload)},
        ),
    )

    study = ExperimentStudyModel.model_validate(_fixture("experiment-study-v1"))
    validate_experiment_study_against_tasks_and_runs(
        study,
        [task],
        [run],
        evidence_by_run={
            run.run_id: ExperimentRunEvidenceInputs(
                capture_specs={capture_spec.capture_spec_id: capture_spec},
                evidence_records={evidence_record.evidence_record_id: evidence_record},
                artifact_readers={"auth-log-evidence": io.BytesIO(payload)},
            )
        },
    )


def test_authoritative_task_run_validation_rejects_unsatisfied_observation_reference() -> None:
    task, run, capture_spec, evidence_record, payload = _evidence_bundle()
    task_payload = task.model_dump(mode="json")
    task_payload["evaluation_protocol"]["observation_requirements"][0]["ref_digest"] = "sha256:" + "0" * 64
    task = ExperimentTaskModel.model_validate(task_payload)

    evidence = ExperimentRunEvidenceInputs(
        capture_specs={capture_spec.capture_spec_id: capture_spec},
        evidence_records={evidence_record.evidence_record_id: evidence_record},
        artifact_readers={"auth-log-evidence": io.BytesIO(payload)},
    )
    with pytest.raises(ValueError, match="task observation requirements"):
        validate_experiment_run_against_task(task, run, evidence=evidence)


def test_static_artifact_id_cannot_stand_in_for_the_validated_capture_artifact() -> None:
    task, run, capture_spec, evidence_record, payload_bytes = _evidence_bundle()
    payload = run.model_dump(mode="json")
    captured_artifact = payload["evidence_artifacts"][0]
    captured_artifact["artifact_id"] = "captured-artifact"
    captured_artifact["satisfies_refs"] = []
    dummy_artifact = dict(captured_artifact)
    dummy_artifact.update(
        artifact_id="auth-log-evidence",
        uri="runs/run-techvault-001/dummy.json",
        satisfies_refs=[{"ref_kind": "evidence", "ref_id": "auth-log-evidence"}],
    )
    payload["evidence_artifacts"].append(dummy_artifact)
    invalid_run = ExperimentRunModel.model_validate(payload)

    with pytest.raises(ValueError, match="validated metric evidence bindings"):
        _validate_evidence_bundle(
            task,
            invalid_run,
            capture_spec,
            evidence_record,
            payload_bytes,
            artifact_id="captured-artifact",
        )


def test_output_contract_shape_and_registry_are_enforced_before_selectors() -> None:
    invalid = _evidence_bundle(b'{"events":[{"action":"scan"}]}')
    with pytest.raises(ValueError, match="output_contract"):
        _validate_evidence_bundle(*invalid)

    unknown = _evidence_bundle(output_contract="unknown-output-contract-v1")
    with pytest.raises(ValueError, match="authoritative contract registry"):
        _validate_evidence_bundle(*unknown)


def test_output_contract_semantic_invariants_are_enforced() -> None:
    events = json.loads(EVENT_STREAM_FIXTURE.read_text(encoding="utf-8"))
    events[0]["operation_ref"] = "operation-without-lifecycle-phase"
    payload = json.dumps(events).encode()
    task, run, capture_spec, evidence_record, _ = _evidence_bundle(payload)

    with pytest.raises(ValueError, match="output_contract"):
        _validate_evidence_bundle(task, run, capture_spec, evidence_record, payload)


def test_json_lines_is_validated_as_the_declared_array_contract() -> None:
    events = json.loads(EVENT_STREAM_FIXTURE.read_text(encoding="utf-8"))
    payload = b"\n".join(json.dumps(event).encode() for event in events)
    task, run, capture_spec, evidence_record, _ = _evidence_bundle(payload, media_type="application/jsonl")

    _validate_evidence_bundle(task, run, capture_spec, evidence_record, payload)


def test_redaction_policy_and_artifact_sensitivity_are_bound_to_the_capture() -> None:
    task, run, capture_spec, evidence_record, payload = _evidence_bundle()
    capture_payload = capture_spec.model_dump(mode="json")
    capture_payload["capture_requirements"]["auth-log-evidence"]["redaction_policy"] = "policy:mask-identities"
    redacted_spec = ExperimentCaptureSpecModel.model_validate(capture_payload)
    with pytest.raises(ValueError, match="redaction policy was not applied"):
        _validate_evidence_bundle(task, run, redacted_spec, evidence_record, payload)

    redacted_record_payload = evidence_record.model_dump(mode="json")
    redacted_record_payload.update(sensitivity="redacted", redaction_state="redacted")
    redacted_record_payload["redaction_policy"] = "policy:mask-identities"
    redacted_record_payload["raw_content"]["loss_disclosure"] = "Participant identifiers were masked."
    redacted_record = ExperimentEvidenceRecordModel.model_validate(redacted_record_payload)
    redacted_capture_payload = redacted_spec.model_dump(mode="json")
    redacted_capture_payload["capture_requirements"]["auth-log-evidence"]["sensitivity"] = "redacted"
    redacted_spec = ExperimentCaptureSpecModel.model_validate(redacted_capture_payload)
    redacted_run_payload = run.model_dump(mode="json")
    redacted_run_payload["evidence_artifacts"][0]["sensitivity"] = "redacted"
    redacted_run = ExperimentRunModel.model_validate(redacted_run_payload)
    with pytest.raises(ValueError, match="has no content verifier"):
        _validate_evidence_bundle(task, redacted_run, redacted_spec, redacted_record, payload)

    run_payload = run.model_dump(mode="json")
    run_payload["evidence_artifacts"][0]["sensitivity"] = "public"
    public_run = ExperimentRunModel.model_validate(run_payload)
    with pytest.raises(ValueError, match="artifact sensitivity"):
        _validate_evidence_bundle(task, public_run, capture_spec, evidence_record, payload)


def test_study_evidence_conditions_consume_only_validated_bindings() -> None:
    task, run, capture_spec, evidence_record, payload = _evidence_bundle()
    study_payload = _fixture("experiment-study-v1")
    assignment = study_payload["run_allocation"]["condition_assignments"]["baseline"]
    assignment["required_refs"] = [{"ref_kind": "evidence", "ref_id": "auth-log-evidence"}]
    study = ExperimentStudyModel.model_validate(study_payload)
    evidence_inputs = ExperimentRunEvidenceInputs(
        capture_specs={capture_spec.capture_spec_id: capture_spec},
        evidence_records={evidence_record.evidence_record_id: evidence_record},
        artifact_readers={"auth-log-evidence": io.BytesIO(payload)},
    )

    validate_experiment_study_against_tasks_and_runs(
        study,
        [task],
        [run],
        evidence_by_run={run.run_id: evidence_inputs},
    )

    run_payload = run.model_dump(mode="json")
    run_payload["generated_refs"].append({"ref_kind": "evidence", "ref_id": "metadata-only-evidence"})
    assignment["required_refs"] = [{"ref_kind": "evidence", "ref_id": "metadata-only-evidence"}]
    metadata_only_study = ExperimentStudyModel.model_validate(study_payload)
    metadata_only_run = ExperimentRunModel.model_validate(run_payload)
    metadata_only_inputs = ExperimentRunEvidenceInputs(
        capture_specs={capture_spec.capture_spec_id: capture_spec},
        evidence_records={evidence_record.evidence_record_id: evidence_record},
        artifact_readers={"auth-log-evidence": io.BytesIO(payload)},
    )
    with pytest.raises(ValueError, match="condition assignments"):
        validate_experiment_study_against_tasks_and_runs(
            metadata_only_study,
            [task],
            [metadata_only_run],
            evidence_by_run={run.run_id: metadata_only_inputs},
        )


def test_sdl_scope_refs_require_exact_offer_scope_targets() -> None:
    scenario = _capture_scenario(scope_declaration="scope_refs: [nodes.vm]")
    matching = plan(compile_runtime_model(scenario), _manifest_with_offers(_offer(scope_refs=frozenset({"nodes.vm"}))))
    mismatched = plan(
        compile_runtime_model(scenario),
        _manifest_with_offers(_offer(scope_refs=frozenset({"nodes.other"}))),
    )

    assert matching.is_valid
    assert any(diagnostic.code == "capture.scope-ref-mismatch" for diagnostic in mismatched.diagnostics)
    wildcard_scope = frozenset({"*"})
    with pytest.raises(ValueError, match="exact authored targets"):
        _offer(scope_refs=wildcard_scope)


def test_reference_backends_publish_no_unimplemented_capture_offers() -> None:
    stub = create_stub_manifest()
    reference = create_reference_backend_manifest()

    assert stub.observation is not None
    assert stub.observation.capture_offers == ()
    assert reference.observation is not None
    assert reference.observation.capture_offers == ()
    rejected = plan(compile_runtime_model(_capture_scenario()), stub)
    assert any(diagnostic.code == "capture.offer-missing" for diagnostic in rejected.diagnostics)


def test_control_plane_cannot_register_an_invalid_composite_capture_plan() -> None:
    target = create_stub_target()
    execution_plan = plan(
        compile_runtime_model(_capture_scenario()),
        target.manifest,
        target_name=target.name,
    )
    assert not execution_plan.is_valid
    control_plane = RuntimeControlPlane(target)

    with pytest.raises(ValueError, match="invalid composite"):
        control_plane.register_planner_produced_plan(execution_plan)
    receipt = control_plane.submit_provisioning(execution_plan.provisioning)

    assert not receipt.accepted
    assert control_plane.snapshot.entries == {}


@pytest.mark.parametrize("domain", ["orchestration", "evaluation"])
def test_control_plane_rejects_unregistered_effectful_plans(domain: str) -> None:
    target = create_stub_target()
    assert target.manifest.observation is not None
    manifest = replace(
        target.manifest,
        capabilities=replace(
            target.manifest.capabilities,
            observation=replace(target.manifest.observation, capture_offers=(_offer(),)),
        ),
    )
    target = replace(target, manifest=manifest)
    control_plane = RuntimeControlPlane(target)
    execution_plan = plan(
        compile_runtime_model(_capture_scenario()),
        target.manifest,
        target_name=target.name,
    )
    submitted = getattr(execution_plan, domain)
    first_operation = submitted.operations[0]
    authorized_variant = replace(
        submitted,
        operations=[
            replace(first_operation, payload={**first_operation.payload, "authorization_variant": True}),
            *submitted.operations[1:],
        ],
    )
    authorization_plan = replace(
        execution_plan,
        **{domain: authorized_variant},
    )
    control_plane.register_planner_produced_plan(authorization_plan)
    assert control_plane.submit_provisioning(execution_plan.provisioning).accepted
    if domain == "orchestration":
        assert control_plane.submit_evaluation(execution_plan.evaluation).accepted

    receipt = getattr(control_plane, f"submit_{domain}")(submitted)

    assert receipt.accepted is False
    assert any(diagnostic.code == "runtime.plan-authorization-mismatch" for diagnostic in receipt.diagnostics)
