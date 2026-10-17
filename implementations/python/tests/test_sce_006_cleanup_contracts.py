"""SCE-007 portable contracts supporting SCE-006 isolated scheduling."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError
from raes_backend_protocols.capabilities import (
    BackendManifest,
    CleanupCapabilities,
    require_cleanup_plan_capability,
)
from raes_backend_protocols.manifest import backend_manifest_from_v2_model, backend_manifest_payload
from raes_backend_stubs.stubs import create_stub_manifest
from raes_contracts.contracts import BackendManifestV2Model, CleanupCapabilitiesModel, schema_bundle
from raes_contracts.contracts.trial_cleanup import (
    CleanStateClaimModel,
    CleanStateRequirementModel,
    CleanupObligationModel,
    CleanupObligationResultModel,
    CleanupResourceBoundaryModel,
    ExecutionRetryPolicyModel,
    IsolationDimensionEvidenceModel,
    SchedulerIsolationProofModel,
    TrialCleanupPlanModel,
    TrialCleanupReceiptModel,
    validate_trial_cleanup_receipt,
)

FIXTURES_ROOT = Path(__file__).resolve().parents[3] / "contracts" / "fixtures"
FIXTURE_GROUPS = {
    "trial-cleanup-plan-v1": "plans",
    "trial-cleanup-receipt-v1": "control-plane",
    "scheduler-isolation-proof-v1": "control-plane",
}


def _boundary() -> CleanupResourceBoundaryModel:
    return CleanupResourceBoundaryModel(
        boundary_id="range-a",
        resource_kind="range-instance",
        owner_ref="apparatus:range-a",
        resource_refs=["node.vm-a", "network.lab-a"],
    )


def _obligation(**overrides: object) -> CleanupObligationModel:
    fields: dict[str, object] = {
        "obligation_id": "destroy-range",
        "boundary_refs": ["range-a"],
        "action_kind": "destroy",
        "triggers": ["success", "failure", "cancellation", "timeout", "abort"],
        "requirement": "required",
        "depends_on": [],
        "idempotency": "idempotent",
        "verification_probe_refs": ["probe:range-absent"],
        "timeout_seconds": 120,
    }
    fields.update(overrides)
    return CleanupObligationModel(**fields)


def _plan(**overrides: object) -> TrialCleanupPlanModel:
    fields: dict[str, object] = {
        "schema_version": "trial-cleanup-plan/v1",
        "plan_id": "cleanup-plan-a",
        "plan_entry_id": "trial-entry-a",
        "run_id": "run-a",
        "clean_state": CleanStateRequirementModel(
            mode="fresh",
            boundary_refs=["range-a"],
            verification_probe_refs=["probe:range-fresh"],
        ),
        "resource_boundaries": {"range-a": _boundary()},
        "cleanup_obligations": {"destroy-range": _obligation()},
        "retry_policy": ExecutionRetryPolicyModel(max_attempts=1, after_effect_policy="disallow"),
    }
    fields.update(overrides)
    return TrialCleanupPlanModel(**fields)


def _result(**overrides: object) -> CleanupObligationResultModel:
    fields: dict[str, object] = {
        "obligation_id": "destroy-range",
        "status": "succeeded",
        "evidence_refs": ["evidence:cleanup-a"],
        "residual_state_refs": [],
    }
    fields.update(overrides)
    return CleanupObligationResultModel(**fields)


def _receipt(**overrides: object) -> TrialCleanupReceiptModel:
    fields: dict[str, object] = {
        "schema_version": "trial-cleanup-receipt/v1",
        "receipt_id": "cleanup-receipt-a",
        "cleanup_plan_ref": "cleanup-plan-a",
        "plan_entry_id": "trial-entry-a",
        "run_id": "run-a",
        "execution_attempt_id": "attempt-a",
        "trial_outcome": "succeeded",
        "cleanup_status": "succeeded",
        "obligation_results": {"destroy-range": _result()},
        "clean_state_claim": CleanStateClaimModel(
            disposition="verified-clean",
            boundary_refs=["range-a"],
            evidence_refs=["evidence:cleanup-a"],
        ),
    }
    fields.update(overrides)
    return TrialCleanupReceiptModel(**fields)


def test_valid_plan_and_receipt_keep_attempt_and_run_identity_distinct() -> None:
    plan = _plan()
    receipt = _receipt()

    validate_trial_cleanup_receipt(plan, receipt)

    assert receipt.execution_attempt_id != receipt.run_id
    assert receipt.cleanup_status == "succeeded"


@pytest.mark.parametrize("trial_outcome", ["failed", "cancelled", "timed-out", "aborted"])
def test_cleanup_success_is_independent_from_primary_trial_outcome(trial_outcome: str) -> None:
    receipt = _receipt(trial_outcome=trial_outcome)

    validate_trial_cleanup_receipt(_plan(), receipt)

    assert receipt.cleanup_status == "succeeded"


def test_required_cleanup_requires_verification_probe() -> None:
    with pytest.raises(ValidationError, match="required cleanup obligations require verification_probe_refs"):
        _obligation(verification_probe_refs=[])


@pytest.mark.parametrize("status", ["skipped", "not-triggered"])
def test_required_cleanup_cannot_be_silently_skipped_or_untriggered(status: str) -> None:
    plan = _plan()
    receipt = _receipt(
        cleanup_status="partial",
        obligation_results={"destroy-range": _result(status=status, evidence_refs=[])},
        clean_state_claim=None,
    )

    with pytest.raises(
        ValueError, match=f"required cleanup obligation 'destroy-range' is owed for trigger 'success'.*'{status}'"
    ):
        validate_trial_cleanup_receipt(plan, receipt)


def test_failed_cleanup_cannot_claim_clean_state() -> None:
    failed_result = _result(
        status="failed",
        evidence_refs=["evidence:failure-a"],
        residual_state_refs=["residual:vm-a"],
    )
    with pytest.raises(ValidationError, match="clean_state_claim requires succeeded cleanup"):
        _receipt(
            cleanup_status="failed",
            obligation_results={"destroy-range": failed_result},
        )


def test_partial_cleanup_discloses_residual_state() -> None:
    receipt = _receipt(
        cleanup_status="partial",
        obligation_results={
            "destroy-range": _result(
                status="failed",
                evidence_refs=["evidence:failure-a"],
                residual_state_refs=["residual:vm-a"],
            )
        },
        clean_state_claim=None,
    )

    assert receipt.obligation_results["destroy-range"].residual_state_refs == ["residual:vm-a"]


_TERMINAL_TRIGGERS = {
    "succeeded": "success",
    "failed": "failure",
    "cancelled": "cancellation",
    "timed-out": "timeout",
    "aborted": "abort",
}


def _unsuccessful_result(status: str) -> CleanupObligationResultModel:
    if status == "unsupported":
        return _result(status=status, evidence_refs=[])
    return _result(status=status, evidence_refs=["evidence:failure-a"], residual_state_refs=["residual:vm-a"])


@pytest.mark.parametrize("trial_outcome", sorted(_TERMINAL_TRIGGERS))
@pytest.mark.parametrize(
    ("cleanup_status", "result_status"),
    [
        ("failed", "failed"),
        ("partial", "failed"),
        ("unsupported", "unsupported"),
        ("unverified", "unverified"),
    ],
)
def test_truthful_required_cleanup_failure_is_reportable_for_every_terminal_trigger(
    trial_outcome: str, cleanup_status: str, result_status: str
) -> None:
    receipt = _receipt(
        trial_outcome=trial_outcome,
        cleanup_status=cleanup_status,
        obligation_results={"destroy-range": _unsuccessful_result(result_status)},
        clean_state_claim=None,
    )

    validate_trial_cleanup_receipt(_plan(), receipt)

    assert receipt.trial_outcome == trial_outcome
    assert receipt.cleanup_status == cleanup_status
    assert receipt.clean_state_claim is None


def test_issue_reproduction_failed_and_interrupted_cleanup_are_accepted() -> None:
    plan = _plan(cleanup_obligations={"destroy-range": _obligation(triggers=["success", "failure", "cancellation"])})
    for trial_outcome, status in (("succeeded", "succeeded"), ("failed", "failed"), ("cancelled", "unverified")):
        result = _result() if status == "succeeded" else _unsuccessful_result(status)
        receipt = _receipt(
            receipt_id=f"receipt-{status}",
            trial_outcome=trial_outcome,
            cleanup_status=status,
            obligation_results={"destroy-range": result},
            clean_state_claim=None,
        )

        validate_trial_cleanup_receipt(plan, receipt)


def test_partial_cleanup_reports_mixed_required_and_best_effort_results() -> None:
    plan = _plan(
        cleanup_obligations={
            "destroy-range": _obligation(),
            "collect-logs": _obligation(
                obligation_id="collect-logs",
                action_kind="verify",
                requirement="best-effort",
                verification_probe_refs=[],
            ),
        }
    )
    receipt = _receipt(
        trial_outcome="failed",
        cleanup_status="partial",
        obligation_results={
            "destroy-range": _result(),
            "collect-logs": _unsuccessful_result("failed").model_copy(update={"obligation_id": "collect-logs"}),
        },
        clean_state_claim=None,
    )

    validate_trial_cleanup_receipt(plan, receipt)


@pytest.mark.parametrize("trial_outcome", sorted(_TERMINAL_TRIGGERS))
@pytest.mark.parametrize("cleanup_status", ["succeeded", "failed", "partial", "unsupported", "unverified"])
def test_owed_required_cleanup_result_cannot_disappear(trial_outcome: str, cleanup_status: str) -> None:
    receipt = _receipt(
        trial_outcome=trial_outcome,
        cleanup_status=cleanup_status,
        obligation_results={},
        clean_state_claim=None,
    )

    trigger = _TERMINAL_TRIGGERS[trial_outcome]
    with pytest.raises(
        ValueError, match=f"required cleanup obligation 'destroy-range' is owed for trigger '{trigger}'"
    ):
        validate_trial_cleanup_receipt(_plan(), receipt)


@pytest.mark.parametrize("trial_outcome", sorted(_TERMINAL_TRIGGERS))
def test_not_required_cleanup_cannot_hide_an_owed_required_obligation(trial_outcome: str) -> None:
    receipt = _receipt(
        trial_outcome=trial_outcome,
        cleanup_status="not-required",
        obligation_results={},
        clean_state_claim=None,
    )

    with pytest.raises(ValueError, match="required cleanup obligation 'destroy-range' is owed"):
        validate_trial_cleanup_receipt(_plan(), receipt)


@pytest.mark.parametrize("result_status", ["failed", "unsupported", "unverified"])
def test_succeeded_cleanup_cannot_report_unsuccessful_required_result(result_status: str) -> None:
    # ContractModel is not frozen and model_copy skips model validation, so the
    # public join must reject false success on its own.
    receipt = _receipt(clean_state_claim=None).model_copy(
        update={"obligation_results": {"destroy-range": _unsuccessful_result(result_status)}}
    )

    with pytest.raises(
        ValueError, match="succeeded cleanup status requires required cleanup obligation 'destroy-range'"
    ):
        validate_trial_cleanup_receipt(_plan(), receipt)


def test_succeeded_cleanup_cannot_report_unsuccessful_best_effort_result() -> None:
    plan = _plan(
        cleanup_obligations={
            "destroy-range": _obligation(),
            "collect-logs": _obligation(
                obligation_id="collect-logs",
                action_kind="verify",
                requirement="best-effort",
                verification_probe_refs=[],
            ),
        }
    )
    receipt = _receipt(clean_state_claim=None).model_copy(
        update={
            "obligation_results": {
                "destroy-range": _result(),
                "collect-logs": _result(obligation_id="collect-logs", status="skipped", evidence_refs=[]),
            }
        }
    )

    with pytest.raises(
        ValueError, match="succeeded cleanup status cannot include unsuccessful result for 'collect-logs'"
    ):
        validate_trial_cleanup_receipt(plan, receipt)


def test_successful_result_cannot_disclose_residual_state() -> None:
    with pytest.raises(ValidationError, match="successful cleanup results cannot disclose residual state"):
        _result(residual_state_refs=["residual:vm-a"])


def test_triggered_best_effort_obligation_may_be_skipped_without_required_coverage() -> None:
    plan = _plan(
        cleanup_obligations={
            "destroy-range": _obligation(),
            "collect-logs": _obligation(
                obligation_id="collect-logs",
                action_kind="verify",
                requirement="best-effort",
                verification_probe_refs=[],
            ),
        }
    )
    receipt = _receipt(
        trial_outcome="cancelled",
        cleanup_status="partial",
        obligation_results={
            "destroy-range": _result(),
            "collect-logs": _result(obligation_id="collect-logs", status="skipped", evidence_refs=[]),
        },
        clean_state_claim=None,
    )

    validate_trial_cleanup_receipt(plan, receipt)


def test_triggered_best_effort_obligation_cannot_claim_not_triggered() -> None:
    plan = _plan(
        cleanup_obligations={
            "destroy-range": _obligation(),
            "collect-logs": _obligation(
                obligation_id="collect-logs",
                action_kind="verify",
                requirement="best-effort",
                verification_probe_refs=[],
            ),
        }
    )
    receipt = _receipt(
        clean_state_claim=None,
        obligation_results={
            "destroy-range": _result(),
            "collect-logs": _result(obligation_id="collect-logs", status="not-triggered", evidence_refs=[]),
        },
    )

    with pytest.raises(ValueError, match="cleanup obligation 'collect-logs' is triggered by 'success'"):
        validate_trial_cleanup_receipt(plan, receipt)


def test_untriggered_obligation_may_be_omitted_or_reported_not_triggered() -> None:
    plan = _plan(cleanup_obligations={"destroy-range": _obligation(triggers=["failure"])})

    validate_trial_cleanup_receipt(plan, _receipt(obligation_results={}, clean_state_claim=None))
    validate_trial_cleanup_receipt(
        plan,
        _receipt(
            obligation_results={"destroy-range": _result(status="not-triggered", evidence_refs=[])},
            clean_state_claim=None,
        ),
    )


@pytest.mark.parametrize("result_status", ["succeeded", "failed"])
def test_untriggered_obligation_cannot_report_an_execution_result(result_status: str) -> None:
    plan = _plan(cleanup_obligations={"destroy-range": _obligation(triggers=["failure"])})
    result = _result() if result_status == "succeeded" else _unsuccessful_result(result_status)
    cleanup_status = "succeeded" if result_status == "succeeded" else "failed"
    receipt = _receipt(
        cleanup_status=cleanup_status,
        obligation_results={"destroy-range": result},
        clean_state_claim=None,
    )

    with pytest.raises(ValueError, match="cleanup obligation 'destroy-range' is not triggered by 'success'"):
        validate_trial_cleanup_receipt(plan, receipt)


@pytest.mark.parametrize("trial_outcome", sorted(_TERMINAL_TRIGGERS))
def test_retry_only_obligation_is_never_owed_by_a_terminal_outcome(trial_outcome: str) -> None:
    reset = _obligation(
        obligation_id="reset-range",
        action_kind="reset",
        triggers=["retry"],
        idempotency="requires-reset",
    )
    plan = _plan(
        cleanup_obligations={"destroy-range": _obligation(), "reset-range": reset},
        retry_policy=ExecutionRetryPolicyModel(
            max_attempts=2,
            after_effect_policy="reset",
            reset_obligation_refs=["reset-range"],
        ),
    )

    validate_trial_cleanup_receipt(plan, _receipt(trial_outcome=trial_outcome))


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"cleanup_plan_ref": "other-plan"}, "cleanup_plan_ref must match plan_id"),
        ({"plan_entry_id": "other-entry"}, "plan_entry_id and run_id must match"),
        ({"run_id": "other-run"}, "plan_entry_id and run_id must match"),
    ],
)
def test_failed_cleanup_receipt_still_binds_plan_identity(overrides: dict[str, object], message: str) -> None:
    receipt = _receipt(
        trial_outcome="failed",
        cleanup_status="failed",
        obligation_results={"destroy-range": _unsuccessful_result("failed")},
        clean_state_claim=None,
        **overrides,
    )

    with pytest.raises(ValueError, match=message):
        validate_trial_cleanup_receipt(_plan(), receipt)


def test_failed_cleanup_receipt_rejects_unknown_obligation_results() -> None:
    receipt = _receipt(
        trial_outcome="failed",
        cleanup_status="failed",
        obligation_results={
            "destroy-range": _unsuccessful_result("failed"),
            "ghost": _unsuccessful_result("failed").model_copy(update={"obligation_id": "ghost"}),
        },
        clean_state_claim=None,
    )

    with pytest.raises(ValueError, match="unknown obligations: ghost"):
        validate_trial_cleanup_receipt(_plan(), receipt)


def test_reusable_state_requires_bounded_evidence() -> None:
    with pytest.raises(ValidationError, match="declared-reusable clean state requires"):
        CleanStateRequirementModel(mode="declared-reusable", boundary_refs=["range-a"])


def test_resource_and_dependency_references_must_resolve() -> None:
    missing_boundary = _obligation(boundary_refs=["missing-range"])
    with pytest.raises(ValidationError, match="unknown resource boundaries"):
        _plan(cleanup_obligations={"destroy-range": missing_boundary})

    missing_dependency = _obligation(depends_on=["missing-obligation"])
    with pytest.raises(ValidationError, match="unknown cleanup dependencies"):
        _plan(cleanup_obligations={"destroy-range": missing_dependency})


def test_cleanup_dependency_graph_must_be_acyclic() -> None:
    first = _obligation(obligation_id="first", depends_on=["second"])
    second = _obligation(obligation_id="second", depends_on=["first"])

    with pytest.raises(ValidationError, match="dependency graph must be acyclic"):
        _plan(cleanup_obligations={"first": first, "second": second})


def test_non_idempotent_retry_requires_explicit_reset_or_compensation() -> None:
    unsafe = _obligation(idempotency="not-repeatable")
    retry_policy = ExecutionRetryPolicyModel(max_attempts=2, after_effect_policy="idempotent")

    with pytest.raises(ValidationError, match="non-idempotent effects require explicit reset or compensation"):
        _plan(
            cleanup_obligations={"destroy-range": unsafe},
            retry_policy=retry_policy,
        )


def test_reset_retry_policy_references_required_retry_capable_reset_obligation() -> None:
    reset = _obligation(
        obligation_id="reset-range",
        action_kind="reset",
        triggers=["retry"],
        idempotency="requires-reset",
    )
    plan = _plan(
        cleanup_obligations={"reset-range": reset},
        retry_policy=ExecutionRetryPolicyModel(
            max_attempts=2,
            after_effect_policy="reset",
            reset_obligation_refs=["reset-range"],
        ),
    )

    assert plan.retry_policy.after_effect_policy == "reset"


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"action_kind": "destroy"}, "not required reset actions triggered by retry"),
        ({"triggers": ["failure"]}, "not required reset actions triggered by retry"),
        ({"requirement": "best-effort"}, "not required reset actions triggered by retry"),
        ({"boundary_refs": ["range-b"]}, "do not cover non-idempotent effect boundaries"),
    ],
)
def test_reset_retry_policy_rejects_non_retry_capable_reset_obligations(
    overrides: dict[str, object], message: str
) -> None:
    reset_fields: dict[str, object] = {
        "obligation_id": "reset-range",
        "action_kind": "reset",
        "triggers": ["retry"],
        "idempotency": "requires-reset",
    }
    reset_fields.update(overrides)
    resource_boundaries = {"range-a": _boundary()}
    if reset_fields.get("boundary_refs") == ["range-b"]:
        resource_boundaries["range-b"] = CleanupResourceBoundaryModel(
            boundary_id="range-b",
            resource_kind="range-instance",
            owner_ref="apparatus:range-b",
            resource_refs=["node.vm-b"],
        )

    obligations = {
        "effect-range": _obligation(
            obligation_id="effect-range",
            idempotency="not-repeatable",
        ),
        "reset-range": _obligation(**reset_fields),
    }
    retry_policy = ExecutionRetryPolicyModel(
        max_attempts=2,
        after_effect_policy="reset",
        reset_obligation_refs=["reset-range"],
    )
    with pytest.raises(ValidationError, match=message):
        _plan(
            resource_boundaries=resource_boundaries,
            cleanup_obligations=obligations,
            retry_policy=retry_policy,
        )


def _dimension(dimension: str) -> IsolationDimensionEvidenceModel:
    return IsolationDimensionEvidenceModel(
        dimension=dimension,
        independent=True,
        evidence_refs=[f"evidence:{dimension}"],
    )


def test_scheduler_isolation_defaults_to_serial_without_parallel_proof() -> None:
    proof = SchedulerIsolationProofModel(
        schema_version="scheduler-isolation-proof/v1",
        proof_id="proof-serial",
        plan_entry_ids=["trial-entry-a"],
    )

    assert proof.requested_parallelism == 1
    assert proof.dimensions == []


def test_parallel_scheduler_requires_every_isolation_dimension() -> None:
    dimensions = [_dimension("range-instance")]
    with pytest.raises(ValidationError, match="parallel isolation proof requires dimensions"):
        SchedulerIsolationProofModel(
            schema_version="scheduler-isolation-proof/v1",
            proof_id="proof-parallel",
            plan_entry_ids=["trial-entry-a", "trial-entry-b"],
            requested_parallelism=2,
            dimensions=dimensions,
        )


def test_parallel_scheduler_accepts_complete_independent_evidence() -> None:
    required = (
        "range-instance",
        "host-capacity",
        "ports",
        "storage",
        "control-plane-locks",
        "secret-scope",
        "cleanup",
    )
    proof = SchedulerIsolationProofModel(
        schema_version="scheduler-isolation-proof/v1",
        proof_id="proof-parallel",
        plan_entry_ids=["trial-entry-a", "trial-entry-b"],
        requested_parallelism=2,
        dimensions=[_dimension(dimension) for dimension in required],
    )

    assert proof.requested_parallelism == 2


def test_parallel_scheduler_requires_secret_scope_isolation() -> None:
    # SCE-006 governs secret scope as a required parallel isolation dimension; a
    # proof carrying every other dimension but omitting secret-scope must fail.
    without_secret_scope = (
        "range-instance",
        "host-capacity",
        "ports",
        "storage",
        "control-plane-locks",
        "cleanup",
    )
    dimensions = [_dimension(dimension) for dimension in without_secret_scope]
    with pytest.raises(ValidationError, match="secret-scope"):
        SchedulerIsolationProofModel(
            schema_version="scheduler-isolation-proof/v1",
            proof_id="proof-parallel",
            plan_entry_ids=["trial-entry-a", "trial-entry-b"],
            requested_parallelism=2,
            dimensions=dimensions,
        )


def test_contracts_forbid_unbounded_metadata_and_secret_payload_fields() -> None:
    payload = _plan().model_dump(mode="json")
    payload["environment"] = {"TOKEN": "secret"}

    with pytest.raises(ValidationError):
        TrialCleanupPlanModel.model_validate(payload)


def test_schema_bundle_publishes_cleanup_and_isolation_contracts() -> None:
    bundle = schema_bundle()

    assert {
        "trial-cleanup-plan-v1",
        "trial-cleanup-receipt-v1",
        "scheduler-isolation-proof-v1",
    } <= set(bundle)
    assert bundle["trial-cleanup-plan-v1"]["additionalProperties"] is False
    assert bundle["trial-cleanup-receipt-v1"]["additionalProperties"] is False
    assert bundle["scheduler-isolation-proof-v1"]["additionalProperties"] is False


def test_cleanup_capability_requires_both_plan_and_receipt_contracts() -> None:
    with pytest.raises(ValidationError, match="cleanup capabilities require contract versions"):
        CleanupCapabilitiesModel(
            name="cleanup",
            supported_contract_versions=["trial-cleanup-plan-v1"],
            supported_action_kinds=["destroy"],
            supported_verification_methods=["probe"],
            supports_reusable_state=True,
            supports_residual_state_disclosure=True,
        )

    supported_contract_versions = frozenset({"trial-cleanup-plan-v1"})
    supported_action_kinds = frozenset({"destroy"})
    supported_verification_methods = frozenset({"probe"})
    with pytest.raises(ValueError, match="CleanupCapabilities.supported_contract_versions"):
        CleanupCapabilities(
            name="cleanup",
            supported_contract_versions=supported_contract_versions,
            supported_action_kinds=supported_action_kinds,
            supported_verification_methods=supported_verification_methods,
            supports_reusable_state=True,
            supports_residual_state_disclosure=True,
        )


def test_reference_manifest_declares_typed_cleanup_capability_and_round_trips() -> None:
    payload = backend_manifest_payload(create_stub_manifest())
    cleanup = payload["capabilities"]["cleanup"]

    assert cleanup["supported_contract_versions"] == [
        "trial-cleanup-plan-v1",
        "trial-cleanup-receipt-v1",
    ]
    assert cleanup["supports_reusable_state"] is True
    assert cleanup["supports_residual_state_disclosure"] is True

    model = BackendManifestV2Model.model_validate(payload)
    round_tripped = backend_manifest_from_v2_model(model)
    assert round_tripped.cleanup is not None
    assert round_tripped.cleanup.supported_action_kinds == frozenset(
        {"destroy", "reset", "restore", "compensate", "verify"}
    )


def _manifest_with_cleanup(cleanup: CleanupCapabilities | None) -> BackendManifest:
    source = create_stub_manifest()
    supported = source.supported_contract_versions
    if cleanup is None:
        supported = supported - {"trial-cleanup-plan-v1", "trial-cleanup-receipt-v1"}
    return BackendManifest(
        identity=source.identity,
        supported_contract_versions=supported,
        compatibility=source.compatibility,
        realization_support=source.realization_support,
        concept_bindings=source.concept_bindings,
        constraints=source.constraints,
        capabilities=replace(source.capabilities, cleanup=cleanup),
    )


def test_cleanup_plan_admission_requires_declared_backend_capability() -> None:
    manifest = _manifest_with_cleanup(None)
    plan = _plan()
    with pytest.raises(ValueError, match="backend does not declare cleanup capabilities"):
        require_cleanup_plan_capability(manifest, plan)


def test_cleanup_plan_admission_rejects_unsupported_action_and_probe_method() -> None:
    base = create_stub_manifest().cleanup
    assert base is not None
    plan = _plan()
    unsupported_action = replace(base, supported_action_kinds=frozenset({"reset"}))
    action_manifest = _manifest_with_cleanup(unsupported_action)
    with pytest.raises(ValueError, match="unsupported cleanup action kinds: destroy"):
        require_cleanup_plan_capability(action_manifest, plan)

    unsupported_probe = replace(base, supported_verification_methods=frozenset({"receipt"}))
    probe_manifest = _manifest_with_cleanup(unsupported_probe)
    with pytest.raises(ValueError, match="unsupported cleanup verification methods: probe"):
        require_cleanup_plan_capability(probe_manifest, plan)


def test_cleanup_plan_admission_accepts_supported_required_cleanup() -> None:
    manifest = create_stub_manifest()

    require_cleanup_plan_capability(manifest, _plan())


@pytest.mark.parametrize(
    "contract_id",
    ["trial-cleanup-plan-v1", "trial-cleanup-receipt-v1", "scheduler-isolation-proof-v1"],
)
def test_cleanup_contract_fixture_corpora_validate(contract_id: str) -> None:
    validator = Draft202012Validator(schema_bundle()[contract_id])
    fixture_dir = FIXTURES_ROOT / FIXTURE_GROUPS[contract_id] / contract_id
    valid = sorted((fixture_dir / "valid").glob("*.json"))
    invalid = sorted((fixture_dir / "invalid").glob("*.json"))

    assert valid, f"missing valid fixtures for {contract_id}"
    assert invalid, f"missing invalid fixtures for {contract_id}"
    for path in valid:
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert not list(validator.iter_errors(payload)), path.name
    for path in invalid:
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert list(validator.iter_errors(payload)), path.name


def test_receipt_fixtures_cover_terminal_outcomes_and_cleanup_failures() -> None:
    fixture_dir = FIXTURES_ROOT / "control-plane" / "trial-cleanup-receipt-v1"
    valid_names = {path.name for path in (fixture_dir / "valid").glob("*.json")}
    invalid_names = {path.name for path in (fixture_dir / "invalid").glob("*.json")}

    assert {
        "success.json",
        "primary-failure-cleanup-succeeded.json",
        "cancellation.json",
        "timeout.json",
        "abort.json",
        "partial-cleanup.json",
        "required-cleanup-failed.json",
        "success-cleanup-failed.json",
        "cancellation-cleanup-unverified.json",
        "timeout-cleanup-unsupported.json",
        "abort-cleanup-failed.json",
    } <= valid_names
    assert {"unverified-clean-claim.json", "unsupported-clean-claim.json"} <= invalid_names


def test_valid_receipt_fixtures_cross_validate_against_the_canonical_cleanup_plan() -> None:
    plan_payload = json.loads(
        (FIXTURES_ROOT / "plans" / "trial-cleanup-plan-v1" / "valid" / "fresh-range.json").read_text(encoding="utf-8")
    )
    plan = TrialCleanupPlanModel.model_validate(plan_payload)
    fixture_dir = FIXTURES_ROOT / "control-plane" / "trial-cleanup-receipt-v1" / "valid"

    for path in sorted(fixture_dir.glob("*.json")):
        receipt = TrialCleanupReceiptModel.model_validate_json(path.read_text(encoding="utf-8"))
        validate_trial_cleanup_receipt(plan, receipt)
