"""Reusable participant tool profiles (issue #301, ACT-619).

The behavior specification is the profile: its ``tool_affordances`` plus its
participant and role selection. A binding may carry its own participant selector,
which only narrows the specification's selection. One profile (`toolkit`) is used
by two roles with different availability (selector), visibility (bound boundary)
and invocation constraints (bound action contract), and the selected profile is
carried through authoring, compilation, v2 projection, admission and evidence.

A profile does not gate admission: SEM-219 D keeps admission independent of
bindings, and the test for it is named after that documented unsupported case.
"""

from __future__ import annotations

import json
from dataclasses import fields, replace

import pytest
from raes import (
    InstantiatedScenario,
    RenameSDLDeclarationRequest,
    Scenario,
    SDLInstantiationError,
    SDLParseError,
    canonical_instantiated_sdl_bytes,
    canonical_instantiated_sdl_digest,
    instantiate_scenario,
    parse_sdl,
    parse_sdl_file,
    rename_sdl_declaration,
)
from raes.participant_behavior_specification import ParticipantToolAffordance
from raes_contracts.participant_binding_v2 import bind_participant_decision_surface_selection_v2
from raes_processor.compiler import compile_runtime_model
from raes_processor.compiler.addresses import _behavior_specification_address
from raes_processor.compiler.participant_behaviors import (
    _compile_behavior_specifications,
    _compile_tool_affordances,
)
from raes_processor.models import project_participant_decision_surface
from test_sem_220_participant_decision_surface import _projection_input
from tool_profile_support import (
    ACTIVE,
    BLUE,
    BLUE_VIEW,
    FIXTURES,
    PASSIVE,
    SCANNER_BLUE,
    SCANNER_WHITE,
    SPEC,
    TOOLKIT,
    WHITE,
    WHITE_VIEW,
    Episode,
    admission_request,
    admit_selection,
    binding_resolvers,
    compiled,
    deliver,
    edited,
    implementation_selection,
    selection_for,
    toolkit_text,
)

SCANNER_BLUE_BLOCK = """\
      scanner-blue:
        tool_ref: nmap
        participant_role_refs: [blue]
        action_contract_refs: [scan-active]
        observation_boundary_refs: [blue-view]
"""
WHITE_SELECTOR_LINE = "        participant_role_refs: [white]\n"
V1_REFUSAL = "participant-scoped tool affordances require participant-decision-surface-v2"


def _white_after_reveal(model=None) -> Episode:
    white = Episode.start(model or compiled(), WHITE, WHITE_VIEW)
    white.reveal(ACTIVE)
    return white


def _entry_affordances(surface) -> dict[str, list[str]]:
    return {
        entry.action_contract_address: list(entry.affordance_refs) for entry in surface.participant_view.action_entries
    }


def test_compiled_bindings_carry_selectors_and_resolved_participants() -> None:
    model = compiled()
    blue, white = model.tool_affordances[SCANNER_BLUE], model.tool_affordances[SCANNER_WHITE]

    assert (blue.participant_refs, blue.participant_role_refs, blue.participant_addresses) == ((), ("blue",), (BLUE,))
    assert (white.participant_role_refs, white.participant_addresses) == (("white",), (WHITE,))
    assert blue.tool_address == white.tool_address == "provision.content.nmap"
    assert BLUE in blue.refresh_dependencies
    assert WHITE not in blue.refresh_dependencies
    assert blue.spec["participant_role_refs"] == ["blue"]
    assert model.behavior_specifications[SPEC].participant_addresses == (BLUE, WHITE)


def test_each_role_is_offered_only_the_bindings_that_select_it() -> None:
    model = compiled()
    blue = Episode.start(model, BLUE, BLUE_VIEW).project((ACTIVE,), (SCANNER_BLUE,))
    white = Episode.start(model, WHITE, WHITE_VIEW).project((ACTIVE,), ())

    assert _entry_affordances(blue) == {ACTIVE: [SCANNER_BLUE]}
    # White declares scan-active and the profile includes it, but scanner-blue does not select white.
    assert ACTIVE in model.participant_behaviors[WHITE].action_contract_addresses
    assert ACTIVE in model.behavior_specifications[SPEC].action_contract_addresses
    assert _entry_affordances(white) == {ACTIVE: []}
    assert white.participant_view.affordance_refs == []


def test_white_binding_is_hidden_with_its_action_until_disclosed() -> None:
    model = compiled()
    white = Episode.start(model, WHITE, WHITE_VIEW)
    with pytest.raises(ValueError, match="refs are not participant-visible at state cut"):
        white.project((PASSIVE,), (SCANNER_WHITE,))

    white.reveal(ACTIVE)
    surface = white.project((ACTIVE, PASSIVE), (SCANNER_WHITE,))

    assert _entry_affordances(surface) == {ACTIVE: [], PASSIVE: [SCANNER_WHITE]}
    # white-view classifies scanner-blue as visible; visibility is not availability.
    initial = model.observation_boundaries[WHITE_VIEW].view_relation_timeline[0]["view_relation"]
    assert initial[SCANNER_BLUE] == "observable"
    assert SCANNER_BLUE not in surface.participant_view.affordance_refs


def test_profile_gated_admission_is_unsupported_white_active_scan_is_admitted_without_a_binding() -> None:
    """Documented unsupported case "profile-gated admission" (SEM-219 D; ADR-083 section 1)."""

    outcomes = []
    for text in (toolkit_text(), edited(toolkit_text(), (SCANNER_BLUE_BLOCK, ""))):
        white = Episode.start(compiled(text), WHITE, WHITE_VIEW)
        receipt = admit_selection(white, white.project((ACTIVE,), ()), ACTIVE, {"rate": 50})
        history = white.control.get_snapshot().snapshot.participant_behavior_history[WHITE]
        outcomes.append((receipt.accepted, [event["action_contract_address"] for event in history]))

    assert outcomes[0] == outcomes[1] == (True, [ACTIVE, ACTIVE, ACTIVE])


def test_admission_refuses_an_undeclared_action_whatever_its_visibility_and_tools() -> None:
    model = compiled()
    blue = Episode.start(model, BLUE, BLUE_VIEW)
    initial = model.observation_boundaries[BLUE_VIEW].view_relation_timeline[0]["view_relation"]
    assert initial[PASSIVE] == "observable"
    assert PASSIVE in model.behavior_specifications[SPEC].action_contract_addresses

    receipt = blue.admit(PASSIVE)

    assert receipt.accepted is False
    assert any("is not declared by compiled participant behavior" in d.message for d in receipt.diagnostics)


@pytest.mark.parametrize(
    ("participant", "action", "rate", "accepted"),
    (
        pytest.param(WHITE, PASSIVE, 50, False, id="white-passive-over-its-domain"),
        pytest.param(WHITE, PASSIVE, 5, True, id="white-passive-within-its-domain"),
        pytest.param(BLUE, ACTIVE, 50, True, id="blue-active-within-its-domain"),
    ),
)
def test_invocation_constraints_come_from_the_bound_action_contract(
    participant: str, action: str, rate: int, accepted: bool
) -> None:
    model = compiled()
    if participant == WHITE:
        episode, affordance = _white_after_reveal(model), SCANNER_WHITE
    else:
        episode, affordance = Episode.start(model, BLUE, BLUE_VIEW), SCANNER_BLUE
    surface = episode.project((action,), (affordance,))

    receipt = admit_selection(episode, surface, action, {"rate": rate})

    assert receipt.accepted is accepted
    rejected = ["participant decision surface argument-shape resolution failed"]
    assert [diagnostic.message for diagnostic in receipt.diagnostics] == ([] if accepted else rejected)


def test_temporal_constraints_stay_on_the_action_contract_not_the_binding() -> None:
    model = compiled()
    binding = model.tool_affordances[SCANNER_WHITE]

    assert model.action_contracts[PASSIVE].temporal_contract_ids == ("passive-cadence",)
    assert PASSIVE in binding.action_contract_addresses
    assert not any("temporal" in field.name for field in fields(binding))
    assert not any("temporal" in key for key in binding.spec)


def test_evidence_identifies_the_profile_by_address_and_its_content_by_snapshot_digest() -> None:
    model = compiled()
    blue = Episode.start(model, BLUE, BLUE_VIEW).project((ACTIVE,), (SCANNER_BLUE,))
    white_episode = _white_after_reveal(model)
    white = white_episode.project((PASSIVE,), (SCANNER_WHITE,))

    assert blue.assurance.behavior_specification_address == white.assurance.behavior_specification_address == SPEC
    assert blue.participant_view.affordance_refs != white.participant_view.affordance_refs
    assert blue.assurance.participant_view_digest != white.assurance.participant_view_digest

    delivered, delivery = deliver(white)
    selection = implementation_selection(WHITE, permitted_refs=("context.public", PASSIVE, SCANNER_WHITE))
    resolvers = binding_resolvers(model, delivery, selection)
    foreign_digest = selection_for(delivered, PASSIVE, {"rate": 5}, digest=blue.assurance.participant_view_digest)
    request = admission_request(WHITE, PASSIVE, WHITE_VIEW, selection=selection)
    with pytest.raises(ValueError, match="selection participant_view_digest must match the canonical participant view"):
        bind_participant_decision_surface_selection_v2(
            surface=delivered,
            selection=foreign_digest,
            admission_request=request,
            argument_shape_resolver=resolvers.argument_shape,
            apparatus_resolver=resolvers.apparatus,
            delivery_resolver=resolvers.delivery,
        )

    snapshot = json.loads(canonical_instantiated_sdl_bytes(instantiate_scenario(parse_sdl_file(TOOLKIT))))
    profiles = snapshot["scenario"]["behavior_specifications"]
    (profile,) = (spec for key, spec in profiles.items() if _behavior_specification_address(key) == SPEC)
    assert profile["semantic_version"] == "1.0.0"
    assert {key: binding["participant_role_refs"] for key, binding in profile["tool_affordances"].items()} == {
        "scanner-blue": ["blue"],
        "scanner-white": ["white"],
    }


def test_semantic_version_is_a_label_and_content_is_pinned_only_by_the_snapshot_digest() -> None:
    changed = edited(
        toolkit_text(),
        (
            "        participant_role_refs: [white]\n        action_contract_refs: [scan-passive]\n",
            "        participant_role_refs: [white]\n        action_contract_refs: [scan-active]\n",
        ),
    )
    original, relabelled = instantiate_scenario(parse_sdl_file(TOOLKIT)), instantiate_scenario(parse_sdl(changed))

    assert relabelled.behavior_specifications["toolkit"].semantic_version == "1.0.0"
    assert canonical_instantiated_sdl_digest(original) != canonical_instantiated_sdl_digest(relabelled)
    assert SPEC in compile_runtime_model(relabelled).behavior_specifications


@pytest.mark.parametrize(
    ("participant", "boundary_error"),
    ((BLUE, None), (WHITE, "probe-white")),
    ids=("blue-agrees-with-its-action", "white-binding-disagrees"),
)
@pytest.mark.parametrize("scoped", (True, False), ids=("scoped", "unscoped-control"))
def test_participant_filter_runs_before_the_one_disposition_check(
    participant: str, boundary_error: str | None, scoped: bool
) -> None:
    text = (FIXTURES / "shared-boundary.sdl.yaml").read_text(encoding="utf-8")
    if not scoped:
        text = text.replace("        participant_role_refs: [blue]\n", "").replace(
            "        participant_role_refs: [white]\n", ""
        )
    spec = "participant.behavior-specification.probes"
    probe_blue, probe_white = f"{spec}.tool-affordance.probe-blue", f"{spec}.tool-affordance.probe-white"
    episode = replace(
        Episode.start(compiled(text), participant, "participant.observation-boundary.ops-view"), spec=spec
    )

    if scoped and boundary_error is None:
        assert _entry_affordances(episode.project((ACTIVE,), (probe_blue,))) == {ACTIVE: [probe_blue]}
        return
    with pytest.raises(ValueError, match="refs are not participant-visible at state cut") as raised:
        episode.project((ACTIVE,), (probe_blue, probe_white))
    assert probe_white in str(raised.value)
    assert probe_blue not in str(raised.value)


def _blue_only_profile(*, scoped: bool) -> str:
    text = edited(
        toolkit_text(),
        ("    participant_role_refs: [blue, white]\n", "    participant_role_refs: [blue]\n"),
        ("    action_contract_refs: [scan-active, scan-passive]\n", "    action_contract_refs: [scan-active]\n"),
        ("    observation_boundary_refs: [blue-view, white-view]\n", "    observation_boundary_refs: [blue-view]\n"),
    )
    # Blue alone never anchors white-view's disclosure transitions, so the blue-only variant drops them.
    text = (
        text[: text.index("    view_transitions:\n")]
        + text[text.index("behavior_specifications:\n") : text.index("      scanner-white:\n")]
    )
    return text if scoped else edited(text, ("        participant_role_refs: [blue]\n", ""))


def test_a_selector_that_covers_the_whole_profile_is_equivalent_to_no_selector() -> None:
    """TP-9: same validation, v2 entries, affordance refs and view digest; only the selector fields differ."""

    models = {scoped: compiled(_blue_only_profile(scoped=scoped)) for scoped in (True, False)}
    surfaces = {
        scoped: Episode.start(model, BLUE, BLUE_VIEW).project((ACTIVE,), (SCANNER_BLUE,))
        for scoped, model in models.items()
    }

    assert surfaces[True].participant_view == surfaces[False].participant_view
    assert surfaces[True].assurance.participant_view_digest == surfaces[False].assurance.participant_view_digest
    scoped, unscoped = models[True].tool_affordances[SCANNER_BLUE], models[False].tool_affordances[SCANNER_BLUE]
    differing = {field.name for field in fields(scoped) if getattr(scoped, field.name) != getattr(unscoped, field.name)}
    assert differing == {"participant_role_refs", "participant_addresses", "refresh_dependencies", "spec"}
    assert {key for key in scoped.spec if scoped.spec[key] != unscoped.spec[key]} == {"participant_role_refs"}
    assert set(scoped.refresh_dependencies) - set(unscoped.refresh_dependencies) == {BLUE}


@pytest.mark.parametrize(
    ("text", "participant", "boundary", "expected"),
    (
        pytest.param(None, WHITE, WHITE_VIEW, V1_REFUSAL, id="two-role-profile"),
        pytest.param(_blue_only_profile(scoped=True), BLUE, BLUE_VIEW, V1_REFUSAL, id="full-coverage-scoped"),
        # The unscoped profile passes the refusal and reaches the next v1 check, on the fixture's foreign action.
        pytest.param(
            _blue_only_profile(scoped=False),
            BLUE,
            BLUE_VIEW,
            "outside the compiled behavior specification",
            id="unscoped",
        ),
    ),
)
def test_v1_projection_refuses_profiles_with_scoped_bindings(
    text: str | None, participant: str, boundary: str, expected: str
) -> None:
    episode = Episode.start(compiled(text), participant, boundary)
    episode.reveal(ACTIVE, action_instance_id="reveal-1" if participant == WHITE else "scan-1")
    _, events, _ = episode.anchor()
    projection = replace(
        _projection_input(observation_order=len(events) - 1),
        participant_address=participant,
        behavior_specification_address=SPEC,
        observation_boundary_address=boundary,
    )

    with pytest.raises(ValueError, match=expected):
        project_participant_decision_surface(
            episode.model, history_events=events, projection=projection, exposure_resolvers=None
        )


def _module_root(tmp_path, *, binding_selector: str, imports: tuple[str, ...] = ("alpha", "bravo")):
    module = (FIXTURES / "profile-module.sdl.yaml").read_text(encoding="utf-8")
    (tmp_path / "profile-module.sdl.yaml").write_text(
        edited(module, ("        participant_refs: [helper]\n", binding_selector)), encoding="utf-8"
    )
    root = "name: profile-root\nimports:\n" + "".join(
        f"  - source: local:profile-module.sdl.yaml\n    namespace: {namespace}\n    version: 1.0.0\n"
        for namespace in imports
    )
    (tmp_path / "root.sdl.yaml").write_text(root, encoding="utf-8")
    return tmp_path / "root.sdl.yaml"


def test_composition_namespaces_explicit_selectors_and_keeps_generated_private_refs() -> None:
    model = compile_runtime_model(parse_sdl_file(FIXTURES / "imports-profile-twice.sdl.yaml"))

    for namespace in ("alpha", "bravo"):
        binding = model.tool_affordances[
            f"participant.behavior-specification.{namespace}.toolkit.tool-affordance.scanner"
        ]
        assert binding.participant_refs == (f"{namespace}.__private.helper",)
        assert binding.participant_addresses == (f"participant.behavior.{namespace}.__private.helper",)


def test_composition_keeps_role_selectors_global(tmp_path) -> None:
    root = _module_root(tmp_path, binding_selector="        participant_role_refs: [blue]\n", imports=("alpha",))

    binding = compile_runtime_model(parse_sdl_file(root)).tool_affordances[
        "participant.behavior-specification.alpha.toolkit.tool-affordance.scanner"
    ]

    assert binding.participant_role_refs == ("blue",)
    assert binding.participant_addresses == (
        "participant.behavior.alpha.__private.helper",
        "participant.behavior.alpha.analyst",
    )


def test_renaming_an_agent_rewrites_binding_selectors() -> None:
    text = edited(
        toolkit_text(), ("        participant_role_refs: [white]\n", "        participant_refs: [observer]\n")
    )

    result = rename_sdl_declaration(
        parse_sdl(text), RenameSDLDeclarationRequest(target_address="agents.observer", new_local_name="referee")
    )

    assert result.output is not None
    binding = result.output.behavior_specifications["toolkit"].tool_affordances["scanner-white"]
    assert binding.participant_refs == ["referee"]
    assert compile_runtime_model(result.output).tool_affordances[SCANNER_WHITE].participant_addresses == (
        "participant.behavior.referee",
    )


@pytest.mark.parametrize(("who", "valid"), (("observer", True), ("analyst", False)))
def test_a_variable_selector_ref_is_rechecked_after_binding(who: str, valid: bool) -> None:
    text = edited(
        toolkit_text(),
        (WHITE_SELECTOR_LINE, '        participant_refs: ["${who}"]\n'),
        ("name: two-role-toolkit\n", "name: two-role-toolkit\nvariables:\n  who:\n    type: string\n"),
    )
    scenario = parse_sdl(text)

    if valid:
        instantiated = instantiate_scenario(scenario, parameters={"who": who})
        assert compile_runtime_model(instantiated).tool_affordances[SCANNER_WHITE].participant_addresses == (WHITE,)
        return
    with pytest.raises(SDLInstantiationError, match="tool affordance 'scanner-white' action_contract_ref"):
        instantiate_scenario(scenario, parameters={"who": who})


PRIVATE_MESSAGE = "authored qualified SDL identifier must not contain the reserved __private segment"


def test_an_authored_private_selector_ref_is_rejected_in_yaml(tmp_path) -> None:
    root = _module_root(tmp_path, binding_selector="        participant_refs: [helper]\n", imports=("alpha",))
    root.write_text(
        root.read_text(encoding="utf-8")
        + "behavior_specifications:\n  reach:\n    semantic_version: 1.0.0\n    participant_role_refs: [blue]\n"
        "    action_contract_refs: [alpha.scan]\n    observation_boundary_refs: [alpha.blue-view]\n"
        "    tool_affordances:\n      private-reach:\n        participant_refs: [alpha.__private.helper]\n"
        "        action_contract_refs: [alpha.scan]\n        observation_boundary_refs: [alpha.blue-view]\n",
        encoding="utf-8",
    )

    with pytest.raises(SDLParseError, match=PRIVATE_MESSAGE) as raised:
        parse_sdl_file(root)
    assert "/behavior_specifications/reach/tool_affordances/private-reach/participant_refs/0" in str(raised.value)


@pytest.mark.parametrize("as_model", (False, True), ids=("mapping-binding", "model-binding"))
def test_an_authored_private_selector_ref_is_rejected_on_direct_construction(as_model: bool) -> None:
    binding = {
        "participant_refs": ["alpha.__private.helper"],
        "action_contract_refs": ["alpha.scan"],
        "observation_boundary_refs": ["alpha.blue-view"],
    }
    spec = {
        "semantic_version": "1.0.0",
        "participant_role_refs": ["blue"],
        "tool_affordances": {"private-reach": binding},
    }
    if as_model:
        spec["tool_affordances"] = {"private-reach": ParticipantToolAffordance.model_validate(binding)}

    with pytest.raises(ValueError, match=PRIVATE_MESSAGE):
        Scenario.model_validate({"name": "direct", "behavior_specifications": {"reach": spec}})


def test_a_variable_profile_selector_defers_the_widening_check() -> None:
    text = edited(
        toolkit_text(),
        ("    participant_role_refs: [blue, white]\n", '    participant_refs: [analyst, "${who}"]\n'),
        (WHITE_SELECTOR_LINE, "        participant_refs: [observer]\n"),
        ("name: two-role-toolkit\n", "name: two-role-toolkit\nvariables:\n  who:\n    type: string\n"),
    )
    scenario = parse_sdl(text)

    instantiated = instantiate_scenario(scenario, parameters={"who": "observer"})
    assert compile_runtime_model(instantiated).tool_affordances[SCANNER_WHITE].participant_addresses == (WHITE,)


def _instantiated_payload(**binding_updates: object) -> dict[str, object]:
    payload = instantiate_scenario(parse_sdl_file(TOOLKIT)).model_dump(mode="python", by_alias=True)
    payload["behavior_specifications"]["toolkit"]["tool_affordances"]["scanner-blue"].update(binding_updates)
    return payload


@pytest.mark.parametrize(
    ("binding_updates", "spec_updates", "expected_codes", "expected_addresses"),
    (
        pytest.param(
            {"participant_refs": ["ghost"], "participant_role_refs": ["red"]},
            {},
            {
                "participant.tool-affordance-participant-ref-unbound",
                "participant.tool-affordance-participant-role-ref-unbound",
            },
            (),
            id="dangling-explicit-and-unmatched-role",
        ),
        pytest.param(
            {"participant_role_refs": ["white"]},
            {"participant_role_refs": ["blue"]},
            {"participant.tool-affordance-participant-widens-parent"},
            (WHITE,),
            id="selects-outside-the-profile",
        ),
    ),
)
def test_compiler_diagnoses_selectors_without_semantic_admission(
    binding_updates: dict[str, object],
    spec_updates: dict[str, object],
    expected_codes: set[str],
    expected_addresses: tuple[str, ...],
) -> None:
    payload = _instantiated_payload(**binding_updates)
    payload["behavior_specifications"]["toolkit"].update(spec_updates)
    diagnostics = []

    records = _compile_tool_affordances(InstantiatedScenario.model_validate(payload), diagnostics)

    assert {diagnostic.code for diagnostic in diagnostics} == expected_codes
    assert records[SCANNER_BLUE].participant_addresses == expected_addresses
    assert records[SCANNER_BLUE].participant_refs or records[SCANNER_BLUE].participant_role_refs


def test_compiler_reports_a_dangling_profile_participant_ref() -> None:
    payload = _instantiated_payload()
    payload["behavior_specifications"]["toolkit"]["participant_refs"] = ["ghost"]
    diagnostics = []

    _compile_behavior_specifications(InstantiatedScenario.model_validate(payload), diagnostics)

    assert [diagnostic.code for diagnostic in diagnostics] == [
        "participant.behavior-specification-participant-ref-unbound"
    ]


def test_projection_fails_closed_when_a_scoped_binding_resolved_to_nobody() -> None:
    model = compiled()
    broken = replace(model.tool_affordances[SCANNER_WHITE], participant_addresses=())
    model = replace(model, tool_affordances={**model.tool_affordances, SCANNER_WHITE: broken})

    white = _white_after_reveal(model).project((PASSIVE,), ())
    blue = Episode.start(model, BLUE, BLUE_VIEW).project((ACTIVE,), (SCANNER_BLUE,))

    assert _entry_affordances(white) == {PASSIVE: []}
    assert _entry_affordances(blue) == {ACTIVE: [SCANNER_BLUE]}
