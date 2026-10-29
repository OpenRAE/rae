"""Explicit presence and consumer choices for declarations that depend on a variable node."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest
import yaml
from jsonschema import Draft202012Validator
from paths import REPO_ROOT
from pydantic import ValidationError
from raes import SDLValidationError, select_scenario_family
from raes.canonical import canonical_sdl_bytes, canonical_sdl_digest
from raes.parser import parse_sdl_file
from raes.scenario import ExpandedScenario, InstantiatedScenario
from raes.selected_scenario import SDLSelectionError
from raes.validator import SemanticValidator
from raes_contracts.contracts import ExperimentSelectionMemberOutcomeModel

_SCHEMA_PATH = REPO_ROOT / "contracts/schemas/sdl/sdl-authoring-input-v1.json"


def _compute() -> dict:
    return {"type": "compute", "os": "linux", "resources": {"ram": "1 gib", "cpu": 1}}


def _artifact(consumers: list[dict]) -> dict:
    return {
        "generator": "certificate_bundle",
        "lifecycle": "reuse_valid",
        "provenance": "example:certs/v1",
        "outputs": [{"name": "ca-certificate", "path": "ca.pem", "sensitivity": "public"}],
        "consumers": consumers,
    }


def _cert_consumer(node: str, mount: str) -> dict:
    return {
        "node": node,
        "mount_destination": mount,
        "access_mode": "read_only",
        "selected_outputs": ["ca-certificate"],
    }


def _presence(owner: str, slot: str) -> dict:
    return {
        "kind": "alternative",
        "target": {"kind": "structural", "owner": owner, "slot": slot},
        "alternatives": {
            "absent": {"kind": "declaration-presence", "present": False},
            "present": {"kind": "declaration-presence", "present": True},
        },
    }


def _consumers(owner: str, slot: str, retained: list[dict], complete: list[dict]) -> dict:
    return {
        "kind": "alternative",
        "target": {"kind": "structural", "owner": owner, "slot": slot},
        "alternatives": {
            "without-intel": {"kind": "resource-consumers", "consumers": retained},
            "all": {"kind": "resource-consumers", "consumers": complete},
        },
    }


_DEPENDENT_POINTS = {
    "db-host": "absent",
    "admin": "absent",
    "config": "absent",
    "data": "absent",
    "rules": "without-intel",
    "certs": "without-intel",
    "intel-certs": "absent",
    "uses-db": "absent",
    "ready-proposition": "absent",
    "ready-assertion": "absent",
    "readiness": "absent",
}


def _payload() -> dict:
    """A family where the coupled `intel` and `intel-db` nodes own every dependent kind."""

    sensor_rules = {"node": "sensor", "mount_destination": "/rules"}
    intel_rules = {"node": "intel", "mount_destination": "/rules"}
    intel_copy = {"node": "intel", "mount_destination": "/rules-copy"}
    return {
        "name": "intel-family",
        "nodes": {"intel": _compute(), "intel-db": _compute(), "sensor": _compute()},
        "infrastructure": {"intel": {"count": 1}, "intel-db": {"count": 1}, "sensor": {"count": 1}},
        "accounts": {"intel-admin": {"username": "admin", "node": "intel"}},
        "content": {"intel-config": {"type": "file", "target": "intel", "path": "/opt/intel/config"}},
        "persistent_volumes": {
            "intel_data": {
                "lifecycle": "retain",
                "access_mode": "read_write_once",
                "consumers": [{"node": "intel", "mount_destination": "/data", "access_mode": "read_write"}],
            },
            "shared_rules": {
                "lifecycle": "ephemeral",
                "access_mode": "read_write_many",
                "consumers": [
                    {**sensor_rules, "access_mode": "read_only"},
                    {**intel_rules, "access_mode": "read_write"},
                    {**intel_copy, "access_mode": "read_only"},
                ],
            },
        },
        "generated_artifacts": {
            "certs": _artifact([_cert_consumer("intel", "/certs"), _cert_consumer("sensor", "/certs")]),
            "intel-certs": _artifact([_cert_consumer("intel", "/intel-certs")]),
        },
        "relationships": {"intel-uses-db": {"type": "depends_on", "source": "intel", "target": "intel-db"}},
        "propositions": {
            "intel-ready": {
                "description": "Intel is ready.",
                "subjects": ["nodes.intel", "nodes.intel-db"],
                "basis": "observed_state",
                "predicate": {
                    "kind": "boolean",
                    "property": "intel-ready",
                    "semantic_ref": "urn:example:observable:intel-ready",
                    "expected": True,
                },
                "evidence_requirements": ["intel-readiness"],
            }
        },
        "assertions": {"intel-ready": {"proposition": "intel-ready", "role": "postcondition"}},
        "evidence_requirements": {
            "intel-readiness": {
                "description": "Intel readiness.",
                "source_refs": ["nodes.intel"],
                "scope_refs": ["nodes.intel", "nodes.intel-db"],
                "boundary_kind": "system_under_test",
                "channel": "api_response",
                "artifact_role": "proposition_truth_evidence",
                "media_types": ["application/json"],
                "sensitivity": "plain",
                "redaction": "redact_secrets",
                "integrity": "checksum",
                "retention": "run_lifetime",
                "loss_disclosure": "required",
            }
        },
        "variation_points": {
            "intel-host": {
                "kind": "alternative",
                "target": {"kind": "structural", "owner": "intel", "slot": "nodes.presence"},
                "alternatives": {
                    "absent": {
                        "kind": "node-presence",
                        "present": False,
                        "requires": [
                            {"point": point, "members": [member]} for point, member in _DEPENDENT_POINTS.items()
                        ],
                    },
                    "present": {"kind": "node-presence", "present": True},
                },
            },
            "db-host": {
                "kind": "alternative",
                "target": {"kind": "structural", "owner": "intel-db", "slot": "nodes.presence"},
                "alternatives": {
                    "absent": {"kind": "node-presence", "present": False},
                    "present": {"kind": "node-presence", "present": True},
                },
            },
            "admin": _presence("intel-admin", "accounts.presence"),
            "config": _presence("intel-config", "content.presence"),
            "data": _presence("intel_data", "persistent_volumes.presence"),
            "rules": _consumers(
                "shared_rules",
                "persistent_volumes.consumers",
                [sensor_rules],
                [sensor_rules, intel_rules, intel_copy],
            ),
            "certs": _consumers(
                "certs",
                "generated_artifacts.consumers",
                [{"node": "sensor", "mount_destination": "/certs"}],
                [{"node": "intel", "mount_destination": "/certs"}, {"node": "sensor", "mount_destination": "/certs"}],
            ),
            "intel-certs": _presence("intel-certs", "generated_artifacts.presence"),
            "uses-db": _presence("intel-uses-db", "relationships.presence"),
            "ready-proposition": _presence("propositions.intel-ready", "propositions.presence"),
            "ready-assertion": _presence("assertions.intel-ready", "assertions.presence"),
            "readiness": _presence("intel-readiness", "evidence_requirements.presence"),
        },
    }


def _family(payload: dict | None = None) -> ExpandedScenario:
    family = ExpandedScenario.model_validate(_payload() if payload is None else payload)
    SemanticValidator(family).validate()
    family._set_semantic_validated(True)
    return family


def _outcome(member: str) -> ExperimentSelectionMemberOutcomeModel:
    return ExperimentSelectionMemberOutcomeModel(kind="member", member_id=member)


def _absent_outcomes() -> dict[str, ExperimentSelectionMemberOutcomeModel]:
    return {
        "intel-host": _outcome("absent"),
        **{point: _outcome(member) for point, member in _DEPENDENT_POINTS.items()},
    }


def _present_outcomes() -> dict[str, ExperimentSelectionMemberOutcomeModel]:
    present = {"rules": "all", "certs": "all"}
    return {point: _outcome(present.get(point, "present")) for point in _payload()["variation_points"]}


def test_node_absence_with_every_dependent_kind_passes_whole_scenario_admission() -> None:
    family = _family()
    before = canonical_sdl_bytes(family)
    selected = select_scenario_family(family, _absent_outcomes())

    assert selected.semantic_validated
    assert set(selected.nodes) == set(selected.infrastructure) == {"sensor"}
    assert selected.accounts == selected.content == selected.relationships == {}
    assert selected.propositions == selected.assertions == selected.evidence_requirements == {}
    assert set(selected.persistent_volumes) == {"shared_rules"}
    assert set(selected.generated_artifacts) == {"certs"}
    rules = selected.persistent_volumes["shared_rules"].consumers
    assert [(row.node, row.mount_destination, row.access_mode.value) for row in rules] == [
        ("sensor", "/rules", "read_only")
    ]
    certs = selected.generated_artifacts["certs"].consumers
    assert [(row.node, row.selected_outputs) for row in certs] == [("sensor", ["ca-certificate"])]
    assert "variation_points" not in selected.model_dump()
    InstantiatedScenario.model_validate(selected.model_dump())
    assert canonical_sdl_bytes(family) == before


def test_present_selection_keeps_every_dependent_declaration() -> None:
    family = _family()
    digest = canonical_sdl_digest(family)
    selected = select_scenario_family(family, _present_outcomes())

    assert set(selected.nodes) == {"intel", "intel-db", "sensor"}
    assert set(selected.accounts) == {"intel-admin"}
    assert set(selected.persistent_volumes) == {"intel_data", "shared_rules"}
    assert set(selected.generated_artifacts) == {"certs", "intel-certs"}
    assert set(selected.propositions) == set(selected.assertions) == {"intel-ready"}
    rules = selected.persistent_volumes["shared_rules"].consumers
    assert rules == family.persistent_volumes["shared_rules"].consumers
    assert canonical_sdl_digest(family) == digest


@pytest.mark.parametrize(
    ("point", "member", "fragment"),
    [
        ("ready-assertion", "present", "whole-scenario semantic admission"),
        ("admin", "present", "whole-scenario semantic admission"),
        ("rules", "all", "whole-scenario semantic admission"),
    ],
)
def test_one_retained_dependent_rejects_the_whole_selection(point: str, member: str, fragment: str) -> None:
    payload = _payload()
    del payload["variation_points"]["intel-host"]["alternatives"]["absent"]["requires"]
    outcomes = {**_absent_outcomes(), point: _outcome(member)}
    family = _family(payload)
    with pytest.raises(SDLSelectionError, match=fragment):
        select_scenario_family(family, outcomes)


def test_consumer_choice_keeps_selected_rows_payload_and_source_order() -> None:
    payload = _payload()
    payload["variation_points"] = {
        "rules": _consumers(
            "shared_rules",
            "persistent_volumes.consumers",
            [
                {"node": "intel", "mount_destination": "/rules-copy"},
                {"node": "nodes.sensor", "mount_destination": "/rules"},
            ],
            [{"node": "intel", "mount_destination": "/rules"}],
        )
    }
    family = _family(payload)
    selected = select_scenario_family(family, {"rules": _outcome("without-intel")})
    original = family.persistent_volumes["shared_rules"].consumers
    assert selected.persistent_volumes["shared_rules"].consumers == [original[0], original[2]]


@pytest.mark.parametrize(
    "selector",
    [
        {"node": "intel", "mount_destination": "/missing"},
        {"node": "ghost", "mount_destination": "/rules"},
        {"node": "intel-db", "mount_destination": "/rules"},
    ],
)
def test_consumer_selectors_must_identify_existing_owner_rows(selector: dict) -> None:
    payload = _payload()
    payload["variation_points"]["rules"]["alternatives"]["without-intel"]["consumers"] = [selector]
    with pytest.raises(SDLValidationError, match="Variation point 'rules'") as raised:
        _family(payload)
    assert selector["mount_destination"] not in str(raised.value)


def test_two_selectors_cannot_identify_one_row() -> None:
    payload = _payload()
    payload["variation_points"]["rules"]["alternatives"]["without-intel"]["consumers"] = [
        {"node": "sensor", "mount_destination": "/rules"},
        {"node": "nodes.sensor", "mount_destination": "/rules"},
    ]
    with pytest.raises(SDLValidationError, match="Variation point 'rules'"):
        _family(payload)


@pytest.mark.parametrize(
    ("point", "member"),
    [("rules", {"kind": "resource-consumers", "consumers": []}), ("certs", None)],
)
def test_last_volume_consumer_and_orphan_artifact_fail_admission(point: str, member: dict | None) -> None:
    payload = _payload()
    payload["variation_points"] = {"choice": deepcopy(payload["variation_points"][point])}
    alternatives = payload["variation_points"]["choice"]["alternatives"]
    if member is None:
        payload["generated_artifacts"]["certs"]["consumers"] = payload["generated_artifacts"]["certs"]["consumers"][:1]
        payload["variation_points"]["choice"]["alternatives"] = {
            "none": {"kind": "resource-consumers", "consumers": []},
            "all": {"kind": "resource-consumers", "consumers": [{"node": "intel", "mount_destination": "/certs"}]},
        }
        member_id = "none"
    else:
        alternatives["without-intel"] = member
        member_id = "without-intel"
    family = _family(payload)
    outcomes = {"choice": _outcome(member_id)}
    with pytest.raises(SDLSelectionError, match="whole-scenario semantic admission"):
        select_scenario_family(family, outcomes)


def test_removing_the_only_consumer_of_an_ssh_output_fails_admission() -> None:
    payload = _payload()
    payload["generated_artifacts"]["access"] = {
        "generator": "ssh_key_bundle",
        "lifecycle": "regenerate_on_change",
        "provenance": "example:ssh/v1",
        "outputs": [
            {"name": "private-key", "path": "id_ed25519", "sensitivity": "secret", "disposition": "producer_private"},
            {"name": "public-key", "path": "id_ed25519.pub", "sensitivity": "public"},
            {"name": "authorized-keys", "path": "authorized_keys", "sensitivity": "restricted"},
        ],
        "consumers": [
            {**_cert_consumer("sensor", "/ssh"), "selected_outputs": ["public-key"]},
            {**_cert_consumer("intel", "/home/operator/.ssh"), "selected_outputs": ["authorized-keys"]},
        ],
    }
    payload["variation_points"] = {
        "access": _consumers(
            "access",
            "generated_artifacts.consumers",
            [{"node": "sensor", "mount_destination": "/ssh"}],
            [
                {"node": "sensor", "mount_destination": "/ssh"},
                {"node": "intel", "mount_destination": "/home/operator/.ssh"},
            ],
        )
    }
    family = _family(payload)
    assert len(select_scenario_family(family, {"access": _outcome("all")}).generated_artifacts["access"].consumers) == 2
    outcomes = {"access": _outcome("without-intel")}
    with pytest.raises(SDLSelectionError, match="whole-scenario semantic admission"):
        select_scenario_family(family, outcomes)


def test_owner_resolves_only_in_the_slot_owner_section() -> None:
    payload = _payload()
    payload["variation_points"] = {
        "assertion": _presence("intel-ready", "assertions.presence"),
        "proposition": _presence("intel-ready", "propositions.presence"),
    }
    family = _family(payload)
    selected = select_scenario_family(family, {"assertion": _outcome("absent"), "proposition": _outcome("present")})
    assert set(selected.propositions) == {"intel-ready"}
    assert selected.assertions == {}

    payload["variation_points"] = {"wrong": _presence("intel", "accounts.presence")}
    with pytest.raises(SDLValidationError, match="Variation point 'wrong'"):
        _family(payload)


@pytest.mark.parametrize(
    ("slot", "member"),
    [
        ("accounts.presence", {"kind": "declaration-presence", "present": "false"}),
        ("accounts.presence", {"kind": "declaration-presence", "present": False, "consumers": []}),
        ("accounts.presence", {"kind": "node-presence", "present": False}),
        ("nodes.presence", {"kind": "declaration-presence", "present": False}),
        ("persistent_volumes.consumers", {"kind": "declaration-presence", "present": False}),
        ("persistent_volumes.consumers", {"kind": "resource-consumers", "consumers": [{"node": "intel"}]}),
        (
            "persistent_volumes.consumers",
            {
                "kind": "resource-consumers",
                "consumers": [{"node": "intel", "mount_destination": "/rules", "access_mode": "read_only"}],
            },
        ),
        ("accounts.node_presence", {"kind": "declaration-presence", "present": False}),
    ],
)
def test_dependent_choices_are_closed_and_type_strict(slot: str, member: dict) -> None:
    payload = _payload()
    payload["variation_points"] = {
        "choice": {
            "kind": "alternative",
            "target": {"kind": "structural", "owner": "intel-admin", "slot": slot},
            "alternatives": {"only": member},
        }
    }
    with pytest.raises(ValidationError):
        ExpandedScenario.model_validate(payload)
    assert list(Draft202012Validator(json.loads(_SCHEMA_PATH.read_text())).iter_errors(payload))


def test_consumer_selector_reuses_the_mount_path_validator() -> None:
    payload = _payload()
    payload["variation_points"]["rules"]["alternatives"]["all"]["consumers"][0]["mount_destination"] = "rules"
    with pytest.raises(ValidationError, match="mount_destination must be a canonical contained POSIX absolute path"):
        ExpandedScenario.model_validate(payload)


@pytest.mark.parametrize("reverse", [False, True])
@pytest.mark.parametrize("edit", ["reference", "consumers"])
def test_declaration_absence_conflicts_with_descendant_writes(edit: str, reverse: bool) -> None:
    payload = _payload()
    if edit == "reference":
        payload["variation_points"] = {
            "admin": _presence("intel-admin", "accounts.presence"),
            "host": {
                "kind": "alternative",
                "target": {"kind": "reference", "owner": "intel-admin", "slot": "accounts.node"},
                "alternatives": {"sensor": {"reference": "sensor"}},
            },
        }
        outcomes = {"admin": _outcome("absent"), "host": _outcome("sensor")}
    else:
        payload["variation_points"] = {
            "volume": _presence("shared_rules", "persistent_volumes.presence"),
            "rules": deepcopy(payload["variation_points"]["rules"]),
        }
        outcomes = {"volume": _outcome("absent"), "rules": _outcome("all")}
    if reverse:
        payload["variation_points"] = dict(reversed(payload["variation_points"].items()))
    family = _family(payload)
    with pytest.raises(SDLSelectionError, match="conflict"):
        select_scenario_family(family, outcomes)


def test_equal_declaration_removals_are_idempotent() -> None:
    payload = _payload()
    payload["variation_points"] = {
        "admin": _presence("intel-admin", "accounts.presence"),
        "duplicate": _presence("accounts.intel-admin", "accounts.presence"),
    }
    selected = select_scenario_family(_family(payload), {"admin": _outcome("absent"), "duplicate": _outcome("absent")})
    assert selected.accounts == {}


def test_qualified_declaration_name_is_not_a_descendant_write() -> None:
    payload = _payload()
    payload["accounts"]["intel-admin.child"] = deepcopy(payload["accounts"]["intel-admin"])
    payload["variation_points"] = {
        "admin": _presence("intel-admin", "accounts.presence"),
        "child-host": {
            "kind": "alternative",
            "target": {"kind": "reference", "owner": "intel-admin.child", "slot": "accounts.node"},
            "alternatives": {"sensor": {"reference": "sensor"}},
        },
    }
    selected = select_scenario_family(_family(payload), {"admin": _outcome("absent"), "child-host": _outcome("sensor")})
    assert set(selected.accounts) == {"intel-admin.child"}
    assert selected.accounts["intel-admin.child"].node == "sensor"


def _write_module(tmp_path: Path, payload: dict, exports: dict) -> Path:
    payload = {**payload, "version": "1.0.0", "module": {"id": "example/intel", "version": "1.0.0", "exports": exports}}
    (tmp_path / "family.yaml").write_text(yaml.safe_dump(payload), encoding="utf-8")
    root = tmp_path / "root.yaml"
    root.write_text(
        "name: root\nimports:\n  - path: family.yaml\n    namespace: shared\n    version: 1.0.0\n", encoding="utf-8"
    )
    return root


def test_imported_private_owner_and_selectors_use_composed_identity(tmp_path: Path) -> None:
    payload = _payload()
    root = _write_module(tmp_path, payload, {"variation_points": list(payload["variation_points"])})
    family = parse_sdl_file(root)
    assert family.variation_points["shared.admin"].target.owner == "shared.__private.intel-admin"
    selector = family.variation_points["shared.rules"].alternatives["without-intel"].consumers[0]
    assert selector.node == "shared.__private.sensor"

    outcomes = {f"shared.{point}": outcome for point, outcome in _absent_outcomes().items()}
    selected = select_scenario_family(family, outcomes)
    assert set(selected.nodes) == {"shared.__private.sensor"}
    assert selected.accounts == {}
    rules = selected.persistent_volumes["shared.__private.shared_rules"].consumers
    assert [row.node for row in rules] == ["shared.__private.sensor"]
    paths = {record.model_path for record in selected.instantiation_provenance.explicitness}
    removed = ("generated_artifacts.shared.__private.intel-certs", "persistent_volumes.shared.__private.intel_data")
    assert not any(path.startswith(prefix) for path in paths for prefix in removed)
    assert not any(".certs.consumers[1]" in path or ".shared_rules.consumers[1]" in path for path in paths)
    assert "generated_artifacts.shared.__private.certs.consumers[0].selected_outputs[0]" in paths
    InstantiatedScenario.model_validate(selected.model_dump())


def test_nodes_prefixed_consumer_reference_follows_import_namespace(tmp_path: Path) -> None:
    payload = _payload()
    del payload["variation_points"]
    payload["persistent_volumes"]["intel_data"]["consumers"][0]["node"] = "nodes.intel"
    payload["generated_artifacts"]["intel-certs"]["consumers"][0]["node"] = "nodes.intel"
    nodes = list(payload["nodes"])
    exports = {"nodes": nodes, "infrastructure": nodes, "persistent_volumes": ["intel_data"]}
    root = _write_module(tmp_path, payload, exports)
    family = parse_sdl_file(root)
    assert family.persistent_volumes["shared.intel_data"].consumers[0].node == "nodes.shared.intel"
    assert family.generated_artifacts["shared.__private.intel-certs"].consumers[0].node == "nodes.shared.intel"


def test_published_schema_admits_every_dependent_slot() -> None:
    validator = Draft202012Validator(json.loads(_SCHEMA_PATH.read_text()))
    validator.validate(_payload())


def test_language_service_completes_owners_and_selector_nodes() -> None:
    from raes.language_service import language_completions, language_references

    source = yaml.safe_dump(_payload())
    owners = language_completions(source, cursor_path="/variation_points/admin/target/owner")
    assert "intel-admin" in {item["label"] for item in owners["items"]}
    assert "intel" not in {item["label"] for item in owners["items"]}
    nodes = language_completions(source, cursor_path="/variation_points/rules/alternatives/all/consumers/0/node")
    assert {"intel", "intel-db", "sensor"} <= {item["label"] for item in nodes["items"]}
    refs = language_references(source, "sensor")
    assert any(
        item["path"] == "/variation_points/rules/alternatives/all/consumers/0/node" for item in refs["occurrences"]
    )


def test_public_fixture_parses_and_selects() -> None:
    path = REPO_ROOT / "contracts/fixtures/sdl/variation-points-v1/valid/dependent-declarations.yaml"
    family = ExpandedScenario.model_validate(
        parse_sdl_file(path).model_dump(mode="python", exclude={"module", "imports", "realization"})
    )
    SemanticValidator(family).validate()
    family._set_semantic_validated(True)
    outcomes = {
        "sync-host": _outcome("absent"),
        "sync-account": _outcome("absent"),
        "shared-mounts": _outcome("without-sync"),
    }
    selected = select_scenario_family(family, outcomes)
    assert set(selected.nodes) == {"sensor"}
    assert selected.accounts == {}
    assert [row.node for row in selected.persistent_volumes["rules"].consumers] == ["sensor"]


def _trial_request(*, isolated_content: str):
    from raes.canonical import canonical_sdl_digest as digest
    from test_issue_1666_factorial_admission import _selection_only, _with_family
    from test_issue_1666_factorial_compilation import _treatment_request, _with_design

    request = _selection_only(_treatment_request())
    family = request.family.model_dump(mode="python", by_alias=True)
    family["content"]["relay-input"] = {"type": "file", "target": "relay-47", "path": "/opt/input"}
    family["variation_points"]["relay-input-state"] = _presence("relay-input", "content.presence")
    request = _with_family(request, family)
    payload = request.experiment.model_dump(mode="json")
    levels = payload["factorial_design"]["level_effects"]["terrain-x"]
    for level, member in (("isolated", isolated_content), ("observed", "present")):
        template = levels[level]["selections"][0]
        levels[level]["selections"].append(
            {
                **template,
                "target": {
                    **template["target"],
                    "variation_point_id": "relay-input-state",
                    "target_id": "content.relay-input.presence",
                },
                "scenario_family_digest": digest(request.family).value,
                "outcome": {"kind": "member", "member_id": member},
            }
        )
    return _with_design(request, payload)


def test_coupled_dependent_treatment_reaches_admitted_snapshots() -> None:
    from raes_processor.trial_compiler import compile_admitted_trial_plan
    from raes_processor.trial_realization import instantiate_admitted_trial_entry

    request = _trial_request(isolated_content="absent")
    result = compile_admitted_trial_plan(request)
    assert result.plan is not None, result.diagnostics
    seen = set()
    for entry_id in result.plan.entries:
        selected = instantiate_admitted_trial_entry(plan=result.plan, plan_entry_id=entry_id, family=request.family)
        present = "relay-47" in selected.nodes
        assert ("relay-input" in selected.content) is present
        seen.add(present)
    assert seen == {False, True}


def test_one_invalid_dependent_treatment_rejects_the_complete_plan() -> None:
    from raes_processor.trial_compiler import compile_admitted_trial_plan

    result = compile_admitted_trial_plan(_trial_request(isolated_content="present"))
    assert result.plan is None
    assert result.diagnostics[0].code == "trial-compiler.selected-scenario-rejected"
    assert all("/opt/input" not in diagnostic.message for diagnostic in result.diagnostics)
