"""Conditional preparation remains effect-capable even with no authored ops."""

from dataclasses import replace

import pytest
from raes_backend_stubs.stubs import create_stub_target
from raes_contracts.observation_demand import ObservationLifecycleStage, ObservationSelector
from raes_contracts.planning import ProvisioningPlan
from raes_contracts.realization_preparation import RealizationPreparationAuthority
from raes_runtime.control_plane_plan_authorization import RuntimePlanAuthorizationMixin
from raes_runtime.observation_admission import observation_submission_diagnostic
from test_issue_1212_runtime_boundaries import _demands, _runtime


def _conditional_empty_plan():
    return ProvisioningPlan(preparation=RealizationPreparationAuthority(manifest_digest="sha256:" + "a" * 64))


def test_empty_conditional_plan_requires_planner_authorization():
    class UnregisteredRuntime(RuntimePlanAuthorizationMixin):
        def is_planner_authorized_plan(self, plan):
            return False

    owner = UnregisteredRuntime()
    assert owner._plan_authorization_diagnostics(ProvisioningPlan()) == []
    diagnostics = owner._plan_authorization_diagnostics(_conditional_empty_plan())
    assert [item.code for item in diagnostics] == ["runtime.plan-authorization-mismatch"]


def test_empty_conditional_plan_cannot_bypass_required_capture_atomicity():
    selector = ObservationSelector(semantic_scope="/nodes", data_kind="stream", names=("audit",))
    runtime = _runtime(
        selector,
        producer=lambda *_: ("audit",),
        stages=frozenset({ObservationLifecycleStage.COLLECTION}),
    )
    requested = replace(
        _conditional_empty_plan(),
        observation_demands=_demands(selector, purpose="experimental", collection="require", required=True),
    )
    diagnostic = observation_submission_diagnostic(
        requested, create_stub_target().manifest, runtime, durable_lifecycle_available=True
    )
    assert diagnostic is not None
    assert diagnostic.code == "observation.required-execution-atomicity-unavailable"


@pytest.mark.parametrize("has_method", [False, True])
def test_advertised_preparation_requires_the_negotiated_callable_shape(has_method):
    from raes_backend_stubs.stubs import StubProvisioner
    from raes_runtime.registry import RuntimeTarget
    from test_issue_1204_preparation_os import _request

    provisioner = StubProvisioner()
    if has_method:
        provisioner.prepare = lambda: None
    _, manifest = _request()
    with pytest.raises(ValueError, match="prepare"):
        RuntimeTarget(name="preparation-shape", manifest=manifest, provisioner=provisioner)


def test_preparation_bounds_predecessor_before_serialization(monkeypatch):
    import pytest
    from raes_contracts import realization_preparation
    from raes_contracts.runtime_state import RuntimeSnapshot

    calls = []
    serialize = realization_preparation.to_jsonable_python

    def recording_serialize(value):
        calls.append(True)
        return serialize(value)

    monkeypatch.setattr(realization_preparation, "to_jsonable_python", recording_serialize)
    previous = RuntimeSnapshot()
    previous.metadata["cycle"] = previous.metadata
    with pytest.raises(ValueError):
        realization_preparation.preparation_snapshot_digest(previous)
    assert calls == []
