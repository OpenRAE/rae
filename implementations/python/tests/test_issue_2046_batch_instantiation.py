"""Issue 2046: validate the complete admitted plan once for batch instantiation.

The batch boundary reconstructs the complete plan once, then instantiates or
realizes each entry without repeating whole-plan reconstruction. These tests
pin the bounded reconstruction count, equivalence with the single-entry path,
closed rejection of changed or mismatched plans and entries, and snapshot
ownership against caller mutation. They also pin that runtime admission and
execution, through shared read-only plan views, repeat no complete-plan work.
"""

from __future__ import annotations

from dataclasses import replace

import pytest
import raes_processor.trial_realization as trial_realization_module
from raes import canonical_instantiated_sdl_digest
from raes_contracts.contracts.admitted_trial_plan import canonical_entry_order
from raes_contracts.errors import InvalidInputError, NotFoundError
from raes_processor.trial_compiler import compile_admitted_trial_plan
from raes_processor.trial_realization import (
    admitted_trial_batch_instantiator,
    admitted_trial_batch_realizer,
    instantiate_admitted_trial_entry,
    realize_admitted_trial_entry,
)
from test_exp_719_factorial_allocation import _factorial_request
from test_sce_002_trial_compiler import _product_family
from test_sce_002_trial_realization import _realization_inputs, _request_with_processor


def _count_reconstructions(monkeypatch) -> dict[str, int]:
    """Count calls to the trial-realization module's plan reconstruction."""

    calls = {"n": 0}
    real = trial_realization_module.revalidate_admitted_trial_plan

    def counting(plan):
        calls["n"] += 1
        return real(plan)

    monkeypatch.setattr(trial_realization_module, "revalidate_admitted_trial_plan", counting)
    return calls


def _multi_entry_instantiation_plan():
    request = _factorial_request()
    plan = compile_admitted_trial_plan(request).plan
    assert plan is not None
    assert len(plan.entries) >= 2
    return request, plan


def _multi_entry_realization():
    request = _request_with_processor()
    plan = compile_admitted_trial_plan(request).plan
    assert plan is not None
    assert len(plan.entries) >= 2
    inputs = _realization_inputs(request, plan, request.task)
    return request, plan, inputs


def test_batch_instantiator_reconstructs_plan_once_for_all_entries(monkeypatch) -> None:
    request, plan = _multi_entry_instantiation_plan()
    calls = _count_reconstructions(monkeypatch)

    instantiate_one = admitted_trial_batch_instantiator(plan=plan, family=request.family)
    assert calls["n"] == 1

    results = [instantiate_one(entry_id) for entry_id in canonical_entry_order(plan)]

    assert len(results) == len(plan.entries)
    assert calls["n"] == 1
    assert len(plan.entries) > calls["n"]


def test_batch_instantiator_matches_single_entry_path() -> None:
    request, plan = _multi_entry_instantiation_plan()
    instantiate_one = admitted_trial_batch_instantiator(plan=plan, family=request.family)

    for entry_id in canonical_entry_order(plan):
        batch = instantiate_one(entry_id)
        single = instantiate_admitted_trial_entry(plan=plan, plan_entry_id=entry_id, family=request.family)
        assert canonical_instantiated_sdl_digest(batch).value == canonical_instantiated_sdl_digest(single).value
        assert batch.instantiation_provenance.trial.plan_entry_id == entry_id
        assert batch.instantiation_provenance.trial.entry_digest == plan.entries[entry_id].entry_digest


def test_batch_instantiator_rejects_tampered_plan_digest() -> None:
    request, plan = _multi_entry_instantiation_plan()
    tampered = plan.model_copy(deep=True)
    tampered.__dict__["plan_digest"] = "sha256:" + "0" * 64

    with pytest.raises(InvalidInputError, match="plan failed closed reconstruction"):
        admitted_trial_batch_instantiator(plan=tampered, family=request.family)


def test_batch_instantiator_rejects_nested_selection_mutation() -> None:
    request, plan, _ = _multi_entry_realization()
    tampered = plan.model_copy(deep=True)
    entry_id = next(iter(tampered.entries))
    tampered.entries[entry_id].selections[0].outcome.__dict__["value"] = "/opt/substituted"

    with pytest.raises(InvalidInputError, match="plan failed closed reconstruction"):
        admitted_trial_batch_instantiator(plan=tampered, family=request.family)


def test_batch_instantiator_rejects_unknown_entry() -> None:
    request, plan, _ = _multi_entry_realization()
    instantiate_one = admitted_trial_batch_instantiator(plan=plan, family=request.family)

    with pytest.raises(NotFoundError, match="plan_entry_id"):
        instantiate_one("missing-entry")


def test_batch_instantiator_rejects_wrong_family() -> None:
    _, plan, _ = _multi_entry_realization()

    with pytest.raises(InvalidInputError, match="family identity"):
        admitted_trial_batch_instantiator(plan=plan, family=_product_family())


def test_batch_instantiator_owns_snapshot_against_caller_mutation() -> None:
    request, plan, _ = _multi_entry_realization()
    entry_id = next(iter(canonical_entry_order(plan)))
    instantiate_one = admitted_trial_batch_instantiator(plan=plan, family=request.family)

    before = canonical_instantiated_sdl_digest(instantiate_one(entry_id)).value
    # Mutate the caller-held plan after capture; the executor owns its snapshot.
    plan.__dict__["plan_digest"] = "sha256:" + "0" * 64
    after = canonical_instantiated_sdl_digest(instantiate_one(entry_id)).value

    assert before == after


def test_batch_instantiator_owns_family_against_caller_mutation() -> None:
    request, plan, _ = _multi_entry_realization()
    entry_id = next(iter(canonical_entry_order(plan)))
    instantiate_one = admitted_trial_batch_instantiator(plan=plan, family=request.family)

    before = canonical_instantiated_sdl_digest(instantiate_one(entry_id)).value
    # Mutate the caller-held family after capture; the executor owns a snapshot.
    request.family.__dict__["name"] = "mutated-family-name"
    after = canonical_instantiated_sdl_digest(instantiate_one(entry_id)).value

    assert before == after


def test_batch_realizer_owns_inputs_against_caller_mutation() -> None:
    _, plan, inputs = _multi_entry_realization()
    entry_id = next(iter(canonical_entry_order(plan)))
    realize_one = admitted_trial_batch_realizer(inputs=inputs)

    before = realize_one(entry_id).snapshot_digest
    # Mutate caller-held realization inputs after capture; the executor owns a snapshot.
    inputs.family.__dict__["name"] = "mutated-family-name"
    inputs.task.__dict__["task_id"] = "mutated-task-id"
    after = realize_one(entry_id).snapshot_digest

    assert before == after


def test_batch_realizer_copies_participant_configurations() -> None:
    from issue_1629_trial_fixture import factorial_inputs

    _, inputs, _ = factorial_inputs()
    entry_id = next(
        entry_id for entry_id in inputs.plan.entries if inputs.plan.entries[entry_id].participant_configurations
    )
    realize_one = admitted_trial_batch_realizer(inputs=inputs)

    first = realize_one(entry_id)
    original_digest = first.participant_configurations[0].configuration_digest
    # Mutate the returned record; the executor must not share it with the snapshot.
    first.participant_configurations[0].__dict__["configuration_digest"] = "sha256:" + "0" * 64
    second = realize_one(entry_id)

    assert second.participant_configurations[0].configuration_digest == original_digest


def test_independent_batches_with_colliding_entry_ids_stay_isolated() -> None:
    request, plan, _ = _multi_entry_realization()
    entry_id = next(iter(canonical_entry_order(plan)))

    first = admitted_trial_batch_instantiator(plan=plan, family=request.family)
    second = admitted_trial_batch_instantiator(plan=plan, family=request.family)

    assert (
        canonical_instantiated_sdl_digest(first(entry_id)).value
        == canonical_instantiated_sdl_digest(second(entry_id)).value
    )


def test_batch_realizer_reconstructs_plan_once_for_all_entries(monkeypatch) -> None:
    _, plan, inputs = _multi_entry_realization()
    calls = _count_reconstructions(monkeypatch)

    realize_one = admitted_trial_batch_realizer(inputs=inputs)
    assert calls["n"] == 1

    results = [realize_one(entry_id) for entry_id in canonical_entry_order(plan)]

    assert len(results) == len(plan.entries)
    assert calls["n"] == 1
    assert len(plan.entries) > calls["n"]


def test_batch_realizer_matches_single_entry_path() -> None:
    _, plan, inputs = _multi_entry_realization()
    realize_one = admitted_trial_batch_realizer(inputs=inputs)

    for entry_id in canonical_entry_order(plan):
        batch = realize_one(entry_id)
        single = realize_admitted_trial_entry(inputs=inputs, plan_entry_id=entry_id)
        assert batch.snapshot_digest == single.snapshot_digest
        assert {reference.plan_kind: reference.artifact_ref.ref_digest for reference in batch.processor_plan_refs} == {
            reference.plan_kind: reference.artifact_ref.ref_digest for reference in single.processor_plan_refs
        }


def test_single_entry_realize_reconstructs_plan_once(monkeypatch) -> None:
    _, plan, inputs = _multi_entry_realization()
    entry_id = next(iter(plan.entries))
    calls = _count_reconstructions(monkeypatch)

    realize_admitted_trial_entry(inputs=inputs, plan_entry_id=entry_id)

    # The single-entry path reconstructed the whole plan twice before this fix.
    assert calls["n"] == 1


def _count_complete_plan_work(monkeypatch) -> dict[str, int]:
    """Count every complete-plan reconstruction and plan dump, through any import alias."""

    import sys

    import raes_contracts.contracts.admitted_trial_plan_ingress as ingress
    from raes_contracts.contracts.admitted_trial_plan import AdmittedTrialPlanModel

    calls = {"reconstruct": 0, "dump": 0}
    real_reconstruct = ingress.revalidate_admitted_trial_plan
    real_dump = AdmittedTrialPlanModel.model_dump

    def reconstruct(plan):
        calls["reconstruct"] += 1
        return real_reconstruct(plan)

    def dump(self, *args, **kwargs):
        calls["dump"] += 1
        return real_dump(self, *args, **kwargs)

    for module in list(sys.modules.values()):
        if getattr(module, "revalidate_admitted_trial_plan", None) is real_reconstruct:
            monkeypatch.setattr(module, "revalidate_admitted_trial_plan", reconstruct)
    monkeypatch.setattr(AdmittedTrialPlanModel, "model_dump", dump)
    return calls


def test_runtime_experiment_complete_plan_work_is_bounded(monkeypatch) -> None:
    # Admission checks the complete plan a fixed number of times. Trial requests,
    # custody checks, and operation commitments then repeat no complete-plan work.
    from issue_1629_trial_fixture import TrialServices, factorial_inputs
    from raes_runtime import RuntimeControlPlane

    _, inputs, target = factorial_inputs()
    entries = len(inputs.plan.entries)
    assert entries >= 8
    calls = _count_complete_plan_work(monkeypatch)

    services = TrialServices(target)
    with RuntimeControlPlane(target) as runtime:
        experiment = runtime.admit_experiment(inputs, services=services)
        admitted = dict(calls)
        for _ in range(200):
            progress = runtime.advance_experiment(experiment)
            if progress.state == "completed":
                break
        assert progress.state == "completed"

    assert admitted["reconstruct"] <= 4 < entries
    assert admitted["dump"] <= 2 * admitted["reconstruct"]
    assert calls == admitted


def test_trial_requests_share_one_read_only_plan_view(monkeypatch) -> None:
    from raes_contracts.trial_unit import AdmittedTrialPlanView, TrialUnitRequest

    _, plan, inputs = _multi_entry_realization()
    realize_one = admitted_trial_batch_realizer(inputs=inputs)
    view = AdmittedTrialPlanView(plan)
    calls = _count_complete_plan_work(monkeypatch)

    requests = []
    for entry_id in canonical_entry_order(plan):
        realized = realize_one(entry_id)
        requests.append(
            TrialUnitRequest(
                plan=view,
                plan_entry_id=entry_id,
                execution_attempt_id="attempt-" + entry_id,
                instantiated_sdl_digest=realized.snapshot_digest,
                provisioning_plan=realized.provisioning_plan,
                orchestration_plan=realized.orchestration_plan,
                evaluation_plan=realized.evaluation_plan,
            )
        )
    assert all(replace(request) == request for request in requests)
    assert calls == {"reconstruct": 0, "dump": 0}

    entry_id = requests[0].plan_entry_id
    with pytest.raises(TypeError):
        view.entries[entry_id] = view.entries[entry_id]  # type: ignore[index]
    with pytest.raises(AttributeError):
        view.plan_digest = "sha256:" + "0" * 64  # type: ignore[misc]
    view.entries[entry_id].participant_configurations.clear()
    requests[0].execution_controls.attempt_timeout_seconds = 1
    assert requests[0].participant_configurations == tuple(plan.entries[entry_id].participant_configurations)
    assert requests[0].execution_controls == plan.entries[entry_id].execution_controls
    assert view.snapshot().model_dump(mode="json") == plan.model_dump(mode="json")


def test_batch_realizer_isolates_planner_dependencies_between_results() -> None:
    from raes_contracts.artifact_requirements import ArtifactAvailabilityContext

    _, plan, inputs = _multi_entry_realization()
    entry_id = next(iter(canonical_entry_order(plan)))
    availability = ArtifactAvailabilityContext()
    realize_one = admitted_trial_batch_realizer(inputs=inputs, artifact_availability=availability)
    untouched = admitted_trial_batch_realizer(inputs=inputs, artifact_availability=ArtifactAvailabilityContext())(
        entry_id
    )

    first = realize_one(entry_id)
    # Change a returned envelope, a returned availability context, and the supplied context.
    first.execution_plan.manifest.realization_envelope.__dict__["id"] = "changed"
    first.execution_plan.artifact_availability.requirements.append("changed")  # type: ignore[arg-type]
    availability.requirements.append("changed")  # type: ignore[arg-type]
    second = realize_one(entry_id)

    assert second.execution_plan.manifest.realization_envelope == untouched.execution_plan.manifest.realization_envelope
    assert second.execution_plan.artifact_availability == ArtifactAvailabilityContext()
    assert second.snapshot_digest == untouched.snapshot_digest
    assert second.processor_plan_refs == untouched.processor_plan_refs
