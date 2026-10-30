"""Issue 1678 sweep R2: participant runtime refusals that narrowed handlers keep (ADR-116).

Each regression test fails without its fix. Retained state that a restored store
holds as opaque legacy data and a live cut that an installed owner cannot serialize
are input. The operation refuses them with a category, so the control-plane API
keeps its 409 refusal, episode admission keeps its unverified outcome and an effect
owner keeps its failed outcome. Unrelated defects still propagate, and no refusal
message, response or log record discloses a value from the rejected input.
"""

from __future__ import annotations

import logging
from contextlib import nullcontext
from dataclasses import replace
from types import SimpleNamespace

import participant_crossing_fixtures as crossing
import participant_inject_runtime_fixtures as inject_fixtures
import pytest
import raes_runtime.participant_control_effects as control_effects
import raes_runtime.participant_control_targets as control_targets
from pydantic_core import PydanticSerializationError
from raes_backend_stubs.stubs import create_stub_target
from raes_contracts.errors import ConflictError, EvidenceIntegrityError, InvalidInputError
from raes_contracts.evaluation import EvaluationExecutionState
from raes_runtime.control_plane import RuntimeControlPlane
from raes_runtime.control_plane_api import create_control_plane_app
from raes_runtime.control_plane_api._responses import _refusal
from raes_runtime.control_plane_security import ControlPlaneIdentity, ControlPlaneRole, ControlPlaneSecurityConfig
from raes_runtime.participant_control import ParticipantProposalControlIntent
from raes_runtime.participant_control_runtime import (
    CONTROL_CUT_REFUSALS,
    ParticipantControlLiveCut,
    resolve_owner_cut,
)
from reusable_control_runtime_fixtures import PARTICIPANT as POLICY_PARTICIPANT
from reusable_control_runtime_fixtures import CutOwner, configured_plane, handoff
from reusable_control_runtime_fixtures import identity as policy_identity
from starlette.testclient import TestClient
from test_run_310_supervisory_lifecycle import (
    _PARTICIPANT,
    _SPEC_ADDRESS,
    _api_security,
    _base_intent_fields,
    _compiled_specification,
    _identity,
    _proposal_body,
)

_SENTINEL = "value-sentinel-1678-sweep-r2"
_OTHER = "participant.behavior.other-agent"


def _seed(plane: RuntimeControlPlane, **histories: object) -> None:
    """Store retained history directly, as a restored or shared store holds it."""

    snapshot = plane.snapshot.with_entries(dict(plane.snapshot.entries), **histories)
    plane._store.save_snapshot(snapshot, expected_revision=plane._store.load_snapshot_state().revision)
    plane._reload_derived_state()


def _assert_value_free(caplog: pytest.LogCaptureFixture, *texts: str) -> None:
    for text in (*texts, *(record.getMessage() for record in caplog.records)):
        assert _SENTINEL not in text
    for record in caplog.records:
        assert _SENTINEL not in (record.exc_text or "")


class _UnserializableCutOwner(CutOwner):
    """An installed owner that returns a live cut whose order cannot serialize."""

    broken: bool = True

    def resolve_cut(self, policy, intent, snapshot):
        cut = super().resolve_cut(policy, intent, snapshot)
        if not self.broken:
            return cut
        return ParticipantControlLiveCut.model_construct(**{**dict(cut), "effective_order": object()})


def _cut_plane(cut: object) -> SimpleNamespace:
    return SimpleNamespace(
        _snapshot_state=SimpleNamespace(revision=1),
        _mutation_authority=SimpleNamespace(external_call=nullcontext),
        _execution_adapter=SimpleNamespace(call=lambda _lane, method, *args, timeout_ms: method(*args)),
        _supervision=SimpleNamespace(admission_ms=1000),
        _snapshot=object(),
        _reload_derived_state=lambda: None,
    )


def _unserializable_cut() -> ParticipantControlLiveCut:
    return ParticipantControlLiveCut.model_construct(
        request_ref="request-1",
        effective_order=object(),
        active_authority_basis_refs=[],
        authorized_scope_refs=[],
        evidence_refs=("evidence:1",),
    )


def test_owner_cut_that_does_not_serialize_is_an_invalid_owner_cut() -> None:
    cut = _unserializable_cut()

    cut_plane = _cut_plane(cut)
    policy = object()
    request = object()
    with pytest.raises(InvalidInputError, match="owner returned an invalid live cut") as raised:
        resolve_owner_cut(cut_plane, policy, request, lambda *_args: cut)

    assert isinstance(raised.value, CONTROL_CUT_REFUSALS)
    assert isinstance(raised.value.__cause__, PydanticSerializationError)


def test_owner_cut_revalidation_defect_still_propagates(monkeypatch: pytest.MonkeyPatch) -> None:
    def defect(_payload: object) -> ParticipantControlLiveCut:
        raise KeyError(_SENTINEL)

    monkeypatch.setattr(ParticipantControlLiveCut, "model_validate", defect)
    cut = ParticipantControlLiveCut(
        request_ref="request-1",
        effective_order=1,
        active_authority_basis_refs=[],
        authorized_scope_refs=[],
        evidence_refs=("evidence:1",),
    )

    cut_plane = _cut_plane(cut)
    policy = object()
    request = object()
    with pytest.raises(KeyError):
        resolve_owner_cut(cut_plane, policy, request, lambda *_args: cut)


def test_episode_admission_keeps_its_unverified_outcome_for_an_unserializable_owner_cut() -> None:
    plane, _ = configured_plane(owner=_UnserializableCutOwner())
    with plane:
        receipt = plane.initialize_participant_episode(
            POLICY_PARTICIPANT, episode_id="episode-1", identity=policy_identity()
        )
        status = plane.get_operation(receipt.operation_id, identity=policy_identity())

    assert status.state.value == "failed"
    assert status.diagnostics[0].code == "runtime.participant-control.admission-unverified"


def test_policy_application_refuses_an_unserializable_owner_cut_as_invalid_input() -> None:
    owner = _UnserializableCutOwner()
    owner.broken = False
    plane, _ = configured_plane(owner=owner)
    with plane:
        plane.initialize_participant_episode(POLICY_PARTICIPANT, episode_id="episode-1", identity=policy_identity())
        owner.broken = True
        intent = handoff(plane, owner, "take", revision=0, head=0, order=1, key="take")

        identity = policy_identity()
        with pytest.raises(InvalidInputError) as raised:
            plane.record_participant_control(POLICY_PARTICIPANT, intent, identity=identity, idempotency_key="take")
        history = plane.snapshot.participant_control_history.get(POLICY_PARTICIPANT, ())

    assert _refusal(raised.value).status_code == 409
    assert not history


def _supervisory_plane() -> RuntimeControlPlane:
    return RuntimeControlPlane(
        create_stub_target(),
        behavior_specifications={_SPEC_ADDRESS: _compiled_specification()},
    )


def _proposal() -> ParticipantProposalControlIntent:
    return ParticipantProposalControlIntent(
        **_base_intent_fields("proposal", 0),
        proposal_id="proposal-1",
        proposal_revision=1,
        action_contract_ref="action-contract:contain-host",
        payload_ref="payload:proposal-1",
    )


_LEGACY_RETAINED_HISTORY = {
    "own-control-record": {
        "participant_control_history": {
            _PARTICIPANT: [{"event_id": "legacy-1", "schema_version": "1.0.0", "participant_address": _PARTICIPANT}]
        }
    },
    "other-control-record": {
        "participant_control_history": {
            _OTHER: [{"event_id": "legacy-1", "schema_version": "1.0.0", "participant_address": _OTHER}]
        }
    },
    "other-behavior-record": {
        "participant_behavior_history": {_OTHER: [{"event_type": "action_attempted", "participant_address": _OTHER}]}
    },
}


def _with_secret(histories: dict[str, dict[str, list[dict[str, object]]]]) -> dict[str, object]:
    return {
        field: {
            participant: [{**record, "note": _SENTINEL} for record in records]
            for participant, records in values.items()
        }
        for field, values in histories.items()
    }


@pytest.mark.parametrize("retained", sorted(_LEGACY_RETAINED_HISTORY))
def test_legacy_retained_record_refuses_supervisory_control_as_an_integrity_failure(
    retained: str, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    plane = _supervisory_plane()
    try:
        _seed(plane, **_with_secret(_LEGACY_RETAINED_HISTORY[retained]))

        proposal = _proposal()
        identity = _identity()
        with pytest.raises(EvidenceIntegrityError) as raised:
            plane.record_participant_control(_PARTICIPANT, proposal, identity=identity)
        with TestClient(create_control_plane_app(plane, security=_api_security())) as client:
            response = client.post(
                f"/participants/{_PARTICIPANT}/control-occurrences",
                json=_proposal_body(),
                headers={"authorization": "Bearer operator-token", "idempotency-key": "key-1"},
            )
            committed = [
                record
                for record in plane.snapshot.participant_control_history.get(_PARTICIPANT, ())
                if record.get("event_id") != "legacy-1"
            ]
    finally:
        plane.close()

    assert response.status_code == 409
    assert response.json() == {"detail": "control intent conflicts with runtime state"}
    assert not committed
    _assert_value_free(caplog, str(raised.value), response.text)


def test_control_target_registration_defect_still_propagates(monkeypatch: pytest.MonkeyPatch) -> None:
    plane = _supervisory_plane()
    try:
        plane.record_participant_control(_PARTICIPANT, _proposal(), identity=_identity())

        def defect(*_args: object, **_kwargs: object) -> None:
            raise ValueError(_SENTINEL)

        monkeypatch.setattr(control_targets, "_register", defect)
        proposal = _proposal()
        identity = _identity()
        with pytest.raises(ValueError, match=_SENTINEL):
            plane.record_participant_control(_PARTICIPANT, proposal, identity=identity)
    finally:
        plane.close()


def test_legacy_retained_crossing_record_refuses_a_crossing_as_an_integrity_failure(
    caplog: pytest.LogCaptureFixture,
) -> None:
    plane = crossing.action_plane(crossing.StaticCrossingResolver())
    try:
        legacy = {"event_id": "legacy-crossing", "participant_address": _OTHER, "note": _SENTINEL}
        _seed(plane, participant_crossing_history={**plane.snapshot.participant_crossing_history, _OTHER: [legacy]})

        with pytest.raises(EvidenceIntegrityError) as raised:
            crossing.admit(plane)
        history = plane.snapshot.participant_crossing_history.get(crossing.PARTICIPANT, ())
    finally:
        plane.close()

    assert _refusal(raised.value).status_code == 409
    assert not history
    _assert_value_free(caplog, str(raised.value))


def _policy_plane_with_legacy_control_record() -> tuple[RuntimeControlPlane, CutOwner]:
    plane, owner = configured_plane()
    plane.initialize_participant_episode(POLICY_PARTICIPANT, episode_id="episode-1", identity=policy_identity())
    legacy = {"event_id": "legacy-1", "schema_version": "1.0.0", "participant_address": _OTHER, "note": _SENTINEL}
    _seed(plane, participant_control_history={**plane.snapshot.participant_control_history, _OTHER: [legacy]})
    return plane, owner


def test_legacy_retained_control_record_refuses_a_policy_application_as_an_integrity_failure(
    caplog: pytest.LogCaptureFixture,
) -> None:
    plane, owner = _policy_plane_with_legacy_control_record()
    with plane:
        intent = handoff(plane, owner, "take", revision=0, head=0, order=1, key="take")

        identity = policy_identity()
        with pytest.raises(EvidenceIntegrityError) as raised:
            plane.record_participant_control(POLICY_PARTICIPANT, intent, identity=identity, idempotency_key="take")
        history = plane.snapshot.participant_control_history.get(POLICY_PARTICIPANT, ())

    assert _refusal(raised.value).status_code == 409
    assert not history
    _assert_value_free(caplog, str(raised.value))


def test_effect_owner_refusal_of_legacy_retained_history_fails_the_effect(monkeypatch: pytest.MonkeyPatch) -> None:
    plane, owner = _policy_plane_with_legacy_control_record()
    with plane:
        intent = handoff(plane, owner, "take", revision=0, head=0, order=1, key="take")

        def submit(*_args: object, **_kwargs: object) -> None:
            plane.record_participant_control(
                POLICY_PARTICIPANT, intent, identity=policy_identity(), idempotency_key="take"
            )

        monkeypatch.setattr(control_effects, "owner_record", lambda *_args: None)
        monkeypatch.setattr(control_effects, "_submit", submit)
        claim = SimpleNamespace(receipt=SimpleNamespace(operation_id="claim-1"))

        outcome = control_effects._submitted_outcome(plane, claim, object(), object(), principal=object())

    assert outcome == "failed"


def test_effect_owner_defect_still_propagates(monkeypatch: pytest.MonkeyPatch) -> None:
    def defect(*_args: object, **_kwargs: object) -> None:
        raise ValueError(_SENTINEL)

    monkeypatch.setattr(control_effects, "owner_record", lambda *_args: None)
    monkeypatch.setattr(control_effects, "_submit", defect)
    claim = SimpleNamespace(receipt=SimpleNamespace(operation_id="claim-1"))

    with pytest.raises(ValueError, match=_SENTINEL):
        control_effects._submitted_outcome(object(), claim, object(), object(), principal=object())


_VIEW_PARTICIPANT = "participant.alice"


def _view_plane_with(field: str, retained: object) -> RuntimeControlPlane:
    plane = RuntimeControlPlane(create_stub_target())
    plane.initialize_participant_episode(_VIEW_PARTICIPANT, episode_id="episode-1")
    _seed(plane, **{field: {**getattr(plane.snapshot, field), _VIEW_PARTICIPANT: retained}})
    return plane


_LEGACY_VIEW_STATE = {
    "status": (
        "participant_episode_results",
        {"episode_id": "episode-1", "status": "running", "note": _SENTINEL},
    ),
    "history": (
        "participant_behavior_history",
        [{"event_type": "legacy", "episode_id": "episode-1", "note": _SENTINEL}],
    ),
}


@pytest.mark.parametrize("view", sorted(_LEGACY_VIEW_STATE))
def test_legacy_retained_state_refuses_a_participant_view_as_an_integrity_failure(
    view: str, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    plane = _view_plane_with(*_LEGACY_VIEW_STATE[view])
    read = {
        "status": lambda: plane.get_participant_status_view(_VIEW_PARTICIPANT),
        "history": lambda: plane.get_participant_history_view(_VIEW_PARTICIPANT, "episode-1"),
    }[view]
    path = {
        "status": f"/participants/{_VIEW_PARTICIPANT}/status",
        "history": f"/participants/{_VIEW_PARTICIPANT}/episodes/episode-1/history",
    }[view]
    operator = ControlPlaneIdentity(
        identity="operator", roles=frozenset({ControlPlaneRole.OPERATOR}), target_name="stub"
    )
    security = ControlPlaneSecurityConfig(bearer_tokens={"operator-token": operator})
    try:
        with pytest.raises(EvidenceIntegrityError) as raised:
            read()
        with TestClient(create_control_plane_app(plane, security=security)) as client:
            response = client.get(path, headers={"authorization": "Bearer operator-token"})
    finally:
        plane.close()

    assert response.status_code == 409
    assert response.json() == {"detail": "participant projection conflict"}
    _assert_value_free(caplog, str(raised.value), response.text)


_BINDING_REJECTED = "runtime.participant-binding.rejected"


def _rejected_binding_message(receipt: object) -> str:
    assert receipt.accepted is False
    assert all(_SENTINEL not in item.message for item in receipt.diagnostics)
    (diagnostic,) = [item for item in receipt.diagnostics if item.code == _BINDING_REJECTED]
    return diagnostic.message


def test_admission_field_refusal_diagnostic_omits_the_rejected_field() -> None:
    plane = RuntimeControlPlane(create_stub_target())
    request = crossing.admission_request()
    try:
        receipt = plane.admit_participant_action(
            crossing.behavior(),
            implementation_manifest=request.implementation_manifest,
            implementation_selection=request.implementation_selection,
            action_contract_address=request.action_contract_address,
            observation_boundary_address=request.observation_boundary_address,
            action_instance_id=request.action_instance_id,
            evidence_refs=request.evidence_refs,
            **{_SENTINEL: "unknown field"},
        )
    finally:
        plane.close()

    message = _rejected_binding_message(receipt)
    assert message == "The admission fields do not satisfy the participant action admission contract."


def _patch_decision_surface_binding(monkeypatch: pytest.MonkeyPatch, version: str, binding: object) -> None:
    if version == "v1":
        monkeypatch.setattr("raes_runtime.participant_control.bind_participant_decision_surface_selection", binding)
        return
    module = "raes_runtime.participant_decision_surface_control_v2"
    monkeypatch.setattr(f"{module}.validate_participant_decision_surface_v2_anchor", lambda *_args: None)
    monkeypatch.setattr(f"{module}.bind_participant_decision_surface_selection_v2", binding)


def _admit_decision_surface(plane: RuntimeControlPlane, version: str) -> object:
    admit = (
        plane.admit_participant_decision_surface_selection
        if version == "v1"
        else plane.admit_participant_decision_surface_selection_v2
    )
    return admit(
        crossing.behavior(),
        surface=object(),
        selection=object(),
        admission_request=crossing.admission_request(),
        resolvers=SimpleNamespace(argument_shape=None, apparatus=None, delivery=None),
    )


@pytest.mark.parametrize("version", ["v1", "v2"])
def test_decision_surface_refusal_diagnostic_omits_the_refusal_text(
    version: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    def refuse(*_args: object, **_kwargs: object) -> None:
        raise ValueError(_SENTINEL)

    _patch_decision_surface_binding(monkeypatch, version, refuse)
    plane = RuntimeControlPlane(create_stub_target())
    try:
        receipt = _admit_decision_surface(plane, version)
    finally:
        plane.close()

    assert _rejected_binding_message(receipt)


@pytest.mark.parametrize("version", ["v1", "v2"])
def test_decision_surface_binding_defect_still_propagates(version: str, monkeypatch: pytest.MonkeyPatch) -> None:
    def defect(*_args: object, **_kwargs: object) -> None:
        raise TypeError(_SENTINEL)

    _patch_decision_surface_binding(monkeypatch, version, defect)
    plane = RuntimeControlPlane(create_stub_target())
    try:
        with pytest.raises(TypeError, match=_SENTINEL):
            _admit_decision_surface(plane, version)
    finally:
        plane.close()


# Area R1 findings: input-caused failures that keep their pre-branch refusal (ADR-116).


def test_installed_delivery_spec_outside_the_canonical_domain_keeps_its_refusals(tmp_path) -> None:
    plane, _backend, _, request = inject_fixtures.configured_plane(tmp_path)
    security = ControlPlaneSecurityConfig(bearer_tokens={"test-token": inject_fixtures.caller()})
    headers = {"Authorization": "Bearer test-token"}
    body = request.model_dump(mode="json")
    with TestClient(create_control_plane_app(plane, security=security)) as client:
        first = client.post("/injects/deliver", json=body, headers=headers)
        assert first.status_code == 200, first.text
        deliveries = plane._inject_delivery.model.participant_inject_deliveries
        delivery = deliveries[request.delivery_address]
        deliveries[request.delivery_address] = replace(
            delivery, spec={**delivery.spec, "control_valid_until_order": 2**53}
        )
        read = client.get(f"/operations/{first.json()['operation_id']}/inject-delivery", headers=headers)
        retry = client.post("/injects/deliver", json=body, headers=headers)

    assert read.status_code == 404
    assert retry.status_code == 409


def test_delivery_binding_digest_defect_still_propagates(monkeypatch: pytest.MonkeyPatch) -> None:
    import raes_runtime.participant_inject_application as inject_application

    def defect(_payload: object) -> str:
        raise ValueError(_SENTINEL)

    monkeypatch.setattr(inject_application, "canonical_json_digest", defect)
    application = SimpleNamespace(delivery_address="delivery", participant_address="participant", delivery_digest="d")
    delivery = SimpleNamespace(participant_address="participant", spec={})
    plane = SimpleNamespace(
        target_name="stub",
        _inject_delivery=SimpleNamespace(model=SimpleNamespace(participant_inject_deliveries={"delivery": delivery})),
    )
    operator = ControlPlaneIdentity(
        identity="operator", roles=frozenset({ControlPlaneRole.OPERATOR}), target_name="stub"
    )

    with pytest.raises(ValueError, match=_SENTINEL):
        inject_application._authorized_binding(plane, application, operator)


_UNREPRESENTABLE_INTENT_FIELDS = {
    "empty-evidence-ref": {"evidence_refs": [""]},
    "audit-unsafe-episode": {"episode_id": "episode 1"},
}


@pytest.mark.parametrize("field", sorted(_UNREPRESENTABLE_INTENT_FIELDS))
def test_supervisory_intent_that_cannot_form_its_records_is_invalid_input(field: str) -> None:
    changes = _UNREPRESENTABLE_INTENT_FIELDS[field]
    plane = _supervisory_plane()
    try:
        intent = ParticipantProposalControlIntent(
            **{**_base_intent_fields("proposal", 0), **changes},
            proposal_id="proposal-1",
            proposal_revision=1,
            action_contract_ref="action-contract:contain-host",
            payload_ref="payload:proposal-1",
        )
        identity = _identity()
        with pytest.raises(InvalidInputError):
            plane.record_participant_control(_PARTICIPANT, intent, identity=identity)
        with TestClient(create_control_plane_app(plane, security=_api_security())) as client:
            response = client.post(
                f"/participants/{_PARTICIPANT}/control-occurrences",
                json={**_proposal_body(), **changes},
                headers={"authorization": "Bearer operator-token", "idempotency-key": "key-1"},
            )
            history = plane.snapshot.participant_control_history.get(_PARTICIPANT, ())
    finally:
        plane.close()

    assert response.status_code == 409
    assert response.json() == {"detail": "control intent conflicts with runtime state"}
    assert not history


@pytest.mark.parametrize("revision", [0, 5], ids=["accepted-candidate", "rejected-candidate"])
def test_policy_application_that_cannot_form_an_occurrence_is_invalid_input(revision: int) -> None:
    plane, owner = configured_plane()
    with plane:
        plane.initialize_participant_episode(POLICY_PARTICIPANT, episode_id="episode-1", identity=policy_identity())
        intent = handoff(plane, owner, "take", revision=revision, head=0, order=1, key="take")
        intent = intent.model_copy(update={"provenance_refs": [""]})

        identity = policy_identity()
        with pytest.raises(InvalidInputError) as raised:
            plane.record_participant_control(POLICY_PARTICIPANT, intent, identity=identity, idempotency_key="take")
        history = plane.snapshot.participant_control_history.get(POLICY_PARTICIPANT, ())

    assert _refusal(raised.value).status_code == 409
    assert not history


def test_malformed_stored_execution_service_state_reads_as_not_found() -> None:
    plane = RuntimeControlPlane(create_stub_target())
    scope = "participant.execution.scope"
    operator = ControlPlaneIdentity(
        identity="operator", roles=frozenset({ControlPlaneRole.OPERATOR}), target_name="stub"
    )
    security = ControlPlaneSecurityConfig(bearer_tokens={"operator-token": operator})
    try:
        _seed(plane, participant_execution_services={scope: {"generation": "not-a-number", "note": _SENTINEL}})
        with pytest.raises(EvidenceIntegrityError):
            plane.participant_execution_state(scope)
        with TestClient(create_control_plane_app(plane, security=security)) as client:
            response = client.get(
                f"/participant-executions/{scope}", headers={"authorization": "Bearer operator-token"}
            )
    finally:
        plane.close()

    assert response.status_code == 404
    assert _SENTINEL not in response.text


def test_view_evidence_refusal_is_recognized_by_its_type() -> None:
    from fastapi import HTTPException
    from raes_runtime.control_plane_api_participant_retrieval import _governed_view
    from raes_runtime.participant_retrieval import ParticipantViewEvidenceUnavailable

    def typed() -> object:
        raise ParticipantViewEvidenceUnavailable(_SENTINEL)

    def same_text() -> object:
        raise ConflictError("participant view crossing evidence is unavailable")

    with pytest.raises(HTTPException) as typed_refusal:
        _governed_view(typed)
    with pytest.raises(HTTPException) as other_refusal:
        _governed_view(same_text)

    assert (typed_refusal.value.status_code, typed_refusal.value.detail) == (
        409,
        "participant view crossing evidence is unavailable",
    )
    assert (other_refusal.value.status_code, other_refusal.value.detail) == (409, "participant projection conflict")


def _evaluation_state(score: int, max_score: int) -> EvaluationExecutionState:
    from raes_contracts.evaluation import EvaluationResultStatus

    return EvaluationExecutionState(
        resource_type="goal",
        run_id="run-1",
        status=EvaluationResultStatus.READY,
        observed_at="2020-01-01T00:00:00Z",
        updated_at="2020-01-01T00:00:00Z",
        score=score,
        max_score=max_score,
    )


def test_evaluation_score_beyond_the_float_range_is_compared_exactly() -> None:
    from raes_runtime.evaluation_result_contracts import _normalized_evaluation_result

    with pytest.raises(ValueError, match="may not exceed max_score"):
        _evaluation_state(10**400, 1)
    with pytest.raises(ValueError, match="may not exceed max_score"):
        _evaluation_state(2**53 + 1, 2**53)
    assert _evaluation_state(2**53, 2**53 + 1).score == 2**53
    payload = _evaluation_state(1, 1).to_payload() | {"score": 10**400}
    state, diagnostics = _normalized_evaluation_result("evaluation.goal", payload)
    assert state is None
    assert [item.message for item in diagnostics] == ["Evaluation result payload is invalid."]


def test_restored_delivery_with_a_spec_outside_the_canonical_domain_is_an_integrity_failure() -> None:
    import rfc8785
    from raes_runtime.participant_inject_control import validate_restored_inject_deliveries

    application = SimpleNamespace(delivery_address="delivery", delivery_digest="sha256:retained", control=None)
    delivery = SimpleNamespace(spec={"control_valid_until_order": 2**53})
    plane = SimpleNamespace(
        _operations={"operation": SimpleNamespace(inject_delivery=SimpleNamespace(application=application))},
        _inject_delivery=SimpleNamespace(model=SimpleNamespace(participant_inject_deliveries={"delivery": delivery})),
    )

    with pytest.raises(EvidenceIntegrityError, match="retained inject delivery binding differs") as raised:
        validate_restored_inject_deliveries(plane)

    assert isinstance(raised.value.__cause__, rfc8785.CanonicalizationError)
