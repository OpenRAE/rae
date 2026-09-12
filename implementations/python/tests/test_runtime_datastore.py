"""Runtime datastore-service (SCN-010 §5.1) SDL surface tests.

Covers the OPEN ``data_model`` discriminator spine, the typed cluster / node /
partition / persistence / transport-security / setting children, secret-bearing
setting redaction, duplicate-id rejection, and — the core correctness feature —
the ``require_profile_for_data_model`` guard (positive for each model plus each
REQUIRE / REJECT negative).
"""

from __future__ import annotations

import json

import pytest
from paths import REPO_ROOT
from pydantic import ValidationError
from raes import VARIABLE_TOKEN_PATTERN
from raes._runtime_service_families import collect_qualified_runtime_family_refs
from raes.runtime_datastore import (
    RuntimeDatastoreCluster,
    RuntimeDatastoreDataModel,
    RuntimeDatastoreEngine,
    RuntimeDatastoreEnginePlugin,
    RuntimeDatastoreMapping,
    RuntimeDatastoreNode,
    RuntimeDatastoreNodeEndpoint,
    RuntimeDatastorePartitionKind,
    RuntimeDatastorePersistence,
    RuntimeDatastoreService,
    RuntimeDatastoreSetting,
    RuntimeDatastoreTemplate,
    RuntimeDatastoreTransportSecurity,
)
from raes.runtime_datastore_vocab import (
    RuntimeDatastoreEvictionPolicy,
    RuntimeDatastoreNodeEndpointRole,
    RuntimeDatastoreNodeRole,
    RuntimeDatastoreReplicationStrategy,
    RuntimeDatastoreSettingProvenance,
    RuntimeDatastoreSettingScope,
    RuntimeDatastoreTransportSecurityMode,
)
from raes.scenario import Scenario

_PUBLISHED_SDL_SCHEMA_NAMES = (
    "instantiated-scenario-snapshot-v1",
    "instantiated-scenario-v1",
    "sdl-authoring-input-v1",
)
_DATASTORE_MAPPING_SCHEMA_FIELDS = {
    "date_detection",
    "description",
    "dynamic_policy",
    "dynamic_template_count",
    "evidence_refs",
    "field_type_census",
    "leaf_field_count",
    "mapping_id",
    "name",
    "partition_ref",
    "schema_digest",
    "top_level_field_count",
}
_DATASTORE_TEMPLATE_SCHEMA_FIELDS = {
    "description",
    "evidence_refs",
    "index_patterns",
    "mapping_ref",
    "name",
    "settings_summary",
    "template_digest",
    "template_id",
}


def _search_index_service(**overrides) -> dict:
    service = {
        "datastore_service_id": "wazuh-indexer",
        "service": "indexer-listener",
        "engine": "opensearch",
        "data_model": "search_index",
        "protocol": "opensearch-transport",
        "version": "2.19.1.0",
        "name": "wazuh-cluster",
        "cluster": {
            "cluster_id": "wazuh-cluster",
            "name": "wazuh",
            "health": "green",
            "discovery_mode": "single-node",
        },
        "nodes": [
            {
                "node_id": "indexer-1",
                "name": "wazuh.indexer",
                "roles": ["cluster_manager", "data", "ingest"],
                "is_coordinator": True,
                "engine_version": "2.19.1",
                "build_hash": "dae2bfc93896178873b43cdf4781f183c72b238f",
                "build_type": "rpm",
                "heap_init_bytes": "1 GiB",
                "heap_max_bytes": "1 GiB",
                "memory_locked": True,
                "endpoints": [
                    {
                        "endpoint_id": "http",
                        "role": "client",
                        "protocol": "https",
                        "address": "172.20.0.12",
                        "port": 9200,
                    },
                    {
                        "endpoint_id": "transport",
                        "role": "peer",
                        "protocol": "transport",
                        "address": "172.20.0.12",
                        "port": 9300,
                    },
                ],
                "plugins": [
                    {"plugin_id": "opensearch-security", "name": "opensearch-security", "version": "2.19.1.0"},
                    {"plugin_id": "opensearch-alerting", "name": "opensearch-alerting", "version": "2.19.1.0"},
                ],
            }
        ],
        "partitions": [
            {
                "partition_id": "wazuh-alerts",
                "kind": "index",
                "name": "wazuh-alerts-4.x-2026.05.30",
                "shard_count": 3,
                "replica_count": 0,
                "health": "green",
            }
        ],
        "templates": [
            {
                "template_id": "wazuh-template",
                "name": "wazuh",
                "index_patterns": ["wazuh-alerts-4.x-*", "wazuh-archives-4.x-*"],
                "settings_summary": {
                    "index.number_of_shards": "3",
                    "index.number_of_replicas": "0",
                    "index.refresh_interval": "5s",
                },
                "mapping_ref": "wazuh-alerts-mapping",
                "template_digest": "sha256:wazuh-template",
                "evidence_refs": ["docs/raes/inventory/wazuh.indexer/evidence/wazuh-indexer-templates.json.gz"],
            }
        ],
        "aliases": ["wazuh-alerts"],
        "mappings": [
            {
                "mapping_id": "wazuh-alerts-mapping",
                "partition_ref": "wazuh-alerts",
                "name": "wazuh-alerts-4.x-*",
                "top_level_field_count": 25,
                "leaf_field_count": 670,
                "field_type_census": {"keyword": 220, "date": 9, "ip": 12, "object": 70},
                "dynamic_policy": "true",
                "dynamic_template_count": 5,
                "date_detection": True,
                "schema_digest": "sha256:wazuh-alerts-mapping",
                "evidence_refs": ["docs/raes/inventory/wazuh.indexer/evidence/wazuh-indexer-family-mappings.json.gz"],
            }
        ],
        "lifecycle_policies": ["wazuh-ism"],
        "ingest_pipelines": ["geoip"],
        "transport_security": {
            "transport_security_id": "indexer-tls",
            "mode": "mutual_tls",
            "node_verification": True,
        },
        "settings": [
            {
                "setting_id": "cluster-name",
                "scope": "cluster",
                "provenance": "configuration_file",
                "name": "cluster.name",
                "value": "wazuh-cluster",
            }
        ],
        "authorization_ref": "wazuh-indexer-rbac",
    }
    service.update(overrides)
    return service


def _wide_column_service(**overrides) -> dict:
    service = {
        "datastore_service_id": "thehive-cassandra",
        "engine": "cassandra",
        "data_model": "wide_column",
        "version": "4.1",
        "cluster": {
            "cluster_id": "thehive-ring",
            "partitioner": "Murmur3Partitioner",
            "native_protocol_version": "5",
        },
        "nodes": [
            {"node_id": "cass-1", "roles": ["seed", "coordinator"], "is_coordinator": True},
        ],
        "partitions": [
            {
                "partition_id": "thehive-ks",
                "kind": "keyspace",
                "name": "thehive",
                "replication_strategy": "network_topology_strategy",
                "replication_factor": 1,
                "per_dc_factor_map": {"dc1": 1},
                "durable_writes": True,
            }
        ],
        "authorization_ref": "cassandra-rbac",
    }
    service.update(overrides)
    return service


def _key_value_service(**overrides) -> dict:
    service = {
        "datastore_service_id": "misp-redis",
        "engine": "redis",
        "data_model": "key_value",
        "version": "7.2",
        "partitions": [
            {"partition_id": "db0", "kind": "logical_db", "name": "0", "datatype_census": {"string": 42, "hash": 7}},
        ],
        "persistence": {
            "persistence_id": "redis-persistence",
            "rdb_save_points": ["3600 1", "300 100", "60 10000"],
            "aof": False,
            "eviction": "noeviction",
            "maxmemory": "0",
        },
        "pubsub_channels": ["misp:channel"],
        "queues_streams": ["resque:queue"],
        "authorization_ref": "redis-acl",
    }
    service.update(overrides)
    return service


# --------------------------------------------------------------------------- #
# Construction / typed-child coercion                                         #
# --------------------------------------------------------------------------- #


def test_search_index_service_typed_children() -> None:
    svc = RuntimeDatastoreService(**_search_index_service())

    assert svc.datastore_service_id == "wazuh-indexer"
    assert svc.engine is RuntimeDatastoreEngine.OPENSEARCH
    assert svc.data_model is RuntimeDatastoreDataModel.SEARCH_INDEX
    assert isinstance(svc.cluster, RuntimeDatastoreCluster)
    node = svc.nodes[0]
    assert node.roles[0] is RuntimeDatastoreNodeRole.CLUSTER_MANAGER
    assert node.engine_version == "2.19.1"
    assert node.build_hash == "dae2bfc93896178873b43cdf4781f183c72b238f"
    assert node.build_type == "rpm"
    assert node.heap_init_bytes == 1_073_741_824
    assert node.heap_max_bytes == 1_073_741_824
    assert node.memory_locked is True
    assert [e.role for e in node.endpoints] == [
        RuntimeDatastoreNodeEndpointRole.CLIENT,
        RuntimeDatastoreNodeEndpointRole.PEER,
    ]
    assert node.endpoints[0].port == 9200
    assert node.endpoints[1].port == 9300
    assert node.plugins[0].name == "opensearch-security"
    assert node.plugins[0].version == "2.19.1.0"
    assert svc.partitions[0].kind is RuntimeDatastorePartitionKind.INDEX
    assert svc.partitions[0].shard_count == 3
    assert isinstance(svc.mappings[0], RuntimeDatastoreMapping)
    assert svc.mappings[0].top_level_field_count == 25
    assert svc.mappings[0].leaf_field_count == 670
    assert svc.mappings[0].partition_ref == "wazuh-alerts"
    assert svc.mappings[0].field_type_census["keyword"] == 220
    assert svc.mappings[0].dynamic_policy == "true"
    assert svc.mappings[0].dynamic_template_count == 5
    assert svc.mappings[0].date_detection is True
    assert svc.mappings[0].schema_digest == "sha256:wazuh-alerts-mapping"
    assert svc.mappings[0].evidence_refs == [
        "docs/raes/inventory/wazuh.indexer/evidence/wazuh-indexer-family-mappings.json.gz"
    ]
    assert isinstance(svc.templates[0], RuntimeDatastoreTemplate)
    assert svc.templates[0].index_patterns == ["wazuh-alerts-4.x-*", "wazuh-archives-4.x-*"]
    assert svc.templates[0].settings_summary == {
        "index.number_of_shards": "3",
        "index.number_of_replicas": "0",
        "index.refresh_interval": "5s",
    }
    assert svc.templates[0].mapping_ref == "wazuh-alerts-mapping"
    assert svc.templates[0].template_digest == "sha256:wazuh-template"
    assert svc.templates[0].evidence_refs == [
        "docs/raes/inventory/wazuh.indexer/evidence/wazuh-indexer-templates.json.gz"
    ]
    assert isinstance(svc.transport_security, RuntimeDatastoreTransportSecurity)
    assert svc.transport_security.mode is RuntimeDatastoreTransportSecurityMode.MUTUAL_TLS
    assert svc.settings[0].scope is RuntimeDatastoreSettingScope.CLUSTER
    assert svc.settings[0].provenance is RuntimeDatastoreSettingProvenance.CONFIGURATION_FILE
    assert svc.authorization_ref == "wazuh-indexer-rbac"


def test_search_index_records_cardinality_size_and_identity() -> None:
    svc = RuntimeDatastoreService(
        **_search_index_service(
            cluster={
                "cluster_id": "wazuh-cluster",
                "uuid": "u-vGl1n0Q7e-SKz1tWvb-w",
                "name": "wazuh",
                "health": "green",
                "discovery_mode": "single-node",
                "node_count": 1,
                "shard_total": 102,
                "shard_primaries": 102,
                "doc_count": 1_053_842,
                "store_size_bytes": 1_391_460_626,
            },
            partitions=[
                {
                    "partition_id": "wazuh-alerts",
                    "uuid": "s0fv6XlzTEuJ",
                    "kind": "index",
                    "name": "wazuh-alerts-4.x-2026.05.28",
                    "shard_count": 3,
                    "replica_count": 0,
                    "doc_count": 68_993,
                    "doc_count_deleted": 0,
                    "store_size_bytes": 96_888_422,
                    "creation_timestamp": "2026-05-28T00:00:05.253Z",
                    "open_closed_status": "open",
                    "health": "green",
                }
            ],
        )
    )

    assert svc.cluster is not None
    assert svc.cluster.uuid == "u-vGl1n0Q7e-SKz1tWvb-w"
    assert svc.cluster.node_count == 1
    assert svc.cluster.shard_total == 102
    assert svc.cluster.shard_primaries == 102
    assert svc.cluster.doc_count == 1_053_842
    assert svc.cluster.store_size_bytes == 1_391_460_626

    partition = svc.partitions[0]
    assert partition.uuid == "s0fv6XlzTEuJ"
    assert partition.doc_count == 68_993
    assert partition.doc_count_deleted == 0
    assert partition.store_size_bytes == 96_888_422
    assert partition.creation_timestamp == "2026-05-28T00:00:05.253Z"
    assert partition.open_closed_status == "open"


def test_datastore_cardinality_fields_accept_variable_refs() -> None:
    svc = RuntimeDatastoreService(
        **_search_index_service(
            cluster={
                "cluster_id": "wazuh-cluster",
                "node_count": "${node_count}",
                "shard_total": "${shards}",
                "shard_primaries": "${primaries}",
                "doc_count": "${docs}",
                "store_size_bytes": "${bytes}",
            },
            partitions=[
                {
                    "partition_id": "wazuh-alerts",
                    "kind": "index",
                    "shard_count": "${shards}",
                    "replica_count": "${replicas}",
                    "doc_count": "${docs}",
                    "doc_count_deleted": "${deleted}",
                    "store_size_bytes": "${bytes}",
                }
            ],
        )
    )

    assert svc.cluster is not None
    assert svc.cluster.doc_count == "${docs}"
    assert svc.cluster.store_size_bytes == "${bytes}"
    assert svc.partitions[0].doc_count_deleted == "${deleted}"


def test_datastore_cluster_rejects_negative_cardinality() -> None:
    with pytest.raises(ValidationError, match="node_count must be >= 0"):
        RuntimeDatastoreCluster(cluster_id="cluster", node_count=-1)


@pytest.mark.parametrize(
    "field_name",
    ["node_count", "shard_total", "shard_primaries", "doc_count", "store_size_bytes"],
)
def test_datastore_cluster_rejects_non_integer_cardinality_strings(field_name: str) -> None:
    with pytest.raises(ValidationError, match=f"{field_name} must be an integer"):
        RuntimeDatastoreCluster(cluster_id="cluster", **{field_name: "92.4mb"})


def test_datastore_partition_rejects_negative_cardinality() -> None:
    with pytest.raises(ValidationError, match="doc_count_deleted must be >= 0"):
        RuntimeDatastoreService(
            **_search_index_service(
                partitions=[
                    {
                        "partition_id": "idx",
                        "kind": "index",
                        "shard_count": 1,
                        "replica_count": 0,
                        "doc_count_deleted": -1,
                    }
                ]
            )
        )


@pytest.mark.parametrize("field_name", ["doc_count", "doc_count_deleted", "store_size_bytes"])
def test_datastore_partition_rejects_non_integer_cardinality_strings(field_name: str) -> None:
    with pytest.raises(ValidationError, match=f"{field_name} must be an integer"):
        RuntimeDatastoreService(
            **_search_index_service(
                partitions=[
                    {
                        "partition_id": "idx",
                        "kind": "index",
                        "shard_count": 1,
                        "replica_count": 0,
                        field_name: "92.4mb",
                    }
                ]
            )
        )


def test_wide_column_service_typed_children() -> None:
    svc = RuntimeDatastoreService(**_wide_column_service())

    partition = svc.partitions[0]
    assert partition.kind is RuntimeDatastorePartitionKind.KEYSPACE
    assert partition.replication_strategy is RuntimeDatastoreReplicationStrategy.NETWORK_TOPOLOGY_STRATEGY
    assert partition.replication_factor == 1
    assert partition.per_dc_factor_map == {"dc1": 1}
    assert partition.durable_writes is True


def test_key_value_service_typed_children() -> None:
    svc = RuntimeDatastoreService(**_key_value_service())

    assert isinstance(svc.persistence, RuntimeDatastorePersistence)
    assert svc.persistence.eviction is RuntimeDatastoreEvictionPolicy.NOEVICTION
    assert svc.persistence.aof is False
    assert svc.partitions[0].datatype_census == {"string": 42, "hash": 7}


def test_kebab_case_enum_inputs_normalize() -> None:
    svc = RuntimeDatastoreService(
        **_search_index_service(
            engine="OpenSearch",
            nodes=[{"node_id": "n1", "roles": ["cluster-manager", "data"]}],
        )
    )
    assert svc.engine is RuntimeDatastoreEngine.OPENSEARCH
    assert svc.nodes[0].roles[0] is RuntimeDatastoreNodeRole.CLUSTER_MANAGER


def test_legacy_string_template_mapping_inputs_coerce_to_typed_manifests() -> None:
    svc = RuntimeDatastoreService(
        **_search_index_service(
            templates=["legacy-template"],
            mappings=["legacy-mapping"],
        )
    )

    assert svc.templates[0].template_id == "legacy-template"
    assert svc.templates[0].name == "legacy-template"
    assert svc.mappings[0].mapping_id == "legacy-mapping"
    assert svc.mappings[0].name == "legacy-mapping"

    single = RuntimeDatastoreService(
        **_search_index_service(
            templates="single-template",
            mappings="single-mapping",
        )
    )
    assert single.templates[0].template_id == "single-template"
    assert single.mappings[0].mapping_id == "single-mapping"


def test_relational_and_open_tail_impose_no_profile() -> None:
    # relational, unknown, other are permissive — a near-empty instance validates.
    for model in ("relational", "unknown", "other"):
        svc = RuntimeDatastoreService(datastore_service_id=f"ds-{model}", data_model=model)
        assert svc.data_model.value == model


def test_variable_ref_data_model_is_exempt_from_guard() -> None:
    svc = RuntimeDatastoreService(datastore_service_id="ds-var", data_model="${data_model}")
    assert svc.data_model == "${data_model}"


def test_variable_refs_for_mapping_and_template_links_are_exempt_from_resolution_guard() -> None:
    svc = RuntimeDatastoreService(
        **_search_index_service(
            mappings=[
                {
                    "mapping_id": "deferred-mapping",
                    "partition_ref": "${partition_id}",
                    "top_level_field_count": 1,
                    "leaf_field_count": 1,
                }
            ],
            templates=[
                {
                    "template_id": "deferred-template",
                    "mapping_ref": "${mapping_id}",
                    "index_patterns": ["wazuh-*"],
                }
            ],
        )
    )

    assert svc.mappings[0].partition_ref == "${partition_id}"
    assert svc.templates[0].mapping_ref == "${mapping_id}"


# --------------------------------------------------------------------------- #
# Duplicate-id and secret-redaction guards                                    #
# --------------------------------------------------------------------------- #


def test_rejects_duplicate_stable_ids_across_children() -> None:
    with pytest.raises(ValidationError, match="Duplicate runtime datastore stable id 'dup'"):
        RuntimeDatastoreService(
            **_search_index_service(
                nodes=[{"node_id": "dup", "roles": ["data"]}],
                partitions=[
                    {"partition_id": "dup", "kind": "index", "shard_count": 1, "replica_count": 0},
                ],
            )
        )


def test_rejects_duplicate_string_list_entries() -> None:
    with pytest.raises(ValidationError, match="Duplicate runtime datastore aliases"):
        RuntimeDatastoreService(**_search_index_service(aliases=["a", "a"]))


def test_rejects_duplicate_mapping_and_template_ids() -> None:
    with pytest.raises(ValidationError, match="Duplicate runtime datastore stable id 'dup'"):
        RuntimeDatastoreService(
            **_search_index_service(
                mappings=[
                    {"mapping_id": "dup", "partition_ref": "wazuh-alerts"},
                    {"mapping_id": "dup", "partition_ref": "wazuh-alerts"},
                ],
            )
        )

    with pytest.raises(ValidationError, match="Duplicate runtime datastore stable id 'dup'"):
        RuntimeDatastoreService(
            **_search_index_service(
                templates=[
                    {"template_id": "dup", "mapping_ref": "wazuh-alerts-mapping"},
                    {"template_id": "dup", "mapping_ref": "wazuh-alerts-mapping"},
                ],
            )
        )


def test_mapping_and_template_reject_duplicate_local_lists() -> None:
    with pytest.raises(ValidationError, match="Duplicate runtime datastore evidence_refs"):
        RuntimeDatastoreMapping(mapping_id="mapping", evidence_refs=["e1", "e1"])

    with pytest.raises(ValidationError, match="Duplicate runtime datastore index_patterns"):
        RuntimeDatastoreTemplate(template_id="template", index_patterns=["wazuh-*", "wazuh-*"])


def test_mapping_and_template_ids_reject_variable_placeholders() -> None:
    with pytest.raises(ValidationError, match="mapping_id must be a portable SDL identifier"):
        RuntimeDatastoreMapping(mapping_id="${mapping_id}")

    with pytest.raises(ValidationError, match="template_id must be a portable SDL identifier"):
        RuntimeDatastoreTemplate(template_id="${template_id}")


def test_secret_named_setting_may_carry_scenario_value() -> None:
    setting = RuntimeDatastoreSetting(setting_id="admin-pw", name="admin_password", value="hunter2")

    assert setting.value == "hunter2"


def test_secret_named_setting_with_redacted_class_is_valid() -> None:
    setting = RuntimeDatastoreSetting(
        setting_id="admin-pw",
        name="admin_password",
        classification="redacted",
    )
    assert setting.value == ""


def test_redacted_class_must_omit_raw_value() -> None:
    with pytest.raises(ValidationError, match="must omit its raw value"):
        RuntimeDatastoreSetting(setting_id="s1", name="cluster.name", classification="redacted", value="x")


def test_node_rejects_duplicate_roles() -> None:
    with pytest.raises(ValidationError, match="Duplicate runtime datastore roles"):
        RuntimeDatastoreNode(node_id="n1", roles=["data", "data"])


# --------------------------------------------------------------------------- #
# require_profile_for_data_model — search_index                               #
# --------------------------------------------------------------------------- #


def test_search_index_requires_index_partition() -> None:
    with pytest.raises(ValidationError, match="requires at least one partition with kind 'index'"):
        RuntimeDatastoreService(**_search_index_service(partitions=[]))


def test_search_index_requires_shard_replica_geometry() -> None:
    with pytest.raises(ValidationError, match="must carry shard_count and replica_count geometry"):
        RuntimeDatastoreService(
            **_search_index_service(partitions=[{"partition_id": "idx", "kind": "index", "shard_count": 3}])
        )


def test_search_index_requires_mapping_manifest() -> None:
    with pytest.raises(ValidationError, match="requires at least one structured mapping manifest"):
        RuntimeDatastoreService(**_search_index_service(mappings=[]))


def test_mapping_partition_ref_must_resolve() -> None:
    with pytest.raises(ValidationError, match="mapping 'orphan' partition_ref 'missing-index' does not resolve"):
        RuntimeDatastoreService(
            **_search_index_service(
                mappings=[{"mapping_id": "orphan", "partition_ref": "missing-index"}],
            )
        )


def test_template_mapping_ref_must_resolve() -> None:
    with pytest.raises(
        ValidationError, match="template 'orphan-template' mapping_ref 'missing-mapping' does not resolve"
    ):
        RuntimeDatastoreService(
            **_search_index_service(
                templates=[{"template_id": "orphan-template", "mapping_ref": "missing-mapping"}],
            )
        )


def test_mapping_and_template_refs_are_targetable() -> None:
    scenario = Scenario(
        name="datastore-refs",
        nodes={
            "indexer": {
                "type": "compute",
                "runtime": {"datastore_services": [_search_index_service()]},
            }
        },
    )

    refs = collect_qualified_runtime_family_refs(scenario, family_keys={"datastore-services"})

    assert "nodes.indexer.runtime.datastore_services.wazuh-indexer.mappings.wazuh-alerts-mapping" in refs
    assert "nodes.indexer.runtime.datastore_services.wazuh-indexer.templates.wazuh-template" in refs


def _string_branch(schema_name: str) -> dict:
    """Shape of a free string subschema in the given published SDL schema.

    The instantiated-scenario contract forbids unresolved ``${var}`` tokens in
    string values (issue #500); the authoring contract still accepts them, so
    the two schemas now differ on every string branch.
    """
    if schema_name in {"instantiated-scenario-v1", "instantiated-scenario-snapshot-v1"}:
        return {"type": "string", "not": {"pattern": VARIABLE_TOKEN_PATTERN}}
    return {"type": "string"}


def test_published_sdl_schemas_include_mapping_and_template_manifests() -> None:
    for schema_name in _PUBLISHED_SDL_SCHEMA_NAMES:
        schema_path = REPO_ROOT / "contracts" / "schemas" / "sdl" / f"{schema_name}.json"
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        defs = schema["$defs"]
        service_properties = defs["RuntimeDatastoreService"]["properties"]
        string_branch = _string_branch(schema_name)

        assert service_properties["mappings"]["items"]["$ref"] == "#/$defs/RuntimeDatastoreMapping"
        assert service_properties["templates"]["items"]["$ref"] == "#/$defs/RuntimeDatastoreTemplate"

        mapping_schema = defs["RuntimeDatastoreMapping"]
        assert mapping_schema["additionalProperties"] is False
        assert set(mapping_schema["properties"]) == _DATASTORE_MAPPING_SCHEMA_FIELDS
        assert mapping_schema["required"] == ["mapping_id"]
        assert mapping_schema["properties"]["field_type_census"]["additionalProperties"]["anyOf"] == [
            {"type": "integer"},
            string_branch,
        ]
        assert mapping_schema["properties"]["date_detection"]["anyOf"] == [
            {"type": "boolean"},
            string_branch,
            {"type": "null"},
        ]

        template_schema = defs["RuntimeDatastoreTemplate"]
        assert template_schema["additionalProperties"] is False
        assert set(template_schema["properties"]) == _DATASTORE_TEMPLATE_SCHEMA_FIELDS
        assert template_schema["required"] == ["template_id"]
        assert template_schema["properties"]["settings_summary"]["additionalProperties"]["anyOf"] == [
            string_branch,
            {"type": "integer"},
            {"type": "boolean"},
        ]


# --------------------------------------------------------------------------- #
# require_profile_for_data_model — key_value                                   #
# --------------------------------------------------------------------------- #


def test_key_value_requires_persistence() -> None:
    with pytest.raises(ValidationError, match="data_model 'key_value' requires a persistence profile"):
        RuntimeDatastoreService(**_key_value_service(persistence=None))


def test_key_value_rejects_relational_partitions() -> None:
    with pytest.raises(ValidationError, match="must not carry .*partitions"):
        RuntimeDatastoreService(
            **_key_value_service(
                partitions=[{"partition_id": "ks", "kind": "keyspace", "name": "x"}],
            )
        )


# --------------------------------------------------------------------------- #
# require_profile_for_data_model — wide_column                                 #
# --------------------------------------------------------------------------- #


def test_wide_column_requires_keyspace_partition() -> None:
    with pytest.raises(ValidationError, match="requires at least one partition with kind 'keyspace'"):
        RuntimeDatastoreService(**_wide_column_service(partitions=[]))


def test_wide_column_requires_replication_strategy_and_factor() -> None:
    with pytest.raises(ValidationError, match="must carry replication_strategy and replication_factor"):
        RuntimeDatastoreService(
            **_wide_column_service(
                partitions=[{"partition_id": "ks", "kind": "keyspace", "name": "thehive"}],
            )
        )


def test_wide_column_rejects_keyspace_missing_factor() -> None:
    with pytest.raises(ValidationError, match="must carry replication_strategy and replication_factor"):
        RuntimeDatastoreService(
            **_wide_column_service(
                partitions=[
                    {
                        "partition_id": "ks",
                        "kind": "keyspace",
                        "replication_strategy": "simple_strategy",
                    }
                ],
            )
        )


# --------------------------------------------------------------------------- #
# DSL-141 — node engine provenance, heap posture, plugins, endpoints          #
# --------------------------------------------------------------------------- #


def test_node_provenance_defaults_are_empty() -> None:
    node = RuntimeDatastoreNode(node_id="n1")
    assert node.engine_version == ""
    assert node.build_hash == ""
    assert node.build_type == ""
    assert node.heap_init_bytes is None
    assert node.heap_max_bytes is None
    assert node.memory_locked is None
    assert node.endpoints == []
    assert node.plugins == []


def test_node_heap_bytes_accept_human_int_and_var() -> None:
    node = RuntimeDatastoreNode(node_id="n1", heap_init_bytes="512 MiB", heap_max_bytes=1_073_741_824)
    assert node.heap_init_bytes == 536_870_912
    assert node.heap_max_bytes == 1_073_741_824

    var_node = RuntimeDatastoreNode(node_id="n2", heap_max_bytes="${heap}")
    assert var_node.heap_max_bytes == "${heap}"


def test_node_rejects_heap_init_above_max() -> None:
    with pytest.raises(ValidationError, match="heap_init_bytes.*heap_max_bytes"):
        RuntimeDatastoreNode(node_id="n1", heap_init_bytes="2 GiB", heap_max_bytes="1 GiB")


def test_node_heap_ordering_exempt_for_variable_bounds() -> None:
    node = RuntimeDatastoreNode(node_id="n1", heap_init_bytes="${init}", heap_max_bytes=1024)
    assert node.heap_init_bytes == "${init}"


def test_node_memory_locked_parses_bool_and_var() -> None:
    assert RuntimeDatastoreNode(node_id="n1", memory_locked="true").memory_locked is True
    assert RuntimeDatastoreNode(node_id="n2", memory_locked="${mlock}").memory_locked == "${mlock}"


def test_engine_plugin_retains_per_plugin_version() -> None:
    plugin = RuntimeDatastoreEnginePlugin(
        plugin_id="opensearch-security", name="opensearch-security", version="2.19.1.0"
    )
    assert plugin.plugin_id == "opensearch-security"
    assert plugin.version == "2.19.1.0"


def test_engine_plugin_id_must_be_stable_symbol() -> None:
    with pytest.raises(ValidationError, match="plugin_id"):
        RuntimeDatastoreEnginePlugin(plugin_id="${plugin}", name="x")
    with pytest.raises(ValidationError, match="plugin_id"):
        RuntimeDatastoreEnginePlugin(plugin_id="", name="x")


def test_node_endpoint_typed_fields() -> None:
    endpoint = RuntimeDatastoreNodeEndpoint(
        endpoint_id="http", role="client", protocol="https", address="172.20.0.12", port=9200
    )
    assert endpoint.role is RuntimeDatastoreNodeEndpointRole.CLIENT
    assert endpoint.address == "172.20.0.12"
    assert endpoint.port == 9200


def test_endpoint_role_normalizes_hyphen_alias_and_open_sentinels() -> None:
    assert RuntimeDatastoreNodeEndpointRole.UNKNOWN.value == "unknown"
    assert RuntimeDatastoreNodeEndpointRole.OTHER.value == "other"
    endpoint = RuntimeDatastoreNodeEndpoint(endpoint_id="e1", role="PEER")
    assert endpoint.role is RuntimeDatastoreNodeEndpointRole.PEER


def test_endpoint_role_rejects_unrecognized_value() -> None:
    # An unqualified private role must fail the governed identity grammar.
    with pytest.raises(ValidationError, match="role must be one of the known terms"):
        RuntimeDatastoreNodeEndpoint(endpoint_id="e1", role="gossip")


def test_endpoint_id_must_be_stable_symbol() -> None:
    with pytest.raises(ValidationError, match="endpoint_id"):
        RuntimeDatastoreNodeEndpoint(endpoint_id="${e}")


def test_endpoint_port_range_enforced() -> None:
    # Both bounds: above the 65535 ceiling and below the minimum of 1.
    with pytest.raises(ValidationError, match="port"):
        RuntimeDatastoreNodeEndpoint(endpoint_id="e1", port=70000)
    with pytest.raises(ValidationError, match="port"):
        RuntimeDatastoreNodeEndpoint(endpoint_id="e1", port=0)


def test_node_rejects_duplicate_plugin_ids() -> None:
    with pytest.raises(ValidationError, match="plugin"):
        RuntimeDatastoreNode(
            node_id="n1",
            plugins=[{"plugin_id": "dup", "name": "a"}, {"plugin_id": "dup", "name": "b"}],
        )


def test_node_rejects_duplicate_endpoint_ids() -> None:
    with pytest.raises(ValidationError, match="endpoint"):
        RuntimeDatastoreNode(
            node_id="n1",
            endpoints=[{"endpoint_id": "dup"}, {"endpoint_id": "dup"}],
        )


def test_service_wide_id_namespace_includes_plugin_and_endpoint_ids() -> None:
    # A plugin id colliding with the node id is a service-wide stable-id clash.
    with pytest.raises(ValidationError, match="Duplicate runtime datastore stable id 'indexer-1'"):
        RuntimeDatastoreService(
            **_search_index_service(
                nodes=[
                    {
                        "node_id": "indexer-1",
                        "roles": ["data"],
                        "plugins": [{"plugin_id": "indexer-1", "name": "x"}],
                    }
                ]
            )
        )


def test_endpoint_id_collision_with_partition_is_service_wide() -> None:
    with pytest.raises(ValidationError, match="Duplicate runtime datastore stable id 'wazuh-alerts'"):
        RuntimeDatastoreService(
            **_search_index_service(
                nodes=[
                    {
                        "node_id": "indexer-1",
                        "roles": ["data"],
                        "endpoints": [{"endpoint_id": "wazuh-alerts"}],
                    }
                ]
            )
        )


def test_same_plugin_id_on_two_nodes_is_rejected_service_wide() -> None:
    # The service-wide namespace spans ALL nodes: the same plugin_id appearing
    # on two distinct nodes is a collision the per-node check cannot catch. A
    # service-scoped check that only deduped within each node would pass this.
    with pytest.raises(ValidationError, match="Duplicate runtime datastore stable id 'opensearch-security'"):
        RuntimeDatastoreService(
            **_search_index_service(
                nodes=[
                    {
                        "node_id": "indexer-1",
                        "roles": ["cluster_manager", "data"],
                        "plugins": [{"plugin_id": "opensearch-security", "name": "x"}],
                    },
                    {
                        "node_id": "indexer-2",
                        "roles": ["data"],
                        "plugins": [{"plugin_id": "opensearch-security", "name": "y"}],
                    },
                ]
            )
        )


def test_same_endpoint_id_on_two_nodes_is_rejected_service_wide() -> None:
    # Same cross-node obligation for endpoint ids: the same endpoint_id on two
    # distinct nodes collides in the service-wide stable-id namespace.
    with pytest.raises(ValidationError, match="Duplicate runtime datastore stable id 'transport'"):
        RuntimeDatastoreService(
            **_search_index_service(
                nodes=[
                    {
                        "node_id": "indexer-1",
                        "roles": ["cluster_manager", "data"],
                        "endpoints": [{"endpoint_id": "transport", "role": "peer"}],
                    },
                    {
                        "node_id": "indexer-2",
                        "roles": ["data"],
                        "endpoints": [{"endpoint_id": "transport", "role": "peer"}],
                    },
                ]
            )
        )


def test_removed_node_address_field_is_rejected() -> None:
    with pytest.raises(ValidationError, match="address"):
        RuntimeDatastoreNode(node_id="n1", address="172.20.0.12")


def test_removed_service_engine_plugins_field_is_rejected() -> None:
    with pytest.raises(ValidationError, match="engine_plugins"):
        RuntimeDatastoreService(**_search_index_service(engine_plugins=["opensearch-security"]))
