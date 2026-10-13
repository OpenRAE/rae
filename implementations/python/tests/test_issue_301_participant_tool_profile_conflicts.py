"""Conflicting profiles, unresolved refs and inferred availability (issue #301, ACT-619).

Binding selectors only narrow their behavior specification and use the same PI-03
resolver over the whole composed scenario (absolute semantics). Conflicts are
rejected, never resolved by order, precedence or override, and no source other
than a binding's own selector makes it available to a participant.
"""

from __future__ import annotations

import json

import pytest
import yaml
from jsonschema import Draft202012Validator
from paths import REPO_ROOT
from raes import SDLParseError, SDLValidationError, parse_sdl, parse_sdl_file
from tool_profile_support import (
    ACTIVE,
    CONTEXT,
    FIXTURES,
    SCANNER_BLUE,
    TOOLKIT,
    WHITE,
    WHITE_VIEW,
    Episode,
    admit_selection,
    compiled,
    edited,
    implementation_selection,
    toolkit_text,
)

AUTHORING_SCHEMA = REPO_ROOT / "contracts" / "schemas" / "sdl" / "sdl-authoring-input-v1.json"
AUTONOMOUS_EXAMPLE = REPO_ROOT / "examples" / "scenarios" / "temporal-profiles" / "automation-dwell.sdl.yaml"
WHITE_SELECTOR = "        participant_role_refs: [white]\n"
BLUE_SELECTOR = "        participant_role_refs: [blue]\n"
SCANNER_BLUE_BLOCK = (
    "      scanner-blue:\n        tool_ref: nmap\n" + BLUE_SELECTOR + "        action_contract_refs: [scan-active]\n"
    "        observation_boundary_refs: [blue-view]\n"
)
SPEC_BY_ROLE = "    participant_role_refs: [blue, white]\n"
SPEC_BY_PARTICIPANT = "    participant_refs: [analyst, observer]\n"
BLUE_LEAD = """\
  blue-lead:
    affiliations: [blue-team]
    actions: [scan-active]
    observation_boundaries: [blue-view]
"""
LEAD_SPEC = """\
  lead-duty:
    semantic_version: 1.0.0
    participant_refs: [blue-lead]
    action_contract_refs: [scan-active]
"""


def _rejected(text: str, *messages: str) -> None:
    with pytest.raises(SDLValidationError) as raised:
        parse_sdl(text)
    for message in messages:
        assert message in str(raised.value)


def _binding(prefix: str) -> str:
    return f"Behavior specification 'toolkit' tool affordance '{prefix}'"


@pytest.mark.parametrize(
    ("edits", "messages"),
    (
        pytest.param(
            (
                (
                    SCANNER_BLUE_BLOCK,
                    SCANNER_BLUE_BLOCK
                    + SCANNER_BLUE_BLOCK.replace("scanner-blue", "scanner-analyst").replace(
                        BLUE_SELECTOR, "        participant_refs: [analyst]\n"
                    ),
                ),
            ),
            ("has duplicate tool affordance relation 'scanner-analyst' matching 'scanner-blue'",),
            id="K2-selectors-are-not-part-of-the-relation",
        ),
        pytest.param(
            ((SPEC_BY_ROLE, "    participant_role_refs: [blue]\n"),),
            (f"{_binding('scanner-white')} selects participant 'observer' outside its owning behavior specification",),
            id="K3-participant-widens-parent",
        ),
        pytest.param(
            ((WHITE_SELECTOR, "        participant_refs: [ghost]\n"),),
            (f"{_binding('scanner-white')} participant_ref 'ghost' does not reference a declared agent",),
            id="K3-participant-unbound",
        ),
        pytest.param(
            ((WHITE_SELECTOR, "        participant_role_refs: [red]\n"),),
            (f"{_binding('scanner-white')} participant_role_ref 'red' does not match any declared participant role",),
            id="K3-role-unbound",
        ),
        pytest.param(
            ((WHITE_SELECTOR, BLUE_SELECTOR),),
            (
                f"{_binding('scanner-white')} action_contract_ref 'scan-passive' is outside participant 'analyst' actions",
                f"{_binding('scanner-white')} observation_boundary_ref 'white-view' is outside participant 'analyst'",
            ),
            id="K4-scoped-binding-outside-a-selected-participant",
        ),
        pytest.param(
            ((BLUE_SELECTOR, ""),),
            (f"{_binding('scanner-blue')} observation_boundary_ref 'blue-view' is outside participant 'observer'",),
            id="297-role-wide-binding-without-selector",
        ),
        pytest.param(
            (("        action_contract_refs: [scan-passive]\n", "        action_contract_refs: [scan-ghost]\n"),),
            (f"{_binding('scanner-white')} action_contract_ref 'scan-ghost' widens its owning behavior specification",),
            id="dangling-action-in-a-scoped-binding",
        ),
        pytest.param(
            (
                (
                    "        observation_boundary_refs: [white-view]\n",
                    "        observation_boundary_refs: [ghost-view]\n",
                ),
            ),
            (
                f"{_binding('scanner-white')} observation_boundary_ref 'ghost-view' widens its owning behavior specification",
            ),
            id="dangling-boundary-in-a-scoped-binding",
        ),
        pytest.param(
            (
                (
                    "      - information_ref: behavior_specifications.toolkit.tool_affordances.scanner-white\n"
                    "        boundary_class: observable_resource\n        disposition: hidden\n"
                    "        visibility_basis: authored classification of the white binding\n",
                    "",
                ),
            ),
            (
                f"{_binding('scanner-white')} reference 'behavior_specifications.toolkit.tool_affordances.scanner-white' must be explicitly classified by observation boundary 'white-view'",
            ),
            id="unclassified-boundary",
        ),
    ),
)
def test_conflicting_or_unresolved_profiles_are_rejected(
    edits: tuple[tuple[str, str], ...], messages: tuple[str, ...]
) -> None:
    _rejected(edited(toolkit_text(), *edits), *messages)


def test_binding_role_selectors_are_absolute_over_the_composed_scenario() -> None:
    """TP-3: an unrelated blue participant elsewhere invalidates a blue binding under an explicit profile."""

    explicit_profile = edited(toolkit_text(), (SPEC_BY_ROLE, SPEC_BY_PARTICIPANT))
    assert SCANNER_BLUE in compiled(explicit_profile).tool_affordances
    with_lead = edited(explicit_profile, ("action_contracts:\n", f"{BLUE_LEAD}action_contracts:\n")) + LEAD_SPEC

    _rejected(
        with_lead,
        f"{_binding('scanner-blue')} selects participant 'blue-lead' outside its owning behavior specification",
    )


@pytest.mark.parametrize(
    ("spec_selector", "message", "absent"),
    (
        pytest.param(
            "    participant_refs: [analyst, helper]\n",
            "tool affordance 'scanner' selects participant 'bravo.analyst' outside its owning behavior specification",
            None,
            id="explicit-profile-participant-widens-parent",
        ),
        pytest.param(
            BLUE_SELECTOR.replace("        ", "    "),
            "tool affordance 'scanner' action_contract_ref 'alpha.scan' is outside participant 'bravo.analyst' actions",
            "outside its owning behavior specification",
            id="role-profile-action-outside-participant",
        ),
    ),
)
def test_module_roles_stay_global_so_role_scoped_bindings_fail_at_a_twice_imported_seam(
    tmp_path, spec_selector: str, message: str, absent: str | None
) -> None:
    module = (FIXTURES / "profile-module.sdl.yaml").read_text(encoding="utf-8")
    variant = edited(
        module,
        ("        participant_refs: [helper]\n", BLUE_SELECTOR),
        ("    participant_refs: [analyst, helper]\n", spec_selector),
    )
    (tmp_path / "profile-module.sdl.yaml").write_text(variant, encoding="utf-8")
    root = tmp_path / "root.sdl.yaml"
    root.write_text((FIXTURES / "imports-profile-twice.sdl.yaml").read_text(encoding="utf-8"), encoding="utf-8")

    with pytest.raises(SDLValidationError) as raised:
        parse_sdl_file(root)
    assert f"Behavior specification 'alpha.toolkit' {message}" in str(raised.value)
    assert absent is None or absent not in str(raised.value)


def test_one_namespace_cannot_hold_two_profiles_with_one_name(tmp_path) -> None:
    (tmp_path / "profile-module.sdl.yaml").write_text(
        (FIXTURES / "profile-module.sdl.yaml").read_text(encoding="utf-8"), encoding="utf-8"
    )
    (tmp_path / "other.sdl.yaml").write_text(
        "name: other-profile\nmodule:\n  id: acme/other-profile\n  version: 1.0.0\n  exports:\n"
        "    behavior_specifications: [toolkit]\nbehavior_specifications:\n  toolkit:\n    semantic_version: 2.0.0\n"
        "    participant_role_refs: [blue]\n    behavior_mode: scripted\n",
        encoding="utf-8",
    )
    (tmp_path / "root.sdl.yaml").write_text(
        "name: collision\nimports:\n  - source: local:profile-module.sdl.yaml\n    namespace: alpha\n    version: 1.0.0\n"
        "  - source: local:other.sdl.yaml\n    namespace: alpha\n    version: 1.0.0\n",
        encoding="utf-8",
    )

    with pytest.raises(SDLParseError, match=r"collides on behavior_specifications: alpha\.toolkit$"):
        parse_sdl_file(tmp_path / "root.sdl.yaml")


def _autonomous_profiles(*, second_owner: bool) -> str:
    text = AUTONOMOUS_EXAMPLE.read_text(encoding="utf-8")
    binding = (
        "    tool_affordances:\n      probe:\n        participant_role_refs: [green]\n"
        "        action_contract_refs: [probe-customer-portal-login]\n        observation_boundary_refs: [participant-view]\n"
    )
    start = text.index("  participant-behavior:\n")
    end = text.index("time_domains:\n")
    spec = text[start:end]
    scoped = spec.replace(
        "    extension_policy: governed-extension\n", binding + "    extension_policy: governed-extension\n"
    )
    owners = scoped + (scoped.replace("  participant-behavior:\n", "  second-behavior:\n") if second_owner else "")
    classified = "".join(
        f"    - behavior_specifications.{name}.tool_affordances.probe\n"
        for name in ("participant-behavior", "second-behavior")
    )
    rules = "".join(
        f"    - information_ref: behavior_specifications.{name}.tool_affordances.probe\n"
        "      boundary_class: observable_resource\n      disposition: observable\n      visibility_basis: authored probe binding\n"
        for name in ("participant-behavior", "second-behavior")
    )
    text = text[:start] + owners + text[end:]
    return edited(
        text,
        (
            "    - nodes.customer-portal.services.http\n    evidence_refs:\n    - content.participant-observation\n    redaction_policy",
            "    - nodes.customer-portal.services.http\n"
            + classified
            + "    evidence_refs:\n    - content.participant-observation\n    redaction_policy",
        ),
        (
            "    realized_view_disclosure: Only the declared response and evidence references.\n",
            "    realized_view_disclosure: Only the declared response and evidence references.\n    view_rules:\n"
            + rules,
        ),
    )


def test_scoped_bindings_neither_create_nor_hide_an_autonomous_owner_overlap() -> None:
    """K5: PI-06 still runs on specification selection when the specifications carry scoped bindings."""

    single_owner = parse_sdl(_autonomous_profiles(second_owner=False))
    assert single_owner.behavior_specifications["participant-behavior"].tool_affordances[
        "probe"
    ].participant_role_refs == ["green"]

    _rejected(
        _autonomous_profiles(second_owner=True),
        "Behavior specification 'second-behavior' autonomous participant 'participant-agent' "
        "is already controlled by behavior specification 'participant-behavior'",
    )


def test_two_bindings_that_select_one_participant_must_agree_on_the_action_disposition() -> None:
    hidden_binding = (
        "      audit-blue:\n"
        + BLUE_SELECTOR
        + "        action_contract_refs: [scan-active]\n        observation_boundary_refs: [blue-view]\n"
    )
    hidden_rule = (
        "      - information_ref: behavior_specifications.toolkit.tool_affordances.audit-blue\n"
        "        boundary_class: observable_resource\n        disposition: hidden\n        visibility_basis: audit binding hidden\n"
        "      - information_ref: participant.behavior-specification.toolkit.tool-affordance.audit-blue\n"
        "        boundary_class: observable_resource\n        disposition: hidden\n        visibility_basis: audit binding hidden\n"
    )
    text = edited(
        toolkit_text(),
        ("      scanner-white:\n", hidden_binding + "      scanner-white:\n"),
        (
            "      - behavior_specifications.toolkit.tool_affordances.scanner-blue\n    evidence_refs",
            "      - behavior_specifications.toolkit.tool_affordances.scanner-blue\n    hidden_refs:\n"
            "      - behavior_specifications.toolkit.tool_affordances.audit-blue\n"
            "      - participant.behavior-specification.toolkit.tool-affordance.audit-blue\n    evidence_refs",
        ),
        (
            "        visibility_basis: authored classification of the blue binding\n",
            "        visibility_basis: authored classification of the blue binding\n" + hidden_rule,
        ),
    )
    blue = Episode.start(compiled(text), "participant.behavior.analyst", "participant.observation-boundary.blue-view")
    audit = "participant.behavior-specification.toolkit.tool-affordance.audit-blue"

    with pytest.raises(ValueError, match="refs are not participant-visible at state cut") as raised:
        blue.project((ACTIVE,), (SCANNER_BLUE, audit))
    assert audit in str(raised.value)


def _observer_with(extra: str) -> str:
    return edited(
        toolkit_text(),
        ("  observer:\n    affiliations: [white-team]\n", "  observer:\n    affiliations: [white-team]\n" + extra),
    )


@pytest.mark.parametrize(
    ("text", "tool_expectations"),
    (
        pytest.param(toolkit_text(), ("shell", "x-acme:nmap"), id="manifest-tool-expectations"),
        pytest.param(
            _observer_with("    interactive_access:\n      console:\n        target_ref: web\n        channel: ssh\n"),
            None,
            id="interactive-access",
        ),
        pytest.param(
            edited(
                toolkit_text(),
                ("    affiliations: [white-team]\n", "    role: white\n    affiliations: [white-team, blue-team]\n"),
            ),
            None,
            id="affiliation-with-the-binding-role",
        ),
    ),
)
def test_nothing_but_a_binding_selector_makes_it_available(
    text: str, tool_expectations: tuple[str, ...] | None
) -> None:
    """A visible, installed, expected or role-adjacent binding is still not white's (SEM-219 B/F; ADR-083 section 1)."""

    white = Episode.start(compiled(text), WHITE, WHITE_VIEW)
    surface = white.project((ACTIVE,), ())

    assert surface.participant_view.affordance_refs == []
    assert [entry.affordance_refs for entry in surface.participant_view.action_entries] == [[]]
    assert admit_selection(white, surface, ACTIVE, {"rate": 5}, tool_expectations=tool_expectations).accepted is True


def test_an_exposure_policy_cannot_add_an_unselected_binding() -> None:
    white = Episode.start(compiled(), WHITE, WHITE_VIEW)
    selection = implementation_selection(WHITE, permitted_refs=(CONTEXT, ACTIVE), tool_affordance_refs=(SCANNER_BLUE,))

    surface = white.project((ACTIVE,), (), selection=selection)

    assert SCANNER_BLUE not in surface.participant_view.affordance_refs
    with pytest.raises(
        ValueError, match="exposure_assessments must exactly cover every serialized participant-view ref"
    ):
        white.project((ACTIVE,), (), exposure_refs=(CONTEXT, ACTIVE, SCANNER_BLUE))


def test_authoring_schema_accepts_selectors_and_rejects_unknown_binding_keys() -> None:
    validator = Draft202012Validator(json.loads(AUTHORING_SCHEMA.read_text(encoding="utf-8")))
    document = yaml.safe_load(TOOLKIT.read_text(encoding="utf-8"))
    assert list(validator.iter_errors(document)) == []

    document["behavior_specifications"]["toolkit"]["tool_affordances"]["scanner-white"]["participant_scope"] = ["white"]
    assert any("participant_scope" in error.message for error in validator.iter_errors(document))
