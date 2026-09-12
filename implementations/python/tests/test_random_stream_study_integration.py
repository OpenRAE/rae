"""``validate_experiment_study_against_tasks_and_runs()`` EXP-718 extension.

When a study's ``run_allocation`` asserts comparability across evaluation
runs (a common-random-number / controlled-variation claim), every
stochastic_controls control_id shared by more than one of those runs must
declare a consistent ``executable_binding.profile_ref``/``namespace``
(EXP-718 preflight: "verify those runs' relevant
stochastic_controls[].executable_binding.profile_ref and namespace match").
A control that is descriptive-only (no ``executable_binding``) on every run
that declares it makes no such claim and is not checked. A control that
carries an ``executable_binding`` on only *some* of the runs that declare it
is an asymmetric claim and is rejected on the same footing as a mismatched
``profile_ref``/``namespace``.
"""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest
from raes_contracts.contracts import (
    ExperimentRunModel,
    ExperimentStudyModel,
    ExperimentTaskModel,
)
from raes_contracts.contracts import (
    validate_experiment_study_structure_against_tasks_and_runs as validate_experiment_study_against_tasks_and_runs,
)
from raes_contracts.contracts.random_stream import (
    PublicSeedModel,
    RandomStreamControlBindingModel,
    RandomStreamProfileReferenceModel,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
VALID_HEX_SEED_A = "aa" * 32
VALID_HEX_SEED_B = "bb" * 32


def _experiment_fixture(contract_id: str, fixture_name: str = "reference.json") -> dict:
    fixture_path = REPO_ROOT / "contracts" / "fixtures" / "experiment-core" / contract_id / "valid" / fixture_name
    return json.loads(fixture_path.read_text(encoding="utf-8"))


def _binding(*, namespace: str, seed: str) -> dict:
    return RandomStreamControlBindingModel(
        profile_ref=RandomStreamProfileReferenceModel(
            ref_kind="profile", ref_id="blake3-xof-v1", ref_version="random-stream-profile/v1"
        ),
        namespace=namespace,
        root_entropy=PublicSeedModel(kind="public-seed", encoding="hex-fixed-width", value=seed),
    ).model_dump(mode="json")


def _second_run_payload(*, run_id: str, namespace: str, seed: str) -> dict:
    payload = deepcopy(_experiment_fixture("experiment-run-v1"))
    payload["run_id"] = run_id
    if payload.get("participant_implementation_provenance") is not None:
        payload["participant_implementation_provenance"]["run_id"] = run_id
    payload["stochastic_controls"][0]["executable_binding"] = _binding(namespace=namespace, seed=seed)
    return payload


def _first_run_with_binding(*, namespace: str, seed: str) -> dict:
    payload = deepcopy(_experiment_fixture("experiment-run-v1"))
    payload["stochastic_controls"][0]["executable_binding"] = _binding(namespace=namespace, seed=seed)
    return payload


def _study_with_two_evaluation_runs(second_run_id: str) -> dict:
    payload = deepcopy(_experiment_fixture("experiment-study-v1"))
    payload["run_allocation"]["target_runs_per_condition"] = 2
    payload["membership"]["run-002"] = {
        "target_ref": {"ref_kind": "run", "ref_id": second_run_id},
        "role": "evaluation-run",
        "grouping": "baseline",
    }
    return payload


class TestConsistentExecutableBindingsAreAccepted:
    def test_same_profile_ref_and_namespace_across_runs_passes(self) -> None:
        task = ExperimentTaskModel.model_validate(_experiment_fixture("experiment-task-v1"))
        run1 = ExperimentRunModel.model_validate(
            _first_run_with_binding(namespace="study-namespace", seed=VALID_HEX_SEED_A)
        )
        run2 = ExperimentRunModel.model_validate(
            _second_run_payload(run_id="run-techvault-002", namespace="study-namespace", seed=VALID_HEX_SEED_A)
        )
        study = ExperimentStudyModel.model_validate(_study_with_two_evaluation_runs("run-techvault-002"))
        validate_experiment_study_against_tasks_and_runs(study, [task], [run1, run2])  # must not raise

    def test_descriptive_only_controls_are_not_checked(self) -> None:
        """Runs with no executable_binding at all make no comparability claim."""
        task = ExperimentTaskModel.model_validate(_experiment_fixture("experiment-task-v1"))
        run1 = ExperimentRunModel.model_validate(_experiment_fixture("experiment-run-v1"))
        run2_payload = deepcopy(_experiment_fixture("experiment-run-v1"))
        run2_payload["run_id"] = "run-techvault-002"
        run2_payload["participant_implementation_provenance"]["run_id"] = "run-techvault-002"
        run2 = ExperimentRunModel.model_validate(run2_payload)
        study = ExperimentStudyModel.model_validate(_study_with_two_evaluation_runs("run-techvault-002"))
        validate_experiment_study_against_tasks_and_runs(study, [task], [run1, run2])  # must not raise


class TestInconsistentExecutableBindingsAreRejected:
    def test_mismatched_namespace_is_rejected(self) -> None:
        task = ExperimentTaskModel.model_validate(_experiment_fixture("experiment-task-v1"))
        run1 = ExperimentRunModel.model_validate(
            _first_run_with_binding(namespace="study-namespace", seed=VALID_HEX_SEED_A)
        )
        run2 = ExperimentRunModel.model_validate(
            _second_run_payload(run_id="run-techvault-002", namespace="a-different-namespace", seed=VALID_HEX_SEED_A)
        )
        study = ExperimentStudyModel.model_validate(_study_with_two_evaluation_runs("run-techvault-002"))
        with pytest.raises(ValueError, match="stochastic"):
            validate_experiment_study_against_tasks_and_runs(study, [task], [run1, run2])

    def test_mismatched_profile_ref_version_is_rejected(self) -> None:
        task = ExperimentTaskModel.model_validate(_experiment_fixture("experiment-task-v1"))
        run1 = ExperimentRunModel.model_validate(
            _first_run_with_binding(namespace="study-namespace", seed=VALID_HEX_SEED_A)
        )
        run2_payload = _second_run_payload(
            run_id="run-techvault-002", namespace="study-namespace", seed=VALID_HEX_SEED_B
        )
        run2_payload["stochastic_controls"][0]["executable_binding"]["profile_ref"]["ref_version"] = (
            "random-stream-profile/v2"
        )
        run2 = ExperimentRunModel.model_validate(run2_payload)
        study = ExperimentStudyModel.model_validate(_study_with_two_evaluation_runs("run-techvault-002"))
        with pytest.raises(ValueError, match="stochastic"):
            validate_experiment_study_against_tasks_and_runs(study, [task], [run1, run2])

    def test_different_root_seed_alone_does_not_trip_the_check(self) -> None:
        """The claim is about profile_ref/namespace identity, not the seed value itself."""
        task = ExperimentTaskModel.model_validate(_experiment_fixture("experiment-task-v1"))
        run1 = ExperimentRunModel.model_validate(
            _first_run_with_binding(namespace="study-namespace", seed=VALID_HEX_SEED_A)
        )
        run2 = ExperimentRunModel.model_validate(
            _second_run_payload(run_id="run-techvault-002", namespace="study-namespace", seed=VALID_HEX_SEED_B)
        )
        study = ExperimentStudyModel.model_validate(_study_with_two_evaluation_runs("run-techvault-002"))
        validate_experiment_study_against_tasks_and_runs(study, [task], [run1, run2])  # must not raise

    def test_one_run_bound_and_shared_run_unbound_is_rejected(self) -> None:
        """An executable claim on one run and no claim at all on the other is asymmetric, not vacuous."""
        task = ExperimentTaskModel.model_validate(_experiment_fixture("experiment-task-v1"))
        run1 = ExperimentRunModel.model_validate(
            _first_run_with_binding(namespace="study-namespace", seed=VALID_HEX_SEED_A)
        )
        run2_payload = deepcopy(_experiment_fixture("experiment-run-v1"))
        run2_payload["run_id"] = "run-techvault-002"
        run2_payload["participant_implementation_provenance"]["run_id"] = "run-techvault-002"
        run2 = ExperimentRunModel.model_validate(run2_payload)
        study = ExperimentStudyModel.model_validate(_study_with_two_evaluation_runs("run-techvault-002"))
        with pytest.raises(ValueError, match="stochastic"):
            validate_experiment_study_against_tasks_and_runs(study, [task], [run1, run2])
