"""Cross-boundary tests for the portable SDL identifier contract."""

from __future__ import annotations

from pathlib import Path

import jsonschema
import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from pydantic import ValidationError
from raes._declarations import build_declaration_index
from raes._errors import SDLParseError, SDLValidationError
from raes._model_diagnostics import _bounded_model_message
from raes._source_profile import SDLParserLimits
from raes.identifiers import (
    PORTABLE_IDENTIFIER_JSON_SCHEMA,
    QUALIFIED_IDENTIFIER_MAX_LENGTH,
    QualifiedName,
    is_portable_identifier,
    require_portable_identifier,
)
from raes.infrastructure import ACLRule
from raes.instantiate import instantiate_scenario
from raes.nodes import ServicePort
from raes.parser import parse_sdl
from raes.runtime_values import require_symbol
from raes.scenario import ExpandedScenario, ImportDecl, ModuleDescriptor, Scenario
from raes.validator import SemanticValidator
from raes_backend_protocols.naming import provider_resource_name
from raes_contracts.addressing import (
    COMPILED_ADDRESS_JSON_SCHEMA,
    COMPILED_ADDRESS_MAX_LENGTH,
    render_compiled_address,
    require_compiled_address,
)
from raes_contracts.contracts import (
    EvaluationPlanModel,
    OrchestrationPlanModel,
    ProvisioningPlanModel,
    RuntimeSnapshotEnvelopeModel,
    schema_bundle,
)
from raes_contracts.planning import (
    ChangeAction,
    OrchestrationPlan,
    PlannedResource,
    ProvisioningPlan,
    ProvisionOp,
    RuntimeDomain,
)
from raes_contracts.runtime_state import (
    ApplyResult,
    OperationAdmissionContext,
    OperationKind,
    OperationState,
    OperationStatus,
    RuntimeSnapshot,
    SnapshotEntry,
)
from raes_processor.compiler import compile_runtime_model
from raes_processor.models import NetworkRuntime, NodeRuntime, RuntimeModel

_PORTABLE_CHARACTERS = "abcdefghijklmnopqrstuvwxyz0123456789-_"
_PORTABLE_START = "abcdefghijklmnopqrstuvwxyz0123456789"
_portable_identifier_strategy = st.builds(
    lambda first, tail: first + tail,
    st.sampled_from(tuple(_PORTABLE_START)),
    st.text(alphabet=_PORTABLE_CHARACTERS, min_size=0, max_size=63),
)


def _minimal_instantiation_provenance() -> dict[str, object]:
    return {
        "authored_digest": {
            "profile": "raes-sdl-semantic/v1",
            "algorithm": "sha256",
            "value": f"sha256:{'0' * 64}",
        }
    }


@pytest.mark.parametrize(
    "identifier",
    ["a", "0", "001", "a-b", "a_b", "a" * 64],
)
def test_portable_identifier_accepts_exact_boundary_values(identifier: str) -> None:
    assert is_portable_identifier(identifier)
    assert require_portable_identifier(identifier, field_name="test_id") == identifier
    jsonschema.validate(identifier, PORTABLE_IDENTIFIER_JSON_SCHEMA)


@pytest.mark.parametrize(
    "identifier",
    [
        "",
        " ",
        "a.b",
        "a/b",
        "a:b",
        "A",
        "_private",
        "caf\u00e9",
        "a\n",
        "a\r",
        "a\x00",
        "a" * 65,
        "${name}",
    ],
)
def test_portable_identifier_rejects_noncanonical_values(identifier: str) -> None:
    assert not is_portable_identifier(identifier)
    with pytest.raises(ValueError, match="portable SDL identifier"):
        require_portable_identifier(identifier, field_name="test_id")
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(identifier, PORTABLE_IDENTIFIER_JSON_SCHEMA)


def test_model_diagnostic_messages_are_control_escaped_and_bounded() -> None:
    message = _bounded_model_message("invalid\n" + "x" * 600)

    assert "\n" not in message
    assert "\\u000a" in message
    assert len(message) == 512
    assert message.endswith("...")


@given(st.text(max_size=80))
def test_python_and_json_schema_identifier_grammars_are_differentially_equivalent(value: str) -> None:
    schema_accepts = not list(jsonschema.Draft202012Validator(PORTABLE_IDENTIFIER_JSON_SCHEMA).iter_errors(value))
    assert schema_accepts is is_portable_identifier(value)


@settings(suppress_health_check=(HealthCheck.too_slow,))
@given(
    st.lists(_portable_identifier_strategy, min_size=1, max_size=6),
    st.lists(_portable_identifier_strategy, min_size=1, max_size=6),
)
def test_qualified_name_rendering_is_injective_over_portable_segments(
    left_parts: list[str],
    right_parts: list[str],
) -> None:
    left = QualifiedName(tuple(left_parts))
    right = QualifiedName(tuple(right_parts))
    assert (left.render() == right.render()) is (left.parts == right.parts)


@pytest.mark.parametrize(
    "address",
    [
        "nodes.vm",
        "nodes.shared.vm",
        "nodes.__private.vm",
        "a." + "b" * 64,
    ],
)
def test_compiled_address_accepts_exact_canonical_values(address: str) -> None:
    assert require_compiled_address(address) == address
    assert render_compiled_address(*address.split(".")) == address
    jsonschema.validate(address, COMPILED_ADDRESS_JSON_SCHEMA)


@pytest.mark.parametrize(
    "address",
    [
        "vm",
        ".nodes.vm",
        "nodes.vm.",
        "nodes..vm",
        "nodes.VM",
        "nodes.vm\n",
        "nodes.caf\u00e9",
        "nodes._private.vm",
        "nodes." + "b" * 65,
        "a." + ".".join("b" for _ in range(COMPILED_ADDRESS_MAX_LENGTH)),
    ],
)
def test_compiled_address_rejects_noncanonical_values(address: str) -> None:
    with pytest.raises(ValueError, match="canonical compiled address"):
        require_compiled_address(address)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(address, COMPILED_ADDRESS_JSON_SCHEMA)


def test_qualified_identifier_has_a_bounded_rendering() -> None:
    overlong = ".".join("a" * 64 for _ in range(33))
    assert len(overlong) > QUALIFIED_IDENTIFIER_MAX_LENGTH
    with pytest.raises(ValueError, match="maximum length"):
        QualifiedName.parse(overlong)


def test_authored_declaration_key_reports_source_range() -> None:
    source = """\
name: root
nodes:
  bad.name:
    type: switch
"""

    with pytest.raises(SDLParseError) as caught:
        parse_sdl(source)

    diagnostic = caught.value.diagnostics[0]
    assert diagnostic.code == "sdl.identifier.invalid"
    assert diagnostic.pointer == "/nodes/bad.name"
    assert diagnostic.primary_range.start.line == 3
    assert diagnostic.primary_range.start.column == 3
    assert "bad.name" not in diagnostic.message


@pytest.mark.parametrize(
    ("source", "pointer", "line"),
    [
        (
            """\
name: root
forwarding_agents:
  - forwarding_agent_id: bad.name
""",
            "/forwarding_agents/0/forwarding_agent_id",
            3,
        ),
        (
            """\
name: root
nodes:
  vm:
    type: compute
    runtime:
      database_services:
        - database_service_id: bad.name
""",
            "/nodes/vm/runtime/database_services/0/database_service_id",
            7,
        ),
    ],
)
def test_scalar_identifier_reports_its_own_source_range(
    source: str,
    pointer: str,
    line: int,
) -> None:
    with pytest.raises(SDLParseError) as caught:
        parse_sdl(source, skip_semantic_validation=True)

    diagnostic = caught.value.diagnostics[0]
    assert diagnostic.code == "sdl.identifier.invalid"
    assert diagnostic.pointer == pointer
    assert diagnostic.primary_range.start.line == line
    assert "bad.name" not in diagnostic.message


def test_identifier_errors_remain_fatal_under_accept_migration_policy() -> None:
    source = """\
name: Root
nodes: {}
"""

    with pytest.raises(SDLParseError) as caught:
        parse_sdl(source, migration_policy="accept")

    assert caught.value.diagnostics[0].code == "sdl.identifier.invalid"
    assert caught.value.diagnostics[0].severity == "error"


@pytest.mark.parametrize("name", ["", "Root", "root.name", "root\n"])
def test_direct_scenario_construction_enforces_name(name: str) -> None:
    with pytest.raises(ValidationError, match="portable SDL identifier"):
        Scenario(name=name)


def test_direct_scenario_construction_enforces_declaration_keys() -> None:
    with pytest.raises(ValidationError, match="portable SDL identifier"):
        Scenario(name="root", nodes={"bad.name": {"type": "switch"}})


def test_non_identifier_data_retains_its_own_contract() -> None:
    scenario = Scenario(
        name="root",
        entities={"team": {"name": "\u00c9quipe de recherche"}},
        content={
            "report": {
                "type": "file",
                "target": "node.with.external.syntax",
                "path": "/var/tmp/Report 01.txt",
            }
        },
    )

    assert scenario.entities["team"].name == "\u00c9quipe de recherche"
    assert scenario.content["report"].path == "/var/tmp/Report 01.txt"


@pytest.mark.parametrize("module_id", ["acme", "Acme/shared", "acme/shared/extra", "acme/bad.name"])
def test_module_id_is_exactly_two_portable_segments(module_id: str) -> None:
    with pytest.raises(ValidationError, match="module.id"):
        ModuleDescriptor(id=module_id, version="1.0.0")


def test_import_requires_explicit_portable_namespace() -> None:
    with pytest.raises(ValidationError, match="namespace"):
        ImportDecl(source="local:shared.yaml")
    with pytest.raises(ValidationError, match="namespace"):
        ImportDecl(source="local:shared.yaml", namespace="shared.module")


@pytest.mark.parametrize(
    ("factory", "field_name"),
    [
        (lambda: ServicePort(port=443, name="https.service"), "name"),
        (lambda: ACLRule(name="allow.web"), "name"),
    ],
)
def test_addressable_nested_names_use_portable_identifiers(factory, field_name: str) -> None:
    with pytest.raises(ValidationError, match=field_name):
        factory()


def test_runtime_stable_ids_use_the_same_identifier_contract() -> None:
    with pytest.raises(ValueError, match="portable SDL identifier"):
        require_symbol("database.primary", field_name="database_id")


def test_raw_forwarding_agent_id_is_local_but_expanded_id_may_be_qualified() -> None:
    with pytest.raises(ValidationError, match="portable SDL identifier"):
        Scenario(
            name="root",
            forwarding_agents=[{"forwarding_agent_id": "shared.shipper"}],
        )

    expanded = ExpandedScenario(
        name="root",
        forwarding_agents=[{"forwarding_agent_id": "shared.shipper"}],
    )
    assert expanded.forwarding_agents[0].forwarding_agent_id == "shared.shipper"

    with pytest.raises(ValidationError, match="portable SDL identifier"):
        ExpandedScenario(
            name="root",
            nodes={
                "shared.vm": {
                    "type": "compute",
                    "runtime": {
                        "forwarding_agents": [
                            {"forwarding_agent_id": "shared.shipper"},
                        ]
                    },
                }
            },
        )


def test_parameter_values_do_not_change_declared_identity() -> None:
    scenario = parse_sdl(
        """\
name: parameterized
variables:
  label:
    type: string
    required: true
nodes:
  vm:
    type: compute
    description: ${label}
    resources: {ram: 1 gib, cpu: 1}
""",
        skip_semantic_validation=True,
    )

    instantiated = instantiate_scenario(
        scenario,
        parameters={"label": "renamed.node"},
    )

    assert set(instantiated.nodes) == {"vm"}
    assert instantiated.nodes["vm"].description == "renamed.node"


def test_declaration_index_covers_typed_nested_addresses_and_aliases() -> None:
    scenario = Scenario(
        name="root",
        nodes={
            "vm": {
                "type": "compute",
                "resources": {"ram": "1 gib", "cpu": 1},
                "roles": {"admin": {"username": "root"}},
                "services": [{"port": 443, "name": "https"}],
            }
        },
        infrastructure={"vm": {"acls": [{"name": "allow-https"}]}},
        entities={"team": {"entities": {"operator": {}}}},
        content={
            "mail": {
                "type": "dataset",
                "target": "vm",
                "items": [{"name": "message", "display_name": "message.eml"}],
            }
        },
        workflows={"flow": {"start": "done", "steps": {"done": {"type": "end"}}}},
    )

    index = build_declaration_index(scenario)

    assert {
        "scenario.root",
        "nodes.vm",
        "nodes.vm.roles.admin",
        "nodes.vm.services.https",
        "infrastructure.vm.acls.allow-https",
        "entities.team",
        "entities.team.operator",
        "content.mail.items.message",
        "workflows.flow.steps.done",
    }.issubset(index.addresses)
    assert index.resolve("https") == set()
    assert index.resolve("nodes.vm.services.https") == {"nodes.vm.services.https"}
    assert index.resolve("flow.done") == {"workflows.flow.steps.done"}


def test_declaration_index_rejects_cross_kind_render_collision() -> None:
    scenario = ExpandedScenario(
        name="root",
        nodes={
            "a": {
                "type": "compute",
                "resources": {"ram": "1 gib", "cpu": 1},
                "services": [{"port": 443, "name": "b"}],
            },
            "a.services.b": {"type": "switch"},
        },
    )

    with pytest.raises(SDLValidationError) as caught:
        build_declaration_index(scenario)

    message = "\n".join(caught.value.errors)
    assert "nodes.a.services.b" in message
    assert "collides between" in message
    assert "service" in message
    assert "node" in message


def test_runtime_references_are_resolved_by_exact_declaration_not_marker_split() -> None:
    application_node = "team.runtime.applications.web"
    database_node = "team.runtime.database_services.db"
    scenario = ExpandedScenario(
        name="root",
        nodes={
            application_node: {
                "type": "compute",
                "services": [{"port": 8080, "name": "http"}],
                "runtime": {
                    "applications": [{"application_id": "frontend", "service": "http"}],
                },
            },
            database_node: {
                "type": "compute",
                "services": [{"port": 5432, "name": "postgres"}],
                "runtime": {
                    "database_services": [
                        {
                            "database_service_id": "primary",
                            "service": "postgres",
                            "engine": "postgresql",
                            "protocol": "postgresql",
                            "databases": [{"database_id": "experiment", "name": "experiment"}],
                            "roles": [{"role_id": "writer", "name": "writer"}],
                        }
                    ],
                },
            },
        },
        relationships={
            "writes": {
                "type": "connects_to",
                "source": f"nodes.{application_node}.runtime.applications.frontend",
                "target": (f"nodes.{database_node}.runtime.database_services.primary.databases.experiment"),
                "database_access": {
                    "role_ref": "writer",
                    "auth_method": "password",
                },
            }
        },
    )

    source = f"nodes.{application_node}.runtime.applications.frontend"
    target = f"nodes.{database_node}.runtime.database_services.primary.databases.experiment"
    index = build_declaration_index(scenario)

    SemanticValidator(scenario).validate()
    assert index.resolve(source) == {source}
    assert index.resolve(target) == {target}


def test_published_authoring_schema_rejects_nonportable_declaration_key() -> None:
    schema = schema_bundle()["sdl-authoring-input-v1"]
    payload = {"name": "root", "nodes": {"bad.name": {"type": "switch"}}}

    with pytest.raises(jsonschema.ValidationError):
        jsonschema.Draft202012Validator(schema).validate(payload)


def test_published_instantiated_schema_accepts_generated_qualified_key() -> None:
    schema = schema_bundle()["instantiated-scenario-v1"]
    payload = {
        "name": "root",
        "nodes": {"shared.vm": {"type": "switch"}},
        "instantiation_provenance": _minimal_instantiation_provenance(),
    }

    assert list(jsonschema.Draft202012Validator(schema).iter_errors(payload)) == []


def test_published_instantiation_request_schema_rejects_nonportable_parameter_key() -> None:
    schema = schema_bundle()["scenario-instantiation-request-v1"]
    payload = {"parameters": {"bad.name": "value"}}

    with pytest.raises(jsonschema.ValidationError):
        jsonschema.Draft202012Validator(schema).validate(payload)


@pytest.mark.parametrize(
    ("contract_id", "model", "address", "resource_type"),
    [
        ("provisioning-plan-v1", ProvisioningPlanModel, "evaluation.objective.fake", "node"),
        ("provisioning-plan-v1", ProvisioningPlanModel, "provision.node.fake", "objective"),
        ("orchestration-plan-v1", OrchestrationPlanModel, "provision.node.fake", "workflow"),
        ("orchestration-plan-v1", OrchestrationPlanModel, "orchestration.workflow.fake", "node"),
        ("evaluation-plan-v1", EvaluationPlanModel, "orchestration.workflow.fake", "objective"),
        ("evaluation-plan-v1", EvaluationPlanModel, "evaluation.objective.fake", "workflow"),
    ],
)
def test_published_plan_contracts_reject_endpoint_identity_incoherence(
    contract_id: str,
    model,
    address: str,
    resource_type: str,
) -> None:
    payload = {
        "operations": [
            {
                "action": "create",
                "address": address,
                "resource_type": resource_type,
            }
        ]
    }
    if model is ProvisioningPlanModel:
        payload["realization_authority"] = []
    with pytest.raises(ValidationError, match="must belong to its runtime domain"):
        model.model_validate(payload)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.Draft202012Validator(schema_bundle()[contract_id]).validate(payload)


def test_typed_plan_rejects_new_operation_outside_endpoint_identity() -> None:
    with pytest.raises(ValueError, match="address must belong to its runtime domain"):
        ProvisioningPlan(
            operations=[
                ProvisionOp(
                    action=ChangeAction.CREATE,
                    address="evaluation.objective.fake",
                    resource_type="node",
                    payload={},
                )
            ]
        )


@pytest.mark.parametrize("map_key", ["bad", "a..b"])
def test_published_snapshot_schema_rejects_noncanonical_entry_keys(map_key: str) -> None:
    schema = schema_bundle()["runtime-snapshot-v1"]

    with pytest.raises(jsonschema.ValidationError):
        jsonschema.Draft202012Validator(schema).validate({"entries": {map_key: {"arbitrary": "untyped"}}})


def test_published_schema_constrains_runtime_family_identifiers() -> None:
    schema = schema_bundle()["sdl-authoring-input-v1"]
    payload = {
        "name": "root",
        "nodes": {
            "vm": {
                "type": "compute",
                "runtime": {
                    "database_services": [
                        {"database_service_id": "bad.name"},
                    ]
                },
            }
        },
    }

    with pytest.raises(jsonschema.ValidationError):
        jsonschema.Draft202012Validator(schema).validate(payload)


def test_published_schema_separates_top_level_forwarder_identity_phases() -> None:
    authoring = schema_bundle()["sdl-authoring-input-v1"]
    instantiated = schema_bundle()["instantiated-scenario-v1"]
    top_level = {
        "name": "root",
        "forwarding_agents": [{"forwarding_agent_id": "shared.shipper"}],
    }
    instantiated_top_level = {
        **top_level,
        "instantiation_provenance": _minimal_instantiation_provenance(),
    }
    nested_runtime = {
        "name": "root",
        "nodes": {
            "shared.vm": {
                "type": "compute",
                "runtime": {
                    "forwarding_agents": [{"forwarding_agent_id": "shared.shipper"}],
                },
            }
        },
        "instantiation_provenance": _minimal_instantiation_provenance(),
    }

    with pytest.raises(jsonschema.ValidationError):
        jsonschema.Draft202012Validator(authoring).validate(top_level)
    jsonschema.Draft202012Validator(instantiated).validate(instantiated_top_level)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.Draft202012Validator(instantiated).validate(nested_runtime)


def test_module_composition_uses_one_aggregate_import_budget(tmp_path: Path) -> None:
    module = tmp_path / "shared.yaml"
    module.write_text(
        """\
name: shared
version: 1.0.0
module:
  id: acme/shared
  version: 1.0.0
  exports:
    nodes: [vm]
nodes:
  vm: {type: switch}
""",
        encoding="utf-8",
    )
    root = tmp_path / "root.yaml"
    root.write_text(
        """\
name: root
imports:
  - source: local:shared.yaml
    namespace: first
  - source: local:shared.yaml
    namespace: second
""",
        encoding="utf-8",
    )

    limits = SDLParserLimits(max_imports=1)
    with pytest.raises(SDLParseError, match="composition import budget"):
        from raes.parser import parse_sdl_file

        parse_sdl_file(root, limits=limits)


def test_module_composition_bounds_decoded_bytes_across_the_request(tmp_path: Path) -> None:
    module = tmp_path / "shared.yaml"
    module.write_text(
        """\
name: shared
version: 1.0.0
module:
  id: acme/shared
  version: 1.0.0
  exports: {nodes: [vm]}
nodes: {vm: {type: switch}}
""",
        encoding="utf-8",
    )
    root = tmp_path / "root.yaml"
    root.write_text(
        """\
name: root
imports:
  - source: local:shared.yaml
    namespace: shared
""",
        encoding="utf-8",
    )

    from raes.parser import parse_sdl_file

    with pytest.raises(SDLParseError, match="decoded-byte budget"):
        parse_sdl_file(root, limits=SDLParserLimits(max_composed_bytes=16))


@pytest.mark.parametrize(
    ("limits", "message"),
    [
        (SDLParserLimits(max_composition_depth=1), "composition depth budget"),
        (SDLParserLimits(max_namespace_depth=1), "namespace-depth budget"),
    ],
)
def test_nested_composition_bounds_depth_and_namespace_growth(
    tmp_path: Path,
    limits: SDLParserLimits,
    message: str,
) -> None:
    (tmp_path / "leaf.yaml").write_text(
        """\
name: leaf
version: 1.0.0
module:
  id: acme/leaf
  version: 1.0.0
  exports: {nodes: [vm]}
nodes: {vm: {type: switch}}
""",
        encoding="utf-8",
    )
    (tmp_path / "middle.yaml").write_text(
        """\
name: middle
version: 1.0.0
module:
  id: acme/middle
  version: 1.0.0
  exports: {nodes: [inner.vm]}
imports:
  - source: local:leaf.yaml
    namespace: inner
""",
        encoding="utf-8",
    )
    root = tmp_path / "root.yaml"
    root.write_text(
        """\
name: root
imports:
  - source: local:middle.yaml
    namespace: outer
""",
        encoding="utf-8",
    )

    from raes.parser import parse_sdl_file

    with pytest.raises(SDLParseError, match=message):
        parse_sdl_file(root, limits=limits)


def test_compiled_runtime_model_rejects_map_key_address_mismatch() -> None:
    resource = NodeRuntime(address="provision.node.vm", name="vm", spec={})

    with pytest.raises(ValueError, match="map key"):
        RuntimeModel(
            scenario_name="root",
            node_deployments={"provision.node.other": resource},
        )


def test_compiled_runtime_model_rejects_cross_family_address_collision() -> None:
    address = "provision.shared"

    with pytest.raises(ValueError, match="duplicate compiled address"):
        RuntimeModel(
            scenario_name="root",
            networks={address: NetworkRuntime(address=address, name="network", spec={})},
            node_deployments={address: NodeRuntime(address=address, name="node", spec={})},
        )


def test_composed_realization_concern_retains_canonical_resource_address() -> None:
    model = compile_runtime_model(
        ExpandedScenario(
            name="root",
            nodes={
                "shared.vm": {
                    "type": "compute",
                    "os": "linux",
                    "resources": {"ram": "1 gib", "cpu": 1},
                }
            },
        )
    )

    requirements = {requirement.field_path: requirement for requirement in model.realization_requirements}
    assert requirements["nodes.shared.vm.os"].address == "provision.node.shared.vm"
    assert requirements["nodes.shared.vm.type"].address == "provision.node.shared.vm"


def test_in_process_plan_rejects_resource_map_key_address_mismatch() -> None:
    resource = PlannedResource(
        address="provision.node.vm",
        domain=RuntimeDomain.PROVISIONING,
        resource_type="node",
        payload={},
    )

    with pytest.raises(ValueError, match="resource map key"):
        ProvisioningPlan(resources={"provision.node.other": resource})


def test_in_process_plan_rejects_duplicate_operations_and_unknown_startup_address() -> None:
    operation = ProvisionOp(
        action=ChangeAction.CREATE,
        address="provision.node.vm",
        resource_type="node",
        payload={},
    )

    with pytest.raises(ValueError, match="operation addresses"):
        ProvisioningPlan(operations=[operation, operation])
    with pytest.raises(ValueError, match="admitted operation"):
        OrchestrationPlan(startup_order=["orchestration.workflow.flow"])


def test_runtime_snapshot_rejects_map_key_address_mismatch() -> None:
    entry = SnapshotEntry(
        address="provision.node.vm",
        domain=RuntimeDomain.PROVISIONING,
        resource_type="node",
        payload={},
    )

    with pytest.raises(ValueError, match="map key"):
        RuntimeSnapshot(entries={"provision.node.other": entry})
    with pytest.raises(ValidationError, match="map key"):
        RuntimeSnapshotEnvelopeModel(
            entries={
                "provision.node.other": {
                    "address": "provision.node.vm",
                    "domain": "provisioning",
                    "resource_type": "node",
                }
            }
        )


@pytest.mark.parametrize("factory", [ApplyResult, OperationStatus])
def test_runtime_changed_addresses_are_canonical_and_unique(factory) -> None:
    if factory is ApplyResult:
        kwargs = {"success": True, "snapshot": RuntimeSnapshot()}
    else:
        kwargs = {
            "operation_id": "operation-test",
            "domain": RuntimeDomain.PROVISIONING,
            "state": OperationState.RUNNING,
            "submitted_at": "2026-09-06T10:00:00Z",
            "updated_at": "2026-09-06T10:00:01Z",
            "context": OperationAdmissionContext(
                actor_id="operator-test",
                authorization_scope=("role:operator",),
                target_scope="target:test",
                run_scope="run:test",
                operation_kind=OperationKind.PROVISIONING,
                request_commitment=f"sha256:{'0' * 64}",
            ),
        }
    with pytest.raises(ValueError, match="canonical compiled address"):
        factory(changed_addresses=["bad address"], **kwargs)
    with pytest.raises(ValueError, match="unique"):
        factory(changed_addresses=["provision.node.vm", "provision.node.vm"], **kwargs)


def test_published_plan_rejects_duplicate_operation_addresses() -> None:
    operation = {
        "action": "create",
        "address": "provision.node.vm",
        "resource_type": "node",
    }

    with pytest.raises(ValidationError, match="operation addresses"):
        ProvisioningPlanModel(operations=[operation, operation], realization_authority=[])


def test_provider_name_is_bounded_and_collision_resistant_for_full_address() -> None:
    first = provider_resource_name(
        "provision.node.first.shared",
        prefix="raes",
        maximum_length=63,
    )
    second = provider_resource_name(
        "provision.node.second.shared",
        prefix="raes",
        maximum_length=63,
    )

    assert first != second
    assert first == provider_resource_name(
        "provision.node.first.shared",
        prefix="raes",
        maximum_length=63,
    )
    assert len(first) <= 63
    assert first.startswith("raes-")
