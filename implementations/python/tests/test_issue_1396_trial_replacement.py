"""Author-directed fresh trial allocation, distinct from attempt/recovery retries."""

from __future__ import annotations

import io
import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace

import pytest
from paths import REPO_ROOT
from pydantic import ValidationError
from raes import canonical_instantiated_sdl_digest
from raes_contracts.contracts import (
    ExperimentRunModel,
    ExperimentSpecModel,
    TrialCleanupReceiptModel,
)
from raes_processor.trial_compiler import compile_admitted_trial_plan
from raes_processor.trial_realization import instantiate_admitted_trial_entry, realize_admitted_trial_entry
from test_sce_002_trial_compiler import _request
from test_sce_002_trial_realization import _realization_inputs, _request_with_processor


def _replacement_request(*, limit=2, triggers=None, sample=True):
    request = _request_with_processor().with_experiment(_request(sample=sample).experiment)
    payload = request.experiment.model_dump(mode="json")
    payload["run_plan"]["replacement_policy"] = {
        "max_replacements": limit,
        "replace_on": ["failed", "invalidated"] if triggers is None else triggers,
    }
    return request.with_experiment(ExperimentSpecModel.model_validate(payload))


def test_authored_replacement_is_explicit_and_bound_to_the_sealed_plan():
    original = _request()
    assert "replacement_policy" not in original.experiment.model_dump(mode="json")["run_plan"]
    request = _replacement_request(sample=False)
    plan = compile_admitted_trial_plan(request).plan
    assert plan is not None
    assert plan.replacement_policy == request.experiment.run_plan.replacement_policy
    assert plan.replacement_policy.max_replacements == 2
    assert plan.plan_id != compile_admitted_trial_plan(original).plan.plan_id


@pytest.mark.parametrize("limit", [True, "2", 1.5, -1, 1001])
def test_replacement_limit_is_a_strict_bounded_integer(limit):
    with pytest.raises(ValidationError):
        _replacement_request(limit=limit)


@pytest.mark.parametrize("triggers", [[], ["failed", "failed"], ["delivery"], ["succeeded"]])
def test_replacement_triggers_are_closed_nonempty_and_unique(triggers):
    with pytest.raises(ValidationError):
        _replacement_request(triggers=triggers)


def _archive(request, plan, *, status="failed", cleanup_status="succeeded"):
    entry = next(iter(plan.entries.values()))
    snapshot = instantiate_admitted_trial_entry(plan=plan, plan_entry_id=entry.plan_entry_id, family=request.family)
    snapshot_digest = canonical_instantiated_sdl_digest(snapshot).value
    realized = realize_admitted_trial_entry(
        inputs=_realization_inputs(request, plan, request.task),
        plan_entry_id=entry.plan_entry_id,
    )
    cleanup = plan.cleanup_plans[entry.execution_controls.cleanup_plan_ref]
    succeeded = status in {"completed", "invalidated"}
    receipt = TrialCleanupReceiptModel(
        receipt_id=f"cleanup:{entry.run_id}",
        cleanup_plan_ref=cleanup.plan_id,
        plan_entry_id=entry.plan_entry_id,
        run_id=entry.run_id,
        execution_attempt_id=f"attempt:{entry.run_id}",
        trial_outcome="succeeded" if succeeded else "failed",
        cleanup_status=cleanup_status,
        obligation_results={
            key: {
                "obligation_id": key,
                "status": "succeeded" if cleanup_status == "succeeded" else "failed",
                "evidence_refs": ["evidence:cleanup"],
            }
            for key in cleanup.cleanup_obligations
        },
        clean_state_claim=(
            {
                "disposition": "verified-clean",
                "boundary_refs": list(cleanup.resource_boundaries),
                "evidence_refs": ["evidence:clean"],
            }
            if cleanup_status == "succeeded"
            else None
        ),
    )
    payload = json.loads(
        (REPO_ROOT / "contracts/fixtures/experiment-core/experiment-run-v1/valid/reference.json").read_text()
    )
    payload.update(
        run_id=entry.run_id,
        run_status=status,
        outcome_status="succeeded" if succeeded else "failed",
        scenario_snapshot_ref={
            "ref_kind": "scenario-snapshot",
            "ref_id": request.family.name,
            "ref_version": "raes-sdl-instantiated-snapshot/v2",
            "ref_digest": snapshot_digest,
        },
        trial_provenance={
            "plan_id": plan.plan_id,
            "plan_digest": plan.plan_digest,
            "plan_entry_id": entry.plan_entry_id,
            "entry_digest": entry.entry_digest,
            "admitted_run_id": entry.run_id,
            "coordinate": entry.coordinate.model_dump(),
            "instantiated_scenario_digest": snapshot_digest,
            "processor_plan_refs": [ref.model_dump() for ref in realized.processor_plan_refs],
            "execution_attempts": [
                {"execution_attempt_id": receipt.execution_attempt_id, "cleanup_receipt_ref": receipt.receipt_id}
            ],
            "terminal_attempt_id": receipt.execution_attempt_id,
        },
        stochastic_controls=[control.model_dump() for control in plan.stochastic_controls.values()],
        stochastic_draws=[draw.model_dump() for draw in entry.stochastic_draws],
    )
    if plan.replacement_origin is not None:
        payload["run_version"] = "1"
    # The archival family requires a declared stochastic control even for deterministic selections.
    if not payload["stochastic_controls"]:
        payload["stochastic_controls"] = [{"control_id": "deterministic", "role": "other"}]
    payload["participant_implementation_provenance"]["run_id"] = entry.run_id
    if status == "invalidated":
        payload["invalidation"] = {"invalidated_at": payload["ended_at"], "reason": "invalid observation"}
    return ExperimentRunModel.model_validate(payload), receipt


def _allocate(request, root, run, receipt, *, history=()):
    from raes_processor.trial_compiler.replacement import compile_replacement_trial

    return compile_replacement_trial(
        request,
        original_plan=root,
        root_entry_id=next(iter(root.entries)),
        previous_allocations=history,
        failed_run=run,
        cleanup_receipts=[receipt],
    )


def test_replacement_has_fresh_identity_initialization_and_preserved_failure():
    request = _replacement_request()
    root = compile_admitted_trial_plan(request).plan
    run, receipt = _archive(request, root)
    before = root.model_dump_json(), run.model_dump_json()
    result = _allocate(request, root, run, receipt)
    assert not result.diagnostics
    child = result.plan
    assert len(child.entries) == 1
    entry = next(iter(child.entries.values()))
    prior = next(iter(root.entries.values()))
    assert {entry.run_id, entry.plan_entry_id, child.plan_id}.isdisjoint(
        {prior.run_id, prior.plan_entry_id, root.plan_id, receipt.execution_attempt_id}
    )
    assert entry.coordinate != prior.coordinate
    assert child.replacement_origin.ordinal == 1
    assert child.replacement_origin.parent_run_id == run.run_id
    assert child.profiles.compiler_profile == "trial-compiler-replacement-v1"
    assert result.superseded_run.run_status == "superseded"
    assert result.superseded_run.run_version != run.run_version
    assert result.superseded_run.invalidation.superseded_by.ref_id == entry.run_id
    for field in (
        "outcome_status",
        "evidence_artifacts",
        "result_summaries",
        "started_at",
        "ended_at",
        "trial_provenance",
    ):
        assert getattr(result.superseded_run, field) == getattr(run, field)
    assert before == (root.model_dump_json(), run.model_dump_json())
    snapshot = instantiate_admitted_trial_entry(plan=child, plan_entry_id=entry.plan_entry_id, family=request.family)
    assert snapshot.instantiation_provenance.trial.run_id == entry.run_id
    assert all(draw.address.trial_coordinate == entry.coordinate for draw in entry.stochastic_draws)
    assert entry.stochastic_draws[0].address != prior.stochastic_draws[0].address


@pytest.mark.parametrize("status", ["failed", "invalidated"])
def test_authored_trigger_is_required(status):
    request = _replacement_request(triggers=["invalidated"] if status == "failed" else ["failed"])
    root = compile_admitted_trial_plan(request).plan
    run, receipt = _archive(request, root, status=status)
    result = _allocate(request, root, run, receipt)
    assert result.plan is None
    assert result.diagnostics[0].code == "trial-compiler.replacement-not-authorized"


def test_omission_cannot_replace_even_a_valid_failed_trial():
    request = _request_with_processor()
    root = compile_admitted_trial_plan(request).plan
    run, receipt = _archive(request, root)
    assert _allocate(request, root, run, receipt).plan is None


@pytest.mark.parametrize("cleanup_status", ["failed", "partial", "unverified"])
def test_cleanup_failure_blocks_replacement_without_erasing_primary_result(cleanup_status):
    request = _replacement_request()
    root = compile_admitted_trial_plan(request).plan
    run, receipt = _archive(request, root, cleanup_status=cleanup_status)
    result = _allocate(request, root, run, receipt)
    assert result.plan is None
    assert result.superseded_run is None
    assert result.diagnostics[0].code == "trial-compiler.replacement-clean-state-unverified"
    assert run.run_status == "failed"


def test_failed_descendants_share_the_original_budget_and_exhaustion_is_explicit():
    request = _replacement_request(limit=2)
    root = compile_admitted_trial_plan(request).plan
    run, receipt = _archive(request, root)
    first = _allocate(request, root, run, receipt)
    child_run, child_receipt = _archive(request, first.plan)
    second = _allocate(request, root, child_run, child_receipt, history=(first,))
    assert second.plan.replacement_origin.ordinal == 2
    last_run, last_receipt = _archive(request, second.plan)
    exhausted = _allocate(request, root, last_run, last_receipt, history=(first, second))
    assert exhausted.plan is None
    assert exhausted.diagnostics[0].code == "trial-compiler.replacement-limit-exhausted"
    assert exhausted.superseded_run is None


def test_duplicate_concurrent_and_restarted_decisions_do_not_multiply_trials():
    request = _replacement_request()
    root = compile_admitted_trial_plan(request).plan
    run, receipt = _archive(request, root)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: _allocate(request, root, run, receipt), range(2)))
    assert results[0].plan.model_dump_json() == results[1].plan.model_dump_json()
    assert _allocate(request, root, run, receipt, history=(results[0],)).plan == results[0].plan


def test_analysis_keeps_failed_evidence_and_counts_only_one_successor_per_slot():
    from raes_contracts.contracts.trial_replacement_analysis import reconcile_replacement_trials

    request = _replacement_request(limit=1)
    root = compile_admitted_trial_plan(request).plan
    run, receipt = _archive(request, root)
    allocation = _allocate(request, root, run, receipt)
    replacement, replacement_receipt = _archive(request, allocation.plan, status="completed")
    result = reconcile_replacement_trials(
        root,
        [allocation.plan],
        [run, allocation.superseded_run, replacement],
        [receipt, replacement_receipt],
    )
    assert tuple(item.run_id for item in result.analysis_runs) == (replacement.run_id,)
    assert run.run_id not in {item.run_id for item in result.analysis_runs}
    assert result.shortfall_entry_ids == tuple(set(root.entries) - {next(iter(root.entries))})
    # Scientific negative outcomes are eligible when trial execution completed.
    negative = replacement.model_copy(update={"outcome_status": "failed"})
    assert negative.run_status == "completed"


def test_analysis_rejects_dangling_supersession_and_duplicate_child_plans():
    from raes_contracts.contracts.trial_replacement_analysis import reconcile_replacement_trials

    request = _replacement_request()
    root = compile_admitted_trial_plan(request).plan
    run, receipt = _archive(request, root)
    allocation = _allocate(request, root, run, receipt)
    with pytest.raises(ValueError):
        reconcile_replacement_trials(root, [], [allocation.superseded_run], [receipt])
    with pytest.raises(ValueError):
        reconcile_replacement_trials(
            root, [allocation.plan, allocation.plan], [run, allocation.superseded_run], [receipt]
        )


def test_study_analysis_joins_replacement_plans_without_counting_retained_parents():
    from raes_contracts.canonical import canonical_json_digest
    from raes_contracts.contracts import ExperimentStudyModel, ExperimentTaskModel, validate_admitted_trial_study

    request = _replacement_request()
    task_payload = request.task.model_dump(mode="json")
    task_payload["scenario_ref"] = {"ref_kind": "scenario", "ref_id": request.family.name}
    task = ExperimentTaskModel.model_validate(task_payload)
    request = replace(
        request,
        task=task,
        input_refs=request.input_refs.model_copy(
            update={
                "task_digest": canonical_json_digest(task.model_dump(mode="json")),
            }
        ),
    )
    root = compile_admitted_trial_plan(request).plan
    run, receipt = _archive(request, root)
    allocation = _allocate(request, root, run, receipt)
    child, child_receipt = _archive(request, allocation.plan, status="completed")
    from raes_contracts.contracts import ExperimentEvidenceRecordModel, ExperimentRunEvidenceInputs
    from test_issue_1112_capture_admission import _evidence_bundle

    _, evidence_run, capture_spec, record, evidence_bytes = _evidence_bundle()
    child_payload = child.model_dump(mode="json")
    for field in ("evidence_artifacts", "result_summaries", "traceability"):
        child_payload[field] = evidence_run.model_dump(mode="json")[field]
    child = ExperimentRunModel.model_validate(child_payload)
    record_payload = record.model_dump(mode="json")
    record_payload["run_ref"] = {"ref_kind": "run", "ref_id": child.run_id, "ref_version": child.run_version}
    record = ExperimentEvidenceRecordModel.model_validate(record_payload)

    def evidence():
        return {
            child.run_id: ExperimentRunEvidenceInputs(
                capture_specs={capture_spec.capture_spec_id: capture_spec},
                evidence_records={record.evidence_record_id: record},
                artifact_readers={"auth-log-evidence": io.BytesIO(evidence_bytes)},
            )
        }

    payload = json.loads(
        (REPO_ROOT / "contracts/fixtures/experiment-core/experiment-study-v1/valid/reference.json").read_text()
    )
    payload["membership"] = {
        "task": {"role": "primary-task", "target_ref": child.task_ref.model_dump(mode="json")},
        "current": {
            "role": "evaluation-run",
            "grouping": "baseline",
            "target_ref": {"ref_kind": "run", "ref_id": child.run_id, "ref_version": child.run_version},
        },
    }
    study = ExperimentStudyModel.model_validate(payload)
    validate_admitted_trial_study(
        root,
        study,
        [task],
        [run, allocation.superseded_run, child],
        replacement_plans=[allocation.plan],
        cleanup_receipts=[receipt, child_receipt],
        evidence_by_run=evidence(),
    )
    payload["membership"]["old"] = {
        "role": "evaluation-run",
        "target_ref": {"ref_kind": "run", "ref_id": run.run_id, "ref_version": run.run_version},
    }
    with pytest.raises(ValueError):
        validate_admitted_trial_study(
            root,
            ExperimentStudyModel.model_validate(payload),
            [task],
            [run, allocation.superseded_run, child],
            replacement_plans=[allocation.plan],
            cleanup_receipts=[receipt, child_receipt],
            evidence_by_run=evidence(),
        )


def test_invalidated_parent_preserves_its_original_reason():
    request = _replacement_request(triggers=["invalidated"])
    root = compile_admitted_trial_plan(request).plan
    run, receipt = _archive(request, root, status="invalidated")
    allocation = _allocate(request, root, run, receipt)
    assert allocation.plan is not None
    assert allocation.superseded_run.invalidation.reason == run.invalidation.reason
    assert allocation.superseded_run.invalidation.invalidated_at == run.invalidation.invalidated_at


def test_policy_edits_and_incomplete_or_forked_history_do_not_reset_the_budget():
    request = _replacement_request(limit=2)
    root = compile_admitted_trial_plan(request).plan
    run, receipt = _archive(request, root)
    first = _allocate(request, root, run, receipt)
    child, child_receipt = _archive(request, first.plan)
    assert _allocate(_replacement_request(limit=3), root, run, receipt).plan is None
    assert _allocate(request, root, child, child_receipt).plan is None
    assert _allocate(request, root, child, child_receipt, history=(first, first)).plan is None
    tampered = replace(first, plan=first.plan.model_copy(update={"plan_digest": "sha256:" + "0" * 64}))
    assert _allocate(request, root, child, child_receipt, history=(tampered,)).plan is None
    edited_run = run.model_copy(update={"run_version": "changed"})
    assert _allocate(request, root, edited_run, receipt, history=(first,)).plan is None


def test_replacement_work_and_history_bytes_are_bounded_before_expansion():
    request = _replacement_request()
    root = compile_admitted_trial_plan(request).plan
    run, receipt = _archive(request, root)
    first = _allocate(request, root, run, receipt)
    child, child_receipt = _archive(request, first.plan)
    bounded = replace(request, limits=request.limits.model_copy(update={"max_coordinates": 2}))
    assert (
        _allocate(bounded, root, run, receipt).diagnostics[0].code == "trial-compiler.replacement-work-limit-exceeded"
    )
    bounded = replace(request, limits=request.limits.model_copy(update={"max_plan_bytes": 1}))
    assert _allocate(bounded, root, child, child_receipt, history=(first,)).plan is None


@pytest.mark.parametrize(
    "claim",
    [
        None,
        {"disposition": "fresh-range-required", "boundary_refs": ["range"], "evidence_refs": ["isolated-name-only"]},
    ],
)
def test_missing_or_nonreusable_clean_state_never_admits_a_replacement(claim):
    request = _replacement_request()
    root = compile_admitted_trial_plan(request).plan
    run, receipt = _archive(request, root)
    receipt = TrialCleanupReceiptModel.model_validate({**receipt.model_dump(), "clean_state_claim": claim})
    assert _allocate(request, root, run, receipt).plan is None


def test_scheduler_failure_and_redelivery_never_create_a_replacement():
    from raes_processor.trial_scheduler import dispatch_batch_schedule, plan_batch_schedule

    request = _replacement_request()
    root = compile_admitted_trial_plan(request).plan
    before = root.model_dump_json()
    schedule = plan_batch_schedule(root)
    for _ in range(2):
        assert dispatch_batch_schedule(schedule, realize=lambda _: "failed") == ["failed", "failed"]
    assert root.model_dump_json() == before
    assert root.replacement_origin is None


def test_replacement_compiler_has_fixed_identity_vectors():
    request = _replacement_request()
    root = compile_admitted_trial_plan(request).plan
    run, receipt = _archive(request, root)
    result = _allocate(request, root, run, receipt)
    vector = json.loads(
        (REPO_ROOT / "contracts/fixtures/plans/trial-compiler-replacement-v1/identity-vectors.json").read_text()
    )
    entry = next(iter(result.plan.entries.values()))
    assert vector["root_plan_id"] == root.plan_id
    assert vector["root_plan_digest"] == root.plan_digest
    for field in ("plan_id", "plan_digest"):
        assert vector[field] == getattr(result.plan, field)
    for field in ("plan_entry_id", "run_id", "entry_digest"):
        assert vector[field] == getattr(entry, field)
    assert vector["coordinate"] == entry.coordinate.model_dump(mode="json")


def test_exhausted_failed_leaf_is_a_shortfall_when_failed_trials_were_selected():
    from raes_contracts.contracts.trial_replacement_analysis import reconcile_replacement_trials

    request = _replacement_request(limit=1)
    root = compile_admitted_trial_plan(request).plan
    run, receipt = _archive(request, root)
    first = _allocate(request, root, run, receipt)
    failed_child, child_receipt = _archive(request, first.plan)
    result = reconcile_replacement_trials(
        root, [first.plan], [run, first.superseded_run, failed_child], [receipt, child_receipt]
    )
    assert result.analysis_runs == ()
    assert next(iter(root.entries)) in result.shortfall_entry_ids
    assert result.exhausted_entry_ids == (next(iter(root.entries)),)


def test_unselected_failed_scientific_result_remains_eligible():
    from raes_contracts.contracts.trial_replacement_analysis import reconcile_replacement_trials

    request = _replacement_request(triggers=["invalidated"])
    root = compile_admitted_trial_plan(request).plan
    run, receipt = _archive(request, root)
    result = reconcile_replacement_trials(root, [], [run], [receipt])
    assert tuple(item.run_id for item in result.analysis_runs) == (run.run_id,)


@pytest.mark.parametrize("bound_record", ["evidence_requirement_relations", "validation_basis_disclosures"])
def test_supersession_preserves_version_bound_assertions_on_the_historical_parent(bound_record):
    request = _replacement_request()
    root = compile_admitted_trial_plan(request).plan
    run, receipt = _archive(request, root)
    payload = run.model_dump(mode="json")
    if bound_record == "validation_basis_disclosures":
        from test_validation_disclosure import _evidence_backed_disclosure_payload

        payload[bound_record] = [
            _evidence_backed_disclosure_payload(
                subject_ref={
                    "ref_kind": "run",
                    "ref_id": run.run_id,
                    "ref_version": run.run_version,
                }
            )
        ]
    else:
        payload[bound_record] = [
            {
                "relation_id": "run-evidence",
                "relation_version": "1",
                "relation_kind": "refine",
                "scope": "run",
                "authority_ref": {"ref_kind": "run", "ref_id": run.run_id, "ref_version": run.run_version},
                "base_scenario_ref": run.scenario_snapshot_ref.model_dump(mode="json"),
                "base_requirement_address": "evidence_requirements.event-log",
                "capture_spec_ref": request.experiment.capture_spec_refs[0].model_dump(mode="json"),
                "capture_requirement_ref": "auth-log-evidence",
                "refinement_dimensions": ["loss-disclosure"],
                "rationale": "Retain the original version-bound evidence assertion.",
            }
        ]
    run = ExperimentRunModel.model_validate(payload)
    result = _allocate(request, root, run, receipt)
    assert result.plan is not None, result.diagnostics
    assert getattr(result.parent_run, bound_record) == getattr(run, bound_record)
    assert getattr(result.superseded_run, bound_record) == []
    assert any(
        ref.ref_id == run.run_id and ref.ref_version == run.run_version
        for ref in result.superseded_run.derived_from_refs
    )
    from raes_contracts.contracts.trial_replacement_analysis import reconcile_replacement_trials

    accounting = reconcile_replacement_trials(root, [result.plan], [run, result.superseded_run], [receipt])
    assert accounting.analysis_runs == ()


@pytest.mark.parametrize("boundary", ["allocation", "reconciliation"])
def test_intermediate_replacement_must_resolve_the_reserved_first_archive_version(boundary):
    from raes_contracts.canonical import canonical_json_digest
    from raes_contracts.contracts.trial_replacement_analysis import reconcile_replacement_trials
    from raes_contracts.contracts.trial_replacement_archive import build_superseded_trial_run
    from raes_processor.trial_compiler.compiler import _compile
    from raes_processor.trial_compiler.replacement_inputs import ReplacementCompilationContext

    request = _replacement_request(limit=2)
    root = compile_admitted_trial_plan(request).plan
    run, receipt = _archive(request, root)
    first = _allocate(request, root, run, receipt)
    child, child_receipt = _archive(request, first.plan)
    second = _allocate(request, root, child, child_receipt, history=(first,))
    unresolved = child.model_copy(update={"run_version": "2"})
    refused = _allocate(request, root, unresolved, child_receipt, history=(first,))
    if boundary == "allocation":
        assert refused.plan is None
        return
    # Build an invalid sealed carrier independently of the guarded public API.
    origin = second.plan.replacement_origin.model_copy(
        update={
            "parent_run_version": "2",
            "parent_run_digest": canonical_json_digest(unresolved.model_dump(mode="json")),
        }
    )
    forged = _compile(request, None, ReplacementCompilationContext(origin, 0))
    final_run, final_receipt = _archive(request, forged, status="completed")
    with pytest.raises(ValueError):
        reconcile_replacement_trials(
            root,
            [first.plan, forged],
            [run, first.superseded_run, unresolved, build_superseded_trial_run(unresolved, forged), final_run],
            [receipt, child_receipt, final_receipt],
        )
