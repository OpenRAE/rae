"""Fresh replacement trials preserve failed originals and resume the same allocation."""

import pytest
from issue_1629_archive_fixture import TrialArchive
from issue_1629_trial_fixture import TrialServices, factorial_inputs
from raes_runtime import RuntimeControlPlane
from raes_runtime.runtime_experiment_replacement import ExperimentReplacementBinding
from raes_runtime.runtime_trial_decisions import TrialReplacementDecision, TrialTerminalDecision
from test_issue_1666_factorial_compilation import _with_design


def replacement_request(request):
    payload = request.experiment.model_dump(mode="json")
    payload["run_plan"]["replacement_policy"] = {"max_replacements": 1, "replace_on": ["failed"]}
    return _with_design(request, payload)


def test_replacement_preserves_failure_after_lost_archive_acknowledgement():
    request, inputs, target = factorial_inputs(replacement_request)
    archive, services = TrialArchive(), TrialServices(target)
    services.execution_fails = True
    with RuntimeControlPlane(target) as engine:
        experiment = engine.admit_experiment(
            inputs, services=services, replacement=ExperimentReplacementBinding(request, archive)
        )
        for _ in range(20):
            engine.advance_experiment(experiment)
            if any(isinstance(item, TrialTerminalDecision) for item in engine._store.load_runtime_decisions()):
                break
        first = services.observed[0][0]
        services.execution_fails = False
        archive.lose_ack = True
        with pytest.raises(OSError, match="acknowledgement lost"):
            engine.advance_experiment(experiment)
        original = archive.runs[(first, "1")].model_copy(deep=True)
        assert original.outcome_status == "failed"
        for _ in range(200):
            progress = engine.advance_experiment(experiment)
            assert progress.state in {"progress", "completed"}, progress
            if progress.state == "completed":
                break
        assert progress.state == "completed"
        (replacement,) = [
            item for item in engine._store.load_runtime_decisions() if isinstance(item, TrialReplacementDecision)
        ]
        child = next(iter(replacement.plan.entries.values()))
        assert child.run_id != first
        assert replacement.ordinal == 1
        assert replacement.parent_run == original
        assert archive.runs[(first, "1")] == original
        assert archive.runs[(first, replacement.superseded_run.run_version)].outcome_status == "failed"
        assert [run_id for run_id, _, _ in services.observed].count(child.run_id) == 1
        assert len(engine.experiment_results(experiment)) == len(inputs.plan.entries) + 1
        for _ in range(2):
            assert engine.advance_experiment(experiment).state == "completed"
        assert (
            len([item for item in engine._store.load_runtime_decisions() if isinstance(item, TrialReplacementDecision)])
            == 1
        )
