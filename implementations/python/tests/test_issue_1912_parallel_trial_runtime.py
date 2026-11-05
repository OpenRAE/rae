"""Coordinator enforcement of authored trial capacity before effects."""

import pytest
from issue_1629_trial_fixture import TrialServices
from issue_1870_trial_fixture import parallel_inputs
from raes_contracts.errors import ConflictError
from raes_processor.trial_scheduler import AllocatorGrant
from raes_runtime import RuntimeControlPlane


@pytest.mark.parametrize(
    "intent",
    [
        {"posture": "exact", "count": 2},
        {"posture": "constrained", "minimum": 2},
    ],
)
def test_coordinator_refuses_serial_grants_and_serial_execution(intent):
    _, inputs, target = parallel_inputs(intent=intent)
    services = TrialServices(target)
    with RuntimeControlPlane(target) as runtime:
        experiment = runtime.admit_experiment(inputs, services=services)
        entry_id = next(iter(inputs.plan.entries))
        with pytest.raises(ConflictError, match="parallelism"):
            runtime.assign_trial(experiment, entry_id, owner_id="worker")
        with pytest.raises(ConflictError, match="parallelism"):
            runtime.advance_experiment(experiment)
        assert runtime.experiment_records(experiment).accounting.started_runs == 0
        assignment = runtime.assign_trial(
            experiment, entry_id, owner_id="worker", grant=AllocatorGrant(effective_parallelism=2)
        )
        assert assignment.effective_parallelism == 2
        assert not services.events


def test_coordinator_refuses_capacity_above_author_maximum():
    _, inputs, target = parallel_inputs(intent={"posture": "constrained", "maximum": 1})
    with RuntimeControlPlane(target) as runtime:
        experiment = runtime.admit_experiment(inputs, services=TrialServices(target))
        entry_id = next(iter(inputs.plan.entries))
        grant = AllocatorGrant(effective_parallelism=2)
        with pytest.raises(ConflictError, match="parallelism"):
            runtime.assign_trial(
                experiment,
                entry_id,
                owner_id="worker",
                grant=grant,
            )
        assert runtime.experiment_records(experiment).accounting.started_runs == 0


@pytest.mark.parametrize("intent", [{"posture": "open"}, {"posture": "constrained", "maximum": 4}])
def test_coordinator_accepts_authored_capacity_above_one(intent):
    _, inputs, target = parallel_inputs(intent=intent)
    with RuntimeControlPlane(target) as runtime:
        experiment = runtime.admit_experiment(inputs, services=TrialServices(target))
        first, second, third = list(inputs.plan.entries)[:3]
        grant = AllocatorGrant(effective_parallelism=3)
        for owner, entry_id in (("worker-a", first), ("worker-b", second), ("worker-c", third)):
            assert runtime.assign_trial(experiment, entry_id, owner_id=owner, grant=grant).effective_parallelism == 3
