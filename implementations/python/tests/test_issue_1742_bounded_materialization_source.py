"""A full-size admitted source survives planning, delivery and archival under one shared bound (#1742)."""

import hashlib
import json
from dataclasses import replace

import pytest
from pydantic import ValidationError
from raes import canonical_instantiated_sdl_bytes, parse_sdl
from raes.canonical import canonical_materialized_sdl_digest
from raes_backend_stubs.stubs import StubProvisioner
from raes_contracts.augmentation_preparation import AugmentationPreparation
from raes_contracts.contracts.materialization_attestation import MaterializationArchiveRecord
from raes_contracts.errors import InvalidInputError
from raes_contracts.materialization import (
    MATERIALIZATION_LIMIT_ERROR,
    MATERIALIZATION_MAX_BYTES,
    MaterializationSubmission,
)
from raes_contracts.plan_projection import provisioning_plan_model, runtime_plan_digest
from raes_contracts.planning import PlanScope
from raes_contracts.realization_structure import RealizationConstraintLimits, validate_realization_value
from raes_contracts.runtime_state import OperationState
from raes_contracts.runtime_value_limits import PLAN_VALUE_LIMITS, RUNTIME_SNAPSHOT_VALUE_LIMITS
from raes_contracts.vocabulary import RealizationSupportMode
from raes_operations.run_artifacts import RunMaterializationArchive
from raes_processor.compiler import compile_runtime_model
from raes_processor.planner import plan
from raes_runtime import RuntimeManager
from raes_runtime.backend_input_contracts import backend_input_violation
from raes_runtime.control_plane import RuntimeControlPlane
from raes_runtime.control_plane_api_models import _provisioning_plan
from raes_runtime.control_plane_store_local import LocalControlPlaneStore
from raes_runtime.registry import RuntimeTarget
from runtime_descendant_fixtures import descendant_runtime
from test_issue_1241_materialization_context import attesting_plan
from test_issue_1241_materialization_runtime import ReportingProvisioner, _apply
from test_issue_1241_materialized_sdl import materialized_payload
from test_sem_218_realization_designation import _manifest

FORMER_LIMIT = 1048576


def _full_size_source(entities=400):
    """Many ordinary bounded values, like a released scenario, not one oversized scalar."""
    members = {f"team-{index:04d}": {"description": f"Unit {index} " + "d" * 2900} for index in range(entities)}
    return json.dumps(
        {
            "name": "full-size",
            "realization": {"default": "open"},
            "nodes": {"host": {"type": "compute"}},
            "entities": members,
        }
    )


def _limit_error_types(error):
    return {item["type"] for item in error.value.errors()}


def test_full_size_source_crosses_the_former_limit_and_keeps_its_original_bytes():
    execution, model = attesting_plan(_full_size_source())

    assert execution.is_valid, execution.diagnostics
    source = execution.provisioning.materialization_source
    original = canonical_instantiated_sdl_bytes(model.realization_instance)
    assert FORMER_LIMIT < len(original) <= MATERIALIZATION_MAX_BYTES
    assert source.snapshot.encode("utf-8") == original
    assert source.instantiated_digest == "sha256:" + hashlib.sha256(original).hexdigest()
    assert source.authored_digest == model.realization_instance.instantiation_provenance.authored_digest.value
    assert execution.orchestration.materialization_source == source
    assert execution.evaluation.materialization_source == source
    restored = _provisioning_plan(provisioning_plan_model(execution.provisioning))
    assert restored.materialization_source == source
    assert runtime_plan_digest(restored) == runtime_plan_digest(execution.provisioning)


def test_full_size_source_is_delivered_reported_and_archived_with_verified_bytes(tmp_path):
    result, backend = _apply(tmp_path, source=_full_size_source())

    assert result.success, result.diagnostics
    assert backend.calls == 1
    [record] = result.snapshot.materialization_attestations
    data = (tmp_path / record.reference.ref_path).read_bytes()
    assert len(data) > FORMER_LIMIT
    assert len(data) == record.artifact.size_bytes
    assert hashlib.sha256(data).hexdigest() == record.artifact.checksum.value
    assert canonical_materialized_sdl_digest(parse_sdl(data.decode("utf-8"))).value == record.reference.ref_digest
    assert RunMaterializationArchive(tmp_path).read(record).sdl == data.decode("utf-8")


def test_full_size_source_keeps_its_target_binding_through_descendant_reporting(tmp_path):
    manager, backend, execution, _target, _archive = descendant_runtime(tmp_path, source=_full_size_source())
    try:
        source = execution.provisioning.materialization_source
        assert len(source.snapshot.encode("utf-8")) > FORMER_LIMIT
        assert (source.run_id, source.target_scope) == ("run-1", "target:descendants")
        result = manager.apply(execution)
        assert result.success, result.diagnostics
        assert backend.last_request.materialization_source == source
        [record] = result.snapshot.materialization_attestations
        assert (record.run_id, record.inventory.target_scope) == ("run-1", "target:descendants")
    finally:
        manager.close()


def test_full_size_source_survives_durable_store_restart_without_reapplying(tmp_path):
    execution, _model = attesting_plan(_full_size_source())
    backend = ReportingProvisioner(execution.manifest)
    target = RuntimeTarget(name="attesting", manifest=execution.manifest, provisioner=backend)

    def control_plane():
        return RuntimeControlPlane(
            target,
            store=LocalControlPlaneStore(tmp_path / "state"),
            materialization_archive=RunMaterializationArchive(tmp_path / "archive"),
            run_scope=f"run:{execution.provisioning.run_id}",
        )

    control = control_plane()
    try:
        control.register_planner_produced_plan(execution)
        receipt = control.submit_provisioning(execution.provisioning, idempotency_key="full-size-once")
        assert receipt.accepted, receipt.diagnostics
        assert control.get_operation(receipt.operation_id).state == OperationState.SUCCEEDED
    finally:
        control.close()
    recovered = control_plane()
    try:
        assert recovered.submit_provisioning(execution.provisioning, idempotency_key="full-size-once") == receipt
        assert backend.calls == 1
        assert len(recovered.snapshot.materialization_attestations) == 1
    finally:
        recovered.close()


def test_source_beyond_the_shared_bound_is_a_distinct_limit_refusal():
    execution, _model = attesting_plan(_full_size_source(entities=1500))

    codes = {diagnostic.code for diagnostic in execution.diagnostics}
    assert "materialization.source-limit-exceeded" in codes
    assert "materialization.source-context-required" not in codes
    assert execution.provisioning.materialization_source is None
    refusal = next(item for item in execution.diagnostics if item.code == "materialization.source-limit-exceeded")
    assert str(MATERIALIZATION_MAX_BYTES) in refusal.message
    assert "Unit" not in refusal.message


def test_missing_run_context_remains_the_context_refusal():
    original = _manifest(RealizationSupportMode.OPEN_REALIZATION)
    manifest = replace(
        original,
        supported_contract_versions=original.supported_contract_versions | {"backend-materialization-attestation-v1"},
    )
    execution = plan(compile_runtime_model(parse_sdl(_full_size_source())), manifest, scope=PlanScope())

    codes = {diagnostic.code for diagnostic in execution.diagnostics}
    assert "materialization.source-context-required" in codes
    assert "materialization.source-limit-exceeded" not in codes


@pytest.mark.parametrize(
    ("sdl", "accepted"),
    [
        ("a" * MATERIALIZATION_MAX_BYTES, True),
        ("a" * (MATERIALIZATION_MAX_BYTES + 1), False),
        ("ü" * (MATERIALIZATION_MAX_BYTES // 2), True),
        ("ü" * (MATERIALIZATION_MAX_BYTES // 2) + "a", False),
    ],
    ids=["ascii-inclusive", "ascii-one-beyond", "multibyte-inclusive", "multibyte-one-byte-beyond"],
)
def test_submission_bound_is_inclusive_and_counts_utf8_bytes(sdl, accepted):
    if accepted:
        assert len(MaterializationSubmission(sdl=sdl).sdl.encode("utf-8")) <= MATERIALIZATION_MAX_BYTES
        return
    with pytest.raises(ValidationError) as error:
        MaterializationSubmission(sdl=sdl)
    assert _limit_error_types(error) & {MATERIALIZATION_LIMIT_ERROR, "string_too_long"}


def test_prospective_content_uses_the_same_byte_bound():
    content = json.dumps({"name": "ü" * (MATERIALIZATION_MAX_BYTES // 2)}, ensure_ascii=False)
    with pytest.raises(ValidationError) as error:
        AugmentationPreparation(binding_digest="sha256:" + "0" * 64, content=content)
    assert MATERIALIZATION_LIMIT_ERROR in _limit_error_types(error)


def test_only_a_declared_document_field_receives_the_document_ceiling():
    body = "a" * (2 * FORMER_LIMIT)
    declared = MaterializationSubmission(sdl=body)
    limits = RUNTIME_SNAPSHOT_VALUE_LIMITS

    assert validate_realization_value(declared, limits=limits, python_carriers=True).conformant
    undeclared = validate_realization_value({"sdl": body}, limits=limits, python_carriers=True)
    assert "max_scalar_bytes" in undeclared.diagnostics[0].message

    class Claimed(str):
        pass

    claimed = MaterializationSubmission.model_construct(sdl=Claimed(body))
    assert not validate_realization_value(claimed, limits=limits, python_carriers=True).conformant
    forged = MaterializationSubmission.model_construct(sdl="a" * (MATERIALIZATION_MAX_BYTES + 1))
    exceeded = validate_realization_value(forged, limits=limits, python_carriers=True)
    assert "max_document_scalar_bytes" in exceeded.diagnostics[0].message
    # Limits without a document ceiling keep the ordinary scalar ceiling for declared fields.
    assert not validate_realization_value(MaterializationSubmission(sdl="a" * 5000), python_carriers=True).conformant


@pytest.mark.parametrize(
    "limits",
    [
        {"max_scalar_bytes": 10, "max_document_scalar_bytes": 5},
        {"max_total_scalar_bytes": 100, "max_document_scalar_bytes": 200},
    ],
    ids=["below-scalar", "above-total"],
)
def test_document_ceiling_must_lie_between_scalar_and_total_limits(limits):
    with pytest.raises(ValidationError):
        RealizationConstraintLimits(**limits)


def test_archive_refuses_oversized_content_before_writing(tmp_path):
    archive = RunMaterializationArchive(tmp_path / "archive")
    with pytest.raises(InvalidInputError, match="materialization document limit"):
        archive.publish("a" * (MATERIALIZATION_MAX_BYTES + 1))
    assert not (tmp_path / "archive").exists()


def test_archive_refuses_rendered_bytes_that_expand_beyond_the_bound(tmp_path, monkeypatch):
    import raes.formatting

    class Expanded:
        content = "a" * (MATERIALIZATION_MAX_BYTES + 1)

    monkeypatch.setattr(raes.formatting, "render_sdl_source", lambda scenario: Expanded())
    archive = RunMaterializationArchive(tmp_path / "archive")
    content = json.dumps(materialized_payload())
    with pytest.raises(InvalidInputError, match="materialization document limit"):
        archive.publish(content)
    assert not (tmp_path / "archive").exists()


def test_archive_record_cannot_advertise_bytes_beyond_the_bound(tmp_path):
    record = RunMaterializationArchive(tmp_path).publish(json.dumps(materialized_payload()))
    document = record.model_dump(mode="json")
    document["artifact"]["size_bytes"] = MATERIALIZATION_MAX_BYTES + 1
    with pytest.raises(ValidationError, match="materialization document limit"):
        MaterializationArchiveRecord.model_validate(document)


def _scale_plan(hosts=80):
    manifest = _manifest(RealizationSupportMode.OPEN_REALIZATION)
    source = json.dumps(
        {"name": "scale", "nodes": {f"host-{index:04d}": {"type": "compute"} for index in range(hosts)}}
    )
    return plan(compile_runtime_model(parse_sdl(source)), manifest), manifest


def test_plan_scale_authority_uses_the_plan_budget_and_applies(tmp_path):
    execution, manifest = _scale_plan()
    provisioning = execution.provisioning
    # The plan crosses the ordinary runtime node budget but stays within the plan budget.
    assert not validate_realization_value(
        provisioning, limits=RUNTIME_SNAPSHOT_VALUE_LIMITS, python_carriers=True
    ).conformant
    assert validate_realization_value(provisioning, limits=PLAN_VALUE_LIMITS, python_carriers=True).conformant
    assert backend_input_violation((provisioning,)) is None
    # A carrier that is not a plan keeps the ordinary budget, even when it has the same shape.
    assert backend_input_violation((provisioning_plan_model(provisioning).model_dump(mode="json"),)) is not None

    manager = RuntimeManager(
        RuntimeTarget(name="scale", manifest=manifest, provisioner=StubProvisioner(manifest.realization_envelope))
    )
    try:
        result = manager.apply(replace(execution, target_name="scale"))
        assert result.success, result.diagnostics
        assert len(manager.snapshot.entries) == 80
    finally:
        manager.close()
