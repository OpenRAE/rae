"""Cross-authority, scope, and published-contract locks for issue #1212."""

import pytest
from jsonschema import Draft202012Validator
from raes_contracts.contracts import schema_bundle
from raes_contracts.observation_demand import (
    EffectiveObservationDemand,
    ObservationDemandDocument,
    ObservationDemandRule,
    ObservationSelector,
    execute_observation_lifecycle,
    normalize_observation_demands,
)
from raes_contracts.realization_structure import (
    RealizationClosure,
    RealizationCollectionProfile,
    canonical_semantic_address,
)


def _selector(scope: str, name: str) -> ObservationSelector:
    return ObservationSelector(semantic_scope=scope, data_kind="stream", names=(name,))


def _resolve(*rules: ObservationDemandRule, scopes: tuple[str, ...] = ("/nodes",)):
    return normalize_observation_demands(
        ObservationDemandDocument(
            schema_version="observation-demand/v1",
            document_id="policy-boundaries",
            scope_profile="recursive-realization-constraint/v1",
            rules=rules,
        ),
        target_scopes=scopes,
    )


def test_independent_selectors_keep_requiredness_and_retention() -> None:
    optional = _selector("/nodes", "private-trace")
    mandatory = _selector("/nodes", "audit")
    resolution = _resolve(
        ObservationDemandRule(
            rule_id="author",
            scope="/nodes",
            purpose="experimental",
            mode="selected",
            selector=optional,
            redaction="none",
            integrity="none",
            retention="disable",
        ),
        ObservationDemandRule(
            rule_id="operator",
            authority_ref="operator",
            scope="/nodes",
            purpose="experimental",
            mode="selected",
            selector=mandatory,
            redaction="none",
            integrity="none",
            retention="require",
            required=True,
        ),
    )
    assert resolution.is_valid
    result = execute_observation_lifecycle(
        resolution,
        producers={mandatory.key: lambda: ("audit",)},
        supported=frozenset({mandatory.key}),
    )
    assert [item.values for item in result.retained] == [("audit",)]

    result = execute_observation_lifecycle(
        resolution,
        producers={mandatory.key: lambda: ("audit",), optional.key: lambda: ("private",)},
        supported=frozenset({mandatory.key, optional.key}),
    )
    assert len(result.collected) == 2
    assert [item.values for item in result.retained] == [("audit",)]


def test_narrow_selector_is_collected_once_when_rule_scope_is_broader() -> None:
    selector = _selector("/nodes", "trace")
    resolution = _resolve(
        ObservationDemandRule(
            rule_id="parent",
            scope="",
            purpose="experimental",
            mode="selected",
            selector=selector,
            redaction="none",
            integrity="none",
            retention="require",
        ),
        scopes=("", "/nodes"),
    )
    assert resolution.is_valid
    calls = []
    result = execute_observation_lifecycle(
        resolution,
        producers={selector.key: lambda: calls.append("collect") or ("event",)},
        supported=frozenset({selector.key}),
    )
    assert calls == ["collect"]
    assert [item.values for item in result.retained] == [("event",)]
    for demand in resolution.effective:
        EffectiveObservationDemand.model_validate(demand.model_dump())


@pytest.mark.parametrize("collection_only_retention, valid", [(None, True), ("disable", False)])
def test_mandatory_collection_composes_with_explicit_retention(collection_only_retention, valid) -> None:
    selector = _selector("/nodes", "audit")
    resolution = _resolve(
        *(
            ObservationDemandRule(
                rule_id=authority,
                authority_ref=authority,
                scope="/nodes",
                purpose="experimental",
                mode="selected",
                selector=selector,
                collection="require",
                retention=retention,
                redaction="none",
                integrity="none",
                required=True,
            )
            for authority, retention in (("collection", collection_only_retention), ("archive", "require"))
        )
    )
    assert resolution.is_valid is valid
    if valid:
        result = execute_observation_lifecycle(
            resolution,
            producers={selector.key: lambda: ("audit",)},
            supported=frozenset({selector.key}),
        )
        assert [item.values for item in result.retained] == [("audit",)]


def test_child_retention_only_collects_the_child_partition() -> None:
    resolution = _resolve(
        ObservationDemandRule(
            rule_id="parent",
            scope="/nodes",
            purpose="experimental",
            mode="selected",
            selector=_selector("/nodes", "trace"),
            redaction="none",
            integrity="none",
        ),
        ObservationDemandRule(
            rule_id="child",
            scope="/nodes/sensitive",
            purpose="experimental",
            retention="require",
        ),
        scopes=("/nodes", "/nodes/sensitive"),
    )
    assert resolution.is_valid
    selectors = [selector for demand in resolution.effective for selector in demand.selectors]
    data = {"/nodes/public": "public", "/nodes/sensitive": "sensitive"}

    def produce(selector):
        return tuple(
            value
            for scope, value in data.items()
            if scope.startswith(selector.semantic_scope)
            and not any(scope.startswith(excluded) for excluded in selector.excluded_scopes)
        )

    result = execute_observation_lifecycle(
        resolution,
        producers={selector.key: lambda selector=selector: produce(selector) for selector in selectors},
        supported=frozenset(selector.key for selector in selectors),
    )
    assert [item.values for item in result.retained] == [("sensitive",)]
    assert sorted(value for item in result.collected for value in item.values) == ["public", "sensitive"]


def test_positional_member_rejects_duplicate_profile_identities() -> None:
    profile = RealizationCollectionProfile(
        field_pointer="/items",
        collection_kind="test",
        identity_fields=("name",),
        closure=RealizationClosure(
            posture="closed",
            universe="test/v1",
            profile="recursive-realization-constraint/v1",
        ),
    )
    with pytest.raises(ValueError, match="unique"):
        canonical_semantic_address(
            "/items/0",
            {"items": [{"name": "same"}, {"name": "same"}]},
            collection_profiles=(profile,),
        )


@pytest.mark.parametrize("other_name, valid", [("private-trace", False), ("audit", True)])
def test_selector_prohibition_blocks_only_overlapping_independent_retention(other_name: str, valid: bool) -> None:
    resolution = _resolve(
        ObservationDemandRule(
            rule_id="privacy",
            scope="/nodes",
            purpose="experimental",
            mode="selected",
            selector=_selector("/nodes", "private-trace"),
            redaction="none",
            integrity="none",
            retention="forbid",
        ),
        ObservationDemandRule(
            rule_id="operator",
            authority_ref="operator",
            scope="/nodes",
            purpose="experimental",
            mode="selected",
            selector=_selector("/nodes", other_name),
            redaction="none",
            integrity="none",
            retention="require",
            required=True,
        ),
    )
    assert resolution.is_valid is valid
    if not valid:
        with pytest.raises(ValueError, match="invalid-observation-demand"):
            execute_observation_lifecycle(resolution, producers={}, supported=frozenset())


def test_experimental_none_does_not_disable_independent_operational_readback() -> None:
    from types import SimpleNamespace

    from raes_contracts.realization_observation_demand import compute_substrate_demand_applies

    resolution = _resolve(
        ObservationDemandRule(
            rule_id="operational",
            scope="/nodes",
            purpose="operational",
            mode="operational-only",
            selector=ObservationSelector(semantic_scope="/nodes", data_kind="field", names=("compute-substrate",)),
        ),
        ObservationDemandRule(rule_id="none", scope="/nodes/vm", purpose="experimental", mode="none"),
        scopes=("/nodes", "/nodes/vm"),
    )
    assert resolution.is_valid
    constraint = SimpleNamespace(governing_scope="#/nodes/vm", concern="compute-substrate", address="provision.node.vm")
    plan = SimpleNamespace(observation_demands=resolution.effective)
    assert compute_substrate_demand_applies(plan, constraint, stage="collection")
    assert not compute_substrate_demand_applies(plan, constraint, stage="retention")


@pytest.mark.parametrize(
    "changes",
    [
        {"mode": "none"},
        {"mode": "inherit"},
        {"mode": "exhaustive"},
        {"collection": "inherit"},
        {"collection": "disable", "retention": "require"},
        {"mode": "operational-only"},
    ],
)
def test_effective_policy_invariants_match_published_plan_schema(changes: dict[str, object]) -> None:
    value = {
        "scope": "/nodes",
        "purpose": "experimental",
        "mode": "selected",
        "selectors": [_selector("/nodes", "trace").model_dump(mode="json")],
        "collection": "require",
        "retention": "disable",
        "export": "disable",
        "basis": "observed",
        "redaction": "none",
        "integrity": "none",
        **changes,
    }
    with pytest.raises(ValueError):
        EffectiveObservationDemand.model_validate(value)
    validator = Draft202012Validator(schema_bundle()["provisioning-plan-v1"])
    assert list(validator.iter_errors({"realization_authority": [], "observation_demands": [value]}))
