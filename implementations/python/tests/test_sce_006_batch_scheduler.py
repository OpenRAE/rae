"""SCE-006 isolated batch trial scheduling: deterministic order, sealed-plan
isolation authority, and immutable execution receipts over the one-entry seam."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError
from raes_contracts.canonical import canonical_json_digest
from raes_contracts.contracts import (
    AdmittedTrialPlanModel,
    BatchExecutionReceiptModel,
    validate_batch_execution_receipt,
    validate_scheduler_isolation_proof,
)
from raes_contracts.contracts.trial_cleanup import (
    CleanupObligationResultModel,
    IsolationDimensionEvidenceModel,
    SchedulerIsolationProofModel,
    TrialCleanupReceiptModel,
)
from raes_processor.trial_scheduler import (
    CANONICAL_ORDER_POLICY_ID,
    AllocatorGrant,
    AttemptOutcome,
    build_batch_execution_receipt,
    dispatch_batch_schedule,
    plan_batch_schedule,
)

FIXTURES = Path(__file__).resolve().parents[3] / "contracts" / "fixtures" / "plans" / "admitted-trial-plan-v1" / "valid"
ALL_DIMENSIONS = (
    "range-instance",
    "host-capacity",
    "ports",
    "storage",
    "control-plane-locks",
    "secret-scope",
    "cleanup",
)


def _plan(name: str) -> AdmittedTrialPlanModel:
    return AdmittedTrialPlanModel.model_validate(json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8")))


def _proof(entry_ids: list[str], *, requested_parallelism: int = 2) -> SchedulerIsolationProofModel:
    return SchedulerIsolationProofModel(
        schema_version="scheduler-isolation-proof/v1",
        proof_id="proof-parallel",
        plan_entry_ids=entry_ids,
        requested_parallelism=requested_parallelism,
        dimensions=[
            IsolationDimensionEvidenceModel(dimension=d, independent=True, evidence_refs=[f"evidence:{d}"])
            for d in ALL_DIMENSIONS
        ],
    )


def _resealed_plan(payload: dict) -> AdmittedTrialPlanModel:
    payload["input_refs"].setdefault("capture_spec_refs", [])
    content = {key: value for key, value in payload.items() if key != "plan_digest"}
    payload["plan_digest"] = canonical_json_digest(content)
    return AdmittedTrialPlanModel.model_validate(payload)


def _receipt(plan: AdmittedTrialPlanModel, **overrides: object) -> BatchExecutionReceiptModel:
    fields: dict[str, object] = {
        "receipt_id": "receipt-1",
        "plan_id": plan.plan_id,
        "plan_digest": plan.plan_digest,
        "plan_entry_id": "entry-a",
        "run_id": "run-a",
        "execution_attempt_id": "attempt-1",
        "dispatch_ordinal": 0,
        "effective_parallelism": 1,
        "trial_outcome": "succeeded",
        "cleanup_receipt_ref": "cleanup-receipt-1",
    }
    fields.update(overrides)
    return BatchExecutionReceiptModel(**fields)


def _success_cleanup_receipt(**overrides: object) -> TrialCleanupReceiptModel:
    fields: dict[str, object] = {
        "schema_version": "trial-cleanup-receipt/v1",
        "receipt_id": "cleanup-receipt-1",
        "cleanup_plan_ref": "cleanup-a",
        "plan_entry_id": "entry-a",
        "run_id": "run-a",
        "execution_attempt_id": "attempt-1",
        "trial_outcome": "succeeded",
        "cleanup_status": "succeeded",
        "obligation_results": {
            "destroy-range": CleanupObligationResultModel(
                obligation_id="destroy-range", status="succeeded", evidence_refs=["evidence:absent"]
            )
        },
    }
    fields.update(overrides)
    return TrialCleanupReceiptModel(**fields)


# --- deterministic order and admitted ceiling --------------------------------


def test_minimal_plan_is_serial() -> None:
    schedule = plan_batch_schedule(_plan("minimal"))

    assert schedule.admitted_parallelism_ceiling == 1
    assert schedule.isolation_proof_ref is None
    assert schedule.scheduling_policy_id == CANONICAL_ORDER_POLICY_ID
    assert [entry.plan_entry_id for entry in schedule.entries] == ["entry-a"]
    assert [entry.dispatch_ordinal for entry in schedule.entries] == [0]


def test_parallel_plan_reports_ceiling_from_sealed_proof() -> None:
    schedule = plan_batch_schedule(_plan("parallel-isolated"))

    assert schedule.admitted_parallelism_ceiling == 2
    assert schedule.isolation_proof_ref == "proof-parallel"
    assert [entry.plan_entry_id for entry in schedule.entries] == ["entry-a", "entry-b"]
    assert [entry.dispatch_ordinal for entry in schedule.entries] == [0, 1]


def test_embedded_serial_proof_reports_ceiling_one() -> None:
    payload = json.loads((FIXTURES / "parallel-isolated.json").read_text(encoding="utf-8"))
    payload["isolation_proof"] = {
        "schema_version": "scheduler-isolation-proof/v1",
        "proof_id": "proof-serial",
        "plan_entry_ids": ["entry-a", "entry-b"],
        "requested_parallelism": 1,
        "dimensions": [],
    }
    schedule = plan_batch_schedule(_resealed_plan(payload))

    assert schedule.admitted_parallelism_ceiling == 1
    assert schedule.isolation_proof_ref is None


def test_schedule_is_independent_of_entry_map_order() -> None:
    # SVR-014 / SVR-031: reordering the entries map must not change identity or
    # the dispatch order; canonical order comes from the coordinate.
    payload = json.loads((FIXTURES / "parallel-isolated.json").read_text(encoding="utf-8"))
    payload["entries"] = dict(reversed(list(payload["entries"].items())))
    schedule = plan_batch_schedule(AdmittedTrialPlanModel.model_validate(payload))

    assert [entry.plan_entry_id for entry in schedule.entries] == ["entry-a", "entry-b"]


def test_dispatch_commits_entries_in_canonical_order() -> None:
    schedule = plan_batch_schedule(_plan("parallel-isolated"))
    calls: list[str] = []

    results = dispatch_batch_schedule(schedule, realize=lambda entry_id: (calls.append(entry_id), entry_id.upper())[1])

    assert calls == ["entry-a", "entry-b"]
    assert results == ["ENTRY-A", "ENTRY-B"]


def test_canonical_order_helper_decodes_replicate_and_orders() -> None:
    from raes_contracts.contracts.random_stream import TrialCoordinateModel
    from raes_contracts.contracts.trial_coordinate_order import canonical_coordinate_sort_key, replicate_ordinal

    assert replicate_ordinal("replicate-000003") == 3
    assert canonical_coordinate_sort_key(TrialCoordinateModel(replicate_id="replicate-000010")) == ("", 10)
    assert canonical_coordinate_sort_key(TrialCoordinateModel(condition_id="b", replicate_id="replicate-000001")) == (
        "b",
        1,
    )
    with pytest.raises(ValueError, match="not a trial-coordinate-v1 identifier"):
        replicate_ordinal("bogus")


def test_canonical_order_ignores_block_id() -> None:
    # trial-coordinate-canonical-v1 orders by condition then replicate ordinal;
    # block_id is not an ordering dimension. When block and replicate ordering
    # would conflict, replicate ordinal wins and block is ignored.
    from raes_contracts.contracts.random_stream import TrialCoordinateModel
    from raes_contracts.contracts.trial_coordinate_order import canonical_coordinate_sort_key

    earlier = TrialCoordinateModel(condition_id="c", block_id="z-late", replicate_id="replicate-000001")
    later = TrialCoordinateModel(condition_id="c", block_id="a-early", replicate_id="replicate-000002")

    assert canonical_coordinate_sort_key(earlier) == ("c", 1)
    assert canonical_coordinate_sort_key(later) == ("c", 2)
    assert sorted((later, earlier), key=canonical_coordinate_sort_key) == [earlier, later]


# --- plan-to-schedule isolation join -----------------------------------------


def test_isolation_join_accepts_the_admitted_plan_proof() -> None:
    plan = _plan("parallel-isolated")
    assert plan.isolation_proof is not None
    validate_scheduler_isolation_proof(plan, plan.isolation_proof)


def test_isolation_join_accepts_a_serial_proof() -> None:
    plan = _plan("parallel-isolated")
    serial_proof = SchedulerIsolationProofModel(
        schema_version="scheduler-isolation-proof/v1", proof_id="proof-serial", plan_entry_ids=["entry-a"]
    )
    validate_scheduler_isolation_proof(plan, serial_proof)


def test_isolation_join_rejects_entries_outside_the_plan() -> None:
    plan = _plan("parallel-isolated")
    proof = _proof(["entry-a", "entry-absent"])
    with pytest.raises(ValueError, match="outside the admitted plan"):
        validate_scheduler_isolation_proof(plan, proof)


def test_isolation_join_rejects_resource_sharing_parallel_entries() -> None:
    payload = json.loads((FIXTURES / "parallel-isolated.json").read_text(encoding="utf-8"))
    payload["isolation_proof"] = None  # drop the embedded proof so the plan validates as serial
    payload["cleanup_plans"]["cleanup-b"]["resource_boundaries"]["range-b"]["resource_refs"] = ["node.vm-a"]
    plan = _resealed_plan(payload)
    proof = _proof(["entry-a", "entry-b"])

    with pytest.raises(ValueError, match="share resources"):
        validate_scheduler_isolation_proof(plan, proof)


# --- immutable execution receipt: model-level field validation ---------------


def test_receipt_requires_a_cleanup_receipt_ref() -> None:
    fields = {
        "receipt_id": "receipt-1",
        "plan_id": "plan-a",
        "plan_digest": "sha256:" + "a" * 64,
        "plan_entry_id": "entry-a",
        "run_id": "run-a",
        "execution_attempt_id": "attempt-1",
        "dispatch_ordinal": 0,
        "trial_outcome": "succeeded",
    }
    with pytest.raises(ValidationError, match="cleanup_receipt_ref"):
        BatchExecutionReceiptModel(**fields)


@pytest.mark.parametrize(
    ("overrides", "match"),
    [
        ({"scheduling_policy_id": "attacker-supplied-policy"}, "trial-coordinate-canonical-v1"),
        ({"execution_attempt_id": "run-a"}, "execution_attempt_id must be distinct"),
        ({"isolation_proof_ref": "proof-parallel"}, "must not cite an isolation proof"),
        ({"lease_evidence_refs": ["lease:a"]}, "must not cite live lease evidence"),
        ({"effective_parallelism": 2, "lease_evidence_refs": ["lease:a"]}, "requires an isolation_proof_ref"),
        ({"effective_parallelism": 2, "isolation_proof_ref": "proof-parallel"}, "requires live lease_evidence_refs"),
        (
            {
                "effective_parallelism": 2,
                "isolation_proof_ref": "proof-parallel",
                "lease_evidence_refs": ["lease:a", "lease:a"],
            },
            "lease_evidence_refs must not contain duplicates",
        ),
        ({"operation_refs": ["op:a", "op:a"]}, "operation_refs must not contain duplicates"),
    ],
)
def test_receipt_model_rejects_invalid_fields(overrides: dict, match: str) -> None:
    plan = _plan("minimal")
    with pytest.raises(ValidationError, match=match):
        _receipt(plan, **overrides)


# --- immutable execution receipt: cross-artifact validation ------------------


def test_valid_serial_receipt_validates_with_matching_cleanup() -> None:
    plan = _plan("minimal")
    validate_batch_execution_receipt(plan, _receipt(plan), cleanup_receipt=_success_cleanup_receipt())


@pytest.mark.parametrize(
    ("plan_name", "receipt_overrides", "cleanup_overrides", "match"),
    [
        ("minimal", {"plan_id": "plan-other"}, {}, "plan_id must match"),
        ("minimal", {"plan_digest": "sha256:" + "0" * 64}, {}, "plan_digest must match"),
        ("minimal", {"plan_entry_id": "entry-absent"}, {}, "plan_entry_id does not resolve"),
        ("minimal", {"run_id": "run-other"}, {}, "run_id must match"),
        ("parallel-isolated", {"dispatch_ordinal": 1}, {}, "does not match the canonical dispatch order"),
        (
            "minimal",
            {"effective_parallelism": 2, "isolation_proof_ref": "proof-parallel", "lease_evidence_refs": ["lease:a"]},
            {},
            "requires an admitted plan isolation proof",
        ),
        (
            "parallel-isolated",
            {"effective_parallelism": 2, "isolation_proof_ref": "wrong-proof", "lease_evidence_refs": ["lease:a"]},
            {},
            "isolation_proof_ref must match",
        ),
        (
            "parallel-isolated",
            {"effective_parallelism": 3, "isolation_proof_ref": "proof-parallel", "lease_evidence_refs": ["lease:a"]},
            {},
            "cannot exceed the admitted isolation proof",
        ),
        ("minimal", {"cleanup_receipt_ref": "other-cleanup-receipt"}, {}, "cleanup_receipt_ref must match"),
        ("minimal", {}, {"execution_attempt_id": "attempt-2"}, "cleanup receipt identities must match"),
        ("minimal", {}, {"trial_outcome": "failed"}, "trial_outcome must match"),
    ],
)
def test_receipt_cross_artifact_validation_rejects(
    plan_name: str, receipt_overrides: dict, cleanup_overrides: dict, match: str
) -> None:
    plan = _plan(plan_name)
    receipt = _receipt(plan, **receipt_overrides)
    cleanup_receipt = _success_cleanup_receipt(**cleanup_overrides)
    with pytest.raises(ValueError, match=match):
        validate_batch_execution_receipt(plan, receipt, cleanup_receipt=cleanup_receipt)


def test_failed_cleanup_cannot_be_reported_as_a_clean_successful_trial() -> None:
    plan = _plan("minimal")
    failed_cleanup = TrialCleanupReceiptModel(
        schema_version="trial-cleanup-receipt/v1",
        receipt_id="cleanup-receipt-1",
        cleanup_plan_ref="cleanup-a",
        plan_entry_id="entry-a",
        run_id="run-a",
        execution_attempt_id="attempt-1",
        trial_outcome="succeeded",
        cleanup_status="failed",
        obligation_results={
            "destroy-range": CleanupObligationResultModel(
                obligation_id="destroy-range", status="failed", residual_state_refs=["residual:node.vm-a"]
            )
        },
    )
    receipt = _receipt(plan)
    with pytest.raises(ValueError, match="required cleanup obligation 'destroy-range' must succeed"):
        validate_batch_execution_receipt(plan, receipt, cleanup_receipt=failed_cleanup)


# --- receipt builder ---------------------------------------------------------


def test_build_receipt_rejects_entry_outside_schedule() -> None:
    schedule = plan_batch_schedule(_plan("minimal"))
    outcome = AttemptOutcome(
        execution_attempt_id="attempt-1", trial_outcome="succeeded", cleanup_receipt_ref="cleanup-receipt-1"
    )
    with pytest.raises(ValueError, match="not part of the batch schedule"):
        build_batch_execution_receipt(schedule, "entry-absent", receipt_id="receipt-1", outcome=outcome)


def test_build_receipt_rejects_effective_above_ceiling() -> None:
    schedule = plan_batch_schedule(_plan("minimal"))  # ceiling 1
    outcome = AttemptOutcome(
        execution_attempt_id="attempt-1", trial_outcome="succeeded", cleanup_receipt_ref="cleanup-receipt-1"
    )
    grant = AllocatorGrant(effective_parallelism=2, lease_evidence_refs=["lease:a"])
    with pytest.raises(ValueError, match="cannot exceed the schedule's admitted parallelism ceiling"):
        build_batch_execution_receipt(schedule, "entry-a", receipt_id="receipt-1", outcome=outcome, grant=grant)


def test_built_serial_receipt_validates() -> None:
    plan = _plan("minimal")
    schedule = plan_batch_schedule(plan)
    receipt = build_batch_execution_receipt(
        schedule,
        "entry-a",
        receipt_id="receipt-1",
        outcome=AttemptOutcome(
            execution_attempt_id="attempt-1", trial_outcome="succeeded", cleanup_receipt_ref="cleanup-receipt-1"
        ),
    )
    assert receipt.effective_parallelism == 1
    assert receipt.isolation_proof_ref is None
    validate_batch_execution_receipt(plan, receipt, cleanup_receipt=_success_cleanup_receipt())


def test_built_parallel_receipt_records_allocator_decision_and_validates() -> None:
    plan = _plan("parallel-isolated")
    schedule = plan_batch_schedule(plan)
    receipt = build_batch_execution_receipt(
        schedule,
        "entry-a",
        receipt_id="receipt-1",
        outcome=AttemptOutcome(
            execution_attempt_id="attempt-1", trial_outcome="succeeded", cleanup_receipt_ref="cleanup-receipt-1"
        ),
        grant=AllocatorGrant(effective_parallelism=2, lease_evidence_refs=["lease:a", "lease:b"]),
    )
    assert receipt.effective_parallelism == 2
    assert receipt.isolation_proof_ref == "proof-parallel"  # defaulted from the schedule's admitted proof
    assert receipt.dispatch_ordinal == 0
    validate_batch_execution_receipt(plan, receipt, cleanup_receipt=_success_cleanup_receipt())


# --- schema publication and conformance corpus -------------------------------


def test_schema_bundle_publishes_batch_execution_receipt() -> None:
    from raes_contracts.contracts import schema_bundle

    bundle = schema_bundle()
    assert "batch-execution-receipt-v1" in bundle
    assert bundle["batch-execution-receipt-v1"]["additionalProperties"] is False


def test_batch_execution_receipt_fixture_corpora_validate() -> None:
    from jsonschema import Draft202012Validator
    from raes_contracts.contracts import schema_bundle

    validator = Draft202012Validator(schema_bundle()["batch-execution-receipt-v1"])
    fixture_dir = (
        Path(__file__).resolve().parents[3] / "contracts" / "fixtures" / "control-plane" / "batch-execution-receipt-v1"
    )
    valid = sorted((fixture_dir / "valid").glob("*.json"))
    invalid = sorted((fixture_dir / "invalid").glob("*.json"))
    assert valid, "missing compliant scheduler fixtures"
    assert invalid, "missing contaminating scheduler fixtures"
    for path in valid:
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert not list(validator.iter_errors(payload)), path.name
        BatchExecutionReceiptModel.model_validate(payload)
    for path in invalid:
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert list(validator.iter_errors(payload)), path.name
