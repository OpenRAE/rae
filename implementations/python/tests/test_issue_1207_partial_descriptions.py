"""Partial inventory is valid information, never implicit execution authority."""

from copy import deepcopy

import pytest
import yaml
from pydantic import ValidationError
from raes import parse_sdl
from raes.runtime_configuration import RuntimeConfiguration
from raes.runtime_datastore import RuntimeDatastoreService
from raes.runtime_forwarding_agent import RelationshipForwardingEdge, RuntimeForwardingShipTarget
from raes.validator import SemanticValidator
from test_issue_1206_vocabulary_consumers import _AgreementBoundary

PARTIAL_RECORDS = [
    ("datastore_services", {"datastore_service_id": "cache", "data_model": "key_value"}),
    ("datastore_services", {"datastore_service_id": "search", "data_model": "search_index", "partitions": []}),
    (
        "datastore_services",
        {
            "datastore_service_id": "search",
            "data_model": "search_index",
            "partitions": [{"partition_id": "index", "kind": "index", "shard_count": 1}],
        },
    ),
    (
        "datastore_services",
        {
            "datastore_service_id": "columns",
            "data_model": "wide_column",
            "partitions": [{"partition_id": "keyspace", "kind": "keyspace"}],
        },
    ),
    ("forwarding_agents", {"forwarding_agent_id": "logs", "agent_kind": "log_forwarder"}),
    ("forwarding_agents", {"forwarding_agent_id": "sync", "agent_kind": "content_sync"}),
    (
        "orchestration_authorities",
        {"orchestration_authority_id": "authority", "privilege_class": "host_root_equivalent"},
    ),
    (
        "app_authorizations",
        {"app_authorization_id": "rbac", "resource_vocabulary": "app_resource", "permission_grants": []},
    ),
    ("database_services", {"database_service_id": "db", "engine": "postgresql"}),
    ("database_services", {"database_service_id": "db", "engine": "postgresql", "protocol": "unknown"}),
]


@pytest.mark.parametrize("family,record", PARTIAL_RECORDS)
def test_partial_records_parse_validate_and_round_trip_without_invented_facts(family, record):
    source = {"name": "partial", "nodes": {"host": {"type": "compute", "runtime": {family: [record]}}}}
    scenario = parse_sdl(yaml.safe_dump(source))
    SemanticValidator(scenario).validate()
    runtime = scenario.nodes["host"].runtime
    assert runtime.model_dump(mode="json", exclude_unset=True) == {family: [record]}
    restored = RuntimeConfiguration.model_validate_json(runtime.model_dump_json(exclude_unset=True))
    assert restored.model_dump(mode="json", exclude_unset=True) == {family: [record]}
    assert not scenario.evidence_requirements


def test_disabled_redis_mechanisms_are_distinct_from_unknown_persistence():
    unknown = RuntimeDatastoreService(datastore_service_id="cache", data_model="key_value")
    disabled = RuntimeDatastoreService(
        datastore_service_id="cache",
        data_model="key_value",
        persistence={"persistence_id": "memory-only", "aof": False, "rdb_save_points": []},
    )
    assert "persistence" not in unknown.model_dump(exclude_unset=True)
    assert disabled.model_dump(exclude_unset=True)["persistence"] == {
        "persistence_id": "memory-only",
        "aof": False,
        "rdb_save_points": [],
    }


def test_non_ioc_synchronizer_can_buffer_and_enroll_without_a_reload_channel():
    record = {
        "forwarding_agent_id": "files",
        "agent_kind": "content_sync",
        "sources": [{"source_id": "files-in", "kind": "tailed_path", "location": "/srv/content"}],
        "transforms": [{"transform_id": "parse", "kind": "parse"}],
        "buffer_policy": {"buffer_policy_id": "buffer", "queue_capacity": 0},
        "ship_targets": [{"target_id": "peer", "enrollment_identity_classification": "operator_secret"}],
        "reload_channels": [],
    }
    runtime = RuntimeConfiguration(forwarding_agents=[record])
    assert runtime.model_dump(mode="json", exclude_unset=True) == {"forwarding_agents": [record]}


@pytest.mark.parametrize("access", ["unknown", "read_write", "read_only"])
def test_privilege_description_does_not_infer_authority_from_socket_spelling(access):
    source = {
        "name": "partial-authority",
        "nodes": {
            "host": {
                "type": "compute",
                "runtime": {
                    "local_control_interfaces": [
                        {
                            "control_interface_id": "control",
                            "kind": "unix_socket",
                            "path": "/run/podman/podman.sock",
                            "access": access,
                        }
                    ],
                    "orchestration_authorities": [
                        {
                            "orchestration_authority_id": "authority",
                            "privilege_class": "host_root_equivalent",
                            "control_interface_ref": "control",
                        }
                    ],
                },
            }
        },
    }
    scenario = parse_sdl(yaml.safe_dump(source))
    SemanticValidator(scenario).validate()


@pytest.mark.parametrize("protocol", [None, "unknown", "${protocol}"])
def test_partial_target_protocol_is_not_an_explicit_disagreement(protocol):
    boundary = _AgreementBoundary()
    fields = {} if protocol is None else {"protocol": protocol}
    target = RuntimeForwardingShipTarget(target_id="target", **fields)
    edge = RelationshipForwardingEdge(forwarder_ref="forwarder", protocol="syslog")
    boundary._check_forwarding_edge_protocol_agreement(edge, [target], "forwarder", "edge")
    assert boundary.errors == []


@pytest.mark.parametrize("role", ["agent_event_ingestion", "agent_enrollment"])
@pytest.mark.parametrize("ports", [{}, {"ingestion_port": None, "enrollment_port": None}])
def test_partial_target_ports_survive_semantic_validation_and_instantiation(role, ports):
    from raes_processor.compiler import compile_runtime_model

    source = {
        "name": "partial-edge",
        "nodes": {
            "host": {
                "type": "compute",
                "runtime": {
                    "forwarding_agents": [
                        {
                            "forwarding_agent_id": "forwarder",
                            "agent_kind": "log_forwarder",
                            "ship_targets": [{"target_id": "target", **ports}],
                        }
                    ]
                },
            },
            "dest": {"type": "compute"},
        },
        "relationships": {
            "edge": {
                "type": "connects_to",
                "source": "host",
                "target": "dest",
                "forwarding_edge": {"forwarder_ref": "forwarder", "target_listener_role": role},
            }
        },
    }
    scenario = parse_sdl(yaml.safe_dump(source))
    SemanticValidator(scenario).validate()
    model = compile_runtime_model(scenario)
    assert not [row for row in model.diagnostics if row.is_error]
    target = scenario.nodes["host"].runtime.forwarding_agents[0].ship_targets[0]
    assert target.model_dump(mode="json", exclude_unset=True) == {"target_id": "target", **ports}


@pytest.mark.parametrize("family,record", PARTIAL_RECORDS[:8])
def test_partiality_does_not_disable_closed_model_shapes(family, record):
    invalid = deepcopy(record)
    invalid["invented_authority"] = True
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        RuntimeConfiguration.model_validate({family: [invalid]})
