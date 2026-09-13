"""The public refinement ladder uses generic OS and software constraints."""

import pytest
import yaml
from raes import parse_sdl
from raes_contracts.realization_structure import evaluate_realization_constraint
from raes_processor.compiler import compile_runtime_model
from raes_processor.semantics.realization_concerns import realization_concern_descriptor


@pytest.mark.parametrize("level", ["distribution", "exact-tool", "pinned-with-optional"])
def test_kali_refinement_ladder_keeps_inherited_freedom_and_binding_leaves(level):
    node = {"type": "compute", "os": "linux", "os_distribution": "x-kali:kali"}
    if level != "distribution":
        node["runtime"] = {"software_components": [{"component_id": "nmap", "name": "nmap", "version": "7.95"}]}
    if level == "pinned-with-optional":
        node["os_version"] = "2025.1"
        node["runtime"]["software_components"].append(
            {"component_id": "editor", "name": "editor", "presence": "optional", "version": "2.0"}
        )
    model = compile_runtime_model(
        parse_sdl(yaml.safe_dump({"name": "ladder", "realization": {"default": "open"}, "nodes": {"host": node}}))
    )
    requirements = {item.requirement_kind: item for item in model.realization_requirements}
    distribution = requirements["os-distribution"].constraint_document
    assert evaluate_realization_constraint(distribution, "x-kali:kali").conformant
    assert not evaluate_realization_constraint(distribution, "ubuntu").conformant
    os_version = requirements["os-version"].constraint_document
    if level == "pinned-with-optional":
        assert evaluate_realization_constraint(os_version, "2025.1").conformant
        assert not evaluate_realization_constraint(os_version, "2025.2").conformant
    else:
        assert os_version is None
        assert requirements["os-version"].explicitness.value == "open"
    software = requirements.get("runtime-software-components")
    if level == "distribution":
        assert software.constraint_document is None
        return
    project = realization_concern_descriptor("runtime-software-components").project
    installed = [{"component_id": "nmap", "name": "nmap", "version": "7.95", "package_manager": "private"}]
    assert evaluate_realization_constraint(software.constraint_document, project(installed, recursive=True)).conformant
    assert not evaluate_realization_constraint(
        software.constraint_document, project([{**installed[0], "version": "7.96"}], recursive=True)
    ).conformant
    if level == "pinned-with-optional":
        wrong_optional = installed + [{"component_id": "editor", "name": "editor", "version": "3.0"}]
        assert not evaluate_realization_constraint(
            software.constraint_document, project(wrong_optional, recursive=True)
        ).conformant
