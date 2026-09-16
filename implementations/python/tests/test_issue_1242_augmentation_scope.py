"""Author addition permission is separate from realization and defaults open."""

import json

import pytest
from raes import parse_sdl
from raes._errors import SDLError
from raes.instantiate import instantiate_scenario


def scenario_with_scope(policy):
    return parse_sdl(
        json.dumps(
            {
                "name": "scope-example",
                "nodes": {"host": {"type": "compute"}, "management": {"type": "compute"}},
                "augmentation_scope": policy,
            }
        )
    )


def test_omission_is_open_without_changing_historical_serialization():
    from raes_contracts.augmentation_scope import effective_augmentation_scope

    scenario = parse_sdl("name: legacy\nnodes: {host: {type: compute}}")
    assert effective_augmentation_scope(scenario.augmentation_scope, "/nodes/host").permission == "open"
    assert "augmentation_scope" not in scenario.model_dump(mode="json", exclude_unset=True)


def test_explicit_scope_survives_instantiation_with_local_exceptions():
    from raes_contracts.augmentation_scope import effective_augmentation_scope

    scenario = scenario_with_scope(
        {
            "default": "closed",
            "scopes": [{"scope": "/nodes/management", "permission": "open"}],
        }
    )
    instance = instantiate_scenario(scenario)
    policy = instance.augmentation_scope
    assert policy == scenario.augmentation_scope
    assert effective_augmentation_scope(policy, "/nodes/host/runtime").permission == "closed"
    assert effective_augmentation_scope(policy, "/nodes/management/runtime").permission == "open"
    assert effective_augmentation_scope(policy, "/nodes/management-extra").permission == "closed"


def test_open_realization_is_not_addition_permission():
    from raes_contracts.augmentation_scope import effective_augmentation_scope

    scenario = parse_sdl("""
name: separate-authorities
realization: {default: open}
augmentation_scope: {default: closed}
nodes: {host: {type: compute}}
""")
    assert effective_augmentation_scope(scenario.augmentation_scope, "/nodes/host").permission == "closed"


@pytest.mark.parametrize("scope", ["nodes/host", "/nodes/missing", "/nodes/hostish"])
def test_scope_must_resolve_to_an_admitted_semantic_location(scope):
    with pytest.raises(SDLError):
        scenario_with_scope({"scopes": [{"scope": scope, "permission": "closed"}]})


def test_conflicting_equal_specificity_rules_are_refused():
    with pytest.raises(SDLError):
        scenario_with_scope(
            {
                "scopes": [
                    {"scope": "/nodes/host", "permission": "open"},
                    {"scope": "/nodes/host", "permission": "closed"},
                ]
            }
        )


def test_unresolved_namespace_cannot_silently_disable_a_restriction():
    with pytest.raises(SDLError):
        scenario_with_scope({"scopes": [{"scope": "/nodes/host", "permission": "closed", "namespace": ["missing"]}]})


def test_imported_restriction_survives_outer_open_policy(tmp_path):
    from raes import parse_sdl_file
    from raes_contracts.augmentation_scope import effective_augmentation_scope

    (tmp_path / "protected.yaml").write_text("""
name: protected
module: {id: example/protected, version: 1.0.0, exports: {nodes: [host]}}
augmentation_scope: {default: closed}
nodes: {host: {type: compute}}
""")
    root = tmp_path / "root.yaml"
    root.write_text("""
name: composed
imports: [{source: 'local:protected.yaml', namespace: protected}]
augmentation_scope: {default: open}
nodes: {local: {type: compute}}
""")
    instance = instantiate_scenario(parse_sdl_file(root))
    policy = instance.augmentation_scope
    assert effective_augmentation_scope(policy, "/nodes/local").permission == "open"
    assert effective_augmentation_scope(policy, "/nodes/protected.host").permission == "closed"
    assert effective_augmentation_scope(policy, "/nodes/protected.collector").permission == "closed"


@pytest.mark.parametrize("section", ["nodes", "forwarding_agents"])
def test_existing_import_namespace_cannot_hide_a_local_restriction(tmp_path, section):
    from raes import admit_instantiated_scenario, parse_sdl_file

    (tmp_path / "protected.yaml").write_text("""
name: protected
module: {id: example/protected, version: 1.0.0, exports: {nodes: [host], forwarding_agents: [shipper]}}
nodes: {host: {type: compute}}
forwarding_agents: [{forwarding_agent_id: shipper}]
""")
    root = tmp_path / "root.yaml"
    root.write_text("""
name: composed
imports: [{source: 'local:protected.yaml', namespace: protected}]
nodes: {local: {type: compute}}
forwarding_agents: [{forwarding_agent_id: local}]
""")
    instance = instantiate_scenario(parse_sdl_file(root))
    payload = instance.model_dump(mode="json")
    pointer = "/nodes/local"
    if section == "forwarding_agents":
        index = next(i for i, agent in enumerate(payload[section]) if agent["forwarding_agent_id"] == "local")
        pointer = f"/forwarding_agents/{index}"
    payload["augmentation_scope"] = {"scopes": [{"scope": pointer, "permission": "closed", "namespace": ["protected"]}]}
    with pytest.raises(SDLError, match="namespace.*own"):
        admit_instantiated_scenario(payload)


@pytest.mark.parametrize("outer_exception", [False, True])
def test_imported_open_default_needs_outer_author_permission(tmp_path, outer_exception):
    from raes import parse_sdl_file
    from raes_contracts.augmentation_scope import effective_augmentation_scope

    (tmp_path / "open.yaml").write_text("""
name: open-module
module: {id: example/open, version: 1.0.0, exports: {nodes: [host]}}
augmentation_scope: {default: open}
nodes: {host: {type: compute}}
""")
    root = tmp_path / "root.yaml"
    root.write_text(
        json.dumps(
            {
                "name": "outer",
                "imports": [{"source": "local:open.yaml", "namespace": "inner"}],
                "augmentation_scope": {
                    "default": "closed",
                    "scopes": ([{"scope": "/nodes/inner.host", "permission": "open"}] if outer_exception else []),
                },
            }
        )
    )
    instance = instantiate_scenario(parse_sdl_file(root))
    decision = effective_augmentation_scope(instance.augmentation_scope, "/nodes/inner.host")
    assert decision.permission == ("open" if outer_exception else "closed")


@pytest.mark.parametrize(
    "policy", ["{default: closed}", "{scopes: [{scope: /forwarding_agents/0, permission: closed}]}"]
)
def test_imported_list_declaration_retains_its_scope_owner_after_merge(tmp_path, policy):
    from dataclasses import replace

    from raes import parse_sdl_file
    from raes_backend_protocols.augmentation import augmentation_preparation
    from raes_contracts.augmentation_preparation import AugmentationEffect
    from raes_contracts.planning import PlanScope
    from raes_contracts.runtime_state import RuntimeSnapshot
    from raes_processor.compiler import compile_runtime_model
    from raes_processor.planner import plan
    from raes_processor.planner.augmentation_admission import admit_augmentation_preparation
    from test_issue_1242_scope_admission import scoped_plan

    (tmp_path / "shared.yaml").write_text(
        """
name: shared
module: {id: example/shared, version: 1.0.0, exports: {forwarding_agents: [shipper]}}
augmentation_scope: POLICY
forwarding_agents: [{forwarding_agent_id: shipper}]
""".replace("POLICY", policy)
    )
    root = tmp_path / "root.yaml"
    root.write_text("""
name: composed
imports: [{source: 'local:shared.yaml', namespace: shared}]
forwarding_agents: [{forwarding_agent_id: local}]
""")
    manifest = scoped_plan().manifest
    execution = plan(compile_runtime_model(parse_sdl_file(root)), manifest, scope=PlanScope(run_id="run-1"))
    request = replace(execution.provisioning, operation_id="operation-1")
    content = json.loads(request.materialization_source.snapshot)["scenario"]
    content.pop("instantiation_provenance")
    imported_index = next(
        index
        for index, item in enumerate(content["forwarding_agents"])
        if item["forwarding_agent_id"] == "shared.shipper"
    )
    content["forwarding_agents"][imported_index]["description"] = "extra configuration"
    scope = f"/forwarding_agents/{imported_index}"
    report = augmentation_preparation(
        request,
        manifest,
        RuntimeSnapshot(),
        content=json.dumps(content),
        effects=(
            AugmentationEffect(
                field_pointer=scope + "/description",
                requirement_refs=("backend-operational",),
                affected_scopes=(scope,),
            ),
        ),
    )
    assert not admit_augmentation_preparation(report, request, manifest, RuntimeSnapshot()).is_valid
