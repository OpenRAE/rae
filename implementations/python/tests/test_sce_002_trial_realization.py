"""Public admitted-entry realization and archival provenance integration."""

from __future__ import annotations

import json
from dataclasses import replace

import pytest
import raes_processor.trial_realization as trial_realization_module
from paths import REPO_ROOT
from pydantic import ValidationError
from raes import canonical_instantiated_sdl_digest
from raes.phase_contracts import TrialInstantiationProvenance
from raes_contracts.canonical import canonical_json_digest
from raes_contracts.contracts import (
    CleanStateClaimModel,
    CleanupObligationResultModel,
    ExperimentManifestReferenceModel,
    ExperimentProcessorReferenceModel,
    ExperimentRunModel,
    ExperimentScenarioReferenceModel,
    ExperimentStudyModel,
    ExperimentTaskModel,
    ProcessorManifestV2Model,
    TrialCleanupReceiptModel,
    TrialExecutionAttemptReferenceModel,
    TrialRunProvenanceModel,
    reconcile_admitted_trial_plan,
    validate_admitted_trial_run,
    validate_admitted_trial_study,
)
from raes_processor.trial_compiler import TrialCompilationRequest, compile_admitted_trial_plan
from raes_processor.trial_realization import (
    TrialRealizationInputs,
    instantiate_admitted_trial_entry,
    realize_admitted_trial_entry,
)
from test_sce_002_trial_compiler import _product_family, _request

_TASK_FIXTURE = (
    REPO_ROOT / "contracts" / "fixtures" / "experiment-core" / "experiment-task-v1" / "valid" / "reference.json"
)
_PROCESSOR_FIXTURE = (
    REPO_ROOT / "contracts" / "fixtures" / "processor-manifest" / "processor-manifest-v2" / "valid" / "reference.json"
)
_RUN_FIXTURE = (
    REPO_ROOT / "contracts" / "fixtures" / "experiment-core" / "experiment-run-v1" / "valid" / "reference.json"
)
_STUDY_FIXTURE = (
    REPO_ROOT / "contracts" / "fixtures" / "experiment-core" / "experiment-study-v1" / "valid" / "reference.json"
)
_BACKEND_KEY = ("backend", "backend-a", "1", "backend-manifest/v2")


def _plan_and_entry():
    request = _request_with_processor()
    result = compile_admitted_trial_plan(request)
    assert result.plan is not None
    assert result.diagnostics == ()
    entry = next(iter(result.plan.entries.values()))
    return request, result.plan, entry


def _request_with_processor() -> TrialCompilationRequest:
    request = _request(run_count=2, sample=True)
    payload = json.loads(_PROCESSOR_FIXTURE.read_text(encoding="utf-8"))
    payload["compatibility"]["backends"] = ["backend-a"]
    processor = ProcessorManifestV2Model.model_validate(payload)
    processor_ref = ExperimentManifestReferenceModel(
        ref_kind="manifest",
        ref_id=processor.identity.name,
        ref_version=processor.schema_version,
        ref_digest=canonical_json_digest(processor.model_dump(mode="json")),
        subject_ref=ExperimentProcessorReferenceModel(
            ref_kind="processor",
            ref_id=processor.identity.name,
            ref_version=processor.identity.version,
        ),
    )
    apparatus = request.apparatus.model_copy(
        update={"manifest_refs": [*request.apparatus.manifest_refs, processor_ref]}
    )
    manifests = {
        **request.apparatus_manifests,
        (
            "processor",
            processor.identity.name,
            processor.identity.version,
            processor.schema_version,
        ): processor,
    }
    return replace(request, apparatus=apparatus, apparatus_manifests=manifests)


def _realization_inputs(
    request: TrialCompilationRequest,
    plan,
    task: ExperimentTaskModel,
    *,
    apparatus_manifests=None,
) -> TrialRealizationInputs:
    return TrialRealizationInputs(
        plan=plan,
        family=request.family,
        experiment=request.experiment,
        task=task,
        capture_specs=request.capture_specs,
        apparatus_manifests=request.apparatus_manifests if apparatus_manifests is None else apparatus_manifests,
        realization_envelope=request.realization_envelope,
        backend_key=_BACKEND_KEY,
    )


def test_admitted_entry_uses_public_instantiation_and_binds_complete_lineage() -> None:
    request, plan, entry = _plan_and_entry()

    instantiated = instantiate_admitted_trial_entry(
        plan=plan,
        plan_entry_id=entry.plan_entry_id,
        family=request.family,
    )

    provenance = instantiated.instantiation_provenance
    assert provenance is not None
    assert isinstance(provenance.trial, TrialInstantiationProvenance)
    assert provenance.trial.scenario_family_id == request.family.name
    assert provenance.trial.scenario_family_digest == plan.input_refs.scenario_family_ref.ref_digest
    assert provenance.trial.plan_id == plan.plan_id
    assert provenance.trial.plan_digest == plan.plan_digest
    assert provenance.trial.plan_entry_id == entry.plan_entry_id
    assert provenance.trial.entry_digest == entry.entry_digest
    assert provenance.trial.run_id == entry.run_id
    assert provenance.trial.coordinate.model_dump(mode="json") == entry.coordinate.model_dump(mode="json")
    assert [record.record for record in provenance.trial.selections] == [
        selection.model_dump(mode="json") for selection in entry.selections
    ]
    assert [record.record for record in provenance.trial.bindings] == [
        binding.model_dump(mode="json") for binding in entry.bindings
    ]
    assert canonical_instantiated_sdl_digest(instantiated).value.startswith("sha256:")


def test_admitted_entry_rejects_family_substitution_before_selection() -> None:
    _, plan, entry = _plan_and_entry()
    substituted_family = _product_family()

    with pytest.raises(ValueError, match="family identity"):
        instantiate_admitted_trial_entry(
            plan=plan,
            plan_entry_id=entry.plan_entry_id,
            family=substituted_family,
        )


def test_admitted_entry_reconstructs_plan_before_entry_lookup() -> None:
    request, plan, entry = _plan_and_entry()
    plan.__dict__["plan_digest"] = "sha256:" + "0" * 64

    with pytest.raises(ValueError, match="plan failed closed reconstruction"):
        instantiate_admitted_trial_entry(
            plan=plan,
            plan_entry_id=entry.plan_entry_id,
            family=request.family,
        )


def test_admitted_entry_rejects_selected_value_substitution() -> None:
    request, plan, entry = _plan_and_entry()
    tampered = plan.model_copy(deep=True)
    tampered.entries[entry.plan_entry_id].selections[0].outcome.__dict__["value"] = "/opt/substituted"

    with pytest.raises(ValueError, match="plan failed closed reconstruction"):
        instantiate_admitted_trial_entry(
            plan=tampered,
            plan_entry_id=entry.plan_entry_id,
            family=request.family,
        )


def test_admitted_entry_rejects_unknown_entry_without_fallback() -> None:
    request, plan, _ = _plan_and_entry()

    with pytest.raises(ValueError, match="plan_entry_id"):
        instantiate_admitted_trial_entry(
            plan=plan,
            plan_entry_id="missing-entry",
            family=request.family,
        )


def test_trial_realization_emits_three_digest_bound_public_processor_plans() -> None:
    request, plan, entry = _plan_and_entry()
    task = ExperimentTaskModel.model_validate_json(_TASK_FIXTURE.read_text(encoding="utf-8"))

    realized = realize_admitted_trial_entry(
        inputs=_realization_inputs(request, plan, task),
        plan_entry_id=entry.plan_entry_id,
    )

    assert realized.instantiated.instantiation_provenance.trial.plan_entry_id == entry.plan_entry_id
    assert realized.snapshot_digest == canonical_instantiated_sdl_digest(realized.instantiated).value
    assert {reference.plan_kind for reference in realized.processor_plan_refs} == {
        "provisioning",
        "orchestration",
        "evaluation",
    }
    assert all(reference.artifact_ref.ref_digest for reference in realized.processor_plan_refs)
    projected = {
        "provisioning": realized.provisioning_plan,
        "orchestration": realized.orchestration_plan,
        "evaluation": realized.evaluation_plan,
    }
    assert {reference.plan_kind: reference.artifact_ref.ref_digest for reference in realized.processor_plan_refs} == {
        plan_kind: canonical_json_digest(model.model_dump(mode="json")) for plan_kind, model in projected.items()
    }
    assert realized.execution_plan.provisioning is not None


def test_trial_realization_rejects_task_or_manifest_substitution() -> None:
    request, plan, entry = _plan_and_entry()
    task = ExperimentTaskModel.model_validate_json(_TASK_FIXTURE.read_text(encoding="utf-8"))
    wrong_task = task.model_copy(update={"task_id": "other-task"})
    wrong_task_inputs = _realization_inputs(request, plan, wrong_task)

    with pytest.raises(ValueError, match="task identity"):
        realize_admitted_trial_entry(
            inputs=wrong_task_inputs,
            plan_entry_id=entry.plan_entry_id,
        )

    substituted_task = task.model_copy(update={"title": "Substituted task content"})
    substituted_task_inputs = _realization_inputs(request, plan, substituted_task)
    with pytest.raises(ValueError, match="task identity"):
        realize_admitted_trial_entry(
            inputs=substituted_task_inputs,
            plan_entry_id=entry.plan_entry_id,
        )

    manifests = dict(request.apparatus_manifests)
    manifests[("backend", "backend-a", "1", "backend-manifest/v2")] = manifests[
        ("backend", "backend-a", "1", "backend-manifest/v2")
    ].model_copy(update={"constraints": {"substituted": "true"}})
    substituted_manifest_inputs = _realization_inputs(request, plan, task, apparatus_manifests=manifests)
    with pytest.raises(ValueError, match="manifest"):
        realize_admitted_trial_entry(
            inputs=substituted_manifest_inputs,
            plan_entry_id=entry.plan_entry_id,
        )


def test_trial_realization_rejects_capture_spec_identity_mismatch() -> None:
    request, plan, _ = _plan_and_entry()
    task = ExperimentTaskModel.model_validate_json(_TASK_FIXTURE.read_text(encoding="utf-8"))

    with pytest.raises(ValueError, match="capture specification identities"):
        trial_realization_module._validate_capture_specs(plan, request.experiment, task, {})


def test_trial_realization_rejects_capture_spec_digest_mismatch() -> None:
    request, plan, _ = _plan_and_entry()
    task = ExperimentTaskModel.model_validate_json(_TASK_FIXTURE.read_text(encoding="utf-8"))
    capture_spec = next(iter(request.capture_specs.values()))
    changed_spec = capture_spec.model_copy(update={"title": "Substituted capture specification"})

    with pytest.raises(ValueError, match="capture specification digests"):
        trial_realization_module._validate_capture_specs(
            plan,
            request.experiment,
            task,
            {changed_spec.capture_spec_id: changed_spec},
        )


def test_trial_realization_rejects_unresolved_task_evidence_requirement() -> None:
    request, plan, _ = _plan_and_entry()
    task = ExperimentTaskModel.model_validate_json(_TASK_FIXTURE.read_text(encoding="utf-8"))
    capture_spec = next(iter(request.capture_specs.values()))
    requirement = next(iter(capture_spec.capture_requirements.values())).model_copy(
        update={"requirement_id": "other-evidence"}
    )
    changed_spec = capture_spec.model_copy(update={"capture_requirements": {requirement.requirement_id: requirement}})
    changed_ref = plan.input_refs.capture_spec_refs[0].model_copy(
        update={"ref_digest": canonical_json_digest(changed_spec.model_dump(mode="json"))}
    )
    changed_plan = plan.model_copy(
        update={"input_refs": plan.input_refs.model_copy(update={"capture_spec_refs": [changed_ref]})}
    )

    with pytest.raises(ValueError, match="task evidence requirements"):
        trial_realization_module._validate_capture_specs(
            changed_plan,
            request.experiment,
            task,
            {changed_spec.capture_spec_id: changed_spec},
        )


def _archival_run_and_receipt():
    request, plan, entry = _plan_and_entry()
    task = ExperimentTaskModel.model_validate_json(_TASK_FIXTURE.read_text(encoding="utf-8"))
    realized = realize_admitted_trial_entry(
        inputs=_realization_inputs(request, plan, task),
        plan_entry_id=entry.plan_entry_id,
    )
    cleanup_plan = plan.cleanup_plans[entry.execution_controls.cleanup_plan_ref]
    results = {
        obligation_id: CleanupObligationResultModel(
            obligation_id=obligation_id,
            status="succeeded",
            evidence_refs=[f"evidence:{obligation_id}"],
            residual_state_refs=[],
        )
        for obligation_id in cleanup_plan.cleanup_obligations
    }
    receipt = TrialCleanupReceiptModel(
        receipt_id="receipt-attempt-1",
        cleanup_plan_ref=cleanup_plan.plan_id,
        plan_entry_id=entry.plan_entry_id,
        run_id=entry.run_id,
        execution_attempt_id="attempt-1",
        trial_outcome="succeeded",
        cleanup_status="succeeded",
        obligation_results=results,
        clean_state_claim=CleanStateClaimModel(
            disposition="verified-clean",
            boundary_refs=list(cleanup_plan.resource_boundaries),
            evidence_refs=["evidence:clean"],
        ),
    )
    linkage = TrialRunProvenanceModel(
        plan_id=plan.plan_id,
        plan_digest=plan.plan_digest,
        plan_entry_id=entry.plan_entry_id,
        entry_digest=entry.entry_digest,
        admitted_run_id=entry.run_id,
        coordinate=entry.coordinate,
        instantiated_scenario_digest=realized.snapshot_digest,
        processor_plan_refs=list(realized.processor_plan_refs),
        execution_attempts=[
            TrialExecutionAttemptReferenceModel(
                execution_attempt_id=receipt.execution_attempt_id,
                cleanup_receipt_ref=receipt.receipt_id,
            )
        ],
        terminal_attempt_id=receipt.execution_attempt_id,
    )
    payload = json.loads(_RUN_FIXTURE.read_text(encoding="utf-8"))
    payload["run_id"] = entry.run_id
    payload["participant_implementation_provenance"]["run_id"] = entry.run_id
    payload["scenario_snapshot_ref"] = {
        "ref_kind": "scenario-snapshot",
        "ref_id": request.family.name,
        "ref_version": "raes-sdl-instantiated-snapshot/v1",
        "ref_digest": realized.snapshot_digest,
    }
    payload["stochastic_controls"] = [control.model_dump(mode="json") for control in plan.stochastic_controls.values()]
    payload["stochastic_draws"] = [draw.model_dump(mode="json") for draw in entry.stochastic_draws]
    payload["trial_provenance"] = linkage.model_dump(mode="json")
    run = ExperimentRunModel.model_validate(payload)
    return plan, entry, run, receipt


def test_archival_run_reconciles_exact_entry_attempt_and_cleanup_evidence() -> None:
    plan, _, run, receipt = _archival_run_and_receipt()

    validate_admitted_trial_run(plan, run, [receipt])
    reconciliation = reconcile_admitted_trial_plan(plan, [run], [receipt])

    assert reconciliation.entry_count == len(plan.entries)
    assert reconciliation.attempted_entry_ids == (run.trial_provenance.plan_entry_id,)
    assert reconciliation.unattempted_entry_ids


def test_archival_reconciliation_rejects_cross_entry_or_stale_attempt_refs() -> None:
    plan, _, run, receipt = _archival_run_and_receipt()
    wrong_receipt = receipt.model_copy(update={"execution_attempt_id": "attempt-other"})

    with pytest.raises(ValueError, match="execution attempt"):
        validate_admitted_trial_run(plan, run, [wrong_receipt])

    duplicate = run.model_copy(update={"run_version": "second"})
    with pytest.raises(ValueError, match="more than one archival run"):
        reconcile_admitted_trial_plan(plan, [run, duplicate], [receipt])


def test_cleanup_failure_does_not_rewrite_successful_primary_outcome() -> None:
    plan, _, run, receipt = _archival_run_and_receipt()
    failed_cleanup = receipt.model_copy(
        update={
            "cleanup_status": "partial",
            "clean_state_claim": None,
            "obligation_results": {
                key: value.model_copy(update={"status": "failed"}) for key, value in receipt.obligation_results.items()
            },
        }
    )

    with pytest.raises(ValueError, match="required cleanup obligation"):
        validate_admitted_trial_run(plan, run, [failed_cleanup])
    assert run.run_status == "completed"
    assert run.outcome_status == "succeeded"


def test_attempt_identity_cannot_collapse_into_run_identity_or_duplicate_on_retry() -> None:
    _, _, run, _ = _archival_run_and_receipt()
    payload = run.trial_provenance.model_dump(mode="json")
    payload["execution_attempts"][0]["execution_attempt_id"] = run.run_id
    payload["terminal_attempt_id"] = run.run_id
    with pytest.raises(ValidationError, match="distinct from admitted run identity"):
        TrialRunProvenanceModel.model_validate(payload)

    payload = run.trial_provenance.model_dump(mode="json")
    payload["execution_attempts"].append(dict(payload["execution_attempts"][0]))
    with pytest.raises(ValidationError, match="execution_attempt_id values must be unique"):
        TrialRunProvenanceModel.model_validate(payload)


def test_study_reconciliation_requires_admitted_run_membership() -> None:
    plan, _, run, _ = _archival_run_and_receipt()
    task = ExperimentTaskModel.model_validate_json(_TASK_FIXTURE.read_text(encoding="utf-8")).model_copy(
        update={
            "scenario_ref": ExperimentScenarioReferenceModel(
                ref_kind="scenario",
                ref_id=run.scenario_snapshot_ref.ref_id,
            )
        }
    )
    payload = json.loads(_STUDY_FIXTURE.read_text(encoding="utf-8"))
    study = ExperimentStudyModel.model_validate(payload)

    with pytest.raises(ValueError, match="study run membership"):
        validate_admitted_trial_study(plan, study, [task], [run])

    payload["membership"]["run-001"]["target_ref"]["ref_id"] = run.run_id
    admitted_study = ExperimentStudyModel.model_validate(payload)
    with pytest.raises(ValueError, match="content-backed evidence inputs"):
        validate_admitted_trial_study(plan, admitted_study, [task], [run])
