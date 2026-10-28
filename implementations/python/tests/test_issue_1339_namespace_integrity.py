"""ACL and detection references bind to their own composed declarations, even beside root collisions."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest
import yaml
from raes import SDLValidationError, parse_sdl, parse_sdl_file
from raes_processor.compiler import compile_scenario_runtime_model
from test_issue_1339_relationship_endpoints import fixture_payload, matrix_payload


def _module_payload() -> dict:
    payload = matrix_payload()
    payload["infrastructure"]["lan"]["acls"] = deepcopy(fixture_payload()["infrastructure"]["lan"]["acls"])
    payload["infrastructure"]["lan"]["acls"][0].update(from_net="lan", to_net="lan")
    payload["nodes"]["app"]["runtime"]["security_monitoring_managers"][0]["detection_definitions"][0][
        "source_artifact_ref"
    ] = "nodes.app"
    return payload


def _module(path: Path, payload: dict) -> None:
    payload = deepcopy(payload)
    payload["module"] = {
        "id": "example/namespace-integrity",
        "version": "1.0.0",
        "exports": {
            key: list(value) for key, value in payload.items() if isinstance(value, dict) and key != "variables"
        },
    }
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


@pytest.mark.parametrize("namespaces", [("first",), ("first", "second")], ids=["once", "twice"])
@pytest.mark.parametrize("root_collision", [False, True])
@pytest.mark.parametrize("nested", [False, True])
def test_imported_acl_and_detection_references_preserve_semantic_and_compiled_identity(
    tmp_path: Path, namespaces: tuple[str, ...], root_collision: bool, nested: bool
) -> None:
    payload = _module_payload()
    parse_sdl(yaml.safe_dump(payload, sort_keys=False))
    _module(tmp_path / "module.yaml", payload)
    imports = [{"path": "module.yaml", "namespace": name} for name in namespaces]
    prefix = ""
    if nested:
        _module(tmp_path / "container.yaml", {"name": "container", "imports": imports})
        imports = [{"path": "container.yaml", "namespace": "outer"}]
        prefix = "outer.__private."
    root = matrix_payload() if root_collision else {"name": "root"}
    root["imports"] = imports
    path = tmp_path / "root.yaml"
    path.write_text(yaml.safe_dump(root, sort_keys=False), encoding="utf-8")

    scenario = parse_sdl_file(path)
    model = compile_scenario_runtime_model(scenario)
    for namespace in namespaces:
        name = f"{prefix}{namespace}"
        acl = scenario.infrastructure[f"{name}.lan"].acls[0]
        definition = scenario.nodes[f"{name}.app"].runtime.security_monitoring_managers[0].detection_definitions[0]
        assert (acl.from_net, acl.to_net) == (f"{name}.lan", f"{name}.lan")
        assert definition.source_artifact_ref == f"nodes.{name}.app"
        network = next(item for item in model.networks.values() if item.node_name == f"{name}.lan")
        node = next(item for item in model.node_deployments.values() if item.node_name == f"{name}.app")
        compiled_acl = network.spec["infrastructure"]["acls"][0]
        assert (compiled_acl["from_net"], compiled_acl["to_net"]) == (f"{name}.lan", f"{name}.lan")
        assert (
            node.spec["node"]["runtime"]["security_monitoring_managers"][0]["detection_definitions"][0][
                "source_artifact_ref"
            ]
            == f"nodes.{name}.app"
        )


@pytest.mark.parametrize("field", ["from_net", "to_net", "source_artifact_ref"])
def test_unknown_acl_and_detection_references_remain_invalid_after_composition(tmp_path: Path, field: str) -> None:
    payload = _module_payload()
    if field == "source_artifact_ref":
        payload["nodes"]["app"]["runtime"]["security_monitoring_managers"][0]["detection_definitions"][0][field] = (
            "nodes.missing"
        )
    else:
        payload["infrastructure"]["lan"]["acls"][0][field] = "missing"
    _module(tmp_path / "module.yaml", payload)
    path = tmp_path / "root.yaml"
    path.write_text(yaml.safe_dump({"name": "root", "imports": [{"path": "module.yaml", "namespace": "first"}]}))
    with pytest.raises(SDLValidationError, match="missing"):
        parse_sdl_file(path)
