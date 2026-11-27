"""Rule-source choices on a network detection engine and resolved ``generated_by`` references."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest
import yaml
from jsonschema import Draft202012Validator
from paths import REPO_ROOT
from raes import SDLValidationError, select_scenario_family
from raes.canonical import canonical_sdl_bytes
from raes.parser import parse_sdl_file
from raes.scenario import ExpandedScenario, InstantiatedScenario
from raes.selected_scenario import SDLSelectionError
from raes.validator import SemanticValidator
from raes_contracts.contracts import ExperimentSelectionMemberOutcomeModel

_SCHEMA_PATH = REPO_ROOT / "contracts/schemas/sdl/sdl-authoring-input-v1.json"
_SLOT = "nodes.runtime.network_detection_engines.rule_sources"
_ENGINE = "nodes.sensor.runtime.network_detection_engines.engine"
_AGENT = "nodes.sync.runtime.forwarding_agents.misp-ioc-to-suricata"
_LOCAL = f"{_ENGINE}.rule_sources.local-rules"
_MISP = f"{_ENGINE}.rule_sources.misp-iocs"


def _compute(runtime: dict) -> dict:
    return {"type": "compute", "os": "linux", "resources": {"ram": "1 gib", "cpu": 1}, "runtime": runtime}


def _engine(engine_id: str = "engine") -> dict:
    return {
        "network_detection_engine_id": engine_id,
        "implementation": "suricata",
        "rule_sources": [
            {"source_id": "local-rules", "kind": "local", "name": "local.rules"},
            {"source_id": "misp-iocs", "kind": "ioc", "name": "misp-iocs.rules", "generated_by": _AGENT},
            {"source_id": "community", "kind": "community", "name": "community.rules"},
        ],
    }


def _rule_sources_point(owner: str = _ENGINE, retained: list[str] | None = None) -> dict:
    return {
        "kind": "alternative",
        "target": {"kind": "structural", "owner": owner, "slot": _SLOT},
        "alternatives": {
            "without-misp": {"kind": "runtime-inventory", "references": [_LOCAL] if retained is None else retained},
            "all": {"kind": "runtime-inventory", "references": [_LOCAL, _MISP, f"{_ENGINE}.rule_sources.community"]},
        },
    }


def _payload() -> dict:
    """The observed case: the engine's `misp-iocs` source names an agent on the variable `sync` node."""

    return {
        "name": "misp-family",
        "nodes": {
            "sync": _compute({"forwarding_agents": [{"forwarding_agent_id": "misp-ioc-to-suricata"}]}),
            "sensor": _compute({"network_detection_engines": [_engine()]}),
        },
        "infrastructure": {"sync": {"count": 1}, "sensor": {"count": 1}},
        "variation_points": {
            "sync-host": {
                "kind": "alternative",
                "target": {"kind": "structural", "owner": "sync", "slot": "nodes.presence"},
                "alternatives": {
                    "absent": {
                        "kind": "node-presence",
                        "present": False,
                        "requires": [{"point": "misp-rules", "members": ["without-misp"]}],
                    },
                    "present": {"kind": "node-presence", "present": True},
                },
            },
            "misp-rules": _rule_sources_point(),
        },
    }


def _family(payload: dict | None = None) -> ExpandedScenario:
    family = ExpandedScenario.model_validate(_payload() if payload is None else payload)
    SemanticValidator(family).validate()
    family._set_semantic_validated(True)
    return family


def _outcome(member: str) -> ExperimentSelectionMemberOutcomeModel:
    return ExperimentSelectionMemberOutcomeModel(kind="member", member_id=member)


def _source_ids(scenario: object, node: str = "sensor") -> list[str]:
    return [source.source_id for source in scenario.nodes[node].runtime.network_detection_engines[0].rule_sources]


def _errors(payload: dict) -> list[str]:
    validator = SemanticValidator(ExpandedScenario.model_validate(payload))
    with pytest.raises(SDLValidationError) as exc_info:
        validator.validate()
    return [str(error) for error in exc_info.value.errors]


def test_node_absence_with_rule_source_choice_passes_whole_scenario_admission() -> None:
    family = _family()
    before = canonical_sdl_bytes(family)
    selected = select_scenario_family(family, {"sync-host": _outcome("absent"), "misp-rules": _outcome("without-misp")})

    assert set(selected.nodes) == {"sensor"}
    assert _source_ids(selected) == ["local-rules"]
    engine = selected.nodes["sensor"].runtime.network_detection_engines[0]
    assert engine.implementation == family.nodes["sensor"].runtime.network_detection_engines[0].implementation
    InstantiatedScenario.model_validate(selected.model_dump())
    assert canonical_sdl_bytes(family) == before


def test_rule_source_choice_keeps_payload_and_source_order() -> None:
    payload = _payload()
    payload["variation_points"]["misp-rules"] = _rule_sources_point(
        retained=[f"{_ENGINE}.rule_sources.community", _LOCAL]
    )
    selected = select_scenario_family(
        _family(payload), {"sync-host": _outcome("absent"), "misp-rules": _outcome("without-misp")}
    )
    assert _source_ids(selected) == ["local-rules", "community"]
    assert selected.nodes["sensor"].runtime.network_detection_engines[0].rule_sources[1].name == "community.rules"


def test_present_selection_keeps_every_rule_source() -> None:
    selected = select_scenario_family(_family(), {"sync-host": _outcome("present"), "misp-rules": _outcome("all")})
    assert set(selected.nodes) == {"sync", "sensor"}
    assert _source_ids(selected) == ["local-rules", "misp-iocs", "community"]


def test_absent_generator_without_rule_source_choice_fails_admission() -> None:
    payload = _payload()
    del payload["variation_points"]["sync-host"]["alternatives"]["absent"]["requires"]
    family = _family(payload)
    outcomes = {"sync-host": _outcome("absent"), "misp-rules": _outcome("all")}
    with pytest.raises(SDLSelectionError, match="whole-scenario semantic admission"):
        select_scenario_family(family, outcomes)


@pytest.mark.parametrize(
    "references",
    [
        [_ENGINE],
        ["nodes.sensor.runtime.network_detection_engines.other.rule_sources.local-rules"],
        [f"{_ENGINE}.rule_sources.missing"],
        [f"{_ENGINE}.network_sets.home-net"],
    ],
)
def test_candidates_must_be_rule_sources_of_the_owner_engine(references: list[str]) -> None:
    payload = _payload()
    payload["nodes"]["sensor"]["runtime"]["network_detection_engines"].append(_engine("other"))
    payload["nodes"]["sensor"]["runtime"]["network_detection_engines"][0]["network_sets"] = [{"set_id": "home-net"}]
    payload["variation_points"]["misp-rules"] = _rule_sources_point(retained=references)
    errors = _errors(payload)
    assert any("member 'without-misp' has an invalid structural target or candidate" in error for error in errors)


@pytest.mark.parametrize(
    "owner",
    ["sensor", "nodes.sensor", "nodes.sensor.runtime.network_detection_engines.missing", _AGENT, _LOCAL],
)
def test_owner_must_resolve_to_one_network_detection_engine(owner: str) -> None:
    payload = _payload()
    payload["variation_points"]["misp-rules"]["target"]["owner"] = owner
    errors = _errors(payload)
    assert any("has an invalid structural target or candidate" in error for error in errors)


@pytest.mark.parametrize("reverse", [False, True])
def test_rule_source_write_conflicts_with_engine_inventory_write(reverse: bool) -> None:
    payload = _payload()
    payload["variation_points"]["engines"] = {
        "kind": "alternative",
        "target": {"kind": "structural", "owner": "sensor", "slot": "nodes.runtime.network_detection_engines"},
        "alternatives": {"keep": {"kind": "runtime-inventory", "references": [_ENGINE]}},
    }
    if reverse:
        payload["variation_points"] = dict(reversed(payload["variation_points"].items()))
    family = _family(payload)
    outcomes = {"sync-host": _outcome("absent"), "misp-rules": _outcome("without-misp"), "engines": _outcome("keep")}
    with pytest.raises(SDLSelectionError, match="conflicts with a descendant variation write"):
        select_scenario_family(family, outcomes)


def test_rule_source_write_conflicts_with_owner_node_absence() -> None:
    payload = _payload()
    payload["variation_points"]["sensor-host"] = {
        "kind": "alternative",
        "target": {"kind": "structural", "owner": "sensor", "slot": "nodes.presence"},
        "alternatives": {"absent": {"kind": "node-presence", "present": False}},
    }
    family = _family(payload)
    outcomes = {
        "sync-host": _outcome("present"),
        "misp-rules": _outcome("all"),
        "sensor-host": _outcome("absent"),
    }
    with pytest.raises(SDLSelectionError, match="conflict"):
        select_scenario_family(family, outcomes)


def test_equal_rule_source_writes_are_idempotent() -> None:
    payload = _payload()
    payload["variation_points"]["duplicate"] = deepcopy(payload["variation_points"]["misp-rules"])
    outcomes = {
        "sync-host": _outcome("absent"),
        "misp-rules": _outcome("without-misp"),
        "duplicate": _outcome("without-misp"),
    }
    family = _family(payload)
    assert _source_ids(select_scenario_family(family, outcomes)) == ["local-rules"]
    outcomes["duplicate"] = _outcome("all")
    with pytest.raises(SDLSelectionError, match="conflicting values for one canonical target"):
        select_scenario_family(family, outcomes)


def _write_module(tmp_path: Path, payload: dict, exports: dict) -> Path:
    payload = {**payload, "version": "1.0.0", "module": {"id": "example/misp", "version": "1.0.0", "exports": exports}}
    (tmp_path / "family.yaml").write_text(yaml.safe_dump(payload), encoding="utf-8")
    root = tmp_path / "root.yaml"
    root.write_text(
        "name: root\nimports:\n  - path: family.yaml\n    namespace: shared\n    version: 1.0.0\n", encoding="utf-8"
    )
    return root


def test_retained_rule_source_evidence_follows_its_identity(tmp_path: Path) -> None:
    payload = _payload()
    payload["variables"] = {"loaded": {"type": "boolean", "default": True, "allowed_values": [True, False]}}
    for source in payload["nodes"]["sensor"]["runtime"]["network_detection_engines"][0]["rule_sources"]:
        source["loaded"] = "${loaded}"
    payload["variation_points"]["misp-rules"] = _rule_sources_point(
        retained=[_LOCAL, f"{_ENGINE}.rule_sources.community"]
    )
    nodes = list(payload["nodes"])
    exports = {"nodes": nodes, "infrastructure": nodes, "variation_points": list(payload["variation_points"])}
    family = parse_sdl_file(_write_module(tmp_path, payload, exports))
    outcomes = {"shared.sync-host": _outcome("absent"), "shared.misp-rules": _outcome("without-misp")}
    selected = select_scenario_family(family, outcomes)

    assert _source_ids(selected, "shared.sensor") == ["local-rules", "community"]
    pointer = "/nodes/shared.sensor/runtime/network_detection_engines/0/rule_sources/"
    assert sorted(item.field_pointer for item in selected.instantiation_provenance.capability_constraints) == [
        f"{pointer}0/loaded",
        f"{pointer}1/loaded",
    ]
    paths = {record.model_path for record in selected.instantiation_provenance.explicitness}
    model = "nodes.shared.sensor.runtime.network_detection_engines[0].rule_sources"
    assert f"{model}[1].name" in paths
    assert f"{model}[2].name" not in paths
    InstantiatedScenario.model_validate(selected.model_dump())


def test_imported_owner_references_and_generator_use_composed_identity(tmp_path: Path) -> None:
    payload = _payload()
    root = _write_module(tmp_path, payload, {"variation_points": list(payload["variation_points"])})
    family = parse_sdl_file(root)

    engine = "nodes.shared.__private.sensor.runtime.network_detection_engines.engine"
    point = family.variation_points["shared.misp-rules"]
    assert point.target.owner == engine
    assert point.alternatives["without-misp"].references == [f"{engine}.rule_sources.local-rules"]
    source = family.nodes["shared.__private.sensor"].runtime.network_detection_engines[0].rule_sources[1]
    assert source.generated_by == "nodes.shared.__private.sync.runtime.forwarding_agents.misp-ioc-to-suricata"

    outcomes = {"shared.sync-host": _outcome("absent"), "shared.misp-rules": _outcome("without-misp")}
    selected = select_scenario_family(family, outcomes)
    assert _source_ids(selected, "shared.__private.sensor") == ["local-rules"]


@pytest.mark.parametrize(
    "generated_by",
    [
        "misp-suricata-sync",
        "nodes.sync.runtime.forwarding_agents.missing",
        "nodes.sync",
        _LOCAL,
        "forwarding_agents.misp-ioc-to-suricata",
    ],
)
def test_generated_by_must_resolve_to_a_declared_forwarding_agent(generated_by: str) -> None:
    payload = _payload()
    del payload["variation_points"]
    source = payload["nodes"]["sensor"]["runtime"]["network_detection_engines"][0]["rule_sources"][1]
    source["generated_by"] = generated_by
    errors = _errors(payload)
    assert any(
        f"generated_by '{generated_by}' does not resolve to a declared forwarding agent" in error for error in errors
    )


@pytest.mark.parametrize("generated_by", [_AGENT, "forwarding_agents.scenario-sync", "${generator}"])
def test_generated_by_resolves_node_scoped_and_scenario_agents(generated_by: str) -> None:
    payload = _payload()
    del payload["variation_points"]
    payload["forwarding_agents"] = [{"forwarding_agent_id": "scenario-sync"}]
    payload["variables"] = {"generator": {"type": "string", "default": _AGENT}}
    source = payload["nodes"]["sensor"]["runtime"]["network_detection_engines"][0]["rule_sources"][1]
    source["generated_by"] = generated_by
    SemanticValidator(ExpandedScenario.model_validate(payload)).validate()


def test_static_scenario_rejects_generator_on_a_removed_node() -> None:
    payload = _payload()
    del payload["variation_points"]
    del payload["nodes"]["sync"]
    del payload["infrastructure"]["sync"]
    errors = _errors(payload)
    assert any(f"generated_by '{_AGENT}' does not resolve" in error for error in errors)


def test_published_schema_admits_rule_source_slot() -> None:
    validator = Draft202012Validator(json.loads(_SCHEMA_PATH.read_text()))
    validator.validate(_payload())
    invalid = _payload()
    invalid["variation_points"]["misp-rules"]["alternatives"]["all"] = {"kind": "node-presence", "present": True}
    assert list(validator.iter_errors(invalid))


def test_language_service_scopes_rule_source_candidates_to_the_owner_engine() -> None:
    from raes.language_service import language_completions, language_references

    payload = _payload()
    payload["nodes"]["sensor"]["runtime"]["network_detection_engines"].append(_engine("other"))
    source = yaml.safe_dump(payload)
    result = language_completions(
        source, cursor_path="/variation_points/misp-rules/alternatives/without-misp/references"
    )
    assert {item["label"] for item in result["items"]} == {_LOCAL, _MISP, f"{_ENGINE}.rule_sources.community"}
    refs = language_references(source, _LOCAL)
    assert any(
        item["path"] == "/variation_points/misp-rules/alternatives/without-misp/references/0"
        for item in refs["occurrences"]
    )
