"""Compiled view relations key authored action and binding classifications by address (issue #1572).

Authors classify participant visibility by authored reference: `action_contracts.<name>` and
`behavior_specifications.<spec>.tool_affordances.<id>`. Decision-surface projection, history
anchoring and exposure read the compiled view relation by runtime address. The compiler resolves
those two declaration kinds to their canonical addresses (ADR-076 section 3) and carries every
other information ref as written. Two classifications of one declaration in one boundary fail
compilation instead of letting one disposition silently replace the other.
"""

from __future__ import annotations

import re
from dataclasses import replace
from pathlib import Path

import pytest
from raes import parse_sdl
from raes_backend_stubs.stubs import create_stub_target
from raes_processor.compiler import compile_runtime_model
from raes_processor.models import (
    ParticipantBehaviorHistoryEvent,
    ParticipantBehaviorProjectionAnchorRequestV2,
    RuntimeModel,
    project_participant_decision_surface,
    project_participant_decision_surface_v2,
    resolve_participant_behavior_projection_anchor_v2,
    resolve_participant_episode_readiness_anchor_v2,
)
from raes_runtime.control_plane import RuntimeControlPlane
from test_issue_297_behavior_authoring import NAMESPACES, ROOT, _compose, _edited
from test_sem_220_participant_decision_surface import (
    BOUNDARY,
    EPISODE,
    EXFILTRATE,
    PARTICIPANT,
    SCAN,
    SCAN_AFFORDANCE,
    _admission_request,
    _history,
    _projection_exposure_resolvers,
    _projection_input,
    _runtime_model,
)
from test_sem_220_participant_decision_surface_v2_runtime import _exposure_resolvers, _projection

FIXTURE = Path(__file__).parent / "fixtures" / "view-relation-keys" / "authored-classifications.sdl.yaml"
SCANNER_REF = "behavior_specifications.red-surface.tool_affordances.scanner"
SCAN_RULE = "      - information_ref: action_contracts.scan\n"
SCANNER_BASIS = "        visibility_basis: the scanner binding is visible with its action\n"
SCAN_BASIS = "        visibility_basis: red participants see scanning from the start\n"
LITERAL_SCAN = (
    (SCAN_RULE, f"      - information_ref: {SCAN}\n"),
    ("      - action_contracts.scan\n", f"      - {SCAN}\n"),
)
SCANNER_TWIN = (
    (f"      - {SCANNER_REF}\n", f"      - {SCANNER_REF}\n      - {SCAN_AFFORDANCE}\n"),
    (
        SCANNER_BASIS,
        SCANNER_BASIS + f"      - information_ref: {SCAN_AFFORDANCE}\n"
        "        boundary_class: observable_resource\n"
        "        disposition: observable\n"
        "        visibility_basis: runtime-address copy of the scanner binding\n",
    ),
)
SCAN_TWIN = (
    ("    hidden_refs:\n", f"    hidden_refs:\n      - {SCAN}\n"),
    (
        SCAN_BASIS,
        SCAN_BASIS + f"      - information_ref: {SCAN}\n"
        "        boundary_class: observable_resource\n"
        "        disposition: hidden\n"
        "        visibility_basis: runtime-address copy of the scan action\n",
    ),
)
# Observed on dev cf8b4308 (before this change) for the document with both spellings of the
# scanner binding (LITERAL_SCAN plus SCANNER_TWIN), at v1 observation_order 0 and at both v2 anchors.
DEV_SCAN_VIEW = {
    "visible_context_refs": ["context.public"],
    "affordance_refs": [SCAN_AFFORDANCE],
    "action_entries": [(SCAN, "observable", [SCAN_AFFORDANCE])],
}


def _document(*edits: tuple[str, str]) -> str:
    return _edited(FIXTURE.read_text(encoding="utf-8"), edits)


def _compiled(*edits: tuple[str, str]) -> RuntimeModel:
    return compile_runtime_model(parse_sdl(_document(*edits)))


def _for_model(projection, model: RuntimeModel):
    """Use the compiled argument shapes and assess only the bindings the model declares."""

    return replace(
        projection,
        action_assessments={
            address: replace(assessment, selection_shape_ref=model.action_contracts[address].argument_shape_ref)
            for address, assessment in projection.action_assessments.items()
        },
        exposure_assessments={
            ref: assessment
            for ref, assessment in projection.exposure_assessments.items()
            if ".tool-affordance." not in ref or ref in model.tool_affordances
        },
    )


def _project_v1(model: RuntimeModel, *, observation_order: int = 0, action_address: str = SCAN):
    projection = _for_model(
        _projection_input(observation_order=observation_order, action_address=action_address),
        model,
    )
    return project_participant_decision_surface(
        model,
        history_events=_history(),
        projection=projection,
        exposure_resolvers=_projection_exposure_resolvers(projection),
    )


def _project_v2(model: RuntimeModel, *, behavior_anchor: bool = False):
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
    history: tuple[ParticipantBehaviorHistoryEvent, ...] = ()
    if behavior_anchor:
        # The stub target's admission history has no reveal-1 observation and no SEM-211 action
        # results. As in the SEM-220 later-epoch test, this case keeps the compiled initial relation
        # without its transitions and drops the contracts' SEM-211 classes.
        boundary = model.observation_boundaries[BOUNDARY]
        model = replace(
            model,
            action_contracts={
                address: replace(contract, precondition_classes=(), effect_classes=(), failure_classes=())
                for address, contract in model.action_contracts.items()
            },
            observation_boundaries={
                BOUNDARY: replace(
                    boundary,
                    view_transitions=(),
                    view_relation_timeline=boundary.view_relation_timeline[:1],
                )
            },
        )
        _, selection = _exposure_resolvers(_projection(anchor))
        control.admit_participant_action(
            model.participant_behaviors[PARTICIPANT],
            replace(_admission_request(), implementation_selection=selection),
        )
        snapshot = control.get_snapshot().snapshot
        history = tuple(
            ParticipantBehaviorHistoryEvent.from_payload(payload)
            for payload in snapshot.participant_behavior_history[PARTICIPANT]
        )
        anchor = resolve_participant_behavior_projection_anchor_v2(
            snapshot,
            runtime_model=model,
            request=ParticipantBehaviorProjectionAnchorRequestV2(
                participant_address=PARTICIPANT,
                episode_id=EPISODE,
                decision_epoch=1,
                behavior_history_order=2,
                evidence_refs=("evidence.scan-result",),
                provenance_refs=("provenance.runtime-control-plane",),
            ),
        )
    projection = _for_model(_projection(anchor), model)
    resolvers, _ = _exposure_resolvers(projection)
    surface = project_participant_decision_surface_v2(
        model,
        snapshot,
        history_events=history,
        projection=projection,
        exposure_resolvers=resolvers,
    )
    return surface.participant_view


def _view_summary(view) -> dict[str, object]:
    return {
        "visible_context_refs": list(view.visible_context_refs),
        "affordance_refs": list(view.affordance_refs),
        "action_entries": [
            (entry.action_contract_address, entry.visibility, list(entry.affordance_refs))
            for entry in view.action_entries
        ],
    }


def _relations(model: RuntimeModel) -> list[dict[str, str]]:
    return [dict(item["view_relation"]) for item in model.observation_boundaries[BOUNDARY].view_relation_timeline]


def test_authored_classifications_compile_to_the_hand_built_relation() -> None:
    compiled = _compiled()
    hand_built = _runtime_model().observation_boundaries[BOUNDARY]
    relations = _relations(compiled)

    assert relations[0] == hand_built.view_relation_timeline[0]["view_relation"]
    assert relations[-1] == hand_built.view_relation_timeline[-1]["view_relation"]
    assert [item["information_ref"] for item in compiled.observation_boundaries[BOUNDARY].view_transitions] == [
        item["information_ref"] for item in hand_built.view_transitions
    ]
    spec = compiled.observation_boundaries[BOUNDARY].spec
    assert [rule["information_ref"] for rule in spec["view_rules"]][1:3] == ["action_contracts.scan", SCANNER_REF]
    assert SCANNER_REF in compiled.observation_boundaries[BOUNDARY].observable_refs


def test_v1_projection_reads_authored_classifications_at_each_history_index() -> None:
    model = _compiled()

    with pytest.raises(ValueError, match="is not participant-visible at observation_order 0"):
        _project_v1(model, observation_order=0, action_address=EXFILTRATE)
    revealed = _project_v1(model, observation_order=1, action_address=EXFILTRATE)
    assert revealed.action_entries[0].visibility == "disclosed"
    assert _view_summary(_project_v1(model)) == DEV_SCAN_VIEW


@pytest.mark.parametrize("behavior_anchor", [False, True], ids=["episode-readiness", "behavior-history"])
def test_v2_projection_reads_authored_classifications(behavior_anchor: bool) -> None:
    assert _view_summary(_project_v2(_compiled(), behavior_anchor=behavior_anchor)) == DEV_SCAN_VIEW


@pytest.mark.parametrize(
    ("edits", "address", "spellings"),
    [
        ((*LITERAL_SCAN, *SCANNER_TWIN), SCAN_AFFORDANCE, (SCANNER_REF, SCAN_AFFORDANCE)),
        (SCAN_TWIN, SCAN, ("action_contracts.scan", SCAN)),
    ],
    ids=["binding-and-its-address", "action-and-its-address"],
)
def test_one_declaration_classified_under_two_spellings_fails_compilation(
    edits: tuple[tuple[str, str], ...],
    address: str,
    spellings: tuple[str, str],
) -> None:
    scenario = parse_sdl(_document(*edits))
    message = f"observation boundary red-view classifies {address} more than once: {', '.join(spellings)}"

    with pytest.raises(ValueError, match=re.escape(message)):
        compile_runtime_model(scenario)


def test_migrated_document_projects_the_surfaces_the_two_spelling_document_projected() -> None:
    migrated = _compiled(*LITERAL_SCAN)

    assert _relations(migrated)[0][SCAN] == "observable"
    assert _view_summary(_project_v1(migrated)) == DEV_SCAN_VIEW
    assert _view_summary(_project_v2(migrated)) == DEV_SCAN_VIEW


def test_imported_classifications_compile_to_namespaced_addresses(tmp_path: Path) -> None:
    binding = (
        "    behavior_mode: policy-directed\n",
        "    behavior_mode: policy-directed\n"
        "    tool_affordances:\n"
        "      scanner:\n"
        "        action_contract_refs: [scan]\n"
        "        observation_boundary_refs: [red-view]\n",
    )
    classified = (
        "    observable_refs: []\n",
        "    observable_refs: [action_contracts.scan, behavior_specifications.red-scan-behavior.tool_affordances.scanner]\n"
        "    view_rules:\n"
        "      - information_ref: action_contracts.scan\n"
        "        boundary_class: observable_resource\n"
        "        disposition: observable\n"
        "        visibility_basis: declared participant action\n"
        "      - information_ref: behavior_specifications.red-scan-behavior.tool_affordances.scanner\n"
        "        boundary_class: observable_resource\n"
        "        disposition: discovered\n"
        "        visibility_basis: declared participant tool\n",
    )
    boundaries = compile_runtime_model(_compose(tmp_path, unit_edits=(binding, classified))).observation_boundaries

    for namespace in NAMESPACES:
        boundary = boundaries[f"participant.observation-boundary.{namespace}.red-view"]
        assert boundary.view_relation_timeline[0]["view_relation"] == {
            f"participant.action-contract.{namespace}.scan": "observable",
            f"participant.behavior-specification.{namespace}.red-scan-behavior.tool-affordance.scanner": "discovered",
        }


def test_bare_names_stay_opaque_and_projection_fails_closed() -> None:
    model = _compiled(
        (SCAN_RULE, "      - information_ref: scan\n"), ("      - action_contracts.scan\n", "      - scan\n")
    )

    assert "scan" in _relations(model)[0]
    assert SCAN not in _relations(model)[0]
    with pytest.raises(
        ValueError, match=re.escape(f"lack an effective view disposition at observation_order 0: {SCAN}")
    ):
        _project_v1(model)


def test_literal_address_classifications_compile_unchanged_and_project() -> None:
    text = _document().replace("action_contracts.", "participant.action-contract.").split("    tool_affordances:\n")[0]
    authored = [
        line.removeprefix("      - information_ref: ") for line in text.splitlines() if "- information_ref: " in line
    ]
    model = compile_runtime_model(parse_sdl(text))
    literal_view = {**DEV_SCAN_VIEW, "affordance_refs": [], "action_entries": [(SCAN, "observable", [])]}

    assert set(_relations(model)[0]) == set(authored)
    assert _view_summary(_project_v1(model)) == literal_view
    assert _view_summary(_project_v2(model)) == literal_view


def test_a_token_that_names_two_declarations_fails_compilation(tmp_path: Path) -> None:
    local_scan = _document().split("action_contracts:\n", 1)[1].split("  exfiltrate:\n", 1)[0]
    ambiguous_root = (
        "name: ambiguous-action-ref\n"
        "imports:\n"
        "  - source: local:scan-behavior.sdl.yaml\n"
        "    namespace: action_contracts\n"
        "    version: 1.2.0\n"
        f"action_contracts:\n{local_scan}"
        "observation_boundaries:\n"
        "  local-view:\n"
        "    projection_basis: local view of the scan action\n"
        "    observable_refs: [action_contracts.scan]\n"
        "    redaction_policy: no hidden refs are disclosed\n"
        "    latency_profile: immediate\n"
        "    view_rules:\n"
        "      - information_ref: action_contracts.scan\n"
        "        boundary_class: observable_resource\n"
        "        disposition: observable\n"
        "        visibility_basis: declared participant action\n"
    )
    scenario = _compose(tmp_path, root_edits=((ROOT.read_text(encoding="utf-8"), ambiguous_root),))

    assert {"scan", "action_contracts.scan"} <= set(scenario.action_contracts)
    message = "observation boundary local-view information_ref action_contracts.scan is ambiguous"
    with pytest.raises(ValueError, match=re.escape(message)):
        compile_runtime_model(scenario)
