"""Identity-refactor integration at the mixed-control and delivery boundaries."""

import copy

import pytest
import yaml
from mixed_control_rev1_scenarios import delivery_binding, legacy_scenario, parse, rev1_delivery_scenario, rev1_scenario
from raes._errors import SDLValidationError
from raes.language_service import language_completions, language_references
from raes_processor.compiler import compile_runtime_model
from test_dsl_142_participant_inject_delivery import _external_direction_yaml


def _delivery_scenario(form: str) -> dict:
    if form == "legacy":
        return yaml.safe_load(_external_direction_yaml())
    return rev1_delivery_scenario()


@pytest.mark.parametrize("form", ["legacy", "reusable-policy"])
@pytest.mark.parametrize("field", ["authority_scope_refs", "evidence_refs"])
def test_control_bindings_reject_each_unknown_reference(form: str, field: str) -> None:
    payload = _delivery_scenario(form)
    binding = delivery_binding(payload)
    if form == "legacy":
        binding[f"control_{field}"].append("nodes.unknown")
    else:
        binding["control"][field].append("nodes.unknown")
    with pytest.raises(SDLValidationError, match="nodes.unknown"):
        parse(payload)


@pytest.mark.parametrize("form", ["legacy", "reusable-policy"])
def test_disclosure_permission_and_basis_must_come_from_the_same_rule(form: str) -> None:
    payload = _delivery_scenario(form)
    rules = payload["observation_boundaries"]["red-view"]["view_rules"]
    hidden = copy.deepcopy(rules[0])
    hidden["information_ref"] = "briefing"
    payload["observation_boundaries"]["red-view"]["hidden_refs"] = ["briefing"]
    hidden["disposition"] = "hidden"
    rules[0]["visibility_basis"] = "visibility-bases.other.v1"
    rules.append(hidden)
    with pytest.raises(SDLValidationError, match="visibility/disclosure basis"):
        parse(payload)


def test_rev1_authority_scope_uses_its_domain_before_runtime_projection() -> None:
    payload = rev1_delivery_scenario()
    requirement = payload["evidence_requirements"]["briefing-delivery-evidence"]
    requirement["scope_refs"] = ["nodes.web" if ref == "web" else ref for ref in requirement["scope_refs"]]
    payload["evidence_requirements"]["web"] = copy.deepcopy(requirement)
    delivery_binding(payload)["control"]["authority_scope_refs"] = ["web"]
    model = compile_runtime_model(parse(payload))
    delivery = next(iter(model.participant_inject_deliveries.values()))
    assert delivery.control.authority_scope_addresses == ("provision.node.web",)


@pytest.mark.parametrize("field", ["source_item_ref", "result_item_ref"])
def test_semantic_only_required_delivery_items_produce_a_compiler_diagnostic(field: str) -> None:
    payload = rev1_delivery_scenario()
    delivery_binding(payload)[field] = "entities.red-team"
    if field == "result_item_ref":
        boundary = payload["observation_boundaries"]["red-view"]
        boundary["observable_refs"] = ["entities.red-team"]
        boundary["view_rules"][0]["information_ref"] = "entities.red-team"
    model = compile_runtime_model(parse(payload))
    assert not model.participant_inject_deliveries
    assert any(
        item.code == "participant.inject-delivery-item-unaddressable"
        and item.address == "participant.behavior-specification.red-briefing.inject-delivery.briefing"
        and field in item.message
        for item in model.diagnostics
    )


@pytest.mark.parametrize(
    "field, reference", [("authority_scope_refs", "nodes.web"), ("evidence_refs", "entities.blue-team")]
)
def test_nested_control_references_have_editor_completion_and_navigation(field: str, reference: str) -> None:
    payload = rev1_delivery_scenario()
    pointer = f"/behavior_specifications/red-briefing/participant_inject_deliveries/briefing/control/{field}"
    source = yaml.safe_dump(payload)
    result = language_completions(source, cursor_path=pointer)
    assert reference in {item["detail"] for item in result["items"]}
    assert pointer + "/0" in {item["path"] for item in language_references(source, reference)["occurrences"]}


@pytest.mark.parametrize("form", ["legacy", "reusable-policy", "finite-script"])
@pytest.mark.parametrize(
    "field, reference",
    [
        ("authority_basis_refs", "entities.red-team"),
        ("scope_refs", "nodes.web"),
        ("evidence_refs", "entities.red-team"),
    ],
)
def test_controller_state_references_share_editor_domains_in_every_form(form: str, field: str, reference: str) -> None:
    payload = legacy_scenario() if form == "legacy" else rev1_scenario(form=form)
    pointer = f"/behavior_specifications/controlled-red/mixed_control/controller_states/autonomous/{field}"
    source = yaml.safe_dump(payload)
    items = language_completions(source, cursor_path=pointer)["items"]
    assert reference in {item["detail"] for item in items}
    assert pointer + "/0" in {item["path"] for item in language_references(source, reference)["occurrences"]}


@pytest.mark.parametrize("form", ["legacy", "reusable-policy", "finite-script"])
@pytest.mark.parametrize("suffix", ["", "/0"])
@pytest.mark.parametrize(
    "field, expected", [("authority_basis_refs", "entities.red-team"), ("scope_refs", "nodes.web")]
)
def test_controller_state_completion_offers_only_references_held_by_its_owners(
    form: str, suffix: str, field: str, expected: str
) -> None:
    payload = legacy_scenario() if form == "legacy" else rev1_scenario(form=form)
    pointer = f"/behavior_specifications/controlled-red/mixed_control/controller_states/autonomous/{field}{suffix}"
    items = language_completions(yaml.safe_dump(payload), cursor_path=pointer)["items"]
    assert {item["detail"] for item in items} == {expected}
    for item in items:
        candidate = copy.deepcopy(payload)
        candidate["behavior_specifications"]["controlled-red"]["mixed_control"]["controller_states"]["autonomous"][
            field
        ] = [item["label"]]
        parse(candidate)
