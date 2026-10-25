"""Node membership and owner-scoped inventory variation through public SDL admission."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError
from raes import SDLValidationError, select_scenario_family
from raes.canonical import canonical_instantiated_sdl_digest, canonical_sdl_bytes, canonical_sdl_digest
from raes.parser import parse_sdl_file
from raes.scenario import ExpandedScenario, InstantiatedScenario
from raes.validator import SemanticValidator
from raes_contracts.contracts import ExperimentSelectionMemberOutcomeModel


def _payload() -> dict:
    return {
        "name": "inventory-family",
        "nodes": {
            "host": {
                "type": "compute",
                "os": "linux",
                "resources": {"ram": "1 gib", "cpu": 1},
                "runtime": {
                    "scheduled_jobs": [
                        {"scheduled_job_id": "baseline", "name": "Baseline job"},
                        {"scheduled_job_id": "extra", "name": "Extra job"},
                    ]
                },
            }
        },
        "infrastructure": {"host": {"count": 1}},
        "variation_points": {
            "host-state": {
                "kind": "alternative",
                "target": {"kind": "structural", "owner": "host", "slot": "nodes.presence"},
                "alternatives": {
                    "absent": {"kind": "node-presence", "present": False},
                    "baseline": {
                        "kind": "node-presence",
                        "present": True,
                        "inventory": {"nodes.runtime.scheduled_jobs": ["nodes.host.runtime.scheduled_jobs.baseline"]},
                    },
                    "complete": {"kind": "node-presence", "present": True},
                },
            }
        },
    }


def _family(payload: dict | None = None) -> ExpandedScenario:
    family = ExpandedScenario.model_validate(_payload() if payload is None else payload)
    SemanticValidator(family).validate()
    family._set_semantic_validated(True)
    return family


def _outcome(member: str) -> ExperimentSelectionMemberOutcomeModel:
    return ExperimentSelectionMemberOutcomeModel(kind="member", member_id=member)


def _inventory_point(references: list[str]) -> dict:
    return {
        "kind": "alternative",
        "target": {"kind": "structural", "owner": "nodes.host", "slot": "nodes.runtime.scheduled_jobs"},
        "alternatives": {"chosen": {"kind": "runtime-inventory", "references": references}},
    }


def test_node_presence_and_coupled_inventory_preserve_family_identity() -> None:
    family = _family()
    before = canonical_sdl_bytes(family)
    digest = canonical_sdl_digest(family)
    complete = select_scenario_family(family, {"host-state": _outcome("complete")})
    baseline = select_scenario_family(family, {"host-state": _outcome("baseline")})
    absent = select_scenario_family(family, {"host-state": _outcome("absent")})

    assert [row.scheduled_job_id for row in complete.nodes["host"].runtime.scheduled_jobs] == ["baseline", "extra"]
    assert baseline.nodes["host"].runtime.scheduled_jobs == complete.nodes["host"].runtime.scheduled_jobs[:1]
    assert baseline.nodes["host"].runtime.scheduled_jobs[0].name == "Baseline job"
    assert absent.nodes == absent.infrastructure == {}
    assert complete.infrastructure["host"].count == 1
    assert canonical_sdl_bytes(family) == before
    assert canonical_sdl_digest(family) == digest
    assert baseline.semantic_validated and absent.semantic_validated
    assert "variation_points" not in baseline.model_dump()
    InstantiatedScenario.model_validate(baseline.model_dump())
    assert canonical_instantiated_sdl_digest(complete) != canonical_instantiated_sdl_digest(baseline)


def test_inventory_selection_keeps_payload_and_source_order() -> None:
    payload = _payload()
    payload["variation_points"] = {
        "jobs": _inventory_point(
            [
                "nodes.host.runtime.scheduled_jobs.extra",
                "nodes.host.runtime.scheduled_jobs.baseline",
            ]
        )
    }
    selected = select_scenario_family(_family(payload), {"jobs": _outcome("chosen")})
    assert [row.scheduled_job_id for row in selected.nodes["host"].runtime.scheduled_jobs] == ["baseline", "extra"]


@pytest.mark.parametrize(
    "references",
    [
        ["nodes.other.runtime.scheduled_jobs.baseline"],
        ["nodes.host.runtime.applications.baseline"],
        ["nodes.host.runtime.scheduled_jobs.missing"],
        ["host"],
    ],
)
def test_inventory_candidates_must_exist_in_the_exact_owner_collection(references: list[str]) -> None:
    payload = _payload()
    payload["nodes"]["other"] = deepcopy(payload["nodes"]["host"])
    payload["variation_points"] = {"jobs": _inventory_point(references)}
    with pytest.raises(SDLValidationError, match="Variation point"):
        _family(payload)


@pytest.mark.parametrize(
    "edit",
    [
        {"kind": "node-presence", "present": "false"},
        {"kind": "node-presence", "present": False, "inventory": {"nodes.runtime.scheduled_jobs": []}},
        {"kind": "runtime-inventory", "references": []},
        {"kind": "node-presence", "present": True, "patch": {"os": "windows"}},
    ],
)
def test_presence_choices_are_closed_and_type_strict(edit: dict) -> None:
    payload = _payload()
    payload["variation_points"]["host-state"]["alternatives"]["absent"] = edit
    with pytest.raises(ValidationError):
        ExpandedScenario.model_validate(payload)


def test_absence_does_not_remove_surviving_incoming_references() -> None:
    payload = _payload()
    payload["content"] = {"file": {"type": "file", "target": "host", "path": "/opt/file"}}
    family = _family(payload)
    with pytest.raises(ValueError, match="whole-scenario semantic admission"):
        select_scenario_family(family, {"host-state": _outcome("absent")})


@pytest.mark.parametrize("reverse", [False, True])
def test_absence_conflicts_with_descendant_writes_before_application(reverse: bool) -> None:
    payload = _payload()
    payload["variation_points"]["jobs"] = _inventory_point([])
    if reverse:
        payload["variation_points"] = dict(reversed(payload["variation_points"].items()))
    family = _family(payload)
    with pytest.raises(ValueError, match="conflict"):
        select_scenario_family(family, {"host-state": _outcome("absent"), "jobs": _outcome("chosen")})


def test_coupled_and_separate_inventory_writes_must_agree() -> None:
    payload = _payload()
    payload["variation_points"]["jobs"] = _inventory_point([])
    with pytest.raises(ValueError, match="conflict"):
        select_scenario_family(_family(payload), {"host-state": _outcome("baseline"), "jobs": _outcome("chosen")})


def test_imported_private_node_and_inventory_use_composed_identity(tmp_path: Path) -> None:
    payload = _payload()
    payload["version"] = "1.0.0"
    payload["module"] = {"id": "example/inventory", "version": "1.0.0", "exports": {"variation_points": ["host-state"]}}
    (tmp_path / "family.yaml").write_text(yaml.safe_dump(payload), encoding="utf-8")
    root = tmp_path / "root.yaml"
    root.write_text(
        "name: root\nimports:\n  - path: family.yaml\n    namespace: shared\n    version: 1.0.0\n", encoding="utf-8"
    )
    family = parse_sdl_file(root)
    point = family.variation_points["shared.host-state"]
    assert point.target.owner == "shared.__private.host"
    selected = select_scenario_family(family, {"shared.host-state": _outcome("baseline")})
    assert list(selected.nodes) == ["shared.__private.host"]
    assert selected.nodes["shared.__private.host"].runtime.scheduled_jobs[0].scheduled_job_id == "baseline"


def test_imported_inventory_remaps_surviving_parameter_evidence(tmp_path: Path) -> None:
    payload = _payload()
    payload["variables"] = {
        "flag": {"type": "boolean", "default": True, "allowed_values": [True, False]},
        "prefix": {"type": "string", "default": "job"},
    }
    for row in payload["nodes"]["host"]["runtime"]["scheduled_jobs"]:
        row["enabled"] = "${flag}"
        row["name"] = "${prefix}-" + row["scheduled_job_id"]
    payload["variation_points"] = {"jobs": _inventory_point(["nodes.host.runtime.scheduled_jobs.extra"])}
    payload["version"] = "1.0.0"
    payload["module"] = {
        "id": "example/parameters",
        "version": "1.0.0",
        "exports": {"nodes": ["host"], "infrastructure": ["host"], "variation_points": ["jobs"]},
    }
    (tmp_path / "family.yaml").write_text(yaml.safe_dump(payload), encoding="utf-8")
    root = tmp_path / "root.yaml"
    root.write_text(
        "name: root\nimports:\n  - path: family.yaml\n    namespace: shared\n    version: 1.0.0\n", encoding="utf-8"
    )
    family = parse_sdl_file(root)
    selected = select_scenario_family(family, {"shared.jobs": _outcome("chosen")})
    constraints = selected.instantiation_provenance.capability_constraints
    assert len(constraints) == 1
    assert constraints[0].field_pointer == "/nodes/shared.host/runtime/scheduled_jobs/0/enabled"
    assert constraints[0].allowed_values == (True, False)
    assert [item.field_pointer for item in selected.instantiation_provenance.parameter_derivations] == [
        "/nodes/shared.host/runtime/scheduled_jobs/0/name"
    ]
    assert selected.nodes["shared.host"].runtime.scheduled_jobs[0].scheduled_job_id == "extra"
    InstantiatedScenario.model_validate(selected.model_dump())


def test_duplicate_identical_absence_writes_are_idempotent() -> None:
    payload = _payload()
    payload["variation_points"]["duplicate"] = deepcopy(payload["variation_points"]["host-state"])
    result = select_scenario_family(
        _family(payload), {"host-state": _outcome("absent"), "duplicate": _outcome("absent")}
    )
    assert result.nodes == {}


def test_language_candidates_and_navigation_observe_inventory_owner() -> None:
    from raes.language_service import language_completions, language_references

    payload = _payload()
    payload["nodes"]["other"] = deepcopy(payload["nodes"]["host"])
    payload["variation_points"] = {"jobs": _inventory_point(["nodes.host.runtime.scheduled_jobs.baseline"])}
    source = yaml.safe_dump(payload)
    result = language_completions(source, cursor_path="/variation_points/jobs/alternatives/chosen/references")
    assert {item["label"] for item in result["items"]} == {
        "nodes.host.runtime.scheduled_jobs.baseline",
        "nodes.host.runtime.scheduled_jobs.extra",
    }
    refs = language_references(source, "nodes.host.runtime.scheduled_jobs.baseline")
    assert any(
        item["path"] == "/variation_points/jobs/alternatives/chosen/references/0" for item in refs["occurrences"]
    )
    coupled = language_completions(
        yaml.safe_dump(_payload()),
        cursor_path="/variation_points/host-state/alternatives/baseline/inventory/nodes.runtime.scheduled_jobs",
    )
    assert {item["label"] for item in coupled["items"]} == {
        "nodes.host.runtime.scheduled_jobs.baseline",
        "nodes.host.runtime.scheduled_jobs.extra",
    }


def _compiler_request(*, owner: str):
    from raes_contracts.contracts import ExperimentSpecModel
    from test_sce_002_trial_compiler import _request

    request = _request()
    payload = request.family.model_dump(mode="python", by_alias=True)
    payload["nodes"]["optional"] = deepcopy(payload["nodes"]["primary"])
    payload["nodes"]["optional"]["runtime"] = {"scheduled_jobs": [{"scheduled_job_id": "job"}]}
    payload["variation_points"]["node-state"] = {
        "kind": "alternative",
        "target": {"kind": "structural", "owner": owner, "slot": "nodes.presence"},
        "alternatives": {
            "absent": {"kind": "node-presence", "present": False},
            "present": {
                "kind": "node-presence",
                "present": True,
                **({"inventory": {"nodes.runtime.scheduled_jobs": []}} if owner == "optional" else {}),
            },
        },
    }
    # Keep the other node's inventory empty in the negative witness too.
    if owner != "optional":
        payload["nodes"]["optional"]["runtime"] = None
    family = _family(payload)
    spec = request.experiment.model_dump(mode="json")
    spec["run_plan"]["target_run_count"] = 4
    policies = spec["run_plan"]["selection_policies"]
    policies["enumerate-node"] = {
        "kind": "enumerate",
        "policy_id": "enumerate-node",
        "purpose": "nuisance-variation",
        "point_ref": "node-state",
        "output_bound": 2,
    }
    policies["product"] = {
        "kind": "product",
        "policy_id": "product",
        "purpose": "nuisance-variation",
        "policy_refs": ["enumerate-path", "enumerate-node"],
        "output_bound": 4,
    }
    return request.with_family(family).with_experiment(ExperimentSpecModel.model_validate(spec))


def test_experiment_structural_choices_reach_admitted_snapshots() -> None:
    from raes_processor.trial_compiler import compile_admitted_trial_plan
    from raes_processor.trial_realization import instantiate_admitted_trial_entry

    request = _compiler_request(owner="optional")
    family_bytes = canonical_sdl_bytes(request.family)
    result = compile_admitted_trial_plan(request)
    assert result.diagnostics == ()
    assert result.plan is not None
    assert len(result.plan.entries) == 4
    seen = set()
    for entry_id, entry in result.plan.entries.items():
        selected = instantiate_admitted_trial_entry(plan=result.plan, plan_entry_id=entry_id, family=request.family)
        trial = selected.instantiation_provenance.trial
        assert trial.scenario_family_digest == canonical_sdl_digest(request.family).value
        assert trial.run_id == entry.run_id
        assert len(trial.selections) == 2
        seen.add("optional" in selected.nodes)
        if "optional" in selected.nodes:
            assert selected.nodes["optional"].runtime.scheduled_jobs == []
        InstantiatedScenario.model_validate(selected.model_dump())
        canonical_instantiated_sdl_digest(selected)
    assert seen == {False, True}
    assert canonical_sdl_bytes(request.family) == family_bytes


def test_one_invalid_structural_trial_rejects_the_complete_plan() -> None:
    from raes_processor.trial_compiler import compile_admitted_trial_plan

    result = compile_admitted_trial_plan(_compiler_request(owner="primary"))
    assert result.plan is None
    assert result.diagnostics
    assert all("/opt/a" not in diagnostic.message for diagnostic in result.diagnostics)


def test_published_authoring_schema_admits_structural_choices() -> None:
    import json

    from jsonschema import Draft202012Validator
    from paths import REPO_ROOT

    schema = json.loads((REPO_ROOT / "contracts/schemas/sdl/sdl-authoring-input-v1.json").read_text())
    validator = Draft202012Validator(schema)
    validator.validate(_payload())
    invalid = _payload()
    invalid["variation_points"]["host-state"]["alternatives"]["absent"] = {
        "kind": "runtime-inventory",
        "references": [],
    }
    assert list(validator.iter_errors(invalid))
    invalid = _payload()
    invalid["variation_points"]["host-state"]["alternatives"]["absent"]["inventory"] = {
        "nodes.runtime.scheduled_jobs": []
    }
    assert list(validator.iter_errors(invalid))


@pytest.mark.parametrize(
    "point",
    [None, [], {"target": 12}, {"target": {"kind": "structural", "owner": 2, "slot": "nodes.runtime.scheduled_jobs"}}],
)
def test_inventory_completion_handles_incomplete_authoring(point: object) -> None:
    from raes.language_service import language_completions

    source = yaml.safe_dump({"name": "editing", "variation_points": {"jobs": point}})
    result = language_completions(source, cursor_path="/variation_points/jobs/alternatives/chosen/references")
    assert result["status"] == "ok"


def test_legacy_reference_alternative_keeps_implicit_target_kind() -> None:
    payload = _payload()
    payload["content"] = {"file": {"type": "file", "target": "host", "path": "/opt/file"}}
    payload["variation_points"] = {
        "where": {
            "kind": "alternative",
            "target": {"owner": "file", "slot": "content.target"},
            "alternatives": {"host": {"reference": "host"}},
        }
    }
    import hashlib

    from raes.variation import ReferenceTarget
    from raes_contracts.canonical import canonical_json_bytes

    family = _family(payload)
    expected_payload = family.model_dump(
        mode="json", by_alias=True, exclude_unset=True, exclude={"expansion_provenance"}
    )
    expected_payload["variation_points"]["where"]["target"] = ReferenceTarget(
        owner="file",
        slot="content.target",
    ).model_dump(mode="json", exclude_unset=True)
    expected_bytes = canonical_json_bytes(
        {
            "profile": "raes-sdl-semantic/v2",
            "scenario": expected_payload,
            "module_variable_specs": {},
            "module_node_variable_refs": {},
        }
    )
    assert canonical_sdl_bytes(family) == expected_bytes
    assert canonical_sdl_digest(family).value == "sha256:" + hashlib.sha256(expected_bytes).hexdigest()
    assert select_scenario_family(family, {"where": _outcome("host")}).content["file"].target == "host"


def test_public_structural_fixture_parses_and_selects() -> None:
    from paths import REPO_ROOT

    path = REPO_ROOT / "contracts/fixtures/sdl/variation-points-v1/valid/node-inventory.yaml"
    family = ExpandedScenario.model_validate(
        parse_sdl_file(path).model_dump(mode="python", exclude={"module", "imports", "realization"})
    )
    SemanticValidator(family).validate()
    family._set_semantic_validated(True)
    selected = select_scenario_family(family, {"worker-state": _outcome("baseline")})
    assert [row.scheduled_job_id for row in selected.nodes["worker"].runtime.scheduled_jobs] == ["baseline"]
    assert select_scenario_family(family, {"worker-state": _outcome("absent")}).infrastructure == {}


def test_dependent_reference_choice_can_make_node_absence_valid() -> None:
    payload = _payload()
    payload["nodes"]["other"] = deepcopy(payload["nodes"]["host"])
    payload["content"] = {"file": {"type": "file", "target": "host", "path": "/opt/file"}}
    payload["variation_points"]["where"] = {
        "kind": "alternative",
        "target": {"kind": "reference", "owner": "file", "slot": "content.target"},
        "alternatives": {"original": {"reference": "host"}, "other": {"reference": "other"}},
    }
    payload["variation_points"]["host-state"]["alternatives"]["absent"]["requires"] = [
        {"point": "where", "members": ["other"]}
    ]
    family = _family(payload)
    selected = select_scenario_family(family, {"host-state": _outcome("absent"), "where": _outcome("other")})
    assert selected.content["file"].target == "other"
    assert set(selected.nodes) == {"other"}
    with pytest.raises(ValueError, match="violates requires"):
        select_scenario_family(family, {"host-state": _outcome("absent"), "where": _outcome("original")})


def test_qualified_node_name_is_not_a_descendant_write() -> None:
    payload = _payload()
    payload["nodes"]["host.child"] = deepcopy(payload["nodes"]["host"])
    payload["variation_points"]["jobs"] = {
        "kind": "alternative",
        "target": {"kind": "structural", "owner": "host.child", "slot": "nodes.runtime.scheduled_jobs"},
        "alternatives": {"empty": {"kind": "runtime-inventory", "references": []}},
    }
    result = select_scenario_family(_family(payload), {"host-state": _outcome("absent"), "jobs": _outcome("empty")})
    assert set(result.nodes) == {"host.child"}
    assert result.nodes["host.child"].runtime.scheduled_jobs == []


@pytest.mark.parametrize("slot", ["nodes.presence", "nodes.runtime.scheduled_jobs"])
def test_schema_and_runtime_reject_implicit_structural_targets(slot: str) -> None:
    import json

    from jsonschema import Draft202012Validator
    from paths import REPO_ROOT

    payload = _payload()
    payload["variation_points"] = {
        "implicit": {
            "kind": "alternative",
            "target": {"owner": "host", "slot": slot},
            "alternatives": {"host": {"reference": "host"}},
        }
    }
    schema = json.loads((REPO_ROOT / "contracts/schemas/sdl/sdl-authoring-input-v1.json").read_text())
    assert not Draft202012Validator(schema).is_valid(payload)
    with pytest.raises(ValidationError):
        ExpandedScenario.model_validate(payload)
