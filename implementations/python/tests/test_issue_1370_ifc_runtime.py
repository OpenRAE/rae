"""Live API-424/v2 gate blocks loss of an admitted IFC support promise."""

from dataclasses import replace

import pytest
from participant_control_contract_fixtures import ref
from participant_control_v2_fixtures import Resolver, binding
from participant_crossing_fixtures import admit
from raes_contracts.contracts.participant_control_applicability import ParticipantControlSelectionV2Model
from test_issue_1069_participant_control_orchestration import _evaluations, _instrument_backend, _plane, control_target


def test_runtime_blocks_affected_provider_and_backend_after_losing_admitted_strength():
    owner = Resolver()
    selection = owner.selection.model_dump(mode="json")
    for item in [*selection["slots"], *selection["obligations"]]:
        item.update(required_strength="bounded", constraints=[ref("bounded-constraint", "constraint")])
    selection["obligations"][0]["admitted_support"] = [owner.base["support"][0]]
    owner.selection = ParticipantControlSelectionV2Model.model_validate(selection)
    owner.effective_level, owner.support_relation = "bounded", "bounded-compatible"
    target = control_target()
    calls = _instrument_backend(target)
    plane = _plane(binding(owner), target=target)
    try:
        receipt = admit(plane, idempotency_key="lost-ifc-promise")
        assert receipt.accepted  # The operation records the refusal durably.
        assert calls["calls"] == 0
        assert "rule" not in owner.calls
        assert _evaluations(plane)[0]["composition"]["disposition"] == "weakened"
    finally:
        plane.close()


@pytest.mark.parametrize(
    "reader,observation,grants,expected",
    [
        ("reader:carol", True, True, 1),
        ("reader:alice", True, True, 0),
        ("reader:carol", False, True, 0),
        ("reader:carol", True, False, 0),
    ],
)
def test_live_owner_sink_allows_selective_sharing_and_blocks_other_owner_release(reader, observation, grants, expected):
    from participant_crossing_fixtures import policy_capable_target
    from raes_runtime.participant_flow_sink import ParticipantFlowSinkResolution
    from sem233_flow_sink_fixtures import Sem233FlowSinkResolver, sem233_plane
    from test_issue_1370_ifc_profiles import owner_relation

    class OwnerResolver(Sem233FlowSinkResolver):
        def resolve_flow_sink_decision(self, **coords):
            base = super().resolve_flow_sink_decision(**coords)
            relation, context = owner_relation(
                reader=reader, observation=observation, base_relation=base.relation, base_context=base.context
            )
            if not grants:
                context = replace(context, owner_release_authorities=())
            return ParticipantFlowSinkResolution(relation, context)

    target = policy_capable_target()
    calls = _instrument_backend(target)
    plane = sem233_plane(OwnerResolver(), target=target)
    try:
        admit(plane, idempotency_key="owner-selective-sharing")
        assert calls["calls"] == expected
        assert plane.audit_log()[-1].details.get("flow_final_disposition") == (
            "permit" if expected else "deny" if grants else "unresolved"
        )
    finally:
        plane.close()
