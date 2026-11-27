"""Shared-profile projection must respect each participant's own declarations."""

from dataclasses import replace

import pytest
from raes_backend_stubs.stubs import create_stub_target
from raes_processor.models import (
    ParticipantBehaviorRuntime,
    project_participant_decision_surface,
    project_participant_decision_surface_v2,
    resolve_participant_episode_readiness_anchor_v2,
)
from raes_runtime.control_plane import RuntimeControlPlane
from test_sem_220_participant_decision_surface import (
    BOUNDARY,
    EPISODE,
    PARTICIPANT,
    SCAN,
    SCAN_AFFORDANCE,
    _history,
    _projection_exposure_resolvers,
    _projection_input,
    _runtime_model,
)
from test_sem_220_participant_decision_surface_v2_runtime import _exposure_resolvers, _projection


def _model():
    return replace(
        _runtime_model(),
        participant_behaviors={
            PARTICIPANT: ParticipantBehaviorRuntime(
                address=PARTICIPANT,
                name="red-agent",
                spec={},
                participant_name="red-agent",
                action_contract_addresses=(SCAN,),
                observation_boundary_addresses=(BOUNDARY,),
            )
        },
    )


def _project(model, version, *, boundary=BOUNDARY, omit_binding=False):
    def inputs(projection):
        return replace(
            projection,
            observation_boundary_address=boundary,
            exposure_assessments={
                ref: assessment
                for ref, assessment in projection.exposure_assessments.items()
                if not omit_binding or ref != SCAN_AFFORDANCE
            },
            action_assessments={
                ref: replace(assessment, selection_shape_ref=model.action_contracts[ref].argument_shape_ref)
                for ref, assessment in projection.action_assessments.items()
            },
        )

    if version == "v1":
        projection = inputs(_projection_input(observation_order=0))
        return project_participant_decision_surface(
            model,
            history_events=_history(),
            projection=projection,
            exposure_resolvers=_projection_exposure_resolvers(projection),
        )
    control = RuntimeControlPlane(create_stub_target())
    control.initialize_participant_episode(PARTICIPANT, episode_id=EPISODE)
    snapshot = control.get_snapshot().snapshot
    anchor = resolve_participant_episode_readiness_anchor_v2(
        snapshot,
        participant_address=PARTICIPANT,
        decision_epoch=0,
        evidence_refs=("evidence.episode-running",),
        provenance_refs=("provenance.runtime-control-plane",),
    )
    projection = inputs(_projection(anchor))
    resolvers, _ = _exposure_resolvers(projection)
    return project_participant_decision_surface_v2(
        model, snapshot, history_events=(), projection=projection, exposure_resolvers=resolvers
    )


@pytest.mark.parametrize("version", ("v1", "v2"))
@pytest.mark.parametrize("missing", ("action", "boundary", "participant"))
def test_projection_rejects_missing_participant_declarations(version, missing):
    model = _model()
    participant = model.participant_behaviors[PARTICIPANT]
    if missing == "participant":
        model = replace(model, participant_behaviors={})
    else:
        field = "action_contract_addresses" if missing == "action" else "observation_boundary_addresses"
        model = replace(model, participant_behaviors={PARTICIPANT: replace(participant, **{field: ()})})

    with pytest.raises(ValueError, match="compiled participant"):
        _project(model, version)


@pytest.mark.parametrize("version", ("v1", "v2"))
def test_projection_preserves_declared_participant_actions(version):
    surface = _project(_model(), version)
    view = surface if version == "v1" else surface.participant_view
    assert [entry.action_contract_address for entry in view.action_entries] == [SCAN]


@pytest.mark.parametrize("version", ("v1", "v2"))
def test_binding_is_only_offered_at_its_declared_boundaries(version):
    model = _model()
    other = BOUNDARY + "-other"
    boundary = model.observation_boundaries[BOUNDARY]
    other_boundary = replace(
        boundary,
        address=other,
        view_transitions=(),
        view_relation_timeline=(
            {
                "transition_id": "initial",
                "effective_order": -1,
                "view_relation": {"context.public": "observable", SCAN: "observable"},
            },
        ),
    )
    model = replace(
        model,
        observation_boundaries={**model.observation_boundaries, other: other_boundary},
        participant_behaviors={
            PARTICIPANT: replace(
                model.participant_behaviors[PARTICIPANT], observation_boundary_addresses=(BOUNDARY, other)
            )
        },
        behavior_specifications={
            address: replace(spec, observation_boundary_addresses=(BOUNDARY, other))
            for address, spec in model.behavior_specifications.items()
        },
    )

    surface = _project(model, version, boundary=other, omit_binding=True)
    view = surface if version == "v1" else surface.participant_view
    assert view.action_entries[0].affordance_refs == []
    original = _project(model, version)
    original_view = original if version == "v1" else original.participant_view
    assert original_view.action_entries[0].affordance_refs == [SCAN_AFFORDANCE]
