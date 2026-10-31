"""Public runtime adoption of exact-cut API-424/v2 provider evaluation."""

import pytest
from participant_control_v2_fixtures import binding


@pytest.fixture(autouse=True)
def close_planes(monkeypatch):
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


from participant_crossing_fixtures import admit
from test_issue_1069_participant_control_orchestration import _evaluations, _plane


def test_dependency_chain_runs_a_b_a_through_public_ingress():
    installed = binding()
    plane = _plane(installed)
    receipt = admit(plane, idempotency_key="dependency-v2")
    assert receipt.accepted
    assert installed.resolver.calls == ["fact", "assessment", "rule"]
    evaluation = _evaluations(plane)[0]
    assert evaluation["schema_version"] == "participant-control-evaluation/v2"
    assert evaluation["composition"]["disposition"] == "eligible"
    assert evaluation["invocations"][2]["predecessor_inputs"][0]["slot_id"] == "assessment"


from participant_control_v2_fixtures import Resolver, optional_advice
from test_issue_1069_participant_control_orchestration import _instrument_backend, control_target


def test_state_proposals_join_the_atomic_crossing_and_are_reused():
    owner = Resolver()
    owner.writes = {"fact"}
    plane = _plane(binding(owner))
    admit(plane, idempotency_key="state-first")
    first = _evaluations(plane)[0]
    assert first["state_proposals"][0]["after"]["ref"] == "next-fact"
    admit(plane, idempotency_key="state-second")
    assert len(_evaluations(plane)) == 1  # resolver still pins the old version; stale state cannot be accepted


def test_optional_state_is_discarded_when_it_conflicts_with_required_scope():
    owner = optional_advice()
    data = owner.selection.model_dump(mode="json")
    data["bindings"][1]["state_scope"] = data["bindings"][0]["state_scope"]
    data["bindings"][1]["authority"] = data["bindings"][0]["authority"]
    data["bindings"][1]["configuration_digest"] = data["bindings"][0]["configuration_digest"]
    from raes_contracts.contracts.participant_control_applicability import ParticipantControlSelectionV2Model

    owner.selection = ParticipantControlSelectionV2Model.model_validate(data)
    owner.writes = {"fact", "assessment"}
    plane = _plane(binding(owner))
    admit(plane, idempotency_key="optional-state-conflict")
    record = _evaluations(plane)[0]
    assert record["composition"]["disposition"] == "eligible"
    assert record["lost_advice"][0]["reason"] == "conflict"
    assert len(record["state_proposals"]) == 1


@pytest.mark.parametrize("failure", ["exception", "malformed", "missing", "stale"])
def test_optional_failure_has_no_veto_and_no_payload_or_state(failure):
    owner = optional_advice()
    owner.providers["monitor"].failure = failure
    target = control_target()
    count = _instrument_backend(target)
    plane = _plane(binding(owner), target=target)
    admit(plane, idempotency_key="optional-" + failure)
    record = _evaluations(plane)[0]
    assert count["calls"] == 1
    assert record["composition"]["disposition"] == "eligible"
    assert record["results"][-1]["payload"] is None
    assert record["results"][-1]["next_provider_state"] is None
    assert record["lost_advice"][0]["slot_id"] == "assessment"


def test_unsatisfied_predecessor_does_not_invoke_dependents():
    owner = Resolver()
    owner.providers["monitor"].failure = "missing"
    target = control_target()
    count = _instrument_backend(target)
    plane = _plane(binding(owner), target=target)
    admit(plane, idempotency_key="required-predecessor")
    assert owner.calls == ["fact", "assessment"]
    record = _evaluations(plane)[0]
    assert record["results"][-1]["status"] == "missing"
    assert count["calls"] == 0


@pytest.mark.parametrize("mode", ["none", "bad_coverage", "stale"])
def test_unresolved_or_stale_coverage_never_dispatches(mode):
    owner = Resolver()
    setattr(owner, mode, True)
    target = control_target()
    count = _instrument_backend(target)
    plane = _plane(binding(owner), target=target)
    admit(plane, idempotency_key="coverage-" + mode)
    assert count["calls"] == 0
    assert owner.calls == []
    assert _evaluations(plane) == []


def test_complete_empty_subset_preserves_incumbent_permission():
    owner = Resolver()
    owner.empty = True
    plane = _plane(binding(owner))
    admit(plane, idempotency_key="empty-complete")
    record = _evaluations(plane)[0]
    assert owner.calls == []
    assert record["composition"]["disposition"] == "eligible"
    assert record["request"]["applicability"]["coverage"][0]["status"] == "proven-inapplicable"


def test_unresolved_obligation_withholds_the_parent():
    owner = Resolver()
    owner.coverage = "unresolved"
    target = control_target()
    count = _instrument_backend(target)
    plane = _plane(binding(owner), target=target)
    admit(plane, idempotency_key="unresolved-coverage")
    assert count["calls"] == 0
    assert _evaluations(plane)[0]["composition"]["disposition"] == "withhold"


def test_disjoint_ingress_and_egress_use_one_complete_apparatus():
    from raes_contracts.contracts.participant_control_applicability import (
        ParticipantControlSelectionV2Model,
        control_digest,
    )
    from test_issue_1069_participant_control_orchestration import _egress_target, _status_view

    owner = Resolver()
    data = owner.selection.model_dump(mode="json")
    data["slots"] = data["slots"][:2]
    data["slots"][1]["dependencies"] = []
    data["slots"][1]["role"] = "mandatory"
    for item, direction in zip(data["bindings"], ("ingress", "egress"), strict=True):
        item["applicability"] = [app for app in item["applicability"] if app["direction"] == direction]
    data["obligations"] = [
        dict(
            obligation_id=slot["slot_id"],
            profile=provider["profiles"][0],
            required_kind=slot["kind"],
            required_strength="exact",
            constraints=[],
        )
        for slot, provider in zip(data["slots"], data["bindings"], strict=True)
    ]
    owner.selection = ParticipantControlSelectionV2Model.model_validate(data)
    owner.obligation_slots = {"fact": "fact", "assessment": "assessment"}
    installed = binding(owner)
    plane = _plane(installed, target=_egress_target())
    admit(plane, idempotency_key="disjoint-ingress")
    _status_view(plane, idempotency_key="disjoint-egress")
    assert owner.calls == ["fact", "assessment"]
    records = _evaluations(plane)
    assert len(records) == 2
    assert all(
        control_digest(ParticipantControlSelectionV2Model.model_validate(item["request"]["selection"]))
        == control_digest(installed.selection)
        for item in records
    )
    assert [item["request"]["applicability"]["applicable_slot_ids"] for item in records] == [["fact"], ["assessment"]]


def test_serial_tentative_state_is_an_explicit_invocation_input():
    from raes_contracts.contracts.participant_control_applicability import ParticipantControlSelectionV2Model

    owner = Resolver()
    data = owner.selection.model_dump(mode="json")
    data["slots"][2]["dependencies"].append(dict(slot_id="fact", kind="ifc-fact"))
    owner.selection = ParticipantControlSelectionV2Model.model_validate(data)
    owner.writes = {"fact", "rule"}
    plane = _plane(binding(owner, serial=True))
    admit(plane, idempotency_key="serial-state")
    record = _evaluations(plane)[0]
    assert record["invocations"][-1]["state_input"]["source"] == "tentative"
    assert record["invocations"][-1]["state_input"]["state"]["ref"] == "next-fact"
    assert len(record["state_proposals"]) == 2


def test_unordered_required_state_writers_cannot_commit_or_dispatch():
    owner = Resolver()
    owner.writes = {"fact", "rule"}
    target = control_target()
    count = _instrument_backend(target)
    plane = _plane(binding(owner), target=target)
    admit(plane, idempotency_key="unordered-state")
    assert count["calls"] == 0
    assert _evaluations(plane) == []


def test_mixed_v1_v2_durable_replay_preserves_attempts(tmp_path):
    from participant_control_runtime_fixtures import control_binding
    from participant_crossing_fixtures import PARTICIPANT
    from raes_runtime.control_plane_store import LocalControlPlaneStore
    from raes_runtime.participant_control_causal_state import causal_state_from_history

    store = LocalControlPlaneStore(tmp_path / "control.db")
    from participant_crossing_fixtures import StaticCrossingResolver, action_plane

    crossing_resolver = StaticCrossingResolver()
    first = action_plane(crossing_resolver, participant_control=control_binding(), store=store, target=control_target())
    admit(first, idempotency_key="legacy-cut")
    legacy = _evaluations(first)[0]
    first.close()
    store = LocalControlPlaneStore(tmp_path / "control.db")
    owner = Resolver()
    second = action_plane(crossing_resolver, participant_control=binding(owner), store=store, target=control_target())
    admit(second, idempotency_key="amended-cut")
    records = _evaluations(second)
    assert len(records) == 2
    assert records[0] == legacy
    assert records[1]["request"]["context"]["attempt"] > legacy["request"]["context"]["attempt"]
    second.close()
    reopened = LocalControlPlaneStore(tmp_path / "control.db")
    third = action_plane(
        crossing_resolver, participant_control=binding(Resolver()), store=reopened, target=control_target()
    )
    snapshot = third.snapshot
    assert snapshot.participant_control_evaluation_history[PARTICIPANT] == records
    context = records[1]["request"]["context"]
    folded = causal_state_from_history(records, run_ref=context["run"]["ref"], trigger_root=context["trigger_root"])
    assert folded.attempts == records[1]["request"]["context"]["attempt"]
    third.close()


def test_stale_callback_cannot_publish_old_snapshot_with_a_refreshed_revision():
    from raes_runtime.control_plane_store import InMemoryControlPlaneStore
    from raes_runtime.control_plane_store_revision import SnapshotRevisionConflict

    owner = Resolver()
    store = InMemoryControlPlaneStore()
    plane = _plane(binding(owner), store=store)
    before = plane.snapshot

    def advance(_invocation):
        # A second authoritative store transaction models a supervisory commit
        # while the external callback has released the state permit.
        current = store.load_snapshot_state()
        store.save_snapshot(
            current.snapshot.with_entries(dict(current.snapshot.entries), metadata={"supervisor": "retained"}),
            expected_revision=current.revision,
        )
        plane._reload_derived_state()

    owner.providers["monitor"].hook = advance
    with pytest.raises(SnapshotRevisionConflict):
        admit(plane, idempotency_key="stale-callback")
    assert plane.snapshot.metadata == {"supervisor": "retained"}
    assert owner.calls == ["fact", "assessment"]
    assert _evaluations(plane) == []


def test_failed_commit_publishes_no_speculative_provider_state(monkeypatch):
    owner = Resolver()
    owner.writes = {"fact"}
    target = control_target()
    count = _instrument_backend(target)
    plane = _plane(binding(owner), target=target)

    def fail(**kwargs):
        raise OSError("synthetic commit refusal")

    monkeypatch.setattr(plane._store, "commit_participant_transition", fail)
    with pytest.raises(OSError):
        admit(plane, idempotency_key="failed-state-commit")
    assert count["calls"] == 0
    assert _evaluations(plane) == []


def test_v2_contract_pins_and_missing_installation_are_checked_at_public_construction():
    from dataclasses import replace

    installed = binding()
    with pytest.raises(ValueError, match="content pins"):
        replace(installed, contract_digests={})
    with pytest.raises(ValueError, match="exactly match"):
        replace(installed, providers={"influence": installed.providers["influence"]})


def test_provider_cannot_mutate_the_retained_invocation():
    owner = Resolver()

    def mutate(invocation):
        object.__setattr__(invocation.state_input.state, "ref", "private-mutated-state")

    owner.providers["monitor"].hook = mutate
    plane = _plane(binding(owner))
    admit(plane, idempotency_key="detached-invocation")
    record = _evaluations(plane)[0]
    assert record["invocations"][1]["state_input"]["state"]["ref"] == "state-monitor"
    assert record["results"][1]["status"] == "failed"


def test_arbitrary_provider_iterators_are_not_consumed():
    owner = Resolver()

    def generate(_call):
        raise AssertionError("unbounded iterator was consumed")
        yield None

    owner.providers["influence"].resolve_stage = generate
    target = control_target()
    count = _instrument_backend(target)
    plane = _plane(binding(owner), target=target)
    admit(plane, idempotency_key="bounded-provider-material")
    assert count["calls"] == 0
    assert _evaluations(plane)[0]["results"][0]["status"] == "failed"


def test_optional_timeout_releases_parent_and_late_result_cannot_commit():
    from dataclasses import replace
    from threading import Event

    owner = optional_advice()
    entered, release = Event(), Event()
    owner.providers["monitor"].hook = lambda _: (entered.set(), release.wait(5))
    target = control_target()
    count = _instrument_backend(target)
    plane = _plane(binding(owner), target=target)
    plane._supervision = replace(plane._supervision, admission_ms=100)
    try:
        admit(plane, idempotency_key="optional-timeout")
        assert entered.is_set()
        record = _evaluations(plane)[0]
        assert record["composition"]["disposition"] == "eligible"
        assert record["lost_advice"][0]["slot_id"] == "assessment"
        assert count["calls"] == 1
        assert plane._execution_adapter.pending_calls > 0
    finally:
        release.set()
    plane.close()
    assert (
        plane._snapshot_state.snapshot.participant_control_evaluation_history[
            next(iter(plane._snapshot_state.snapshot.participant_control_evaluation_history))
        ][0]
        == record
    )


def test_v2_history_is_not_parsed_or_dispatched_by_the_legacy_effect_drain():
    from participant_crossing_fixtures import PARTICIPANT, identity

    plane = _plane(binding())
    admit(plane, idempotency_key="drain-v2")
    assert plane.dispatch_participant_control_effects(PARTICIPANT, identity=identity()) == ()


def test_local_store_reader_version_excludes_v1_only_readers():
    from raes_runtime.control_plane_store_record_migration import LOCAL_OPERATION_SCHEMA_VERSION

    assert int(LOCAL_OPERATION_SCHEMA_VERSION) >= 8


@pytest.mark.parametrize("relation,expected", [("bounded-compatible", "eligible"), ("insufficient", "weakened")])
def test_support_is_checked_against_admitted_strength(relation, expected):
    from participant_control_contract_fixtures import ref
    from raes_contracts.contracts.participant_control_applicability import ParticipantControlSelectionV2Model

    owner = Resolver()
    data = owner.selection.model_dump(mode="json")
    for item in [*data["slots"], *data["obligations"]]:
        item["required_strength"] = "bounded"
        item["constraints"] = [ref("bounded-constraint", "constraint")]
    owner.selection = ParticipantControlSelectionV2Model.model_validate(data)
    owner.effective_level = "bounded"
    owner.support_relation = relation
    target = control_target()
    count = _instrument_backend(target)
    plane = _plane(binding(owner), target=target)
    admit(plane, idempotency_key="bounded-" + relation)
    assert _evaluations(plane)[0]["composition"]["disposition"] == expected
    assert count["calls"] == (1 if expected == "eligible" else 0)


@pytest.mark.parametrize("decision", ["deny", "withhold"])
def test_parent_refusal_commits_only_authorized_evaluation_state(decision):
    from dataclasses import replace

    owner = Resolver()
    owner.decision = decision
    owner.writes = {"fact", "rule"}
    installed = binding(owner)
    stages = dict(installed.stages)
    stages["rule"] = replace(stages["rule"], commit_on="parent-release")
    installed = replace(installed, stages=stages)
    plane = _plane(installed)
    admit(plane, idempotency_key="refused-" + decision)
    record = _evaluations(plane)[0]
    assert record["composition"]["disposition"] == decision
    assert [item["invocation_id"] for item in record["state_proposals"]] == [record["invocations"][0]["invocation_id"]]


def test_state_version_cannot_form_a_cycle_in_retained_history():
    from participant_control_contract_fixtures import ref

    owner = Resolver()
    owner.writes = {"fact"}
    plane = _plane(binding(owner))
    admit(plane, idempotency_key="cycle-first")

    def current_state(context, coords):
        context["provider_states"][0]["state"] = ref("next-fact", "provider-state")

    owner.context_override = current_state
    owner.next_states["fact"] = ref("state-influence", "provider-state")
    admit(plane, idempotency_key="cycle-second")
    assert len(_evaluations(plane)) == 1


def test_unauthorized_state_proposal_never_commits(monkeypatch):
    from dataclasses import replace

    owner = Resolver()
    owner.writes = {"fact"}
    original = owner.validation_context
    monkeypatch.setattr(
        owner, "validation_context", lambda evaluation: replace(original(evaluation), authorized_state_proposals={})
    )
    target = control_target()
    count = _instrument_backend(target)
    plane = _plane(binding(owner), target=target)
    admit(plane, idempotency_key="unauthorized-state")
    assert count["calls"] == 0
    assert _evaluations(plane) == []


@pytest.mark.parametrize("tokens,expected", [([], "eligible"), (["worked-example"], "deny")])
def test_predecessor_content_changes_the_dependent_parent_decision(tokens, expected):
    owner = Resolver()
    owner.fact_tokens = tokens
    owner.content_decision = True
    target = control_target()
    count = _instrument_backend(target)
    plane = _plane(binding(owner), target=target)
    admit(plane, idempotency_key="content-sensitive")
    record = _evaluations(plane)[0]
    assert owner.calls == ["fact", "assessment", "rule"]
    assert record["composition"]["disposition"] == expected
    assert count["calls"] == (1 if expected == "eligible" else 0)


def test_optional_projection_failure_has_a_blocked_descriptor_without_veto(monkeypatch):
    owner = optional_advice()
    original = owner.projection

    def project(request, slot_id, predecessors):
        if slot_id == "assessment":
            raise ValueError("private projection failure")
        return original(request, slot_id, predecessors)

    monkeypatch.setattr(owner, "projection", project)
    target = control_target()
    count = _instrument_backend(target)
    plane = _plane(binding(owner), target=target)
    admit(plane, idempotency_key="optional-projection")
    record = _evaluations(plane)[0]
    assert owner.calls == ["fact"]
    assert record["composition"]["disposition"] == "eligible"
    assert count["calls"] == 1
    assert record["results"][-1]["status"] == "failed"


def test_stale_required_output_never_reaches_a_dependent_provider():
    owner = Resolver()
    owner.providers["monitor"].failure = "stale"
    target = control_target()
    count = _instrument_backend(target)
    plane = _plane(binding(owner), target=target)
    admit(plane, idempotency_key="stale-required-input")
    assert owner.calls == ["fact", "assessment"]
    assert count["calls"] == 0
    assert _evaluations(plane)[0]["composition"]["disposition"] == "failed"


def test_insufficient_required_support_stops_provider_invocation():
    owner = Resolver()
    owner.support_relation = "insufficient"
    plane = _plane(binding(owner))
    admit(plane, idempotency_key="support-before-call")
    assert owner.calls == []
    assert _evaluations(plane)[0]["composition"]["disposition"] == "weakened"


@pytest.mark.parametrize("sharing,expected_calls", [("run", 1), ("participant", 2)])
def test_shared_run_state_and_participant_isolation_through_public_ingress(sharing, expected_calls):
    from copy import deepcopy
    from dataclasses import replace

    from participant_crossing_fixtures import (
        PARTICIPANT,
        admission_request,
        behavior,
        build_implementation_selection,
        evidence,
        identity,
    )
    from raes_contracts.contracts.participant_control_applicability import ParticipantControlSelectionV2Model

    other = "participant.behavior.blue-agent"
    owner = Resolver()
    data = owner.selection.model_dump(mode="json")
    for item in data["bindings"]:
        item["state_scope"]["sharing"] = sharing
        item["applicability"] += [{**app, "participant_address": other} for app in deepcopy(item["applicability"])]
    owner.selection = ParticipantControlSelectionV2Model.model_validate(data)
    owner.writes = {"fact"}
    target = control_target()
    count = _instrument_backend(target)
    plane = _plane(binding(owner), target=target)
    admit(plane, idempotency_key="shared-state-red")
    plane.initialize_participant_episode(other, episode_id="episode-1")
    request = replace(
        admission_request(), participant_address=other, implementation_selection=build_implementation_selection(other)
    )
    plane.admit_participant_action(
        replace(behavior(), address=other),
        request,
        identity=identity(participant_address=other),
        crossing_evidence=evidence(),
        idempotency_key="shared-state-blue",
    )
    assert count["calls"] == expected_calls
    assert len(plane.snapshot.participant_control_evaluation_history.get(other, ())) == expected_calls - 1
    assert len(plane.snapshot.participant_control_evaluation_history[PARTICIPANT]) == 1


def test_public_stop_during_provider_call_fences_late_evaluation():
    from threading import Event, Thread

    from raes_runtime.control_plane_store_revision import SnapshotRevisionConflict
    from test_issue_1362_runtime_supervision import supervisor

    owner = Resolver()
    entered, release = Event(), Event()
    owner.providers["monitor"].hook = lambda _: (entered.set(), release.wait(5))
    target = control_target()
    count = _instrument_backend(target)
    plane = _plane(binding(owner), target=target)
    failures = []

    def submit():
        try:
            admit(plane, idempotency_key="stop-evaluation")
        except Exception as error:  # noqa: BLE001 - the worker hands the exception to the test thread, which asserts it.
            failures.append(error)

    worker = Thread(target=submit)
    worker.start()
    try:
        assert entered.wait(2)
        plane.stop_admission(identity=supervisor())
    finally:
        release.set()
        worker.join(3)
    assert not worker.is_alive()
    assert len(failures) == 1
    assert isinstance(failures[0], SnapshotRevisionConflict)
    assert count["calls"] == 0
    assert _evaluations(plane) == []


def test_trusted_support_callback_is_supervised_and_cannot_reenter_mutation(monkeypatch):
    from dataclasses import replace

    owner = Resolver()
    original = owner.validation_context
    plane = _plane(binding(owner))
    rejected = []

    def support(_assessment):
        try:
            plane.initialize_participant_episode("participant.callback", episode_id="forbidden")
        except RuntimeError:
            rejected.append(True)
        return True

    monkeypatch.setattr(
        owner, "validation_context", lambda evaluation: replace(original(evaluation), support_resolver=support)
    )
    admit(plane, idempotency_key="support-reentry")
    assert rejected
    assert "participant.callback" not in plane.snapshot.participant_episode_results
    assert _evaluations(plane)[0]["composition"]["disposition"] == "eligible"


@pytest.mark.parametrize("optional_first", [False, True])
def test_optional_result_identity_collision_cannot_veto_required_work(monkeypatch, optional_first):
    from raes_contracts.contracts.participant_control_applicability import ParticipantControlSelectionV2Model

    owner = optional_advice()
    owner.writes = {"assessment"}
    if optional_first:
        data = owner.selection.model_dump(mode="json")
        data["slots"][1]["dependencies"] = []
        data["slots"].reverse()
        owner.selection = ParticipantControlSelectionV2Model.model_validate(data)
    provider = owner.providers["monitor"]
    original = provider.resolve_stage
    monkeypatch.setattr(
        provider,
        "resolve_stage",
        lambda call: tuple(result.model_copy(update={"result_id": "result-fact"}) for result in original(call)),
    )
    target = control_target()
    count = _instrument_backend(target)
    plane = _plane(binding(owner), target=target)
    admit(plane, idempotency_key="duplicate-optional-result")
    assert count["calls"] == 1
    record = _evaluations(plane)[0]
    assert record["composition"]["disposition"] == "eligible"
    assert len({item["result_id"] for item in record["results"]}) == len(record["results"])
    optional = next(item for item in record["results"] if item["slot_id"] == "assessment")
    assert optional["payload"] is None
    assert optional["next_provider_state"] is None
    assert record["lost_advice"][0]["reason"] == "malformed"
    assert record["state_proposals"] == []


@pytest.mark.parametrize("intermediate_v1", [False, True])
def test_v2_to_v1_durable_switch_preserves_other_participants_root_consumption(tmp_path, intermediate_v1):
    from dataclasses import replace

    from participant_control_runtime_fixtures import (
        SyntheticControlProvider,
        SyntheticControlResolver,
        admitted_payload,
        fact_only_payload,
    )
    from participant_crossing_fixtures import (
        AUDIENCE,
        PARTICIPANT,
        StaticCrossingResolver,
        action_plane,
        admission_request,
        behavior,
        build_implementation_selection,
        evidence,
        identity,
    )
    from raes_contracts.contracts.participant_control_selection import ParticipantControlSelectionModel
    from raes_contracts.runtime_state import OperationState
    from raes_runtime.control_plane import RuntimeControlPlane
    from raes_runtime.control_plane_store import LocalControlPlaneStore
    from raes_runtime.participant_control_binding import ParticipantControlRuntimeBinding

    path = tmp_path / "binding-switch"
    crossing = StaticCrossingResolver()
    first = action_plane(
        crossing, target=control_target(), store=LocalControlPlaneStore(path), participant_control=binding()
    )
    admit(first, idempotency_key="shared-v2-root")
    retained = _evaluations(first)
    first.close()

    def open_legacy(participant, attempt):
        payload = admitted_payload(fact_only_payload(), participant=participant, audience=AUDIENCE)
        payload["request"]["context"]["attempt"] = attempt
        provider = SyntheticControlProvider()
        resolver = SyntheticControlResolver(payload=payload, providers=(provider,))
        legacy = ParticipantControlRuntimeBinding(
            selection=ParticipantControlSelectionModel.model_validate(payload["request"]["selection"]),
            providers={"influence": provider},
            resolver=resolver,
        )
        target = control_target()
        count = _instrument_backend(target)
        plane = RuntimeControlPlane(
            target,
            crossing_policy_resolver=crossing,
            store=LocalControlPlaneStore(path),
            participant_control=legacy,
            enforce_final_sink_flow_control=False,
        )
        plane.initialize_participant_episode(participant, episode_id="episode-1")
        return plane, resolver, provider, count

    def submit(plane, participant):
        request = replace(
            admission_request(),
            participant_address=participant,
            implementation_selection=build_implementation_selection(participant),
        )
        return plane.admit_participant_action(
            replace(behavior(), address=participant),
            request,
            identity=identity(participant_address=participant),
            crossing_evidence=evidence(),
            idempotency_key="v1-root-" + participant,
        )

    attempt = retained[0]["request"]["context"]["attempt"]
    if intermediate_v1:
        carry, _, _, counter = open_legacy("participant.behavior.blue-agent", attempt + 1)
        submit(carry, "participant.behavior.blue-agent")
        assert counter["calls"] == 1
        carry.close()
        attempt += 1
    other = "participant.behavior.green-agent"
    second, resolver, provider, count = open_legacy(other, attempt)
    receipt = submit(second, other)
    assert resolver.live["request"]["context"]["attempt"] == attempt
    assert count["calls"] == 0
    assert provider.calls == []
    assert second.get_operation(receipt.operation_id).state is OperationState.FAILED
    assert second.snapshot.participant_control_evaluation_history[PARTICIPANT] == retained
