"""Import binding identities and private visibility retain lexical policy owners."""

import pytest
from raes import parse_sdl_file
from raes_processor.compiler import compile_runtime_model


@pytest.mark.parametrize("kind", ["features", "conditions", "injects"])
def test_imported_binding_policy_follows_its_renamed_key(tmp_path, kind):
    import yaml

    definition = (
        {"type": "configuration"}
        if kind == "features"
        else (
            {"description": "Probe", "command": "true", "interval": 1}
            if kind == "conditions"
            else {"description": "Inject"}
        )
    )
    module = {
        "name": "shared",
        "module": {"id": "acme/shared", "version": "1.0.0", "exports": {"nodes": ["host"], kind: ["setup"]}},
        "nodes": {
            "host": {"type": "compute", "os": "linux", "roles": {"root": {"username": "root"}}, kind: {"setup": "root"}}
        },
        kind: {"setup": definition},
        "execution_policy": {
            "scopes": [
                {"scope": f"/nodes/host/{kind}/setup", "policy": {"policy_id": "binding", "response": "terminate"}}
            ]
        },
    }
    (tmp_path / "module.yaml").write_text(yaml.safe_dump(module))
    root = tmp_path / "root.yaml"
    root.write_text("name: recovery\nimports: [{source: 'local:module.yaml', namespace: shared}]\n")
    scenario = parse_sdl_file(root)
    assert scenario.execution_policy.scopes[0].scope == f"/nodes/shared.host/{kind}/shared.setup"
    policies = compile_runtime_model(scenario).execution_policies
    assert any(
        p.policy.policy_id == "binding" and p.scope.endswith("/shared.setup")
        for values in policies.values()
        for p in values
    )


def test_imported_binding_pointer_preserves_json_pointer_escaping():
    from raes.composition._execution_policy import rewrite_execution_policy

    payload = {
        "execution_policy": {
            "scopes": [
                {"scope": "/nodes/host/features/a~1b~0c", "policy": {"policy_id": "bound", "response": "terminate"}}
            ]
        }
    }
    rewrite_execution_policy(
        payload, {"nodes": {"host": "shared.host"}, "features": {"a/b~c": "shared.a/b~c"}}, "shared"
    )
    assert payload["execution_policy"]["scopes"][0]["scope"] == "/nodes/shared.host/features/shared.a~1b~0c"


@pytest.mark.parametrize("export_one", [False, True])
@pytest.mark.parametrize("section_override", [False, True])
def test_nested_module_policy_follows_mixed_exported_and_private_descendants(tmp_path, export_one, section_override):
    (tmp_path / "inner.yaml").write_text(
        """
name: inner
module: {id: acme/inner, version: 1.0.0, exports: {nodes: [exported, private]}}
nodes:
  exported: {type: compute, os: linux}
  private: {type: compute, os: linux}
execution_policy: {default: {policy_id: inner-default, response: terminate}}
""".replace(
            "execution_policy: {default: {policy_id: inner-default, response: terminate}}",
            "execution_policy: {default: {policy_id: inner-default, response: terminate}, scopes: [{scope: /nodes, policy: {policy_id: inner-section, response: terminate}}]}"
            if section_override
            else "execution_policy: {default: {policy_id: inner-default, response: terminate}}",
        )
    )
    (tmp_path / "outer.yaml").write_text(
        """
name: outer
module: {id: acme/outer, version: 1.0.0, exports: {nodes: EXPORTS}}
imports: [{source: 'local:inner.yaml', namespace: inner}]
execution_policy: {default: {policy_id: outer-default, response: terminate}}
nodes: {local: {type: compute, os: linux}}
""".replace("EXPORTS", "[inner.exported]" if export_one else "[]")
    )
    root = tmp_path / "root.yaml"
    root.write_text("""
name: recovery
imports: [{source: 'local:outer.yaml', namespace: outer}]
execution_policy: {default: {policy_id: root-default, response: terminate}}
nodes: {local: {type: compute, os: linux}}
""")
    compiled = compile_runtime_model(parse_sdl_file(root))
    export_namespace = ("outer", "inner") if export_one else ("outer", "__private", "inner")
    exported = compiled.execution_policies["provision.node." + ".".join(export_namespace) + ".exported"][0]
    private = compiled.execution_policies["provision.node.outer.__private.inner.private"][0]
    assert (
        exported.policy.policy_id
        == private.policy.policy_id
        == ("inner-section" if section_override else "inner-default")
    )
    assert exported.namespace == export_namespace
    assert compiled.execution_policies["provision.node.outer.__private.local"][0].policy.policy_id == "outer-default"
    assert private.namespace == ("outer", "__private", "inner")
    assert compiled.execution_policies["provision.node.local"][0].policy.policy_id == "root-default"
