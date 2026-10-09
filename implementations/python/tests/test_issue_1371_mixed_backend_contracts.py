"""Published mixed-backend execution bindings, shared-operation admission and stage readback (#1371)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError
from raes_backend_protocols import require_mixed_backend_service
from raes_contracts import contracts
from raes_contracts.canonical import canonical_json_digest
from raes_contracts.contracts import seal_mixed_composition_profile
from raes_contracts.contracts.time_model import TimeModelDeclarationModel, TimeRuntimeStateModel
from raes_contracts.versions import BACKEND_OPERATION_CONTRACT_IDS, MIXED_BACKEND_CONTRACT_IDS
from test_issue_1014_mixed_composition_contracts import _context, _staged_profile, _time_model
from test_issue_1016_mixed_runtime_coordination import _runtime_mixed_profile, _runtime_profile

ROOT = Path(__file__).resolve().parents[3]
FIXTURES = ROOT / "contracts/fixtures/control-plane"
BINDING = "mixed-backend-execution-binding-v1"
STAGES = "mixed-backend-stage-report-v1"
SCENARIOS = {
    "mixed-edge": "mixed-edge",
    "mixed-edge-partial": "mixed-edge",
    "mixed-edge-refused": "mixed-edge",
    "mixed-edge-time-refused": "mixed-edge",
    "mixed-handoff": "mixed-handoff",
    "mixed-handoff-stale": "mixed-handoff",
}
# Committed source and destination clock coordinates; after a reset the
# destination clock of the time-refused example sits in a later segment.
COMMITTED_CLOCKS = {"mixed-edge-time-refused": ((0, 4, 0), (1, 2, 0))}


def _fixture(family: str, kind: str, name: str) -> dict:
    return json.loads((FIXTURES / family / kind / f"{name}.json").read_text(encoding="utf-8"))


def _subject_payload(name: str, **subject: object) -> dict:
    payload = _fixture(BINDING, "valid", name)
    payload["subject"].update(subject)
    return payload


def _binding(name: str = "mixed-edge", **subject: object) -> contracts.MixedBackendExecutionBindingModel:
    return contracts.MixedBackendExecutionBindingModel.model_validate(_subject_payload(name, **subject))


def _scenario(name: str) -> tuple[contracts.BackendOperationRequestModel, list, list]:
    request = contracts.BackendOperationRequestModel.model_validate(
        _fixture("backend-operation-request-v1", "valid", name)
    )
    responses = [
        contracts.BackendOperationResponseModel.model_validate_json(path.read_text(encoding="utf-8"))
        for path in sorted((FIXTURES / "backend-operation-response-v1/valid").glob(f"{name}-0*.json"))
    ]
    reports = [
        contracts.MixedBackendStageReportModel.model_validate_json(path.read_text(encoding="utf-8"))
        for path in sorted((FIXTURES / STAGES / "valid").glob(f"{name}-0*.json"))
    ]
    return request, responses, reports


def _coordinate(segment: int, tick: int, microstep: int) -> dict:
    return {"segment": segment, "tick": tick, "microstep": microstep}


def _time_state(
    source: tuple[int, int, int] = (0, 4, 0),
    destination: tuple[int, int, int] = (0, 4, 1),
    *,
    declaration: TimeModelDeclarationModel | None = None,
) -> TimeRuntimeStateModel:
    """Typed time readback with the bound simulation and emulation clocks at the given coordinates."""

    declaration = declaration or _time_model()
    positions = {"time.clocks.sim": source, "time.clocks.emu": destination}
    clocks = {}
    for address, clock in declaration.clocks.items():
        coordinate = _coordinate(*positions.get(address, (0, 0, 0)))
        clocks[address] = {
            "clock_address": address,
            "time_domain_address": clock.time_domain_address,
            "authority_kind": clock.authority_kind,
            "authority_ref": clock.authority_ref,
            "state": "running",
            "coordinate": coordinate,
            "sequence": 0,
            "history": [
                {
                    "sequence": 0,
                    "kind": "initialize",
                    "previous": None,
                    "resulting": coordinate,
                    "resulting_state": "running",
                }
            ],
        }
    return TimeRuntimeStateModel.model_validate(
        {"declaration_digest": declaration.canonical_digest(), "clocks": clocks}
    )


def _declaration(**emulation_clock: object) -> TimeModelDeclarationModel:
    fields = _time_model().model_dump(mode="python")
    clock = fields["clocks"].pop("time.clocks.emu") | emulation_clock
    fields["clocks"][clock["address"]] = clock
    return TimeModelDeclarationModel.model_validate(fields)


def _composition_state(profile=None, **changes: object) -> contracts.MixedCompositionRuntimeStateModel:
    """Committed composition state; by default the staged profile's source phase before its handoff."""

    profile = profile or _staged_profile()
    return contracts.MixedCompositionRuntimeStateModel.model_validate(
        {
            "run_id": "run:mixed",
            "plan_id": "plan:mixed",
            "plan_entry_id": "entry:mixed",
            "profile_id": profile.profile_id,
            "profile_digest": profile.profile_digest,
            "phase_id": "phase.sim",
            "phase_revision": 0,
            "active_component_ids": ["sim"],
            "active_allocation_ids": ["allocation.participant", "allocation.action"],
            "history_head": "composition:activation:initial",
        }
        | changes
    )


def _edge_composition_state(*active_edge_ids: str) -> contracts.MixedCompositionRuntimeStateModel:
    """Committed state of the edge profile's only phase, with the given edges active."""

    return _composition_state(
        _runtime_mixed_profile(),
        phase_id="phase.main",
        active_component_ids=["sim", "emu"],
        active_edge_ids=list(active_edge_ids),
    )


def _trusted(scenario: str) -> dict:
    """Caller-resolved inputs: time model and its identity, time readbacks and the composition state."""

    readback = _time_state(*COMMITTED_CLOCKS.get(scenario, ()))
    time = _fixture(BINDING, "valid", SCENARIOS[scenario])["subject"]["time"]
    trusted = {
        "time_model": _time_model(),
        "time_model_ref": time["time_model_ref"],
        "time_model_digest": time["time_model_digest"],
        "time_state": readback,
        "post_time_state": readback,
    }
    if SCENARIOS[scenario] == "mixed-handoff":
        trusted["composition_state"] = _composition_state()
    return trusted


def _stage_context(scenario: str, **overrides: object) -> contracts.MixedBackendStageContext:
    return contracts.MixedBackendStageContext(**(_trusted(scenario) | overrides))


def _validate(scenario: str, *, binding=None, responses=None, reports=None, **trusted: object) -> None:
    request, default_responses, default_reports = _scenario(scenario)
    contracts.validate_mixed_backend_stage_reports(
        binding or _binding(SCENARIOS[scenario]),
        request,
        default_responses if responses is None else responses,
        default_reports if reports is None else reports,
        context=_stage_context(scenario, **trusted),
    )


def _restage(report, **stage: object) -> contracts.MixedBackendStageReportModel:
    payload = report.model_dump(mode="json")
    payload["stage"].update(stage)
    return contracts.MixedBackendStageReportModel.model_validate(payload)


def _remessage(response, **message: object) -> contracts.BackendOperationResponseModel:
    payload = response.model_dump(mode="json")
    payload["message"].update(message)
    return contracts.BackendOperationResponseModel.model_validate(payload)


def _failed_outcome(response, *cited) -> contracts.BackendOperationResponseModel:
    """Rewrite a transcript's outcome as a known failure with no effect that cites the given reports."""

    references = [
        {
            "contract_id": STAGES,
            "artifact_id": f"stage:{report.stage.stage}",
            "digest": canonical_json_digest(report.model_dump(mode="json")),
        }
        for report in cited
    ]
    effects = response.message.effects.model_dump(mode="json") | {
        "effect": "absent",
        "cessation_established": True,
        "evidence_refs": references,
        "residual_scope": [],
        "residual_state": None,
    }
    return _remessage(
        response,
        proposed_state="failed",
        satisfaction="unsatisfied",
        release_gates_satisfied=False,
        result=None,
        effects=effects,
    )


def _reseal(profile, change) -> object:
    fields = profile.model_dump(mode="python", exclude={"profile_digest"})
    change(fields)
    return seal_mixed_composition_profile(**fields)


@pytest.mark.parametrize("scenario", sorted(SCENARIOS))
def test_example_transcripts_validate_for_each_supported_arrangement(scenario: str) -> None:
    _validate(scenario)


def test_execution_delivery_and_observation_remain_distinct_evidenced_stages() -> None:
    _, _, reports = _scenario("mixed-edge")
    stages = {report.stage.stage: report.stage for report in reports}

    assert list(stages) == ["time-grant", "execution", "delivery", "observation"]
    assert {stages[name].evidence_refs for name in ("execution", "delivery", "observation")} == {
        ("evidence:backend-readback",),
        ("evidence:destination-receipt",),
        ("evidence:participant-readback",),
    }
    _, _, partial = _scenario("mixed-edge-partial")
    assert [report.stage.stage for report in partial] == ["time-grant", "execution"]
    assert partial[1].stage.status == "partial"


@pytest.mark.parametrize(
    ("profile_factory", "name"), [(_runtime_mixed_profile, "mixed-edge"), (_staged_profile, "mixed-handoff")]
)
def test_bindings_join_the_admitted_sealed_profile(profile_factory, name: str) -> None:
    profile = profile_factory()
    contracts.validate_mixed_backend_bindings(profile, _context(profile), [_binding(name)])


def _grow_membership(fields: dict) -> None:
    fields["phases"]["phase.emu"]["active_component_ids"] = ["sim", "emu"]
    fields["phases"]["phase.emu"]["active_allocation_ids"] += ["allocation.participant", "allocation.action"]
    for allocation_id in ("allocation.participant", "allocation.action"):
        fields["allocations"][allocation_id]["phase_ids"] = ["phase.sim", "phase.emu"]


def _keep_membership(fields: dict) -> None:
    fields["phases"]["phase.sim2"] = {**fields["phases"]["phase.sim"], "phase_id": "phase.sim2"}
    for allocation_id in ("allocation.participant", "allocation.action"):
        fields["allocations"][allocation_id]["phase_ids"] = ["phase.sim", "phase.sim2"]
    fields["phase_order"] = ["phase.sim", "phase.sim2", "phase.emu"]
    template = fields["transitions"].pop("transition.sim-to-emu")
    fields["transitions"] = {
        "transition.sim-to-sim2": {
            **template,
            "transition_id": "transition.sim-to-sim2",
            "target_phase_id": "phase.sim2",
        },
        "transition.sim2-to-emu": {
            **template,
            "transition_id": "transition.sim2-to-emu",
            "source_phase_id": "phase.sim2",
        },
    }


def _wall_clock_edge(fields: dict) -> None:
    fields["edges"]["edge.sim-to-emu"]["time_binding"]["ordering_basis"] = "wall_clock_only"


def _defer_owner_allocation(fields: dict) -> None:
    # The destination action allocation becomes active only in a later phase
    # where the edge is inactive, so a binding naming it can never execute.
    main = fields["phases"]["phase.main"]
    main["active_allocation_ids"].remove("allocation.action")
    fields["phases"]["phase.later"] = {
        **main,
        "phase_id": "phase.later",
        "active_allocation_ids": ["allocation.action"],
        "active_edge_ids": [],
    }
    fields["allocations"]["allocation.action"]["phase_ids"] = ["phase.later"]
    fields["phase_order"] = ["phase.main", "phase.later"]
    template = _staged_profile().transitions["transition.sim-to-emu"].model_dump(mode="python")
    fields["transitions"] = {
        "transition.main-to-later": {
            **template,
            "transition_id": "transition.main-to-later",
            "source_phase_id": "phase.main",
            "target_phase_id": "phase.later",
        }
    }


@pytest.mark.parametrize(
    ("profile", "bindings", "rebind", "message"),
    [
        (_runtime_mixed_profile, [], True, "active mixed edge requires an executable binding"),
        (_staged_profile, [], True, "requires an executable handoff binding"),
        (_staged_profile, [_binding()], False, "another composition profile"),
        (_runtime_mixed_profile, [_binding(), _binding()], True, "identities must be unique"),
        (lambda: _reseal(_runtime_mixed_profile(), _wall_clock_edge), [], True, "ungoverned order"),
        (lambda: _reseal(_staged_profile(), _grow_membership), [], True, "outside one-to-one native handoff"),
        (
            lambda: _reseal(_runtime_mixed_profile(), _defer_owner_allocation),
            [_binding()],
            True,
            "own the destination provider's action allocation",
        ),
        (
            lambda: _reseal(_staged_profile(), _keep_membership),
            [_binding("mixed-handoff", transition_id="transition.sim-to-sim2")],
            True,
            "needs no native handoff binding",
        ),
    ],
)
def test_binding_sets_refuse_missing_foreign_or_unsupported_obligations(
    profile, bindings, rebind: bool, message: str
) -> None:
    # ``rebind`` points the bindings at the selected profile so that only the
    # case's own defect remains; the foreign-profile case keeps its identity.
    selected = profile()
    identity = {"profile_id": selected.profile_id, "profile_digest": selected.profile_digest}
    rebound = [binding.model_copy(update=identity) if rebind else binding for binding in bindings]
    context = _context(selected)
    with pytest.raises(ValueError, match=message):
        contracts.validate_mixed_backend_bindings(selected, context, rebound)


def test_alternative_profiles_admit_no_executable_binding() -> None:
    alternative = _runtime_profile()
    contracts.validate_mixed_backend_bindings(alternative, _context(alternative), [])
    foreign = _binding().model_copy(
        update={"profile_id": alternative.profile_id, "profile_digest": alternative.profile_digest}
    )
    context = _context(alternative)
    with pytest.raises(ValueError, match="must name admitted edges"):
        contracts.validate_mixed_backend_bindings(alternative, context, [foreign])


def test_one_obligation_cannot_be_bound_twice() -> None:
    profile = _runtime_mixed_profile()
    bindings = [_binding(), _binding().model_copy(update={"binding_id": "binding:edge.duplicate"})]
    context = _context(profile)
    with pytest.raises(ValueError, match="binds one obligation twice"):
        contracts.validate_mixed_backend_bindings(profile, context, bindings)


def test_component_keeping_transitions_need_no_binding() -> None:
    profile = _reseal(_staged_profile(), _keep_membership)
    handoff = _binding("mixed-handoff", transition_id="transition.sim2-to-emu").model_copy(
        update={"profile_id": profile.profile_id, "profile_digest": profile.profile_digest}
    )
    contracts.validate_mixed_backend_bindings(profile, _context(profile), [handoff])


def test_binding_sets_and_stage_transcripts_are_bounded() -> None:
    # One past the published bounds of 2048 bindings and 64 stage reports.
    profile = _runtime_mixed_profile()
    context, oversized = _context(profile), [_binding()] * 2049
    with pytest.raises(ValueError, match="binding set exceeds its bound"):
        contracts.validate_mixed_backend_bindings(profile, context, oversized)
    _, responses, reports = _scenario("mixed-edge")
    with pytest.raises(ValueError, match="transcript exceeds its bound"):
        _validate("mixed-edge", responses=responses, reports=[reports[0]] * 65)


EDGE_TIME = _fixture(BINDING, "valid", "mixed-edge")["subject"]["time"]


@pytest.mark.parametrize(
    "subject",
    [
        {"owner_component_id": "sim"},
        {"owner_allocation_id": "allocation.participant"},
        {"bridge": {"service_ref": "route:unadmitted", "version": "1", "digest": "sha256:" + "1" * 64}},
        {"audience_scope_ref": "audience:other"},
        {"participant_address": "participant.behavior.blue-agent"},
        {"required_evidence_refs": ["evidence:unrelated"]},
        {"mapping_loss": {**_fixture(BINDING, "valid", "mixed-edge")["subject"]["mapping_loss"], "kind": "none"}},
        {"time": {**EDGE_TIME, "ordering_basis": "total_order"}},
        {"time": {**EDGE_TIME, "time_model_digest": "sha256:" + "e" * 64}},
        {"time": {**EDGE_TIME, "destination_clock_address": "time.clocks.sim"}},
        {"time": {**EDGE_TIME, "temporal_coupling": "tight"}},
    ],
)
def test_edge_binding_must_match_the_admitted_edge_and_destination_owner(subject: dict) -> None:
    profile = _runtime_mixed_profile()
    context, bindings = _context(profile), [_binding(**subject)]
    with pytest.raises(ValueError, match="mixed edge binding"):
        contracts.validate_mixed_backend_bindings(profile, context, bindings)


HANDOFF_TIME = _fixture(BINDING, "valid", "mixed-handoff")["subject"]["time"]


@pytest.mark.parametrize(
    ("subject", "message"),
    [
        ({"source_component_id": "emu", "destination_component_id": "sim"}, "transition ownership"),
        ({"destination_owner_ref": "native-ownership:other"}, "transition ownership"),
        ({"required_evidence_refs": ["evidence:unrelated"]}, "transition ownership"),
        ({"time": {**HANDOFF_TIME, "time_model_digest": "sha256:" + "e" * 64}}, "unresolved or stale"),
        ({"time": {**HANDOFF_TIME, "mapping_ref": "time.mappings.unknown"}}, "clocks and mapping"),
        (
            {
                "time": {
                    **HANDOFF_TIME,
                    "source_clock_address": "time.clocks.emu",
                    "destination_clock_address": "time.clocks.sim",
                }
            },
            "clocks and mapping",
        ),
    ],
)
def test_handoff_binding_must_match_one_to_one_ownership_and_resolved_time(subject: dict, message: str) -> None:
    profile = _staged_profile()
    context, bindings = _context(profile), [_binding("mixed-handoff", **subject)]
    with pytest.raises(ValueError, match=message):
        contracts.validate_mixed_backend_bindings(profile, context, bindings)


EDGE_SUBJECT = _fixture(BINDING, "valid", "mixed-edge")["subject"]
BRIDGE_SERVICE, DELIVERY_SERVICE = EDGE_SUBJECT["bridge"], EDGE_SUBJECT["delivery_reader"]
TRANSFER_SERVICE = _fixture(BINDING, "valid", "mixed-handoff")["subject"]["transfer"]


@pytest.mark.parametrize(
    "payload",
    [
        pytest.param(_fixture(BINDING, "invalid", "bridge-as-reader"), id="invalid-bridge-as-reader"),
        pytest.param(_fixture(BINDING, "invalid", "transfer-as-owner-reader"), id="invalid-transfer-as-owner-reader"),
        pytest.param(_subject_payload("mixed-edge", delivery_reader=BRIDGE_SERVICE), id="bridge-reads-delivery"),
        pytest.param(_subject_payload("mixed-edge", observation_reader=BRIDGE_SERVICE), id="bridge-reads-observation"),
        pytest.param(_subject_payload("mixed-edge", observation_reader=DELIVERY_SERVICE), id="one-reader-two-stages"),
        pytest.param(
            _subject_payload("mixed-edge", time={**EDGE_TIME, "coordinator": BRIDGE_SERVICE}),
            id="bridge-grants-order",
        ),
        pytest.param(
            _subject_payload("mixed-edge", delivery_reader={**BRIDGE_SERVICE, "service_ref": "reader:renamed"}),
            id="shared-digest",
        ),
        pytest.param(
            _subject_payload(
                "mixed-edge", delivery_reader={**DELIVERY_SERVICE, "service_ref": BRIDGE_SERVICE["service_ref"]}
            ),
            id="shared-reference",
        ),
        pytest.param(
            _subject_payload("mixed-handoff", time={**HANDOFF_TIME, "coordinator": TRANSFER_SERVICE}),
            id="transfer-grants-order",
        ),
        pytest.param(
            _subject_payload("mixed-handoff", owner_reader=HANDOFF_TIME["coordinator"]),
            id="coordinator-reads-owner",
        ),
    ],
)
def test_binding_pins_a_distinct_service_for_each_role(payload: dict) -> None:
    # Sharing a reference or a digest would let one service report two stages,
    # such as a bridge reading back its own delivery or granting its own order.
    with pytest.raises(ValidationError, match="distinct service for each role"):
        contracts.MixedBackendExecutionBindingModel.model_validate(payload)


def _capabilities(name: str) -> contracts.BackendOperationCapabilitiesModel:
    return contracts.BackendOperationCapabilitiesModel.model_validate(
        _fixture("backend-operation-capabilities-v1", "valid", name)
    )


def test_contextual_admission_uses_the_shared_operation_protocol() -> None:
    request, responses, _ = _scenario("mixed-edge")
    binding, capabilities = _binding(), _capabilities("mixed-bridge")
    contracts.require_mixed_backend_admission(binding, request, capabilities, responses[0])
    refused, refusal, _ = _scenario("mixed-edge-refused")
    with pytest.raises(ValueError, match="context refused"):
        contracts.require_mixed_backend_admission(binding, refused, capabilities, refusal[0])


def _edge_request(
    operation_kind: str = "participant-crossing", backend_id: str = "route:portable"
) -> contracts.BackendOperationRequestModel:
    payload = _fixture("backend-operation-request-v1", "valid", "mixed-edge")
    payload["binding"]["context"]["operation_kind"] = operation_kind
    payload["binding"]["backend_id"] = backend_id
    return contracts.BackendOperationRequestModel.model_validate(payload)


@pytest.mark.parametrize(
    ("binding", "changes", "message"),
    [
        (lambda: _binding("mixed-handoff"), {}, "does not commit"),
        (lambda: _binding(audience_scope_ref="audience:other"), {}, "does not commit"),
        (_binding, {"operation_kind": "composition-phase"}, "operation kind differs"),
        (_binding, {"backend_id": "transfer:native-ownership"}, "installed mixed service"),
    ],
)
def test_request_must_commit_to_the_exact_binding_kind_and_installed_service(binding, changes, message) -> None:
    selected, request = binding(), _edge_request(**changes)
    with pytest.raises(ValueError, match=message):
        contracts.require_mixed_backend_request(selected, request)


OWNER_READBACK = {
    "stage": "owner-readback",
    "producer": _fixture(BINDING, "valid", "mixed-handoff")["subject"]["owner_reader"],
    "owner_component_id": "emu",
    "owner_ref": "native-ownership:emu",
    "phase_revision": 1,
    "evidence_refs": ["evidence:owner-readback:emu"],
}


def _report(base, sequence: int, stage: dict) -> contracts.MixedBackendStageReportModel:
    payload = base.model_dump(mode="json") | {"sequence": sequence, "stage": stage}
    return contracts.MixedBackendStageReportModel.model_validate(payload)


def _edge_case(mutate) -> tuple[list, list]:
    _, responses, reports = _scenario("mixed-edge")
    return mutate(list(responses), list(reports))


def _grant_case(**grant):
    return lambda responses, reports: (responses, [_restage(reports[0], **grant), *reports[1:]])


def _progress_cites_unsupplied_report(responses: list, reports: list) -> tuple[list, list]:
    unsupplied = _restage(reports[2], receipt_ref="receipt:other")
    reference = {
        "contract_id": STAGES,
        "artifact_id": "stage:mixed-edge:unsupplied",
        "digest": canonical_json_digest(unsupplied.model_dump(mode="json")),
    }
    payload = responses[1].model_dump(mode="json") | {
        "sequence": 3,
        "message": {"kind": "progress", "phase": "executing", "evidence_refs": [reference]},
    }
    return [*responses[:2], contracts.BackendOperationResponseModel.model_validate(payload)], reports


def _rebridged(responses: list, reports: list) -> tuple[list, list]:
    producer = reports[1].stage.producer.model_dump(mode="json") | {"version": "2"}
    return responses, [reports[0], _restage(reports[1], producer=producer), *reports[2:]]


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda r, s: (r, s[1:]), "precedes its prerequisite"),
        (lambda r, s: (r, [s[0], s[2], s[3]]), "precedes its prerequisite"),
        (lambda r, s: (r, [s[0], s[1], s[3]]), "precedes its prerequisite"),
        (lambda r, s: (r[:1], s[:2]), "accepted acknowledgement"),
        (lambda r, s: (r, [_restage(s[0], comparison="incomparable"), *s[1:]]), "ordered time grant"),
        (
            _grant_case(source_coordinate=_coordinate(0, 0, 0), destination_coordinate=_coordinate(0, 999999, 0)),
            "committed time readback",
        ),
        (_grant_case(timing_evidence_refs=["evidence:time-grant"]), "admitted evidence"),
        (_grant_case(ordering_basis="total_order"), "bound mapping or ordering basis"),
        (
            lambda r, s: (r, [s[0], _restage(s[1], mapping_loss_refs=[]), *s[2:]]),
            "installed subjects or declared loss",
        ),
        (_rebridged, "names a producer other than"),
        (lambda r, s: (r, [*s[:2], _restage(s[2], destination_component_id="sim"), s[3]]), "destination provider"),
        (lambda r, s: (r, [*s[:3], _restage(s[3], audience_scope_ref="audience:other")]), "participant or audience"),
        (lambda r, s: (r, [*s, _report(s[3], 5, OWNER_READBACK)]), "belong to this mixed binding"),
        (lambda r, s: (r, [*s, s[3].model_copy(update={"sequence": 9})]), "at most once"),
        (lambda r, s: (r, [*s, _restage(s[3], observation_ref="observation:rewritten")]), "changed its content"),
        (lambda r, s: (r, s[:2]), "claims more than the mixed stages establish"),
        (lambda r, s: (r, [s[0], s[1], _restage(s[2], receipt_ref="receipt:other"), s[3]]), "cites a stage report"),
        (_progress_cites_unsupplied_report, "cites a stage report"),
    ],
)
def test_edge_transcript_rejects_out_of_order_foreign_or_overclaimed_stages(mutate, message: str) -> None:
    responses, reports = _edge_case(mutate)
    with pytest.raises(ValueError, match=message):
        _validate("mixed-edge", responses=responses, reports=reports)


@pytest.mark.parametrize(
    ("source", "destination"),
    [((0, 4, 0), (0, 3, 0)), ((0, 4, 0), (1, 9, 0)), ((0, 4, 2), (0, 4, 1))],
)
def test_ordered_grant_must_establish_the_mapped_order_at_the_committed_readback(source, destination) -> None:
    # The grant repeats the committed coordinates exactly, but they do not
    # support the claimed order: a later mapped tick, another segment, or a
    # later source microstep at an equal mapped tick.
    _, _, reports = _scenario("mixed-edge")
    grant = _restage(
        reports[0], source_coordinate=_coordinate(*source), destination_coordinate=_coordinate(*destination)
    )
    committed = _time_state(source, destination)
    with pytest.raises(ValueError, match="required order"):
        _validate("mixed-edge", reports=[grant, *reports[1:]], time_state=committed)


@pytest.mark.parametrize(
    ("scenario", "index", "impostor"),
    [
        ("mixed-edge", 0, 1),  # the bridge cannot grant its own time order
        ("mixed-edge", 1, 2),  # a reader cannot report bridge execution
        ("mixed-edge", 2, 1),  # the bridge cannot report destination delivery
        ("mixed-edge", 3, 1),  # nor participant observation
        ("mixed-handoff", 1, 2),  # the owner reader cannot report the transfer
        ("mixed-handoff", 2, 1),  # the transfer service cannot read back its own result
    ],
)
def test_each_stage_must_name_the_service_pinned_for_its_role(scenario: str, index: int, impostor: int) -> None:
    _, responses, reports = _scenario(scenario)
    reports[index] = _restage(reports[index], producer=reports[impostor].stage.producer.model_dump(mode="json"))
    with pytest.raises(ValueError, match="names a producer other than"):
        _validate(scenario, responses=responses, reports=reports)


def _rebind(binding: contracts.MixedBackendExecutionBindingModel, name: str = "mixed-edge") -> tuple:
    """Recommit a scenario's request and correlated messages to another installed binding."""

    request, responses, reports = _scenario(name)
    request = request.model_copy(update={"command": contracts.mixed_backend_binding_reference(binding)})
    digest = contracts.backend_operation_request_digest(request)
    rebound = [message.model_copy(update={"request_digest": digest}) for message in (*responses, *reports)]
    return request, rebound[: len(responses)], rebound[len(responses) :]


def test_an_observation_report_needs_a_pinned_observation_reader() -> None:
    binding = _binding(observation_reader=None)
    request, responses, reports = _rebind(binding)
    context = _stage_context("mixed-edge")
    with pytest.raises(ValueError, match="names a producer other than"):
        contracts.validate_mixed_backend_stage_reports(binding, request, responses, reports, context=context)


def _foreign_time_state() -> dict:
    return {"time_state": _time_state(declaration=_declaration(description="another emulation clock"))}


def _uncovered_clocks() -> dict:
    declaration = _declaration(address="time.clocks.other")
    return {"time_model": declaration, "time_state": _time_state(declaration=declaration), "post_time_state": None}


def _foreign_post_time_state() -> dict:
    return {"post_time_state": _time_state(declaration=_declaration(description="another emulation clock"))}


def _composition_after_handoff() -> dict:
    # The transition already happened at the same head and revision.
    return {"composition_state": _composition_state(phase_id="phase.emu", active_component_ids=["emu"])}


@pytest.mark.parametrize(
    ("scenario", "trusted", "message"),
    [
        ("mixed-edge", _foreign_time_state, "declaration_digest does not match"),
        ("mixed-edge", _uncovered_clocks, "does not cover the bound clocks"),
        ("mixed-edge", _foreign_post_time_state, "declaration_digest does not match"),
        ("mixed-edge", lambda: {"time_model_digest": "sha256:" + "e" * 64}, "time model reference or digest"),
        ("mixed-handoff", lambda: {"time_model_ref": "time-model:other"}, "time model reference or digest"),
        ("mixed-handoff", lambda: {"composition_state": None}, "requires the committed composition state"),
        (
            "mixed-handoff",
            lambda: {"composition_state": _composition_state(profile_id="profile:other")},
            "belongs to another profile",
        ),
        ("mixed-handoff", _composition_after_handoff, "does not precede the native handoff"),
        (
            "mixed-handoff",
            lambda: {"composition_state": _composition_state(active_component_ids=["sim", "emu"])},
            "does not precede the native handoff",
        ),
        (
            "mixed-handoff",
            lambda: {"composition_state": _composition_state(active_component_ids=["other"])},
            "does not precede the native handoff",
        ),
        ("mixed-edge", lambda: {"composition_state": _edge_composition_state()}, "does not activate the bound edge"),
    ],
)
def test_trusted_inputs_must_match_the_binding_time_model_clocks_and_composition(scenario, trusted, message) -> None:
    overrides = trusted()
    with pytest.raises(ValueError, match=message):
        _validate(scenario, **overrides)


def test_an_edge_validates_against_a_composition_state_that_activates_it() -> None:
    _validate("mixed-edge", composition_state=_edge_composition_state("edge.sim-to-emu"))


@pytest.mark.parametrize(
    ("handoff", "readback"),
    [
        ({"predecessor_history_head": "composition:foreign:head"}, {}),
        ({"phase_revision": 41}, {}),
        ({"predecessor_history_head": "composition:foreign:head", "phase_revision": 41}, {"phase_revision": 42}),
    ],
)
def test_native_handoff_is_fenced_on_the_committed_composition_head_and_revision(handoff, readback) -> None:
    _, responses, reports = _scenario("mixed-handoff")
    reports[1:] = [_restage(reports[1], **handoff), _restage(reports[2], **readback)]
    with pytest.raises(ValueError, match="committed composition history head or phase revision"):
        _validate("mixed-handoff", responses=responses, reports=reports)


FAILED_EXECUTION = {"status": "failed", "cessation_evidence_refs": ["evidence:provider-cessation"]}


@pytest.mark.parametrize("execution", [{"status": "unknown", "evidence_refs": []}, FAILED_EXECUTION])
def test_unknown_or_failed_execution_cannot_support_a_success_outcome(execution: dict) -> None:
    _, responses, reports = _scenario("mixed-edge")
    weakened = [reports[0], _restage(reports[1], **execution)]
    with pytest.raises(ValueError, match="claims more"):
        _validate("mixed-edge", responses=responses, reports=weakened)


def test_partial_execution_cannot_settle_as_a_known_failure() -> None:
    _, responses, reports = _scenario("mixed-edge-partial")
    effects = responses[-1].message.effects.model_dump(mode="json") | {"cessation_established": True}
    failed = _remessage(responses[-1], proposed_state="failed", satisfaction="unsatisfied", effects=effects)
    with pytest.raises(ValueError, match="claims more"):
        _validate("mixed-edge-partial", responses=[responses[0], failed], reports=reports)


def test_known_failed_execution_cannot_be_followed_by_delivery() -> None:
    _, responses, reports = _scenario("mixed-edge")
    delivered_after_failure = [reports[0], _restage(reports[1], **FAILED_EXECUTION), reports[2]]
    with pytest.raises(ValueError, match="cannot be followed by delivery"):
        _validate("mixed-edge", responses=responses[:2], reports=delivered_after_failure)


def test_known_failed_execution_settles_without_post_effect_time() -> None:
    _, responses, reports = _scenario("mixed-edge")
    failed = _restage(reports[1], **FAILED_EXECUTION)
    transcript = [*responses[:-1], _failed_outcome(responses[-1], failed)]
    _validate("mixed-edge", responses=transcript, reports=[reports[0], failed], post_time_state=None)


@pytest.mark.parametrize("scenario", ["mixed-edge", "mixed-handoff"])
def test_incomparable_grant_without_invocation_settles_as_known_failure(scenario: str) -> None:
    _, responses, reports = _scenario(scenario)
    grant = _restage(reports[0], comparison="incomparable")
    transcript = [*responses[:-1], _failed_outcome(responses[-1], grant)]
    _validate(scenario, responses=transcript, reports=[grant], post_time_state=None)


@pytest.mark.parametrize("scenario", ["mixed-edge", "mixed-handoff"])
def test_an_ordered_grant_without_invocation_establishes_no_failure(scenario: str) -> None:
    # The invocation may have started without reporting, so nothing is known.
    _, responses, reports = _scenario(scenario)
    transcript = [*responses[:-1], _failed_outcome(responses[-1], reports[0])]
    with pytest.raises(ValueError, match="claims more"):
        _validate(scenario, responses=transcript, reports=reports[:1])


@pytest.mark.parametrize("scenario", ["mixed-edge", "mixed-handoff", "mixed-handoff-stale"])
@pytest.mark.parametrize("post", ["missing", "regressed"])
def test_settlement_needs_a_confirmed_post_invocation_time_readback(scenario: str, post: str) -> None:
    readback = {"missing": None, "regressed": _time_state(source=(0, 3, 0))}[post]
    with pytest.raises(ValueError, match="claims more"):
        _validate(scenario, post_time_state=readback)


def test_contextual_refusal_permits_a_grant_record_but_no_invocation_stage() -> None:
    refused, _, _ = _scenario("mixed-edge-refused")
    _, _, reports = _scenario("mixed-edge")
    correlation = {
        "binding": refused.binding.model_dump(mode="json"),
        "request_digest": contracts.backend_operation_request_digest(refused),
    }
    rebound = [
        contracts.MixedBackendStageReportModel.model_validate(report.model_dump(mode="json") | correlation)
        for report in reports[:2]
    ]
    _validate("mixed-edge-refused", reports=rebound[:1])
    with pytest.raises(ValueError, match="accepted acknowledgement"):
        _validate("mixed-edge-refused", reports=rebound)


@pytest.mark.parametrize(
    ("scenario", "index", "stage", "message"),
    [
        (
            "mixed-handoff",
            2,
            {"owner_component_id": "sim", "owner_ref": "native-ownership:sim", "phase_revision": 0},
            "claims more",
        ),
        (
            "mixed-handoff-stale",
            2,
            {"owner_component_id": "emu", "owner_ref": "native-ownership:emu", "phase_revision": 1},
            "claims more",
        ),
        ("mixed-handoff", 1, {"status": "pending"}, "claims more"),
        ("mixed-handoff", 1, {"order_ref": "order:other"}, "granted order"),
        ("mixed-handoff", 1, {"evidence_refs": ["evidence:native-transfer"]}, "admitted evidence"),
    ],
)
def test_handoff_settles_only_on_a_correlated_matching_owner_readback(scenario, index, stage, message) -> None:
    _, responses, reports = _scenario(scenario)
    reports[index] = _restage(reports[index], **stage)
    with pytest.raises(ValueError, match=message):
        _validate(scenario, responses=responses, reports=reports)


def test_committed_transfer_without_owner_readback_cannot_settle() -> None:
    _, responses, reports = _scenario("mixed-handoff")
    with pytest.raises(ValueError, match="claims more"):
        _validate("mixed-handoff", responses=responses, reports=reports[:2])


@pytest.mark.parametrize("contract_id", MIXED_BACKEND_CONTRACT_IDS)
def test_published_schema_matches_the_bundle_and_classifies_the_example_corpus(contract_id: str) -> None:
    schema = json.loads((ROOT / f"contracts/schemas/control-plane/{contract_id}.json").read_text(encoding="utf-8"))
    assert schema == contracts.schema_bundle()[contract_id]
    model = (
        contracts.MixedBackendExecutionBindingModel
        if contract_id == BINDING
        else contracts.MixedBackendStageReportModel
    )
    for kind in ("valid", "context-invalid"):
        for path in sorted((FIXTURES / contract_id / kind).glob("*.json")):
            payload = json.loads(path.read_text(encoding="utf-8"))
            Draft202012Validator(schema).validate(payload)
            model.model_validate(payload)
    invalid = sorted((FIXTURES / contract_id / "invalid").glob("*.json"))
    assert invalid
    for path in invalid:
        payload = json.loads(path.read_text(encoding="utf-8"))
        with pytest.raises(ValidationError):
            model.model_validate(payload)


@pytest.mark.parametrize(
    ("family", "name", "change", "message"),
    [
        (BINDING, "mixed-handoff", {"destination_component_id": "sim"}, "distinct source and destination"),
        (STAGES, "mixed-edge-02", {"status": "succeeded", "evidence_refs": []}, "require readback evidence"),
        (STAGES, "mixed-edge-02", {"status": "partial", "evidence_refs": []}, "require readback evidence"),
    ],
)
def test_closed_models_refuse_contradictory_local_facts(family: str, name: str, change: dict, message: str) -> None:
    payload = _fixture(family, "valid", name)
    payload["subject" if family == BINDING else "stage"].update(change)
    model = contracts.MixedBackendExecutionBindingModel if family == BINDING else contracts.MixedBackendStageReportModel
    with pytest.raises(ValidationError, match=message):
        model.model_validate(payload)


def test_context_invalid_examples_fail_their_trusted_joins() -> None:
    profile = _runtime_mixed_profile()
    bridge = contracts.MixedBackendExecutionBindingModel.model_validate(
        _fixture(BINDING, "context-invalid", "foreign-bridge")
    )
    context = _context(profile)
    with pytest.raises(ValueError, match="differs from the admitted edge"):
        contracts.validate_mixed_backend_bindings(profile, context, [bridge])
    _, responses, reports = _scenario("mixed-edge")
    foreign = contracts.MixedBackendStageReportModel.model_validate(
        _fixture(STAGES, "context-invalid", "foreign-invocation")
    )
    with pytest.raises(ValueError, match="another invocation"):
        _validate("mixed-edge", responses=responses, reports=[*reports, foreign])


def _accepts(*names: str) -> dict:
    return {name: (lambda request: request) for name in names}


BRIDGE = dict(
    operation_capabilities=lambda: None,
    execution_binding=lambda: None,
    **_accepts("check_operation", "start_operation", "observe_operation", "cancel_operation", "reconcile_operation"),
    stage_reports=lambda control: control,
)
SERVICES = {
    "bridge": BRIDGE,
    "coordinator": {"grant": lambda request, time_state: (request, time_state)},
    "reader": {"read_stage": lambda control: control},
}
DECLARED = (*BACKEND_OPERATION_CONTRACT_IDS, *MIXED_BACKEND_CONTRACT_IDS)


@pytest.mark.parametrize("role", sorted(SERVICES))
def test_service_declarations_and_call_shapes_are_checked_without_invocation(role: str) -> None:
    from types import SimpleNamespace

    installed, empty = SimpleNamespace(**SERVICES[role]), SimpleNamespace()
    narrowed = SimpleNamespace(**{name: (lambda: None) for name in SERVICES[role]})
    require_mixed_backend_service(installed, role, DECLARED)
    with pytest.raises(ValueError, match="not declared"):
        require_mixed_backend_service(installed, role, BACKEND_OPERATION_CONTRACT_IDS)
    with pytest.raises(ValueError, match="not installed"):
        require_mixed_backend_service(empty, role, DECLARED)
    with pytest.raises(ValueError, match="call shape"):
        require_mixed_backend_service(narrowed, role, DECLARED)


def test_stub_and_reference_backends_do_not_advertise_mixed_backend_contracts() -> None:
    from raes_backend_stubs.manifest import create_stub_manifest
    from raes_reference_backend.manifest import REFERENCE_BACKEND_SUPPORTED_CONTRACT_VERSIONS

    assert set(MIXED_BACKEND_CONTRACT_IDS).isdisjoint(create_stub_manifest().supported_contract_versions)
    assert set(MIXED_BACKEND_CONTRACT_IDS).isdisjoint(REFERENCE_BACKEND_SUPPORTED_CONTRACT_VERSIONS)
