"""Exact incremental semantic validation for related scenarios (issue #1374).

Relationship completion and variation member admission validate scenarios that
share almost every top-level field with the scenario they derive from. A
validation session reuses pass results exactly when every field a pass read is
the identical object; these tests compare it with unmemoized validation.
"""

from __future__ import annotations

from collections import Counter
from copy import deepcopy

import pytest
import yaml
from raes import SDLValidationError
from raes.language_service import language_completions
from raes.scenario import Scenario
from raes.validator import SemanticValidator, ValidationSession
from test_issue_1339_endpoint_editor import _twin, _with
from test_issue_1339_relationship_endpoints import typed
from test_sdl_variation_points import _family_payload


def _outcome(scenario: Scenario, session: ValidationSession) -> tuple[list[str], list[str], dict[str, object]]:
    validator = SemanticValidator(scenario, session=session)
    try:
        validator.validate()
    except SDLValidationError as error:
        errors = list(error.errors)
    else:
        errors = []
    return errors, validator.warnings, dict(scenario.explicitness)


def _reference(scenario: Scenario) -> tuple[list[str], list[str], dict[str, object]]:
    return _outcome(scenario.model_copy(), ValidationSession(memoize=False))


def _count_pass(monkeypatch: pytest.MonkeyPatch, name: str) -> Counter[str]:
    calls: Counter[str] = Counter()
    original = getattr(SemanticValidator, name)

    def counted(self: SemanticValidator) -> None:
        calls[name] += 1
        original(self)

    monkeypatch.setattr(SemanticValidator, name, counted)
    return calls


def _fixture(relationship: dict) -> Scenario:
    return Scenario.model_validate(_with(relationship))


def _with_relationship(base: Scenario, name: str, **changes: object) -> Scenario:
    relationships = dict(base.relationships)
    relationships[name] = relationships[name].model_copy(update=changes)
    return base.model_copy(update={"relationships": relationships})


def _without_node(base: Scenario, name: str) -> Scenario:
    return base.model_copy(update={"nodes": {key: value for key, value in base.nodes.items() if key != name}})


def _derived_scenarios(base: Scenario) -> list[Scenario]:
    return [
        base.model_copy(),
        _with_relationship(base, "probe", target="dc"),
        _with_relationship(base, "probe", source="corp", target="dc"),
        _without_node(base, "app"),
        base.model_copy(update={"variation_points": {}}),
        base.model_copy(update={"variables": {}}),
    ]


@pytest.mark.parametrize(
    "relationship",
    [
        typed("connects_to", source="dc", target="corp"),
        _twin("mail_access"),
        _twin("proxy_upstream"),
    ],
    ids=["connects-to", "mail-access", "proxy-upstream"],
)
def test_session_reuse_matches_unmemoized_validation(relationship: dict) -> None:
    base = _fixture(relationship)
    session = ValidationSession()

    assert _outcome(base, session) == _reference(base)
    for derived in _derived_scenarios(base):
        assert _outcome(derived, session) == _reference(derived)


def test_variation_family_reuse_matches_unmemoized_validation() -> None:
    base = Scenario.model_validate(deepcopy(_family_payload()))
    broken = deepcopy(_family_payload())
    broken["nodes"]["primary"]["features"]["undeclared-feature"] = ""
    session = ValidationSession()

    for scenario in (base, Scenario.model_validate(broken), base.model_copy(update={"variation_points": {}})):
        assert _outcome(scenario, session) == _reference(scenario)


def test_reused_passes_replay_scenario_side_effects() -> None:
    base = _fixture(typed("connects_to", source="dc", target="corp"))
    session = ValidationSession()
    _outcome(base, session)
    records = base.explicitness
    base._set_explicitness({})

    _outcome(base, session)

    assert records
    assert base.explicitness == records


def test_an_authored_field_set_change_is_a_dependency() -> None:
    base = _fixture(typed("connects_to", source="dc", target="corp"))
    unset = next(
        name for name, value in base.__dict__.items() if name not in base.model_fields_set and value is not None
    )
    derived = base.model_copy(update={unset: base.__dict__[unset]})
    session = ValidationSession()
    _outcome(base, session)

    outcome = _outcome(derived, session)

    assert outcome == _reference(derived)
    assert unset in outcome[2]


def test_tracking_view_reports_reads_that_bypass_field_attributes() -> None:
    from raes._incremental_reuse import ALL_FIELDS, ReadSink, recording, tracking_view

    base = _fixture(typed("connects_to", source="dc", target="corp"))
    sink = ReadSink()
    view = tracking_view(base, sink)
    with recording(sink) as dumped:
        view.model_dump()
    with recording(sink) as named:
        _ = view.relationships, view.model_fields_set, view._explicitness

    assert ALL_FIELDS in dumped
    assert {"relationships", "__pydantic_fields_set__", "_explicitness"} <= named
    assert isinstance(view, Scenario)
    assert view.relationships is base.relationships


def test_member_admission_shares_unchanged_pass_results(monkeypatch: pytest.MonkeyPatch) -> None:
    # The family's members change content, node, story, and script owners;
    # relationship validation reads none of them, so every member reuses it.
    calls = _count_pass(monkeypatch, "_verify_relationships")
    nodes = _count_pass(monkeypatch, "_verify_nodes")

    SemanticValidator(Scenario.model_validate(deepcopy(_family_payload()))).validate()

    assert calls["_verify_relationships"] == 1
    feature_members = 2
    assert nodes["_verify_nodes"] == 1 + feature_members


def test_completion_reuses_passes_that_do_not_read_the_relationship(monkeypatch: pytest.MonkeyPatch) -> None:
    nodes = _count_pass(monkeypatch, "_verify_nodes")
    relationships = _count_pass(monkeypatch, "_verify_relationships")
    payload = _with(typed("connects_to", source="dc", target="corp"))

    result = language_completions(yaml.safe_dump(payload, sort_keys=False), cursor_path="/relationships/probe/target")

    assert len(result["items"]) > 10
    assert nodes["_verify_nodes"] == 1
    assert relationships["_verify_relationships"] > len(result["items"])


def test_completion_rejects_a_structurally_invalid_edit_without_variation_points() -> None:
    from raes._language_relationship_candidates import _RelationshipContext, _semantic_candidate_allowed

    scenario = _fixture(_twin("mail_access")).model_copy(update={"variation_points": {}})
    session = ValidationSession()
    baseline = set(_outcome(scenario, session)[0])
    pointer = ["relationships", "probe", "mail_access", "protocol"]
    context = _RelationshipContext(pointer, "probe", {}, scenario, False, None, baseline, session)  # type: ignore[arg-type]

    assert not _semantic_candidate_allowed("nodes.app", context)
    assert scenario.relationships["probe"].mail_access.protocol.value != "nodes.app"


def test_a_validator_without_a_caller_session_revalidates_a_mutated_scenario() -> None:
    scenario = _fixture(typed("connects_to", source="dc", target="corp"))
    validator = SemanticValidator(scenario)
    validator.validate()
    scenario.relationships["probe"].target = "not-declared"

    with pytest.raises(SDLValidationError, match="not-declared"):
        validator.validate()


def test_a_pass_that_resolves_through_the_runtime_cache_depends_on_its_sources() -> None:
    # Mail-access validation reads nodes only through the runtime-reference
    # cache that runtime configuration built earlier in the same validation.
    relationship = _twin("mail_access")
    relationship["target"] = "nodes.app.runtime.mail_services.mail"
    relationship["mail_access"]["domain_ref"] = "domains"
    base = _fixture(relationship)
    app = base.nodes["app"]
    mail = app.runtime.mail_services[0]
    domains = [domain.model_copy(update={"domain_id": "other-domain"}) for domain in mail.domains]
    runtime = app.runtime.model_copy(update={"mail_services": [mail.model_copy(update={"domains": domains})]})
    derived = base.model_copy(update={"nodes": {**base.nodes, "app": app.model_copy(update={"runtime": runtime})}})
    session = ValidationSession()

    assert _outcome(base, session)[0] == []
    errors = _outcome(derived, session)[0]

    assert errors == _reference(derived)[0]
    assert errors == ["Relationship 'probe' mail_access domain_ref 'domains' does not resolve inside mail service"]


def test_member_admission_runs_once_earlier_errors_are_fixed() -> None:
    payload = deepcopy(_family_payload())
    payload["nodes"]["network"] = {"type": "switch"}
    payload["variation_points"]["host-choice"]["alternatives"]["network"] = {"reference": "network"}
    clean = Scenario.model_validate(payload)
    primary = clean.nodes["primary"]
    broken_primary = primary.model_copy(update={"features": {**primary.features, "undeclared-feature": ""}})
    broken = clean.model_copy(update={"nodes": {**clean.nodes, "primary": broken_primary}})
    session = ValidationSession()

    broken_errors = _outcome(broken, session)[0]
    clean_errors = _outcome(clean, session)[0]

    assert not any("invalid for target slot" in error for error in broken_errors)
    assert clean_errors == _reference(clean)[0]
    assert any("invalid for target slot" in error for error in clean_errors)


def test_a_pass_that_consults_the_declaration_index_depends_on_it() -> None:
    # A new feature named like the relationship target changes only the index;
    # the relationship pass must see the endpoint become ambiguous.
    base = _fixture(typed("connects_to", source="dc", target="corp"))
    feature = next(iter(base.features.values()))
    derived = base.model_copy(update={"features": {**base.features, "corp": feature}})
    session = ValidationSession()

    assert _outcome(base, session)[0] == []
    errors = _outcome(derived, session)[0]

    assert errors == _reference(derived)[0]
    assert any("ambiguous" in error for error in errors)
