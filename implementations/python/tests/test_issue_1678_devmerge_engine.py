"""Issue #1678: the shared runtime engine from dev follows the exception and logging policy.

Each test pins one refusal that escaped as a built-in exception, one catch that
no longer matched the converted signal, or one foreign value that reached a record.
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from time import monotonic
from types import SimpleNamespace

import pytest
from issue_1629_trial_fixture import TrialServices, factorial_inputs
from raes import parse_sdl
from raes_backend_stubs.stubs import create_stub_target
from raes_contracts.contracts import ExperimentRunModel
from raes_contracts.errors import (
    AuthorizationError,
    ConflictError,
    EvidenceIntegrityError,
    InvalidInputError,
    NotFoundError,
    OperationalError,
)
from raes_contracts.planning import ProvisioningPlan
from raes_runtime import RuntimeControlPlane
from raes_runtime.control_plane_security import ControlPlaneIdentity, ControlPlaneRole
from raes_runtime.control_plane_store_local import LocalControlPlaneStore
from raes_runtime.control_plane_store_local_codec import encode_payload
from raes_runtime.errors import RuntimeBudgetExhaustedError
from raes_runtime.operation_policy_admission import authored_attempt_budget
from raes_runtime.runtime_sequence_reference import RuntimeSequenceReference
from test_runtime_manager import _full_scenario

_REPO_ROOT = Path(__file__).resolve().parents[3]
_POLICY_REFUSAL = "runtime.control-plane.execution-policy-unsupported"


def test_engine_reports_an_unknown_run_scope_as_not_found():
    with (
        RuntimeControlPlane(create_stub_target()) as engine,
        pytest.raises(NotFoundError, match="run scope is not owned"),
    ):
        engine.get_run("run:absent")


def test_exhausted_attempt_budget_refuses_work_before_effects():
    with RuntimeControlPlane(create_stub_target()) as engine:
        plan = engine.plan(_full_scenario())
        with authored_attempt_budget(monotonic() - 1):
            receipt = engine.submit_provisioning(ProvisioningPlan())
            applied = engine.apply(plan)
        assert not receipt.accepted
        assert [item.code for item in receipt.diagnostics] == [_POLICY_REFUSAL]
        assert not applied.success
        assert [item.code for item in applied.diagnostics] == [_POLICY_REFUSAL]
        assert engine.snapshot.entries == {}


def test_changed_plan_for_an_admitted_execution_is_a_conflict():
    with RuntimeControlPlane(create_stub_target()) as engine:
        engine.advance_plan(engine.plan(_full_scenario()), execution_id="one")
        other = engine.plan(parse_sdl("name: other\nnodes:\n  server:\n    type: compute\n"))
        with pytest.raises(ConflictError, match="conflicts with its admitted inputs"):
            engine.advance_plan(other, execution_id="one")


def test_binding_an_unknown_experiment_is_not_found():
    with RuntimeControlPlane(create_stub_target()) as engine, pytest.raises(NotFoundError):
        engine.bind_workflow(
            kind="experiment", scope_id="absent", execution_id="one", worker_id="worker", state_queue="queue"
        )


def test_experiment_actor_mismatch_is_an_authorization_refusal():
    _, inputs, target = factorial_inputs()
    services = TrialServices(target)
    stranger = ControlPlaneIdentity(
        identity="stranger", roles=frozenset({ControlPlaneRole.OPERATOR}), target_name=target.name
    )
    with RuntimeControlPlane(target) as engine:
        experiment = engine.admit_experiment(inputs, services=services)
        with pytest.raises(AuthorizationError, match="admitted scope"):
            engine.experiment_results(experiment, identity=stranger)


def test_cessation_without_evidence_is_an_evidence_refusal():
    from raes_runtime.runtime_trial_services import TrialExecutionObservation

    _, inputs, target = factorial_inputs()
    services = TrialServices(target)
    services.observe = lambda request, snapshot: TrialExecutionObservation(state="succeeded", ceased=True, evidence=())
    with RuntimeControlPlane(target) as engine:
        experiment = engine.admit_experiment(inputs, services=services)
        with pytest.raises(EvidenceIntegrityError, match="cessation requires observed evidence"):
            for _ in range(20):
                engine.advance_experiment(experiment)


def test_pending_trial_is_a_conflict_category():
    from raes_runtime.runtime_trial_unit import TrialPending

    assert issubclass(TrialPending, ConflictError)


def _archived_run() -> ExperimentRunModel:
    path = _REPO_ROOT / "contracts/fixtures/experiment-core/experiment-run-v1/valid/reference.json"
    return ExperimentRunModel.model_validate(json.loads(path.read_text()))


class _Archive:
    def __init__(self, readback: object) -> None:
        self.readback = readback

    def write_run(self, run: ExperimentRunModel) -> None:
        del run

    def read_run(self, run_id: str, run_version: str) -> object:
        del run_id, run_version
        return self.readback


@pytest.mark.parametrize("readback", ["changed", "carrier"])
def test_archive_readback_mismatch_is_an_evidence_refusal(readback):
    from raes_runtime.runtime_experiment_replacement import _write_archive

    run = _archived_run()
    observed = run.model_copy(update={"started_at": "2026-05-26T00:11:00Z"}) if readback == "changed" else object()
    with pytest.raises(EvidenceIntegrityError, match="archive readback differs"):
        _write_archive(_Archive(observed), run)


def test_provider_capabilities_carrier_is_an_input_refusal(monkeypatch):
    from raes_runtime import runtime_experiment_admission as admission

    monkeypatch.setattr(admission, "required_trial_operation_guarantees", lambda *_args: ("cessation-evidence",))
    engine = SimpleNamespace(
        _target=SimpleNamespace(operation_provider=SimpleNamespace(operation_capabilities=object)),
        _execution_adapter=SimpleNamespace(call=lambda _lane, method, *args, timeout_ms: method(*args)),
        _supervision=SimpleNamespace(admission_ms=1000),
        target_name="stub",
    )
    request = SimpleNamespace(execution_controls=None, cleanup_plan=SimpleNamespace(retry_policy=None))
    with pytest.raises(InvalidInputError, match="invalid operation carrier"):
        admission._require_operation_guarantees(engine, request)


@pytest.mark.parametrize("tamper", ["identity", "contract"])
def test_stored_runtime_decision_damage_is_an_integrity_refusal(tmp_path, tamper):
    from raes_runtime.runtime_decisions import RunContextDecision

    with RuntimeControlPlane(create_stub_target(), store=LocalControlPlaneStore(tmp_path)) as engine:
        store = engine._store
        decision = RunContextDecision(run_scope="run:one", store_digest="sha256:" + "a" * 64, status="opened")
        store.claim_runtime_decision(decision)
        with store._decision_transaction() as connection:
            if tamper == "identity":
                connection.execute(
                    "UPDATE runtime_decisions SET decision_id=? WHERE decision_id=?",
                    ("sha256:" + "f" * 64, decision.decision_id),
                )
            else:
                content, digest = encode_payload({"schema_version": "unknown-decision/v1"})
                connection.execute(
                    "UPDATE runtime_decisions SET payload=?, digest=? WHERE decision_id=?",
                    (content, digest, decision.decision_id),
                )
        with pytest.raises(EvidenceIntegrityError):
            store.load_runtime_decisions()


class _Authority:
    def __init__(self, failure: BaseException) -> None:
        self.configuration = SimpleNamespace(identity=SimpleNamespace(identity="state-worker"))
        self.failure = failure

    def advance_runtime(self, reference: RuntimeSequenceReference) -> str:
        del reference
        raise self.failure


def _reference_payload(worker_id: str = "state-worker") -> dict[str, object]:
    return RuntimeSequenceReference(
        engine_id="sha256:" + "a" * 64,
        kind="run",
        execution_id="one",
        scope_id="run:default",
        request_digest="sha256:" + "b" * 64,
        worker_id=worker_id,
        state_queue="runtime-state",
    ).model_dump(mode="json")


def _advance(authority: _Authority, payload: dict[str, object]) -> str:
    pytest.importorskip("temporalio")
    from raes_runtime.runtime_temporal_worker import TemporalRuntimeActivities

    return asyncio.run(TemporalRuntimeActivities(authority).advance(payload))


def test_runtime_activity_reports_a_lost_authority_response_as_unavailable():
    failure = OperationalError("worker authority response could not be established")

    assert _advance(_Authority(failure), _reference_payload()) == "unavailable"


def test_runtime_activity_refuses_a_foreign_worker_reference():
    with pytest.raises(AuthorizationError, match="forbidden"):
        _advance(_Authority(RuntimeError("unused")), _reference_payload("foreign"))


def test_runtime_activity_refusal_carries_no_cause_and_logs_only_unexpected_failures(caplog):
    caplog.set_level(logging.ERROR, logger="raes_runtime.runtime_temporal_worker")
    with pytest.raises(ConflictError, match="refused") as refused:
        _advance(_Authority(AuthorizationError("runtime worker reference is forbidden")), _reference_payload())
    assert refused.value.__cause__ is None
    assert refused.value.__context__ is None
    assert not caplog.records

    with pytest.raises(ConflictError, match="refused") as refused:
        _advance(_Authority(RuntimeError("secret-value")), _reference_payload())
    assert refused.value.__context__ is None
    (record,) = caplog.records
    assert record.getMessage() == "runtime state activity failed before its outcome was established"
    assert "secret-value" not in caplog.text


_FOREIGN_SECRET = "host-secret-1678"
_OWNER_RECORD = "installed trial owner failed"


def _foreign(*_args: object, **_kwargs: object) -> object:
    raise LookupError(_FOREIGN_SECRET)


def _assert_one_value_free_owner_record(caplog: pytest.LogCaptureFixture) -> None:
    owner_records = [record for record in caplog.records if record.getMessage() == _OWNER_RECORD]
    assert len(owner_records) == 1
    assert "LookupError" not in caplog.text
    assert _FOREIGN_SECRET not in caplog.text


class _DirectAdapter:
    def call(self, _lane: str, method, *args: object, timeout_ms: int) -> object:
        del timeout_ms
        return method(*args)


def test_installed_owner_refusal_passes_through_without_a_record(caplog):
    from raes_runtime.runtime_trial_services import call_installed_owner

    caplog.set_level(logging.WARNING)
    refusal = ConflictError("installed owner refused")

    def refuse() -> None:
        raise refusal

    with pytest.raises(ConflictError) as raised:
        call_installed_owner(_DirectAdapter(), refuse, timeout_ms=1, failure=OperationalError, message="unused")
    assert raised.value is refusal
    assert not caplog.records


def test_installed_owner_budget_exhaustion_is_a_budget_category(caplog):
    from raes_runtime.errors import RuntimeBudgetExhaustedError
    from raes_runtime.runtime_trial_services import call_installed_owner

    caplog.set_level(logging.WARNING)

    def expire() -> None:
        raise TimeoutError(_FOREIGN_SECRET)

    with pytest.raises(RuntimeBudgetExhaustedError) as raised:
        call_installed_owner(_DirectAdapter(), expire, timeout_ms=1, failure=OperationalError, message="unused")
    assert raised.value.__context__ is None
    assert not caplog.records


def test_installed_owner_foreign_failure_logs_one_value_free_record(caplog):
    from raes_runtime.runtime_trial_services import call_installed_owner

    caplog.set_level(logging.WARNING)
    with pytest.raises(OperationalError, match="owner failed here") as raised:
        call_installed_owner(
            _DirectAdapter(), _foreign, timeout_ms=1, failure=OperationalError, message="owner failed here"
        )
    assert raised.value.__context__ is None
    assert raised.value.__cause__ is None
    _assert_one_value_free_owner_record(caplog)


def test_trial_admission_service_failure_is_isolated(caplog):
    _, inputs, target = factorial_inputs()
    services = TrialServices(target)
    services.admit = _foreign
    caplog.set_level(logging.WARNING)
    with (
        RuntimeControlPlane(target) as engine,
        pytest.raises(ConflictError, match="installed trial services refused the trial"),
    ):
        engine.admit_experiment(inputs, services=services)
    _assert_one_value_free_owner_record(caplog)


def test_trial_admission_service_refusal_needs_no_record(caplog):
    _, inputs, target = factorial_inputs()
    services = TrialServices(target)
    refusal = ConflictError("installed settings are unavailable")

    def refuse(_request: object) -> None:
        raise refusal

    services.admit = refuse
    caplog.set_level(logging.WARNING)
    with RuntimeControlPlane(target) as engine, pytest.raises(ConflictError) as raised:
        engine.admit_experiment(inputs, services=services)
    assert raised.value is refusal
    assert not caplog.records


def test_provider_capabilities_failure_is_isolated(monkeypatch, caplog):
    from raes_runtime import runtime_experiment_admission as admission

    monkeypatch.setattr(admission, "required_trial_operation_guarantees", lambda *_args: ("cessation-evidence",))
    engine = SimpleNamespace(
        _target=SimpleNamespace(operation_provider=SimpleNamespace(operation_capabilities=_foreign)),
        _execution_adapter=_DirectAdapter(),
        _supervision=SimpleNamespace(admission_ms=1000),
        target_name="stub",
    )
    request = SimpleNamespace(execution_controls=None, cleanup_plan=SimpleNamespace(retry_policy=None))
    caplog.set_level(logging.WARNING)
    with pytest.raises(OperationalError, match="capabilities are unavailable"):
        admission._require_operation_guarantees(engine, request)
    _assert_one_value_free_owner_record(caplog)


def test_trial_verification_failure_is_isolated_and_leaves_the_configuration_unresolved(caplog):
    _, inputs, target = factorial_inputs()
    services = TrialServices(target)
    services.verify = _foreign
    caplog.set_level(logging.WARNING)
    with RuntimeControlPlane(target) as engine:
        experiment = engine.admit_experiment(inputs, services=services)
        # The configuration call ran, so the operation boundary settles its effect as unknown.
        assert engine.advance_experiment(experiment).state == "indeterminate"
        assert [phase for _, phase in services.events] == ["configure"]
    _assert_one_value_free_owner_record(caplog)


def test_trial_observer_failure_is_isolated(caplog):
    _, inputs, target = factorial_inputs()
    services = TrialServices(target)
    services.observe = _foreign
    caplog.set_level(logging.WARNING)
    with RuntimeControlPlane(target) as engine:
        experiment = engine.admit_experiment(inputs, services=services)
        with pytest.raises(OperationalError, match="installed trial observer failed"):
            for _ in range(20):
                engine.advance_experiment(experiment)
    _assert_one_value_free_owner_record(caplog)


def _replacement_engine_inputs():
    from issue_1629_archive_fixture import TrialArchive
    from raes_runtime.runtime_experiment_replacement import ExperimentReplacementBinding
    from test_issue_1629_experiment_replacement import replacement_request

    request, inputs, target = factorial_inputs(replacement_request)
    archive, services = TrialArchive(), TrialServices(target)
    return inputs, target, services, archive, ExperimentReplacementBinding(request, archive)


@pytest.mark.parametrize("method", ["build_run", "write_run"])
def test_archive_owner_failure_is_isolated(caplog, method):
    inputs, target, services, archive, binding = _replacement_engine_inputs()
    setattr(archive, method, _foreign)
    message = "could not build the trial run" if method == "build_run" else "could not publish the trial run"
    caplog.set_level(logging.WARNING)
    with RuntimeControlPlane(target) as engine:
        experiment = engine.admit_experiment(inputs, services=services, replacement=binding)
        with pytest.raises(OperationalError, match=message):
            for _ in range(20):
                engine.advance_experiment(experiment)
    _assert_one_value_free_owner_record(caplog)


@pytest.mark.parametrize("error", [TimeoutError("adapter budget"), RuntimeBudgetExhaustedError("budget")])
def test_runtime_progress_route_reports_an_exhausted_call_budget_as_unavailable(monkeypatch, error):
    from fastapi.testclient import TestClient
    from raes_runtime.control_plane_api import create_control_plane_app
    from raes_runtime.control_plane_security import ControlPlaneSecurityConfig

    def expire(*_args: object, **_kwargs: object) -> str:
        raise error

    worker = ControlPlaneIdentity(
        identity="state-worker", roles=frozenset({ControlPlaneRole.BACKEND}), target_name="stub"
    )
    with RuntimeControlPlane(create_stub_target()) as engine:
        monkeypatch.setattr(engine, "advance_workflow", expire)
        security = ControlPlaneSecurityConfig(bearer_tokens={"worker": worker})
        with TestClient(create_control_plane_app(engine, security=security)) as client:
            response = client.post(
                "/runtime/progress", json=_reference_payload(), headers={"Authorization": "Bearer worker"}
            )
    assert response.status_code == 503
    assert str(error) not in response.text
