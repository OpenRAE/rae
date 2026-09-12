"""``ExperimentStochasticControlModel``/``ExperimentRunModel`` EXP-718 extensions.

Covers the plan's two run-level extensions:

* ``ExperimentStochasticControlModel`` gains one new optional
  ``executable_binding`` field (``role``/``value``/``description`` untouched);
* ``ExperimentRunModel`` gains ``stochastic_draws`` and
  ``validate_experiment_run_against_task()`` is extended so every
  ``stochastic_draws[].control_id`` must resolve to a stochastic_controls[]
  entry that itself carries an ``executable_binding`` (a draw against a
  descriptive-only control makes no executable claim to bind to), whose
  ``address.namespace`` matches that binding's namespace, and whose
  ``transform_id``/``transform_version`` is admitted by the binding's
  profile.
"""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest
from raes_contracts.contracts import (
    ExperimentRunModel,
    ExperimentStochasticControlModel,
    ExperimentTaskModel,
)
from raes_contracts.contracts import (
    validate_experiment_run_structure_against_task as validate_experiment_run_against_task,
)
from raes_contracts.contracts.random_stream import (
    PublicRandomOutcomeModel,
    PublicSeedModel,
    RandomStreamControlBindingModel,
    RandomStreamDrawRecordModel,
    RandomStreamProfileReferenceModel,
    StreamAddressModel,
    TrialCoordinateModel,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
VALID_HEX_SEED = "ab" * 32


def _experiment_fixture(contract_id: str, fixture_name: str = "reference.json") -> dict:
    fixture_path = REPO_ROOT / "contracts" / "fixtures" / "experiment-core" / contract_id / "valid" / fixture_name
    return json.loads(fixture_path.read_text(encoding="utf-8"))


def _executable_binding() -> RandomStreamControlBindingModel:
    return RandomStreamControlBindingModel(
        profile_ref=RandomStreamProfileReferenceModel(
            ref_kind="profile", ref_id="blake3-xof-v1", ref_version="random-stream-profile/v1"
        ),
        namespace="study-namespace",
        root_entropy=PublicSeedModel(kind="public-seed", encoding="hex-fixed-width", value=VALID_HEX_SEED),
    )


def _draw_record(
    control_id: str,
    *,
    namespace: str = "study-namespace",
    transform_id: str = "bounded-integer",
    transform_version: str = "1",
) -> dict:
    address = StreamAddressModel(
        namespace=namespace,
        trial_coordinate=TrialCoordinateModel(condition_id="baseline"),
        selection_policy_id="policy-a",
        variation_point_id="point-a",
        draw_purpose="condition-assignment",
        local_coordinate=0,
    )
    record = RandomStreamDrawRecordModel(
        control_id=control_id,
        address=address,
        transform_id=transform_id,
        transform_version=transform_version,
        local_coordinate=0,
        outcome=PublicRandomOutcomeModel(kind="public-value", value="3"),
    )
    return record.model_dump(mode="json")


class TestExperimentStochasticControlModelExtension:
    def test_executable_binding_defaults_to_none(self) -> None:
        control = ExperimentStochasticControlModel(control_id="task-seed", role="seed", value=12345)
        assert control.executable_binding is None

    def test_accepts_executable_binding(self) -> None:
        control = ExperimentStochasticControlModel(
            control_id="task-seed", role="seed", value=12345, executable_binding=_executable_binding()
        )
        assert control.executable_binding is not None
        assert control.executable_binding.namespace == "study-namespace"

    def test_role_value_description_unchanged(self) -> None:
        control = ExperimentStochasticControlModel(
            control_id="task-seed", role="randomization", description="d", executable_binding=_executable_binding()
        )
        assert control.role == "randomization"
        assert control.description == "d"


class TestExperimentRunModelStochasticDraws:
    def test_stochastic_draws_defaults_to_empty(self) -> None:
        payload = _experiment_fixture("experiment-run-v1")
        run = ExperimentRunModel.model_validate(payload)
        assert run.stochastic_draws == []

    def test_accepts_stochastic_draws_resolving_to_declared_control(self) -> None:
        payload = deepcopy(_experiment_fixture("experiment-run-v1"))
        payload["stochastic_controls"][0]["executable_binding"] = _executable_binding().model_dump(mode="json")
        payload["stochastic_draws"] = [_draw_record("task-seed")]
        run = ExperimentRunModel.model_validate(payload)
        assert len(run.stochastic_draws) == 1
        assert run.stochastic_draws[0].control_id == "task-seed"

    def test_run_schema_publishes_stochastic_draws_surface(self) -> None:
        from raes_contracts.contracts import schema_bundle

        schema = schema_bundle()["experiment-run-v1"]
        assert "stochastic_draws" in schema["properties"]


class TestValidateExperimentRunAgainstTaskStochasticDrawResolution:
    def _task_and_run(self) -> tuple[ExperimentTaskModel, dict]:
        task_payload = _experiment_fixture("experiment-task-v1")
        run_payload = deepcopy(_experiment_fixture("experiment-run-v1"))
        return ExperimentTaskModel.model_validate(task_payload), run_payload

    def test_draw_resolves_to_bound_control_with_matching_namespace_and_admitted_transform(self) -> None:
        task, run_payload = self._task_and_run()
        run_payload["stochastic_controls"][0]["executable_binding"] = _executable_binding().model_dump(mode="json")
        run_payload["stochastic_draws"] = [_draw_record("task-seed")]
        run = ExperimentRunModel.model_validate(run_payload)
        validate_experiment_run_against_task(task, run)  # must not raise

    def test_draw_control_id_not_resolving_is_rejected(self) -> None:
        task, run_payload = self._task_and_run()
        run_payload["stochastic_draws"] = [_draw_record("nonexistent-control")]
        run = ExperimentRunModel.model_validate(run_payload)
        with pytest.raises(ValueError, match="stochastic_draws"):
            validate_experiment_run_against_task(task, run)

    def test_draw_against_descriptive_only_control_is_rejected(self) -> None:
        """A draw referencing a control with no executable_binding makes no executable claim to bind to."""
        task, run_payload = self._task_and_run()
        run_payload["stochastic_draws"] = [_draw_record("task-seed")]
        run = ExperimentRunModel.model_validate(run_payload)
        with pytest.raises(ValueError, match="executable_binding"):
            validate_experiment_run_against_task(task, run)

    def test_draw_address_namespace_mismatching_binding_namespace_is_rejected(self) -> None:
        task, run_payload = self._task_and_run()
        run_payload["stochastic_controls"][0]["executable_binding"] = _executable_binding().model_dump(mode="json")
        run_payload["stochastic_draws"] = [_draw_record("task-seed", namespace="a-different-namespace")]
        run = ExperimentRunModel.model_validate(run_payload)
        with pytest.raises(ValueError, match="address.namespace"):
            validate_experiment_run_against_task(task, run)

    def test_draw_transform_id_not_admitted_by_bound_profile_is_rejected(self) -> None:
        task, run_payload = self._task_and_run()
        run_payload["stochastic_controls"][0]["executable_binding"] = _executable_binding().model_dump(mode="json")
        run_payload["stochastic_draws"] = [_draw_record("task-seed", transform_id="unregistered-transform")]
        run = ExperimentRunModel.model_validate(run_payload)
        with pytest.raises(ValueError, match="transform_id"):
            validate_experiment_run_against_task(task, run)

    def test_draw_transform_version_not_admitted_by_bound_profile_is_rejected(self) -> None:
        task, run_payload = self._task_and_run()
        run_payload["stochastic_controls"][0]["executable_binding"] = _executable_binding().model_dump(mode="json")
        run_payload["stochastic_draws"] = [_draw_record("task-seed", transform_version="99")]
        run = ExperimentRunModel.model_validate(run_payload)
        with pytest.raises(ValueError, match="transform_id"):
            validate_experiment_run_against_task(task, run)
