"""Issue #1678: the exception and logging policy on the conformance probes merged from dev.

The runner catches the refusal categories of the runtime, isolates harness and
backend failures with one value-free record, and keeps input values out of its
messages.
"""

from __future__ import annotations

import logging
from dataclasses import replace
from types import SimpleNamespace

import pytest
from raes_contracts.errors import (
    AuthorizationError,
    ConflictError,
    EvidenceIntegrityError,
    InvalidInputError,
    NotFoundError,
    OperationalError,
)

SENTINEL = "PRIVATE-DEVMERGE-CONFORMANCE-1678"
ENVIRONMENT = "sha256:" + "0" * 64


def _records(caplog: pytest.LogCaptureFixture, module: str) -> list[logging.LogRecord]:
    return [record for record in caplog.records if record.name == f"raes_conformance.conformance.{module}"]


def _assert_foreign_record(records: list[logging.LogRecord], foreign_type: str) -> None:
    assert len(records) == 1
    record = records[0]
    assert SENTINEL not in record.getMessage()
    assert SENTINEL not in (record.exc_text or "")
    assert "ForeignCodeFailure" in (record.exc_text or "")
    assert foreign_type not in (record.exc_text or "")


# --- Participant opacity execution ---------------------------------------------------------------------------


def _view_plane(error: BaseException) -> SimpleNamespace:
    def view(*args: object, **kwargs: object) -> None:
        raise error

    return SimpleNamespace(get_participant_status_view=view)


_VIEW_CASE = SimpleNamespace(participant_address="p", identity=None, crossing_evidence=None, idempotency_key="k")


def test_opacity_egress_treats_the_authorization_refusal_as_withholding() -> None:
    from raes_conformance.conformance.participant_opacity_execution import _egress

    assert _egress(_view_plane(AuthorizationError("refused")), _VIEW_CASE) == {"result": "refused"}


def test_opacity_egress_does_not_treat_another_category_as_withholding() -> None:
    from raes_conformance.conformance.participant_opacity_execution import _egress

    with pytest.raises(ConflictError):
        _egress(_view_plane(ConflictError("conflict")), _VIEW_CASE)


def _governed(failures: list[str]):
    from raes_conformance.conformance.participant_opacity_execution import _Governed

    plane = SimpleNamespace(snapshot=SimpleNamespace(participant_crossing_history={}))
    return _Governed(plane, None, "p", failures)


def test_opacity_governed_operation_isolates_a_foreign_failure(caplog: pytest.LogCaptureFixture) -> None:
    def call() -> dict[str, object]:
        raise LookupError(SENTINEL)

    failures: list[str] = []
    with caplog.at_level(logging.ERROR, logger="raes_conformance"):
        assert _governed(failures).run("ingress", call) is None

    assert failures == ["ingress: rejected by LookupError"]
    _assert_foreign_record(_records(caplog, "participant_opacity_execution"), "LookupError")


def test_opacity_governed_refusal_category_needs_no_record(caplog: pytest.LogCaptureFixture) -> None:
    def call() -> dict[str, object]:
        raise ConflictError("refused")

    failures: list[str] = []
    with caplog.at_level(logging.ERROR, logger="raes_conformance"):
        assert _governed(failures).run("replay", call) is None

    assert failures == ["replay: rejected by ConflictError"]
    assert not _records(caplog, "participant_opacity_execution")


def _readback(harness: object, failures: list[str]) -> object:
    from raes_conformance.conformance.participant_opacity_execution import _readback

    return _readback(harness, object(), SimpleNamespace(name="case"), "point", "before", failures)


def test_opacity_untyped_readback_is_invalid_input_without_record(caplog: pytest.LogCaptureFixture) -> None:
    harness = SimpleNamespace(backend_readback=lambda target, case, request: {"digest": SENTINEL})
    failures: list[str] = []
    with caplog.at_level(logging.ERROR, logger="raes_conformance"):
        assert _readback(harness, failures) is None

    assert failures == ["backend readback: rejected by InvalidInputError"]
    assert not _records(caplog, "participant_opacity_execution")


def test_opacity_readback_failure_is_isolated(caplog: pytest.LogCaptureFixture) -> None:
    def backend_readback(target: object, case: object, request: object) -> object:
        raise KeyError(SENTINEL)

    failures: list[str] = []
    with caplog.at_level(logging.ERROR, logger="raes_conformance"):
        assert _readback(SimpleNamespace(backend_readback=backend_readback), failures) is None

    assert failures == ["backend readback: rejected by KeyError"]
    _assert_foreign_record(_records(caplog, "participant_opacity_execution"), "KeyError")


def _history_with_resolver(error: BaseException, failures: list[str]) -> tuple[bool, tuple[object, ...]]:
    from raes_conformance.conformance.participant_opacity_execution import _validated_history

    def validation_context(snapshot: object, participant_address: str) -> object:
        raise error

    plane = SimpleNamespace(snapshot=SimpleNamespace(participant_crossing_history={}))
    point = SimpleNamespace(resolver=SimpleNamespace(validation_context=validation_context))
    return _validated_history(plane, point, "p", failures)


def test_opacity_resolver_refusal_needs_no_record(caplog: pytest.LogCaptureFixture) -> None:
    failures: list[str] = []
    with caplog.at_level(logging.ERROR, logger="raes_conformance"):
        assert _history_with_resolver(ValueError(SENTINEL), failures) == (False, ())

    assert failures == ["committed history: rejected by ValueError"]
    assert not _records(caplog, "participant_opacity_execution")


def test_opacity_resolver_failure_is_isolated(caplog: pytest.LogCaptureFixture) -> None:
    failures: list[str] = []
    with caplog.at_level(logging.ERROR, logger="raes_conformance"):
        assert _history_with_resolver(LookupError(SENTINEL), failures) == (False, ())

    assert failures == ["committed history: rejected by LookupError"]
    _assert_foreign_record(_records(caplog, "participant_opacity_execution"), "LookupError")


def test_opacity_binding_without_trusted_support_is_an_evidence_integrity_failure() -> None:
    from raes_conformance.conformance.participant_opacity_execution import _rejoin_opacity_bindings

    record = SimpleNamespace(occurrence=SimpleNamespace(opacity_enforcement="binding"))
    with pytest.raises(EvidenceIntegrityError):
        _rejoin_opacity_bindings([record], ())


def test_opacity_projection_ignores_a_binding_that_fails_its_contract() -> None:
    from raes_conformance.conformance.participant_opacity_projection import _case_profile_binding

    case = SimpleNamespace(profile_id="profile", profile_revision="rev1", profile_digest=ENVIRONMENT)
    assert _case_profile_binding(case, {"claim": SENTINEL}) is None


# --- Mixed-backend probes ------------------------------------------------------------------------------------


def test_mixed_unbound_dispatch_is_refused_as_a_binding_conflict(tmp_path) -> None:
    from mixed_conformance_harness import Dispatcher, PortableHarness
    from raes_conformance.conformance import run_mixed_backend_conformance

    report = run_mixed_backend_conformance(
        PortableHarness(tmp_path, dispatcher=Dispatcher()), cases=["edge-unbound-refused"]
    )

    assert report.passed, report.cases[0].diagnostics


def test_mixed_submit_isolates_a_foreign_failure(caplog: pytest.LogCaptureFixture) -> None:
    from raes_conformance.conformance.mixed_backend_execution import submit

    def call() -> object:
        raise LookupError(SENTINEL)

    with caplog.at_level(logging.ERROR, logger="raes_conformance"):
        read = submit(call, None, None)

    assert (read.refusal, read.refusal_type) == ("rejected by LookupError", LookupError)
    _assert_foreign_record(_records(caplog, "mixed_backend_execution"), "LookupError")


def test_mixed_submit_refusal_category_needs_no_record(caplog: pytest.LogCaptureFixture) -> None:
    from raes_conformance.conformance.mixed_backend_execution import submit

    def call() -> object:
        raise ConflictError("refused")

    with caplog.at_level(logging.ERROR, logger="raes_conformance"):
        read = submit(call, None, None)

    assert read.refusal_type is ConflictError
    assert not _records(caplog, "mixed_backend_execution")


def test_mixed_close_failure_is_visible_and_isolated(caplog: pytest.LogCaptureFixture) -> None:
    from raes_conformance.conformance.mixed_backend_execution import close_plane

    def close() -> None:
        raise RuntimeError(SENTINEL)

    failures: list[str] = []
    with caplog.at_level(logging.ERROR, logger="raes_conformance"):
        assert close_plane(SimpleNamespace(close=close), failures) is False

    assert failures == ["cleanup: rejected by RuntimeError"]
    _assert_foreign_record(_records(caplog, "mixed_backend_execution"), "RuntimeError")


def test_mixed_harness_failure_fails_the_case_and_is_isolated(caplog: pytest.LogCaptureFixture) -> None:
    from raes_conformance.conformance.mixed_backend_cases import MIXED_BACKEND_CASES
    from raes_conformance.conformance.mixed_backend_probes import _run_case

    def composition(request: object) -> object:
        raise LookupError(SENTINEL)

    with caplog.at_level(logging.ERROR, logger="raes_conformance"):
        result = _run_case(SimpleNamespace(composition=composition), MIXED_BACKEND_CASES[0], ENVIRONMENT, ENVIRONMENT)

    assert result.outcome == "failed"
    assert [item.code for item in result.diagnostics] == ["conformance.mixed-case-error"]
    assert all(SENTINEL not in item.message for item in result.diagnostics)
    _assert_foreign_record(_records(caplog, "mixed_backend_probes"), "LookupError")


def test_mixed_unknown_case_selection_does_not_echo_the_identifier() -> None:
    from raes_conformance.conformance.mixed_backend_cases import select_cases

    with pytest.raises(ValueError, match="unknown case id") as refused:
        select_cases([SENTINEL])
    assert SENTINEL not in str(refused.value)


def test_mixed_malformed_environment_digest_is_invalid_input() -> None:
    from raes_conformance.conformance.mixed_backend_types import require_environment_digest

    with pytest.raises(InvalidInputError, match="environment digest") as refused:
        require_environment_digest(SENTINEL)
    assert SENTINEL not in str(refused.value)


def _combination(monkeypatch: pytest.MonkeyPatch, error: BaseException) -> object:
    from raes_conformance.conformance import mixed_control_probes
    from raes_conformance.conformance.mixed_backend_cases import MIXED_BACKEND_CASES

    def refuse(target: object, **options: object) -> object:
        raise error

    monkeypatch.setattr(mixed_control_probes, "RuntimeControlPlane", refuse)
    case = next(item for item in MIXED_BACKEND_CASES if item.case_id.startswith("combination-"))
    return mixed_control_probes._attempt_combination(case, object(), {})


def test_mixed_combination_refused_by_the_configuration_validator_is_unsupported(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    verdict = _combination(monkeypatch, ValueError(SENTINEL))

    assert verdict.outcome == "unsupported"
    assert [item.message for item in verdict.diagnostics] == [
        "The runtime refused the combination (rejected by ValueError)."
    ]


def test_mixed_combination_failure_outside_the_refusal_contract_is_not_unsupported(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(LookupError):
        _combination(monkeypatch, LookupError(SENTINEL))


# --- Modular-control probes ----------------------------------------------------------------------------------


def _drive_projection(monkeypatch: pytest.MonkeyPatch, outcome: object, *, expect_refusal: bool) -> object:
    from raes_conformance.conformance import modular_control_execution as execution
    from raes_conformance.conformance.modular_control_types import ModularControlOperation, ModularControlStep

    def view(**arguments: object) -> object:
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome

    monkeypatch.setattr(execution, "_capture", lambda plane, store, measured: None)
    measured = execution._Measurement()
    step = ModularControlStep(ModularControlOperation.PROJECTION, {}, expect_refusal=expect_refusal)
    execution._drive(SimpleNamespace(get_participant_status_view=view), None, step, measured)
    return measured


@pytest.mark.parametrize(
    "refusal",
    [AuthorizationError, ConflictError, EvidenceIntegrityError, InvalidInputError, NotFoundError],
)
def test_modular_expected_refusal_accepts_each_runtime_refusal_category(monkeypatch, refusal) -> None:
    measured = _drive_projection(monkeypatch, refusal("refused"), expect_refusal=True)

    assert measured.refusals == 1
    assert measured.outputs == [None]


def test_modular_failed_dependency_is_not_an_expected_refusal(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(OperationalError):
        _drive_projection(monkeypatch, OperationalError("offline"), expect_refusal=True)


def test_modular_runtime_that_does_not_refuse_is_an_evidence_finding(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(EvidenceIntegrityError, match="expected an explicit refusal"):
        _drive_projection(monkeypatch, object(), expect_refusal=True)


def test_modular_options_that_do_not_configure_the_runtime_are_invalid_input(tmp_path) -> None:
    from raes_conformance.conformance.modular_control_execution import _open_plane
    from raes_runtime.control_plane import LocalControlPlaneStore
    from test_issue_1069_participant_control_orchestration import control_target

    with pytest.raises(InvalidInputError, match="options") as refused:
        _open_plane(control_target(), LocalControlPlaneStore(tmp_path), {"run_scope": SENTINEL})
    assert SENTINEL not in str(refused.value)
    assert isinstance(refused.value.__cause__, ValueError)


def test_modular_cleanup_hook_failure_is_isolated(caplog: pytest.LogCaptureFixture) -> None:
    from test_issue_1071_modular_conformance import case_for, run

    def fail() -> tuple[str, ...]:
        raise RuntimeError(SENTINEL)

    with caplog.at_level(logging.ERROR, logger="raes_conformance"):
        report = run(replace(case_for(), cleanup=fail))

    assert report.cases[0].residual_state == ("cleanup-unverified",)
    _assert_foreign_record(_records(caplog, "modular_control_execution"), "RuntimeError")


def test_modular_harness_failure_is_isolated(caplog: pytest.LogCaptureFixture) -> None:
    from raes_conformance.conformance import run_modular_control_conformance
    from test_issue_1069_participant_control_orchestration import control_target

    class BrokenHarness:
        def cases(self, target: object) -> object:
            raise LookupError(SENTINEL)

    with caplog.at_level(logging.ERROR, logger="raes_conformance"):
        report = run_modular_control_conformance(control_target(), harness=BrokenHarness(), obligations=("dependency",))

    assert [item.message for item in report.diagnostics] == ["rejected by LookupError"]
    _assert_foreign_record(_records(caplog, "modular_control"), "LookupError")


def test_modular_untyped_harness_cases_are_invalid_input_without_record(caplog: pytest.LogCaptureFixture) -> None:
    from raes_conformance.conformance import run_modular_control_conformance
    from test_issue_1069_participant_control_orchestration import control_target

    class ListHarness:
        def cases(self, target: object) -> object:
            return [SENTINEL]

    with caplog.at_level(logging.ERROR, logger="raes_conformance"):
        report = run_modular_control_conformance(control_target(), harness=ListHarness(), obligations=("dependency",))

    assert [item.message for item in report.diagnostics] == ["rejected by InvalidInputError"]
    assert not _records(caplog, "modular_control")


def test_modular_recovery_policy_lost_in_planning_is_an_evidence_finding() -> None:
    from raes_conformance.conformance.modular_control_policy import _policy_payload

    with pytest.raises(EvidenceIntegrityError, match="lost in planning"):
        _policy_payload(None, "terminate")


def test_modular_recovery_unexpected_failure_is_logged_once_without_values(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    from raes_conformance.conformance import modular_control_policy
    from test_issue_1069_participant_control_orchestration import control_target

    def fail(target: object, response: str) -> list[dict[str, object]]:
        raise RuntimeError(SENTINEL)

    monkeypatch.setattr(modular_control_policy, "_planned_policies", fail)
    with caplog.at_level(logging.ERROR, logger="raes_conformance"):
        result = modular_control_policy.authored_recovery_case(control_target(), ("authored-recovery",), ())

    assert [item.message for item in result.diagnostics] == ["rejected by RuntimeError"]
    records = _records(caplog, "modular_control_policy")
    assert len(records) == 1
    assert SENTINEL not in record_text(records[0])


def test_modular_recovery_finding_needs_no_record(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    from raes_conformance.conformance import modular_control_policy
    from test_issue_1069_participant_control_orchestration import control_target

    def lost(target: object, response: str) -> list[dict[str, object]]:
        raise EvidenceIntegrityError("authored recovery policy was lost in planning")

    monkeypatch.setattr(modular_control_policy, "_planned_policies", lost)
    with caplog.at_level(logging.ERROR, logger="raes_conformance"):
        result = modular_control_policy.authored_recovery_case(control_target(), ("authored-recovery",), ())

    assert [item.message for item in result.diagnostics] == ["rejected by EvidenceIntegrityError"]
    assert not _records(caplog, "modular_control_policy")


def record_text(record: logging.LogRecord) -> str:
    return record.getMessage() + (record.exc_text or "")
