"""Coordinator enforcement of authored trial capacity before effects."""

import pytest
from issue_1629_trial_fixture import TrialServices
from issue_1870_trial_fixture import parallel_inputs
from pydantic import TypeAdapter
from raes.canonical import canonical_sdl_digest
from raes_contracts.errors import ConflictError
from raes_contracts.trial_parallelism import TrialParallelismModel
from raes_processor.trial_scheduler import AllocatorGrant
from raes_runtime import RuntimeControlPlane
from test_issue_1666_factorial_compilation import _with_design


def _with_parallelism(request, intent):
    family = request.family.model_copy(
        update={"trial_parallelism": TypeAdapter(TrialParallelismModel).validate_python(intent)}
    )
    request = request.with_family(family)
    design = request.experiment.model_dump(mode="json")
    for levels in design["factorial_design"]["level_effects"].values():
        for effect in levels.values():
            for selection in effect.get("selections", []):
                selection["scenario_family_digest"] = canonical_sdl_digest(family).value
    return _with_design(request, design)


@pytest.mark.parametrize(
    "intent",
    [
        {"posture": "exact", "count": 2},
        {"posture": "constrained", "minimum": 2},
    ],
)
def test_coordinator_refuses_serial_grants_and_serial_execution(intent):
    _, inputs, target = parallel_inputs(transform=lambda r: _with_parallelism(r, intent))
    services = TrialServices(target)
    with RuntimeControlPlane(target) as runtime:
        experiment = runtime.admit_experiment(inputs, services=services)
        entry_id = next(iter(inputs.plan.entries))
        with pytest.raises(ConflictError, match="parallelism"):
            runtime.assign_trial(experiment, entry_id, owner_id="worker")
        with pytest.raises(ConflictError, match="parallelism"):
            runtime.advance_experiment(experiment)
        assert runtime.experiment_records(experiment).accounting.started_runs == 0
        grant = AllocatorGrant(effective_parallelism=2)
        with pytest.raises(ConflictError, match="lease|allocator"):
            runtime.assign_trial(experiment, entry_id, owner_id="worker", grant=grant)
        assignment = runtime.assign_trial(
            experiment,
            entry_id,
            owner_id="worker",
            grant=AllocatorGrant(effective_parallelism=2, lease_evidence_refs=("lease:hosts",)),
        )
        assert assignment.effective_parallelism == 2
        assert not services.events


def test_coordinator_refuses_capacity_above_author_maximum():
    _, inputs, target = parallel_inputs(
        transform=lambda r: _with_parallelism(r, {"posture": "constrained", "maximum": 1})
    )
    with RuntimeControlPlane(target) as runtime:
        experiment = runtime.admit_experiment(inputs, services=TrialServices(target))
        entry_id = next(iter(inputs.plan.entries))
        grant = AllocatorGrant(effective_parallelism=2, lease_evidence_refs=("lease",))
        with pytest.raises(ConflictError, match="parallelism"):
            runtime.assign_trial(
                experiment,
                entry_id,
                owner_id="worker",
                grant=grant,
            )
        assert runtime.experiment_records(experiment).accounting.started_runs == 0
