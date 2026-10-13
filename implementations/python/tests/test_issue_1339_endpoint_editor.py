"""Editor completion, navigation and diagnostics follow typed relationship endpoint purposes (#1339)."""

from __future__ import annotations

from copy import deepcopy

import pytest
import yaml
from raes import SDLValidationError, parse_sdl
from raes import _reference_targetability as policy
from raes._declarations import build_declaration_index
from raes._language_context import SECTION_FIELDS, partial_index
from raes._mapping_scopes import HASHMAP_SECTIONS
from raes._relationship_endpoint_policy import RELATIONSHIP_DETAIL_BINDINGS, relationship_endpoint_purposes
from raes.language_service import language_completions, language_diagnostics, language_references
from raes.scenario import ExpandedScenario, Scenario
from test_issue_1339_relationship_endpoints import DETAILS, fixture_index, fixture_payload, structural, typed

_BROKEN = {"command": "true", "interval": "soon"}


def _with(relationship: dict, *, broken: bool = False) -> dict:
    """The all-kinds fixture plus relationship `probe` and condition `pending`, which does not validate if *broken*."""

    payload = fixture_payload()
    payload["relationships"]["probe"] = relationship
    # A broken unrelated entry makes the editor resolve through its partial index.
    payload["conditions"]["pending"] = deepcopy(_BROKEN) if broken else {"command": "true", "interval": 5}
    return payload


def _completions(payload: dict, side: str) -> dict:
    return language_completions(yaml.safe_dump(payload, sort_keys=False), cursor_path=f"/relationships/probe/{side}")


def _labels(payload: dict, pointer: str) -> dict[str, str]:
    """Map each offered declaration to the label that completion offers for it."""

    items = language_completions(yaml.safe_dump(payload, sort_keys=False), cursor_path=pointer)["items"]
    return {item["detail"]: item["label"] for item in items}


def _occurrences(payload: dict, symbol: str) -> set[str]:
    result = language_references(yaml.safe_dump(payload, sort_keys=False), symbol)
    return {item["path"] for item in result["occurrences"]}


def _errors(payload: dict) -> list[str]:
    with pytest.raises(SDLValidationError) as caught:
        parse_sdl(yaml.safe_dump(payload, sort_keys=False))
    return caught.value.errors


def _twin(field: str) -> dict:
    """A typed relationship carrying *field*: its bound type, or a generic type for an unbound detail."""

    return typed(RELATIONSHIP_DETAIL_BINDINGS.get(field, "connects_to"), field, source="dc", target="corp")


_TYPES = (
    "domain_controller_for",
    "joins_domain",
    "forest_trusts",
    "directory_federates_to",
    "placed_on_carrier",
    "uses_shared_service",
    "participant",
    "connects_to",
)
_ROWS = [(name, None) for name in _TYPES] + [(None, field) for field in sorted(DETAILS)]


@pytest.mark.parametrize("side", ["source", "target"])
@pytest.mark.parametrize(("relationship_type", "detail"), _ROWS, ids=lambda value: value or "-")
def test_typed_endpoint_completion_offers_exactly_the_eligible_declarations(
    relationship_type: str | None, detail: str | None, side: str
) -> None:
    relationship = typed(relationship_type, source="dc", target="corp") if relationship_type else _twin(detail)
    purposes = relationship_endpoint_purposes(relationship, side)
    complete = _with(relationship)
    index = build_declaration_index(structural(complete))

    result = _completions(complete, side)

    assert {item["detail"] for item in result["items"]} == {
        declaration.address for declaration in index.declarations if policy.declaration_eligible(declaration, purposes)
    }
    assert result["context"] == f"reference:{policy.reference_domain(purposes)}"
    assert _completions(_with(relationship, broken=True), side) == result
    if detail is not None:
        # A detail written before its type selects the rule that its type would.
        untyped = {key: value for key, value in relationship.items() if key != "type"}
        assert _completions(_with(untyped), side) == result


def test_a_mail_listener_is_a_mail_access_target_and_a_monitoring_listener_is_not() -> None:
    mail = "nodes.app.runtime.mail_services.mail.listeners.listeners"
    monitoring = "nodes.app.runtime.security_monitoring_managers.siem.listeners.listeners"
    relationship = typed("connects_to", "mail_access", source="nodes.workstation", target=mail)

    details = {item["detail"] for item in _completions(_with(relationship), "target")["items"]}
    parse_sdl(yaml.safe_dump(_with(relationship), sort_keys=False))
    relationship["target"] = monitoring

    assert mail in details
    assert monitoring not in details
    assert f"Relationship 'probe' has mail_access but target '{monitoring}' does not resolve to a mail service" in (
        _errors(_with(relationship))
    )


_CONJUNCTIONS = [
    (
        {"type": "domain_controller_for", "domain_controller": {}, "database_access": {}},
        "source",
        "reference:eligible:node_endpoint+runtime_application_endpoint",
        ("a node endpoint", "a runtime application endpoint"),
    ),
    (
        {"type": "connects_to", "database_access": {}, "mail_access": {}},
        "target",
        "reference:eligible:database_endpoint+mail_service_endpoint",
        ("a database endpoint", "a mail service endpoint"),
    ),
]


@pytest.mark.parametrize("reverse", [False, True], ids=["written-in-order", "written-reversed"])
@pytest.mark.parametrize(("relationship", "side", "context", "labels"), _CONJUNCTIONS, ids=["source", "target"])
def test_an_empty_conjunction_offers_nothing_and_names_each_failed_purpose(
    relationship: dict, side: str, context: str, labels: tuple[str, str], reverse: bool
) -> None:
    items = list(relationship.items())
    authored = dict(reversed(items) if reverse else items) | {"source": "nodes.dc", "target": "corp"}

    result = _completions(_with(authored), side)
    authored[side] = "nowhere"
    errors = _errors(_with(authored))

    assert (result["context"], result["items"]) == (context, [])
    refusal = f"Relationship 'probe' {side} 'nowhere' does not reference any defined element eligible as"
    assert f"{refusal} {labels[0]} and as {labels[1]}" in errors


def test_a_conjunction_refusal_names_only_the_purpose_that_the_match_fails() -> None:
    authored = {"type": "domain_controller_for", "source": "nodes.dc", "target": "corp", "domain_controller": {}}
    authored["database_access"] = {}

    errors = _errors(_with(authored))

    assert (
        "Relationship 'probe' source 'nodes.dc' does not reference any defined element eligible as "
        "a runtime application endpoint; it names nodes.dc"
    ) in errors


# (relationship, side, an eligible endpoint, an ineligible endpoint), one row per (rule, side).
_RULE_SIDES = [
    ("domain_controller_for", "source", "nodes.dc", "nodes.app.runtime.applications.web"),
    ("domain_controller_for", "target", "identity_domains.corp", "conditions.alive"),
    ("joins_domain", "source", "nodes.workstation", "identity_domains.corp"),
    ("joins_domain", "target", "identity_domains.partner-corp", "nodes.dc"),
    ("forest_trusts", "source", "identity_forests.enterprise", "identity_domains.corp"),
    ("forest_trusts", "target", "identity_forests.partner", "identity_domains.partner-corp"),
    ("directory_federates_to", "source", "identity_domains.corp", "identity_facades.workforce-oidc"),
    ("directory_federates_to", "target", "identity_facades.workforce-oidc", "identity_forests.enterprise"),
    ("placed_on_carrier", "source", "nodes.workstation", "nodes.app.services.http"),
    ("placed_on_carrier", "target", "nodes.carrier", "deployment_tenants.range-a"),
    ("uses_shared_service", "source", "deployment_tenants.range-a", "deployment_cells.range-a-cell"),
    ("uses_shared_service", "target", "nodes.app.services.http", "nodes.app"),
    ("database_access", "source", "nodes.app.runtime.applications.web", "nodes.app"),
    (
        "database_access",
        "target",
        "nodes.app.runtime.database_services.db.databases.databases",
        "nodes.app.runtime.applications.web",
    ),
    (
        "mail_access",
        "target",
        "nodes.app.runtime.mail_services.mail.listeners.listeners",
        "nodes.app.runtime.security_monitoring_managers.siem.listeners.listeners",
    ),
]


def _rule(name: str, side: str, value: str) -> dict:
    relationship = typed(name, source="nodes.dc", target="corp") if name not in DETAILS else _twin(name)
    return relationship | {side: value}


@pytest.mark.parametrize("broken", [False, True], ids=["valid-document", "incomplete-document"])
@pytest.mark.parametrize(("name", "side", "eligible", "ineligible"), _RULE_SIDES, ids=lambda value: value)
def test_navigation_reports_a_typed_endpoint_only_as_an_occurrence_of_an_eligible_declaration(
    name: str, side: str, eligible: str, ineligible: str, broken: bool
) -> None:
    pointer = f"/relationships/probe/{side}"
    label = policy.PURPOSE_LABELS[relationship_endpoint_purposes(_rule(name, side, eligible), side)[0]]

    assert pointer in _occurrences(_with(_rule(name, side, eligible), broken=broken), eligible)
    assert pointer not in _occurrences(_with(_rule(name, side, ineligible), broken=broken), ineligible)
    refusal = f"Relationship 'probe' {side} '{ineligible}' does not reference any defined element eligible as {label}"
    assert f"{refusal}; it names {ineligible}" in _errors(_with(_rule(name, side, ineligible)))


@pytest.mark.parametrize("broken", [False, True], ids=["valid-document", "incomplete-document"])
@pytest.mark.parametrize(
    ("name", "side", "bare", "declaration"),
    [
        ("uses_shared_service", "target", "http", "nodes.app.services.http"),
        ("database_access", "source", "web", "nodes.app.runtime.applications.web"),
    ],
)
def test_a_bare_name_that_the_index_gives_no_alias_is_neither_offered_nor_an_occurrence(
    name: str, side: str, bare: str, declaration: str, broken: bool
) -> None:
    payload = _with(_rule(name, side, bare), broken=broken)

    labels = _labels(payload, f"/relationships/probe/{side}")

    assert labels[declaration] == declaration
    assert f"/relationships/probe/{side}" not in _occurrences(payload, declaration)
    errors = _errors(_with(_rule(name, side, bare)))
    assert any(f"{side} '{bare}' does not reference any defined element eligible as" in error for error in errors)


@pytest.mark.parametrize("broken", [False, True], ids=["valid-document", "incomplete-document"])
@pytest.mark.parametrize(
    ("name", "side", "value", "occurrence"),
    [
        ("uses_shared_service", "target", "nodes.services.services.smtp", True),
        ("database_access", "source", "nodes.runtime.runtime.applications.resolver", True),
        ("domain_controller_for", "source", "nodes.services", True),
        ("database_access", "source", "nodes.runtime", False),
        ("domain_controller_for", "source", "nodes.services.runtime.applications.portal", False),
    ],
)
def test_grammar_words_as_node_ids_keep_the_kinds_that_typed_construction_gives(
    name: str, side: str, value: str, occurrence: bool, broken: bool
) -> None:
    pointer = f"/relationships/probe/{side}"

    assert (pointer in _occurrences(_with(_rule(name, side, value), broken=broken), value)) is occurrence


def test_a_node_that_does_not_validate_on_its_own_offers_and_resolves_none_of_its_services() -> None:
    payload = _with(_rule("uses_shared_service", "target", "nodes.dc.services.ldap"))
    payload["nodes"]["dc"]["services"][0]["port"] = "ldap-port"
    valid = _with(_rule("uses_shared_service", "target", "nodes.app.services.http"))
    valid["nodes"]["dc"]["services"][0]["port"] = "ldap-port"

    details = {item["detail"] for item in _completions(payload, "target")["items"]}

    assert language_diagnostics(yaml.safe_dump(payload))["status"] == "invalid"
    assert "nodes.dc.services.ldap" not in details
    assert "nodes.app.services.http" in details
    assert "/relationships/probe/target" not in _occurrences(payload, "nodes.dc.services.ldap")
    assert "/relationships/probe/target" in _occurrences(valid, "nodes.app.services.http")


def test_conjunction_navigation_reports_neither_member_kind() -> None:
    combined = {"type": "domain_controller_for", "domain_controller": {}, "database_access": {}, "target": "corp"}
    single = typed("domain_controller_for", source="nodes.dc", target="corp")

    for source in ("nodes.dc", "nodes.app.runtime.applications.web"):
        assert "/relationships/probe/source" not in _occurrences(_with(combined | {"source": source}), source)
    assert "/relationships/probe/source" in _occurrences(_with(single), "nodes.dc")


def _hidden_alias(*, broken: bool) -> dict:
    content = {"type": "dataset", "target": "beta", "items": [{"name": "alpha"}]}
    payload = {
        "name": "hidden-alias",
        "nodes": {name: {"type": "compute", "resources": {"ram": "1 GiB", "cpu": 1}} for name in ("alpha", "beta")},
        "content": {"docs": content | ({"bogus": 1} if broken else {})},
        "relationships": {"r": {"type": "connects_to", "source": "beta", "target": "alpha"}},
    }
    return payload


def test_ambiguity_is_judged_among_the_declarations_the_editor_index_holds() -> None:
    complete, broken = _hidden_alias(broken=False), _hidden_alias(broken=True)
    complete_labels = _labels(complete, "/relationships/r/target")
    broken_labels = _labels(broken, "/relationships/r/target")

    with pytest.raises(SDLValidationError) as caught:
        parse_sdl(yaml.safe_dump(complete))
    assert "Relationship 'r' target 'alpha' is ambiguous; use one of: content.docs.items.alpha, nodes.alpha" in (
        caught.value.errors
    )
    for symbol in ("nodes.alpha", "content.docs.items.alpha"):
        assert "/relationships/r/target" not in _occurrences(complete, symbol)
    assert (complete_labels["nodes.alpha"], complete_labels["content.docs.items.alpha"]) == (
        "nodes.alpha",
        "content.docs.items.alpha",
    )
    # A content entry that does not validate on its own hides its item until it validates.
    assert "/relationships/r/target" in _occurrences(broken, "nodes.alpha")
    assert "/relationships/r/target" not in _occurrences(broken, "content.docs.items.alpha")
    assert "content.docs.items.alpha" not in broken_labels
    assert broken_labels["nodes.alpha"] == "alpha"


def test_the_partial_index_equals_the_complete_index_for_every_entry_that_validates() -> None:
    payload = fixture_payload()
    payload["conditions"]["pending"] = deepcopy(_BROKEN)
    complete = fixture_index()

    partial = partial_index(payload, Scenario)

    for declaration in complete.declarations:
        assert partial.declaration_for(declaration.address) == declaration
        assert partial.spellings_for(declaration.address) == complete.spellings_for(declaration.address)
    assert set(partial.addresses) - set(complete.addresses) == {"conditions.pending"}
    assert partial.spellings_for("conditions.pending") == {"conditions.pending", "pending"}
    # The per-entry split reads the SDL section catalog, which both models share.
    assert set(HASHMAP_SECTIONS) <= set(SECTION_FIELDS)
    assert set(HASHMAP_SECTIONS) <= set(ExpandedScenario.model_fields)
