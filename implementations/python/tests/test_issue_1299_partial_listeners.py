"""Issue #1299: listener descriptions preserve partial knowledge."""

from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import replace

import pytest
import yaml
from jsonschema import Draft202012Validator
from pydantic import ValidationError
from raes import instantiate_scenario, parse_sdl, render_sdl_source
from raes._errors import SDLValidationError
from raes.explicitness import ExplicitnessClass, ExplicitnessProvenance
from raes.runtime_configuration import RuntimeConfiguration
from raes.runtime_listeners import RuntimeListenerProtocol
from raes.runtime_ssh_server import RuntimeSshServer
from raes.scenario import InstantiatedScenario
from raes.validator import SemanticValidator
from raes_contracts.contracts import schema_bundle
from raes_contracts.planning import ChangeAction, ProvisioningPlan, ProvisionOp, RuntimeDomain
from raes_contracts.realization_structure import evaluate_realization_constraint
from raes_contracts.runtime_state import RuntimeSnapshot, SnapshotEntry
from raes_processor.planner.realization_preparation import prepared_realization_violation
from raes_processor.semantics.realization import CompiledRealizationRequirement, realization_disclosure
from raes_processor.semantics.realization_concerns import project_realization_concern
from test_issue_1200_mixed_runtime_constraints import _fixture

PARTIAL_LISTENERS = [
    {"service_listener_id": "tcp-port", "protocol": "tcp", "port": 80},
    {"service_listener_id": "unix-kind", "protocol": "unix"},
    {"service_listener_id": "unknown-kind", "protocol": "unknown"},
    {"service_listener_id": "private-kind", "protocol": "x-example:quic"},
    {"service_listener_id": "explicit-empty", "address": ""},
]


def test_partial_listener_knowledge_parses_and_round_trips_without_invented_facts() -> None:
    source = {
        "name": "partial-listeners",
        "nodes": {"host": {"type": "compute", "runtime": {"service_listeners": PARTIAL_LISTENERS}}},
    }

    scenario = parse_sdl(yaml.safe_dump(source))
    SemanticValidator(scenario).validate()
    runtime = scenario.nodes["host"].runtime
    assert runtime.model_dump(mode="json", exclude_unset=True) == {"service_listeners": PARTIAL_LISTENERS}

    restored = RuntimeConfiguration.model_validate_json(runtime.model_dump_json(exclude_unset=True))
    assert restored.model_dump(mode="json", exclude_unset=True) == {"service_listeners": PARTIAL_LISTENERS}
    assert scenario.evidence_requirements == {}


def test_omitted_legacy_tcp_default_is_source_absent_and_instantiated_default() -> None:
    scenario = parse_sdl(
        """
        name: listener-default
        realization: {default: open}
        nodes:
          host:
            type: compute
            runtime:
              service_listeners:
                - {service_listener_id: web, port: 80}
        """
    )

    authored = scenario.nodes["host"].runtime.service_listeners[0]
    assert authored.protocol is RuntimeListenerProtocol.TCP
    assert "protocol" not in authored.model_fields_set
    rendered_listener = yaml.safe_load(render_sdl_source(scenario).content)["nodes"]["host"]["runtime"][
        "service_listeners"
    ][0]
    assert rendered_listener == {"service_listener_id": "web", "port": 80}

    instantiated = instantiate_scenario(scenario)
    concrete = instantiated.nodes["host"].runtime.service_listeners[0]
    assert concrete.protocol is RuntimeListenerProtocol.TCP
    assert concrete.model_dump(mode="json")["protocol"] == "tcp"
    assert "nodes.host.runtime.service_listeners[0].protocol" not in instantiated.explicitness


@pytest.mark.parametrize(
    "listener_fact",
    [
        {"socket_path": "/run/app.sock"},
        {"address_family": "unix"},
        {"scope": "local_socket"},
    ],
)
def test_protocol_omitted_unix_facts_survive_authoring_and_instantiation(
    listener_fact: dict[str, str],
) -> None:
    source = {
        "name": "partial-unix-listener",
        "nodes": {
            "host": {
                "type": "compute",
                "runtime": {"service_listeners": [{"service_listener_id": "control", **listener_fact}]},
            }
        },
    }

    scenario = parse_sdl(yaml.safe_dump(source))
    SemanticValidator(scenario).validate()
    instantiated = instantiate_scenario(scenario)
    SemanticValidator(instantiated).validate()

    authored = scenario.nodes["host"].runtime.service_listeners[0]
    concrete = instantiated.nodes["host"].runtime.service_listeners[0]
    assert "protocol" not in authored.model_fields_set
    assert "protocol" not in concrete.model_fields_set
    assert concrete.protocol is RuntimeListenerProtocol.TCP

    restored = InstantiatedScenario.model_validate_json(instantiated.model_dump_json())
    SemanticValidator(restored).validate()


def test_explicit_tcp_still_rejects_unix_listener_facts() -> None:
    with pytest.raises(SDLValidationError, match="supplied TCP protocol contradicts Unix listener facts"):
        parse_sdl(
            """
            name: contradictory-listener
            nodes:
              host:
                type: compute
                runtime:
                  service_listeners:
                    - service_listener_id: control
                      protocol: tcp
                      socket_path: /run/app.sock
            """
        )


@pytest.mark.parametrize(
    ("listener", "message"),
    [
        (
            {"service_listener_id": "bad", "address_family": "ipv4", "scope": "local_socket"},
            "scope 'local_socket' contradicts address_family 'ipv4'",
        ),
        (
            {"service_listener_id": "bad", "address_family": "unix", "scope": "network_facing"},
            "scope 'network_facing' contradicts Unix address_family",
        ),
    ],
)
def test_concrete_address_family_and_scope_must_agree(listener: dict[str, str], message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        RuntimeConfiguration.model_validate({"service_listeners": [listener]})


def test_open_listener_scope_delegates_bind_but_preserves_exact_port() -> None:
    model, _, _ = _fixture(
        {"service_listeners": [{"service_listener_id": "web", "port": 80}]},
        scope="/nodes/host/runtime/service_listeners",
    )
    requirement = next(row for row in model.realization_requirements if row.requirement_kind == "service-listeners")
    assert requirement.constraint_document is not None

    selected = [{"service_listener_id": "web", "protocol": "tcp", "port": 80, "address": "127.0.0.1"}]
    projected = project_realization_concern("service-listeners", selected, recursive=True)
    assert evaluate_realization_constraint(requirement.constraint_document, projected).conformant

    selected[0]["port"] = 8080
    projected = project_realization_concern("service-listeners", selected, recursive=True)
    assert not evaluate_realization_constraint(requirement.constraint_document, projected).conformant


def test_sparse_listener_preparation_cannot_satisfy_exact_protocol() -> None:
    _, plan, manifest = _fixture(
        {"service_listeners": [{"service_listener_id": "web", "protocol": "tcp"}]},
        scope="/nodes/host/runtime/service_listeners",
    )
    operation = plan.operations[0]
    payload = deepcopy(operation.payload)
    payload["spec"]["node"]["runtime"]["service_listeners"] = [{"service_listener_id": "web"}]
    selected = replace(plan, operations=(replace(operation, payload=payload),))

    assert prepared_realization_violation(plan, selected, manifest) == (
        "Backend preparation does not satisfy the recursive constraints."
    )


def test_sparse_listener_observation_cannot_satisfy_exact_protocol() -> None:
    requirement = CompiledRealizationRequirement(
        field_path="nodes.host.runtime.service_listeners",
        address="provision.node.host",
        domain="runtime-realization",
        requirement_kind="service-listeners",
        explicitness=ExplicitnessClass.EXACT,
        provenance=ExplicitnessProvenance.AUTHOR_DECLARED,
    )

    def payload(value: object) -> dict[str, object]:
        return {"spec": {"node": {"runtime": {"service_listeners": value}}}}

    plan = ProvisioningPlan(
        operations=[
            ProvisionOp(
                action=ChangeAction.CREATE,
                address=requirement.address,
                resource_type="node",
                payload=payload([{"service_listener_id": "web", "protocol": "tcp"}]),
            )
        ]
    )
    snapshot = RuntimeSnapshot(
        entries={
            requirement.address: SnapshotEntry(
                address=requirement.address,
                domain=RuntimeDomain.PROVISIONING,
                resource_type="node",
                payload=payload([{"service_listener_id": "web"}]),
            )
        }
    )

    diagnostics, provenance = realization_disclosure((requirement,), plan, snapshot)

    assert [diagnostic.code for diagnostic in diagnostics] == ["runtime.backend-contract-invalid"]
    assert provenance == ()


@pytest.mark.parametrize("protocol", [None, "unknown"])
def test_missing_or_unknown_listener_protocol_defers_service_protocol_agreement(protocol: str | None) -> None:
    fields = {} if protocol is None else {"protocol": protocol}
    source = {
        "name": "listener-service-agreement",
        "nodes": {
            "host": {
                "type": "compute",
                "services": [{"name": "dns", "port": 53, "protocol": "udp"}],
                "runtime": {
                    "service_listeners": [{"service_listener_id": "dns", "service": "dns", "port": 53, **fields}]
                },
            }
        },
    }

    scenario = parse_sdl(yaml.safe_dump(source))
    SemanticValidator(scenario).validate()
    SemanticValidator(instantiate_scenario(scenario)).validate()


def test_omitted_listener_protocol_does_not_override_published_ref_protocol() -> None:
    scenario = parse_sdl(
        """
        name: listener-publication-agreement
        nodes:
          host:
            type: compute
            runtime:
              network:
                published_ports:
                  - {container_port: 53, protocol: udp, host_ip: 127.0.0.1, host_port: 5353}
              service_listeners:
                - service_listener_id: dns
                  port: 53
                  published_port_refs:
                    - {container_port: 53, protocol: udp, host_ip: 127.0.0.1, host_port: 5353}
        """
    )

    SemanticValidator(scenario).validate()
    SemanticValidator(instantiate_scenario(scenario)).validate()


def test_concrete_private_listener_protocol_remains_binding() -> None:
    scenario = parse_sdl(
        """
        name: private-listener
        nodes:
          host:
            type: compute
            services:
              - {name: private, port: 4444, protocol: tcp}
            runtime:
              service_listeners:
                - service_listener_id: private
                  service: private
                  port: 4444
                  protocol: x-example:quic
        """,
        skip_semantic_validation=True,
    )

    validator = SemanticValidator(scenario)
    with pytest.raises(SDLValidationError, match="port/protocol must match service 'private'"):
        validator.validate()


def test_partial_listener_does_not_create_access_publication_or_capture_demand() -> None:
    scenario = parse_sdl(
        """
        name: descriptive-listener
        nodes:
          host:
            type: compute
            runtime:
              service_listeners:
                - {service_listener_id: web, protocol: tcp, port: 80}
        """
    )

    node = scenario.nodes["host"]
    assert node.services == []
    assert node.runtime.network is None
    assert scenario.evidence_requirements == {}


def test_ssh_daemon_policy_keeps_its_explicit_service_binding() -> None:
    with pytest.raises(ValidationError, match="service"):
        RuntimeSshServer(ssh_server_id="sshd-default")
    with pytest.raises(ValidationError, match="service"):
        RuntimeSshServer(ssh_server_id="sshd-default", service="")


@pytest.mark.parametrize(
    "schema_name",
    [
        "sdl-authoring-input-v1",
        "instantiated-scenario-v1",
        "materialized-scenario-v1",
        "instantiated-scenario-snapshot-v1",
        "scenario-satisfiability-evidence-v1",
    ],
)
def test_published_listener_schemas_do_not_require_complete_endpoints(schema_name: str) -> None:
    definition = schema_bundle()[schema_name]["$defs"]["RuntimeServiceListener"]
    assert definition["required"] == ["service_listener_id"]
    Draft202012Validator.check_schema(schema_bundle()[schema_name])
    assert "Network listeners require" not in json.dumps(definition)
