"""Issue 1678 review cycle 2: one foreign record at each isolation boundary (ADR-116, H2).

An isolation handler for code that RAES does not own logs ``foreign_failure_record``
one time. The record keeps only the RAES frames. An outer handler does not log the
same failure again, and a later exception does not carry the foreign exception.
Readers of retained state refuse a malformed record as an evidence-integrity failure.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, replace
from types import SimpleNamespace

import pytest
import raes_contracts.contracts.participant_control_continuation as continuation_contract
import raes_runtime.participant_control_effect_continuations as continuations
import raes_runtime.participant_control_evaluation_v2 as evaluation_v2
import raes_runtime.participant_control_operation_index as operation_index
import raes_runtime.participant_control_receipts as receipts
import raes_runtime.participant_inject_control as inject_control
import raes_runtime.participant_scheduler_operations as scheduler_operations
from participant_control_runtime_fixtures import control_binding
from participant_control_v2_fixtures import Resolver, binding
from participant_crossing_fixtures import admit
from raes_contracts._host_isolation import isolated_host_call
from raes_contracts.contracts.participant_control_occurrence_v2 import parse_participant_control_occurrence
from raes_contracts.errors import ConflictError, EvidenceIntegrityError, InvalidInputError, OperationalError
from raes_contracts.runtime_state import OperationState, RuntimeSnapshot
from raes_runtime.mixed_runtime_phase import _evaluate
from raes_runtime.participant_control_binding import fenced_validation_context
from raes_runtime.participant_control_effect_owners import prepare_v2_effect_dispatch
from raes_runtime.participant_control_effects import _effect_operation
from raes_runtime.participant_control_orchestration import _resolve
from raes_runtime.participant_control_runtime import _archived_policy, archived_policies
from raes_runtime.participant_control_targets import _retained_record, archived_control_targets
from raes_runtime.participant_flow_sink import _resolve_flow_sink_relation
from raes_runtime.participant_inject_application import _projection_cut, _resolve_delivery, require_projected_inject
from raes_runtime.participant_scheduler_binding import _bound_runtime_request
from test_issue_1069_participant_control_orchestration import _plane

_SENTINEL = "value-sentinel-1678-cycle2"
_ForeignError = type("ForeignSecretError1678c2", (RuntimeError,), {})
_ForeignTypeError = type("ForeignTypeError1678c2", (TypeError,), {})
_FOREIGN_NAMES = ("ForeignSecretError1678c2", "ForeignTypeError1678c2", "_raise_foreign_1678c2", "OSError")


def _raise_foreign_1678c2(*_args: object, **_kwargs: object) -> object:
    try:
        raise OSError(_SENTINEL)
    except OSError as cause:
        raise _ForeignError(_SENTINEL) from cause


def _raise_foreign_type_1678c2(*_args: object, **_kwargs: object) -> object:
    raise _ForeignTypeError(_SENTINEL)


@pytest.fixture(autouse=True)
def _capture(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG)


@pytest.fixture(autouse=True)
def _close_planes(monkeypatch: pytest.MonkeyPatch):
    from raes_runtime.control_plane import RuntimeControlPlane

    original = RuntimeControlPlane.__init__
    planes = []

    def initialize(self, *args, **kwargs):
        original(self, *args, **kwargs)
        planes.append(self)

    monkeypatch.setattr(RuntimeControlPlane, "__init__", initialize)
    yield
    for plane in planes:
        plane.close()


def _failure_records(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    return [item for item in caplog.records if item.name.startswith("raes") and item.levelno >= logging.WARNING]


def _assert_foreign(record: logging.LogRecord) -> None:
    assert _SENTINEL not in record.getMessage()
    assert record.exc_info is None
    assert "ForeignCodeFailure" in (record.exc_text or "")
    for name in (_SENTINEL, *_FOREIGN_NAMES):
        assert name not in record.exc_text


def _single_foreign(caplog: pytest.LogCaptureFixture, logger: str, level: int = logging.ERROR) -> logging.LogRecord:
    records = _failure_records(caplog)
    assert [(item.name, item.levelno) for item in records] == [(logger, level)]
    _assert_foreign(records[0])
    return records[0]


def _assert_no_foreign_chain(error: BaseException) -> None:
    seen = error
    while seen is not None:
        assert not isinstance(seen, (_ForeignError, _ForeignTypeError, OSError))
        seen = seen.__cause__ or seen.__context__


# --- core-F8: installed evaluator and resolver boundaries ---------------------


def test_mixed_phase_evaluator_failure_logs_only_raes_frames(caplog: pytest.LogCaptureFixture) -> None:
    plane = SimpleNamespace(
        _mixed_runtime=SimpleNamespace(transition_evaluators={"evaluator": _raise_foreign_1678c2}),
        _snapshot=RuntimeSnapshot(),
    )
    transition = SimpleNamespace(evaluator_ref="evaluator", evidence_bindings=(), progress_bound=1)

    evaluation = _evaluate(plane, transition, object())

    assert evaluation.order_ref == "order:evaluator-failed"
    _single_foreign(caplog, "raes_runtime.mixed_runtime_phase")


def test_fenced_validation_context_failure_logs_only_raes_frames(caplog: pytest.LogCaptureFixture) -> None:
    installed = SimpleNamespace(resolver=SimpleNamespace(validation_context=_raise_foreign_1678c2))

    context = fenced_validation_context(SimpleNamespace(), installed, object())

    assert context(object()) is None
    _single_foreign(caplog, "raes_runtime.participant_control_binding")


def _fake_cut(monkeypatch: pytest.MonkeyPatch) -> None:
    cut = SimpleNamespace(
        call=lambda method, *args, provider=False: method(*args),
        require_current=lambda: None,
    )
    monkeypatch.setattr(evaluation_v2._EvaluationCut, "capture", classmethod(lambda cls, plane, origin=None: cut))


def _dispatch_fixture(monkeypatch: pytest.MonkeyPatch, resolver: object):
    _fake_cut(monkeypatch)
    monkeypatch.setattr(receipts, "retained_effect_claim", lambda *_args: None)
    monkeypatch.setattr(receipts, "realization", lambda request, disposition, ref: (disposition, ref))
    installed = SimpleNamespace(resolver=resolver)
    return prepare_v2_effect_dispatch(
        SimpleNamespace(), installed, object(), object(), SimpleNamespace(effect_id="effect-1")
    )


def test_effect_dispatch_context_failure_logs_only_raes_frames(
    caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    outcome = _dispatch_fixture(monkeypatch, SimpleNamespace(validation_context=_raise_foreign_1678c2))

    assert outcome == (("withheld", "authority-unresolved.effect-1"), None)
    _single_foreign(caplog, "raes_runtime.participant_control_binding")


def _host_refusal(*_args: object) -> None:
    with isolated_host_call("participant control current effect authority validation failed", keep_cause=False):
        _raise_foreign_1678c2()


def test_effect_dispatch_host_failure_is_logged_once(
    caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(continuation_contract, "validate_participant_control_effect_dispatch_v2", _host_refusal)

    outcome = _dispatch_fixture(monkeypatch, SimpleNamespace(validation_context=lambda _evaluation: object()))

    assert outcome == (("withheld", "authority-unresolved.effect-1"), None)
    _single_foreign(caplog, "raes_contracts._host_isolation")


@dataclass(frozen=True)
class _Context:
    parent_admission_receipt: object = None
    parent_application_receipt: object = None
    commit_receipt: object = None


def _continuation_admitted(monkeypatch: pytest.MonkeyPatch, resolver: object) -> bool:
    _fake_cut(monkeypatch)
    monkeypatch.setattr(continuations, "validate_incremental_effect_admission", lambda *_args: None)
    monkeypatch.setattr(continuations, "with_retained_effect_evidence", lambda context, _retained: context)
    plan = SimpleNamespace(parent_admission_receipt=None, parent_application_receipt=None)
    source = SimpleNamespace(commit=SimpleNamespace(receipt=None))
    cut = evaluation_v2._EvaluationCut.capture(SimpleNamespace())
    return continuations._continuation_admitted(
        SimpleNamespace(), SimpleNamespace(resolver=resolver), cut, object(), source, plan, {}
    )


def test_continuation_context_failure_logs_only_raes_frames(
    caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert not _continuation_admitted(monkeypatch, SimpleNamespace(validation_context=_raise_foreign_1678c2))
    _single_foreign(caplog, "raes_runtime.participant_control_binding")


def test_continuation_host_failure_is_logged_once(
    caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(continuations, "validate_participant_control_continuation_v2", _host_refusal)

    assert not _continuation_admitted(monkeypatch, SimpleNamespace(validation_context=lambda _record: _Context()))
    _single_foreign(caplog, "raes_contracts._host_isolation")


def test_continuation_first_party_defect_is_not_reported_as_a_refusal(monkeypatch: pytest.MonkeyPatch) -> None:
    def defect(*_args: object) -> None:
        raise KeyError("internal defect")

    monkeypatch.setattr(continuations, "validate_participant_control_continuation_v2", defect)

    with pytest.raises(KeyError, match="internal defect"):
        _continuation_admitted(monkeypatch, SimpleNamespace(validation_context=lambda _record: _Context()))


# --- core-F9: resolver, owner and provider boundaries ------------------------


def test_v1_control_resolver_failure_logs_only_raes_frames(caplog: pytest.LogCaptureFixture) -> None:
    installed = SimpleNamespace(resolver=SimpleNamespace(resolve=_raise_foreign_1678c2))

    outcome = _resolve(SimpleNamespace(_snapshot=RuntimeSnapshot()), installed, SimpleNamespace(intent=None), "x", ())

    assert outcome.reason_code == "control-unresolved"
    _single_foreign(caplog, "raes_runtime.participant_control_orchestration")


def test_v1_resolver_request_failure_logs_only_raes_frames(caplog: pytest.LogCaptureFixture) -> None:
    from raes_runtime.participant_control_binding import ParticipantControlResolution

    resolution = ParticipantControlResolution(SimpleNamespace(model_dump=_raise_foreign_1678c2), (), "permit", None)
    installed = SimpleNamespace(resolver=SimpleNamespace(resolve=lambda **_coordinates: resolution))

    outcome = _resolve(SimpleNamespace(_snapshot=RuntimeSnapshot()), installed, SimpleNamespace(intent=None), "x", ())

    assert outcome.reason_code == "control-unresolved"
    _single_foreign(caplog, "raes_runtime.participant_control_orchestration")


def test_v1_context_resolver_failure_is_logged_once(
    caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    installed = control_binding()
    monkeypatch.setattr(installed.resolver, "validation_context", _raise_foreign_1678c2)
    plane = _plane(installed)

    admit(plane, idempotency_key="cycle2-v1-context")

    assert plane.audit_log()[-1].reason == "control-context-invalid"
    _single_foreign(caplog, "raes_runtime.participant_control_binding")


def test_v1_malformed_resolver_support_is_isolated(
    caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    installed = control_binding()
    original = installed.resolver.resolve

    def resolve(**coordinates: object) -> object:
        return replace(original(**coordinates), support=(SimpleNamespace(),))

    monkeypatch.setattr(installed.resolver, "resolve", resolve)
    plane = _plane(installed)

    admit(plane, idempotency_key="cycle2-v1-support")

    assert plane.audit_log()[-1].reason == "control-context-invalid"
    _single_foreign(caplog, "raes_runtime.participant_control_orchestration")


def test_v2_resolver_failure_logs_only_raes_frames(
    caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    _fake_cut(monkeypatch)
    installed = SimpleNamespace(resolver=SimpleNamespace(resolve=_raise_foreign_1678c2))
    crossing = SimpleNamespace(record=None, intent=SimpleNamespace(participant_address="participant"))

    outcome = evaluation_v2.resolve_v2_outcome(SimpleNamespace(_snapshot=RuntimeSnapshot()), installed, crossing, "x")

    assert outcome.reason_code == "control-context-invalid"
    _single_foreign(caplog, "raes_runtime.participant_control_binding")


def _v2_admission(owner: Resolver, key: str) -> object:
    plane = _plane(binding(owner))
    admit(plane, idempotency_key=key)
    return plane


def test_v2_context_resolver_failure_is_logged_once(
    caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner = Resolver()
    monkeypatch.setattr(owner, "validation_context", _raise_foreign_1678c2)

    plane = _v2_admission(owner, "cycle2-v2-context")

    assert plane.audit_log()[-1].reason == "control-context-invalid"
    _single_foreign(caplog, "raes_runtime.participant_control_binding")


def test_v2_trusted_callback_failure_is_logged_once(
    caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner = Resolver()
    original = owner.validation_context
    monkeypatch.setattr(
        owner,
        "validation_context",
        lambda evaluation: replace(original(evaluation), support_resolver=_raise_foreign_1678c2),
    )

    plane = _v2_admission(owner, "cycle2-v2-callback")

    assert plane.audit_log()[-1].reason == "control-context-invalid"
    _single_foreign(caplog, "raes_contracts._host_isolation")


def test_v2_first_party_defect_is_not_reported_as_a_refusal(monkeypatch: pytest.MonkeyPatch) -> None:
    def defect(*_args: object) -> None:
        raise KeyError("internal defect")

    monkeypatch.setattr(evaluation_v2, "validate_control_support_v2", defect)

    with pytest.raises(KeyError, match="internal defect"):
        _v2_admission(Resolver(), "cycle2-v2-defect")


def test_v2_projection_resolver_failure_logs_only_raes_frames(
    caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner = Resolver()
    monkeypatch.setattr(owner, "projection", _raise_foreign_1678c2)

    _v2_admission(owner, "cycle2-v2-projection")

    records = _failure_records(caplog)
    assert "raes_runtime.participant_control_evaluation_v2" in {item.name for item in records}
    for record in records:
        _assert_foreign(record)


def test_effect_operation_resolver_failure_logs_only_raes_frames(caplog: pytest.LogCaptureFixture) -> None:
    installed = SimpleNamespace(resolver=SimpleNamespace(effect_operation=_raise_foreign_1678c2))
    evaluation = SimpleNamespace(request=SimpleNamespace(context=None))

    assert _effect_operation(SimpleNamespace(), installed, evaluation, object()) is None
    _single_foreign(caplog, "raes_runtime.participant_control_effects")


def test_flow_sink_resolver_failure_logs_only_raes_frames(caplog: pytest.LogCaptureFixture) -> None:
    plane = SimpleNamespace(_snapshot=RuntimeSnapshot())

    decision = _resolve_flow_sink_relation(plane, SimpleNamespace(intent=None), _raise_foreign_1678c2, "x", ())

    assert decision.reason_code == "flow-sink-unresolved"
    _single_foreign(caplog, "raes_runtime.participant_flow_sink")


def test_inject_resolver_failure_refusal_carries_no_foreign_exception(caplog: pytest.LogCaptureFixture) -> None:
    from contextlib import nullcontext

    plane = SimpleNamespace(
        _mutation_authority=SimpleNamespace(external_call=nullcontext),
        _execution_adapter=SimpleNamespace(call=lambda *_args, **_kwargs: _raise_foreign_1678c2()),
        _inject_delivery=SimpleNamespace(resolver=SimpleNamespace(resolve_delivery=_raise_foreign_1678c2)),
        _snapshot=RuntimeSnapshot(),
        _supervision=SimpleNamespace(admission_ms=1000),
    )

    with pytest.raises(ConflictError) as raised:
        _resolve_delivery(plane, object(), object(), object())

    _assert_no_foreign_chain(raised.value)
    _single_foreign(caplog, "raes_runtime.participant_inject_application")


def test_inject_resolver_content_failure_carries_no_foreign_exception(caplog: pytest.LogCaptureFixture) -> None:
    with pytest.raises(InvalidInputError) as raised:
        require_projected_inject(object(), object(), SimpleNamespace(model_dump=_raise_foreign_type_1678c2), object())

    _assert_no_foreign_chain(raised.value)
    _single_foreign(caplog, "raes_runtime.participant_inject_application", logging.WARNING)


def test_inject_resolver_cut_failure_carries_no_foreign_exception(caplog: pytest.LogCaptureFixture) -> None:
    resolution = SimpleNamespace(cut=SimpleNamespace(model_dump=_raise_foreign_type_1678c2))

    with pytest.raises(InvalidInputError) as raised:
        _projection_cut(resolution)

    _assert_no_foreign_chain(raised.value)
    _single_foreign(caplog, "raes_runtime.participant_inject_application", logging.WARNING)


@pytest.mark.parametrize("failure", [_raise_foreign_1678c2, ConflictError("owner refused")])
def test_inject_live_cut_owner_failure_carries_no_foreign_exception(
    caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch, failure: object
) -> None:
    def owner(*_args: object) -> object:
        if isinstance(failure, BaseException):
            raise failure
        return failure()

    monkeypatch.setattr(inject_control, "resolve_owner_cut", owner)
    plane = SimpleNamespace(_mixed_control=SimpleNamespace(resolver=SimpleNamespace(resolve_delivery_cut=owner)))

    with pytest.raises(ConflictError, match="live control cut is unavailable") as raised:
        inject_control._resolve_live_cut(plane, object(), object())

    assert raised.value.__context__ is None
    if isinstance(failure, BaseException):
        assert _failure_records(caplog) == []
    else:
        _single_foreign(caplog, "raes_runtime.participant_inject_control")


# --- core-F10: malformed retained records -----------------------------------


_PARTICIPANT_ACTION = SimpleNamespace(
    receipt=SimpleNamespace(context=SimpleNamespace(operation_kind=SimpleNamespace(value="participant-action")))
)


@pytest.mark.parametrize(
    "admission",
    [{"policy": {}}, ["policy", "cut"], "policy", {"policy": {}, "cut": {}, "extra": {}}],
    ids=["missing-field", "wrong-container", "string", "extra-field"],
)
def test_malformed_retained_admission_is_an_integrity_refusal(admission: object) -> None:
    with pytest.raises(EvidenceIntegrityError, match="admission evidence is unverifiable") as raised:
        _archived_policy(_PARTICIPANT_ACTION, admission)

    # The shape check refuses the record before a field reader runs.
    assert raised.value.__cause__ is None


@pytest.mark.parametrize("admissions", [5, {"policy": {}, "cut": {}}, "admissions"])
def test_malformed_retained_admission_list_is_an_integrity_refusal(
    monkeypatch: pytest.MonkeyPatch, admissions: object
) -> None:
    record = SimpleNamespace(
        status=SimpleNamespace(state=OperationState.SUCCEEDED),
        result_payload={"mixed_control_episode_admissions": admissions},
    )
    monkeypatch.setattr(
        operation_index, "operation_index", lambda _plane: SimpleNamespace(policy_records={"r": record})
    )

    with pytest.raises(EvidenceIntegrityError, match="admission evidence is unverifiable"):
        archived_policies(SimpleNamespace(), "participant")


@pytest.mark.parametrize("payload", ["record", ["event_id"], 7])
def test_non_mapping_retained_occurrence_is_an_integrity_refusal(payload: object) -> None:
    with pytest.raises(EvidenceIntegrityError, match="retained participant history does not validate"):
        _retained_record(parse_participant_control_occurrence, payload)


_TARGET = {
    "target_kind": "action",
    "target_ref": "action-1",
    "target_revision": 1,
    "participant_address": "participant",
    "episode_id": "episode-1",
    "available_at": 0,
}


@pytest.mark.parametrize(
    "targets",
    [
        [{key: value for key, value in _TARGET.items() if key != "participant_address"}],
        [{key: value for key, value in _TARGET.items() if key != "available_at"}],
        [{**_TARGET, "unexpected": "field"}],
        ["target"],
        [7],
        "targets",
        5,
    ],
    ids=["missing-address", "missing-coordinate", "extra-field", "string-entry", "int-entry", "string-list", "int"],
)
def test_malformed_retained_target_is_an_integrity_refusal(monkeypatch: pytest.MonkeyPatch, targets: object) -> None:
    record = SimpleNamespace(
        status=SimpleNamespace(state=OperationState.SUCCEEDED),
        result_payload={"participant_control_available_targets": targets, "participant_control_occurrence_ref": "e"},
    )
    monkeypatch.setattr(
        operation_index, "operation_index", lambda _plane: SimpleNamespace(target_records={"r": record})
    )
    plane = SimpleNamespace(_snapshot=SimpleNamespace(participant_control_history={}))

    with pytest.raises(EvidenceIntegrityError, match="not bound to its committed control cut"):
        archived_control_targets(plane, "participant")


# --- core-F12: the backend autonomous binding callback -----------------------


def _binding_context(bind: object) -> SimpleNamespace:
    policy = SimpleNamespace(
        observation_boundary_address="boundary",
        participant_implementation_ref="manifest",
        execution_bindings=(),
    )
    return SimpleNamespace(
        policy=policy,
        participant_address="participant",
        participant_runtime=SimpleNamespace(bind_autonomous_action=bind),
    )


@pytest.mark.parametrize("bind", [_raise_foreign_1678c2, _raise_foreign_type_1678c2])
def test_backend_binding_failure_is_not_a_domain_refusal(caplog: pytest.LogCaptureFixture, bind: object) -> None:
    with pytest.raises(OperationalError) as raised:
        _bound_runtime_request(_binding_context(bind), RuntimeSnapshot(), None, "action", "attempt", (), False)

    assert not isinstance(raised.value, InvalidInputError)
    _assert_no_foreign_chain(raised.value)
    _single_foreign(caplog, "raes_runtime.participant_scheduler_binding")


def test_backend_binding_returning_a_non_request_is_a_contract_refusal() -> None:
    with pytest.raises(InvalidInputError, match="does not satisfy its contract"):
        _bound_runtime_request(_binding_context(lambda *_args: object()), RuntimeSnapshot(), None, "a", "b", (), False)


def test_serial_backend_binding_failure_settles_with_its_own_diagnostic(monkeypatch: pytest.MonkeyPatch) -> None:
    def failed(*_args: object) -> object:
        raise OperationalError("backend autonomous action binding did not complete")

    monkeypatch.setattr(scheduler_operations, "_bound_action_request", failed)
    run = SimpleNamespace(working=RuntimeSnapshot(), diagnostics=[], failure=None)

    assert scheduler_operations._try_bound_action_request(_binding_context(None), object(), run) is None
    assert run.diagnostics[-1].code == "runtime.participant-autonomous-binding-failed"
    assert run.failure is not None


# --- contracts, conformance and processor host isolation ----------------------


@pytest.mark.parametrize("keep_cause", [True, False])
def test_host_isolation_failure_carries_no_foreign_exception(
    caplog: pytest.LogCaptureFixture, keep_cause: bool
) -> None:
    with pytest.raises(ValueError, match="^refused$") as raised, isolated_host_call("refused", keep_cause=keep_cause):
        _raise_foreign_1678c2()

    _assert_no_foreign_chain(raised.value)
    _single_foreign(caplog, "raes_contracts._host_isolation")


def test_host_isolation_dependency_failure_carries_no_foreign_exception(caplog: pytest.LogCaptureFixture) -> None:
    def dependency() -> None:
        try:
            raise OSError(_SENTINEL)
        except OSError as cause:
            raise OperationalError("host dependency failed") from cause

    with pytest.raises(ValueError, match="^refused$") as raised, isolated_host_call("refused"):
        dependency()

    _assert_no_foreign_chain(raised.value)
    _single_foreign(caplog, "raes_contracts._host_isolation", logging.WARNING)


def test_host_isolation_refusal_keeps_its_contract(caplog: pytest.LogCaptureFixture) -> None:
    with pytest.raises(ValueError, match="^refused$") as raised, isolated_host_call("refused"):
        raise ConflictError(_SENTINEL)

    assert isinstance(raised.value.__cause__, ConflictError)
    assert _failure_records(caplog) == []


def test_flow_control_trusted_context_failure_carries_no_foreign_exception(caplog: pytest.LogCaptureFixture) -> None:
    from dataclasses import fields

    from raes_contracts.contracts.participant_flow_control_context import ParticipantFlowControlValidationContext
    from raes_contracts.contracts.participant_flow_control_validation import (
        validate_participant_flow_control_resolved_context,
    )

    empty = {item.name: () for item in fields(ParticipantFlowControlValidationContext) if item.init}
    context = ParticipantFlowControlValidationContext(**empty)

    with pytest.raises(ValueError, match="context validation failed") as raised:
        validate_participant_flow_control_resolved_context(object(), lambda *_: context)

    assert raised.value.__context__ is None
    _single_foreign(caplog, "raes_contracts.contracts.participant_flow_control_validation")


def test_information_state_malformed_context_carries_no_foreign_exception(caplog: pytest.LogCaptureFixture) -> None:
    from raes_contracts.contracts.participant_information_state import (
        ParticipantInformationStateValidationContext,
        validate_participant_information_state_resolved_context,
    )

    context = ParticipantInformationStateValidationContext(
        occurrence_histories={}, resolved_sources={}, source_coordinates={}, proof_digests={}
    )
    record = SimpleNamespace(reconstruction_profile_ref=None)

    with pytest.raises(ValueError, match="resolved context is malformed") as raised:
        validate_participant_information_state_resolved_context(record, lambda *_: context)

    assert raised.value.__cause__ is None
    assert raised.value.__context__ is None
    _single_foreign(caplog, "raes_contracts.contracts.participant_information_state")


def test_control_context_asset_host_failure_logs_only_raes_frames(
    caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    import raes_conformance.conformance.control_context_assets as assets

    monkeypatch.setattr(assets, "ParticipantControlContextRecordModel", SimpleNamespace(model_validate=lambda p: p))
    monkeypatch.setattr(assets, "validate_control_context_record", _raise_foreign_1678c2)

    diagnostics = assets._control_context_asset_diagnostics(
        "participant-control-context-record-v1", {}, SimpleNamespace(content_binding=None)
    )

    assert diagnostics[0].code == "conformance.context-resolution-failed"
    _single_foreign(caplog, "raes_conformance.conformance.control_context_assets")


_PROJECTION = SimpleNamespace(
    projection_policy_ref="p",
    participant_address="a",
    audience_scope_ref="s",
    implementation_selection_ref="i",
    exposure_policy_ref="e",
    decision_cut_ref="c",
)


def _exposure_calls() -> list[object]:
    from raes_processor.models import participant_exposure, participant_exposure_policy, participant_exposure_v2

    policy, v2 = participant_exposure_policy, participant_exposure_v2
    resolvers = SimpleNamespace(
        projection_policy=_raise_foreign_1678c2,
        apparatus=_raise_foreign_1678c2,
        authorization=_raise_foreign_1678c2,
        occurrence=_raise_foreign_1678c2,
    )
    assessment = SimpleNamespace(realization=SimpleNamespace(occurrence_ref="o"))
    return [
        lambda: policy._resolve_authorization(
            authorization_record_ref="a", item_ref="i", resolver=_raise_foreign_1678c2
        ),
        lambda: policy._resolved_projection_policy_revisions(_PROJECTION, _raise_foreign_1678c2),
        lambda: policy._selected_exposure_policy(_PROJECTION, _raise_foreign_1678c2, observation_order=1),
        lambda: v2._resolve_policy_decision(_PROJECTION, resolvers),
        lambda: v2._selected_exposure_policy(_PROJECTION, resolvers),
        lambda: v2._resolve_authorization(_PROJECTION, item_ref="i", authorization_record_ref="a", resolvers=resolvers),
        lambda: participant_exposure._resolve_occurrence(assessment, _PROJECTION, resolvers),
    ]


@pytest.mark.parametrize("index", range(7))
def test_exposure_resolver_failure_carries_no_foreign_exception(caplog: pytest.LogCaptureFixture, index: int) -> None:
    with pytest.raises(OperationalError, match="resolution failed") as raised:
        _exposure_calls()[index]()

    _assert_no_foreign_chain(raised.value)
    _single_foreign(caplog, "raes_processor.models.participant_exposure_policy")


# --- Installed cut owner refusals and augmentation composition -----------------


@pytest.mark.parametrize(
    ("refusal", "category"), [(PermissionError, "AuthorizationError"), (ValueError, "ConflictError")]
)
def test_owner_cut_refusal_chains_only_the_foreign_record(refusal: type[Exception], category: str) -> None:
    from raes_contracts.errors import RaesError
    from raes_contracts.operational_logging import describe_exception
    from raes_runtime.participant_control_runtime import resolve_owner_cut
    from test_issue_1678_sweep_r2 import _cut_plane

    owner_refusal = type("OwnerOnlyRefusal1678c2", (refusal,), {})

    def owner(*_args: object) -> object:
        raise owner_refusal(_SENTINEL)

    with pytest.raises(RaesError) as raised:
        resolve_owner_cut(_cut_plane(None), object(), object(), owner)

    assert type(raised.value).__name__ == category
    described = describe_exception(raised.value)
    assert "ForeignCodeFailure" in described
    assert "OwnerOnlyRefusal1678c2" not in described
    assert _SENTINEL not in described


def test_augmentation_composition_failure_logs_only_raes_frames(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    import raes_runtime.backend_augmentation as augmentation

    monkeypatch.setattr(augmentation, "compose_augmentation_admission", _raise_foreign_1678c2)
    context = SimpleNamespace(augmentation=SimpleNamespace(is_valid=True), operation_plan=object())

    returned, diagnostics = augmentation.compose_augmentation_invocation(context, object(), None)

    assert returned is context
    assert [item.code for item in diagnostics] == ["augmentation.composition-invalid"]
    _single_foreign(caplog, "raes_runtime.backend_augmentation")
