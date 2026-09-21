"""Actual control-plane production and durable admission of local outcomes."""

from dataclasses import replace

import pytest
import yaml
from raes.parser import parse_sdl
from raes_backend_stubs.stubs import create_stub_target
from raes_processor.compiler import compile_runtime_model
from raes_runtime.control_plane import RuntimeControlPlane
from raes_runtime.control_plane_security import ControlPlaneIdentity, ControlPlaneRole, ParticipantControlSubjectBinding
from test_act_618_outcome_definition import local_scenario
from test_act_618_outcome_state import snapshot
from test_sem_215_participant_outcome_interpretation import EPISODE_ID, PARTICIPANT_ADDRESS, RULE_ADDRESS


def identity():
    return ControlPlaneIdentity(
        "operator",
        frozenset({ControlPlaneRole.OPERATOR}),
        "stub",
        participant_control_subjects=(ParticipantControlSubjectBinding(PARTICIPANT_ADDRESS, "controller:operator"),),
    )


def request():
    from raes_runtime.participant_outcome_control import ParticipantOutcomeUpdateRequest

    return ParticipantOutcomeUpdateRequest(
        participant_address=PARTICIPANT_ADDRESS,
        episode_id=EPISODE_ID,
        outcome_id="local-task",
        event_id="report-1",
        rule_address=RULE_ADDRESS,
        expected_revision=0,
        expected_snapshot_revision=0,
    )


def control_plane(**options):
    return RuntimeControlPlane(
        create_stub_target(),
        participant_outcome_model=compile_runtime_model(parse_sdl(yaml.safe_dump(local_scenario()))),
        **(({"initial_snapshot": snapshot()} if "store" not in options else {}) | options),
    )


def test_control_plane_commits_report_and_audit_atomically_and_retries_once():
    with control_plane() as runtime:
        receipt = runtime.record_participant_outcome(request(), identity=identity())
        assert runtime.snapshot.participant_outcome_history[PARTICIPANT_ADDRESS][0]["attainment"] == "attained"
        assert runtime.record_participant_outcome(request(), identity=identity()) == receipt
        assert len(runtime.snapshot.participant_outcome_history[PARTICIPANT_ADDRESS]) == 1
        assert any(event.action == "record_participant_outcome" for event in runtime.audit_log())


@pytest.mark.parametrize(
    "principal",
    [
        None,
        ControlPlaneIdentity("unbound", frozenset({ControlPlaneRole.OPERATOR})),
        replace(identity(), target_name="other"),
        replace(identity(), roles=frozenset({ControlPlaneRole.AUDITOR})),
    ],
)
def test_outcome_write_requires_operator_target_and_participant_authority(principal):
    with control_plane() as runtime:
        update = request()
        with pytest.raises(PermissionError):
            runtime.record_participant_outcome(update, identity=principal)
        assert runtime.snapshot.participant_outcome_history == {}


def test_changed_retry_is_rejected():
    with control_plane() as runtime:
        runtime.record_participant_outcome(request(), identity=identity())
        changed = request().model_copy(update={"outcome_id": "different"})
        principal = identity()
        with pytest.raises(ValueError, match="retry"):
            runtime.record_participant_outcome(changed, identity=principal)


def test_stale_snapshot_revision_cannot_commit():
    with control_plane() as runtime:
        changed = request().model_copy(update={"expected_snapshot_revision": 9})
        principal = identity()
        with pytest.raises(ValueError, match="revision"):
            runtime.record_participant_outcome(changed, identity=principal)
        assert runtime.snapshot.participant_outcome_history == {}


@pytest.mark.parametrize("role", ["red", "blue", "green"])
def test_same_category_is_produced_for_offensive_defensive_and_service_roles(role):
    scenario = local_scenario()
    scenario["entities"]["red-team"]["role"] = role
    model = compile_runtime_model(parse_sdl(yaml.safe_dump(scenario)))
    with RuntimeControlPlane(
        create_stub_target(), participant_outcome_model=model, initial_snapshot=snapshot()
    ) as runtime:
        runtime.record_participant_outcome(request(), identity=identity())
        report = runtime.snapshot.participant_outcome_history[PARTICIPANT_ADDRESS][0]
        assert (report["category"], report["attainment"]) == ("task_completion", "attained")
        assert runtime.snapshot.evaluation_results == {}
        assert runtime.snapshot.orchestration_results == {}


def test_local_store_replay_and_retry_survive_process_restart(tmp_path):
    from raes_runtime.control_plane_store import LocalControlPlaneStore

    path = tmp_path / "runtime"
    store = LocalControlPlaneStore(path)
    update = request().model_copy(update={"expected_snapshot_revision": 1})
    with control_plane(store=store) as runtime:
        store.save_snapshot(snapshot(), expected_revision=0)
        receipt = runtime.record_participant_outcome(update, identity=identity())
    with control_plane(store=LocalControlPlaneStore(path)) as restarted:
        assert restarted.record_participant_outcome(update, identity=identity()) == receipt
        assert restarted.snapshot.participant_outcome_history[PARTICIPANT_ADDRESS][0]["attainment"] == "attained"


def test_failed_store_commit_never_publishes_outcome_state(monkeypatch):
    from raes_runtime.control_plane_store import InMemoryControlPlaneStore

    store = InMemoryControlPlaneStore(snapshot())
    with control_plane(store=store) as runtime:

        def fail(**kwargs):
            raise OSError("simulated store failure")

        monkeypatch.setattr(store, "commit_participant_transition", fail)
        update, principal = request(), identity()
        with pytest.raises(OSError):
            runtime.record_participant_outcome(update, identity=principal)
        assert store.load_snapshot().participant_outcome_history == {}
        assert not any(event.action == "record_participant_outcome" for event in store.read_audit())


def test_wrong_rule_binding_cannot_add_a_report():
    with control_plane() as runtime:
        update = request().model_copy(update={"rule_address": "private:unknown"})
        principal = identity()
        with pytest.raises(ValueError, match="binding"):
            runtime.record_participant_outcome(update, identity=principal)
        assert runtime.snapshot.participant_outcome_history == {}


def test_participant_views_do_not_leak_local_criteria_or_outcome_reports():
    scenario = local_scenario()
    scenario["outcome_interpretation_rules"]["scan-evidence-objective"]["local_outcome"]["criterion_basis"] = (
        "private-criterion-canary"
    )
    model = compile_runtime_model(parse_sdl(yaml.safe_dump(scenario)))
    with RuntimeControlPlane(
        create_stub_target(), participant_outcome_model=model, initial_snapshot=snapshot()
    ) as runtime:
        runtime.record_participant_outcome(request(), identity=identity())
        views = [
            runtime.get_participant_status_view(PARTICIPANT_ADDRESS),
            runtime.get_participant_history_view(PARTICIPANT_ADDRESS, EPISODE_ID),
        ]
        for view in views:
            rendered = view.model_dump_json()
            assert "private-criterion-canary" not in rendered
            assert "local-task" not in rendered
            assert "report-1" not in rendered


@pytest.mark.parametrize("binding", ["other-participant", "other-role", "unbound-rule"])
def test_declared_rule_requires_applicable_behavior_specification(binding):
    from copy import deepcopy

    scenario = local_scenario()
    scenario["entities"]["blue-team"] = {"role": "blue"}
    scenario["agents"]["blue-agent"] = deepcopy(scenario["agents"]["red-agent"])
    scenario["agents"]["blue-agent"]["entity"] = "blue-team"
    specification = scenario["behavior_specifications"]["local-task"]
    if binding == "other-participant":
        specification["participant_refs"] = ["blue-agent"]
    elif binding == "other-role":
        specification["participant_refs"] = []
        specification["participant_role_refs"] = ["blue"]
    else:
        specification["outcome_interpretation_rule_refs"] = []
    model = compile_runtime_model(parse_sdl(yaml.safe_dump(scenario)))
    with RuntimeControlPlane(
        create_stub_target(), participant_outcome_model=model, initial_snapshot=snapshot()
    ) as runtime:
        update, principal = request(), identity()
        with pytest.raises(ValueError, match="binding"):
            runtime.record_participant_outcome(update, identity=principal)
        assert runtime.snapshot.participant_outcome_history == {}


def test_role_bound_behavior_specification_admits_its_outcome_rule():
    scenario = local_scenario()
    specification = scenario["behavior_specifications"]["local-task"]
    specification["participant_refs"] = []
    specification["participant_role_refs"] = ["red"]
    model = compile_runtime_model(parse_sdl(yaml.safe_dump(scenario)))
    with RuntimeControlPlane(
        create_stub_target(), participant_outcome_model=model, initial_snapshot=snapshot()
    ) as runtime:
        runtime.record_participant_outcome(request(), identity=identity())
        assert runtime.snapshot.participant_outcome_history[PARTICIPANT_ADDRESS][0]["attainment"] == "attained"


@pytest.mark.parametrize("role", [ControlPlaneRole.BACKEND, ControlPlaneRole.OPERATOR, ControlPlaneRole.AUDITOR])
def test_generic_snapshot_api_does_not_disclose_private_outcome_history(role):
    from raes_runtime.control_plane_api import create_control_plane_app
    from raes_runtime.control_plane_security import ControlPlaneSecurityConfig
    from starlette.testclient import TestClient

    with control_plane() as runtime:
        runtime.record_participant_outcome(request(), identity=identity())
        security = ControlPlaneSecurityConfig(
            trust_proxy_identity_headers=True,
            trusted_identities={"reader": ControlPlaneIdentity("reader", frozenset({role}), "stub")},
        )
        with TestClient(create_control_plane_app(runtime, security=security)) as client:
            response = client.get(
                "/snapshot",
                headers={"x-raes-client-verified": "true", "x-raes-client-identity": "reader"},
            )
            assert runtime.snapshot.participant_outcome_history[PARTICIPANT_ADDRESS]
        assert response.status_code == 200
        assert response.json().get("participant_outcome_history", {}) == {}
        assert "local-task" not in response.text
        assert "report-1" not in response.text
