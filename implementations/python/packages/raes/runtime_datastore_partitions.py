"""Cluster, node, partition, persistence, and setting child models for the
``runtime.datastore_services`` family (SCN-010 §5.1).

Split out of ``runtime_datastore.py`` so no single source file exceeds the
ADR-015 600-line cap. These typed children compose into
:class:`~raes.runtime_datastore.RuntimeDatastoreService`; the top spine and
its ``require_profile_for_data_model`` guard live in ``runtime_datastore.py``.

Every typed child carries a ``<child_noun>_id`` validated by ``require_symbol``.
Settings explicitly classified ``redacted`` / ``operator_secret`` omit their raw
value, exactly as the relational ``DatabaseSetting`` does.
"""

from pydantic import Field, ValidationInfo, field_validator, model_validator

from raes.runtime_vocabulary import GovernedVocabulary

from ._base import SDLModel, parse_int_or_var
from ._runtime_datastore_support import _REDACTED_SENSITIVITIES, _reject_duplicate_values, _require_object_name
from .runtime_datastore_nodes import RuntimeDatastoreEnginePlugin, RuntimeDatastoreNode, RuntimeDatastoreNodeEndpoint
from .runtime_datastore_vocab import (
    RuntimeDatastoreEvictionPolicy,
    RuntimeDatastorePartitionKind,
    RuntimeDatastoreReplicationStrategy,
    RuntimeDatastoreSettingProvenance,
    RuntimeDatastoreSettingScope,
    RuntimeDatastoreTransportSecurityMode,
)
from .runtime_filesystem import RuntimeSensitivityClassification
from .runtime_values import (
    coerce_string_list,
    enforce_observed_value_redaction,
    parse_optional_bool_or_var,
    parse_runtime_enum_or_var,
    require_symbol,
)

__all__ = [
    "RuntimeDatastoreCluster",
    "RuntimeDatastoreEnginePlugin",
    "RuntimeDatastoreMapping",
    "RuntimeDatastoreNode",
    "RuntimeDatastoreNodeEndpoint",
    "RuntimeDatastorePartition",
    "RuntimeDatastorePersistence",
    "RuntimeDatastoreSetting",
    "RuntimeDatastoreTemplate",
    "RuntimeDatastoreTransportSecurity",
]


class RuntimeDatastoreCluster(SDLModel):
    """The single observed cluster posture of a datastore service.

    Captures the cluster-identity facts a search/wide-column cluster exposes:
    native UUID, aggregate cardinality and size, shard totals, health,
    discovery mode, partitioner, and native protocol version.
    """

    cluster_id: str
    uuid: str = ""
    name: str = ""
    health: str = ""
    discovery_mode: str = ""
    partitioner: str = ""
    native_protocol_version: str = ""
    node_count: int | str | None = None
    shard_total: int | str | None = None
    shard_primaries: int | str | None = None
    doc_count: int | str | None = None
    store_size_bytes: int | str | None = None
    description: str = ""

    @field_validator("cluster_id")
    @classmethod
    def validate_cluster_id(cls, v: str) -> str:
        return require_symbol(v, field_name="cluster_id")

    @field_validator("node_count", "shard_total", "shard_primaries", "doc_count", "store_size_bytes", mode="before")
    @classmethod
    def parse_counts(cls, v: object, info: ValidationInfo) -> int | str | None:
        return parse_int_or_var(v, minimum=0, field_name=info.field_name) if v is not None else v


class RuntimeDatastorePartition(SDLModel):
    """An observed partition primitive (index / keyspace / logical_db / family).

    Carries the geometry that differentiates one datastore data model from
    another: native partition/index UUID, shard/replica and document counts for
    a search index, replication strategy + factor + per-DC factor map for a
    wide-column keyspace, and a datatype census for a key-value logical
    database.
    """

    partition_id: str
    kind: GovernedVocabulary[RuntimeDatastorePartitionKind] = RuntimeDatastorePartitionKind.UNKNOWN
    name: str = ""
    uuid: str = ""
    shard_count: int | str | None = None
    replica_count: int | str | None = None
    doc_count: int | str | None = None
    doc_count_deleted: int | str | None = None
    store_size_bytes: int | str | None = None
    creation_timestamp: str = ""
    open_closed_status: str = ""
    replication_strategy: GovernedVocabulary[RuntimeDatastoreReplicationStrategy] = (
        RuntimeDatastoreReplicationStrategy.UNKNOWN
    )
    replication_factor: int | str | None = None
    per_dc_factor_map: dict[str, int | str] = Field(default_factory=dict)
    durable_writes: bool | str | None = None
    datatype_census: dict[str, int | str] = Field(default_factory=dict)
    health: str = ""
    description: str = ""

    @field_validator("partition_id")
    @classmethod
    def validate_partition_id(cls, v: str) -> str:
        return require_symbol(v, field_name="partition_id")

    @field_validator("kind", mode="before")
    @classmethod
    def normalize_kind(cls, v: RuntimeDatastorePartitionKind | str) -> object:
        return parse_runtime_enum_or_var(v, RuntimeDatastorePartitionKind, field_name="kind")

    @field_validator("replication_strategy", mode="before")
    @classmethod
    def normalize_replication_strategy(cls, v: RuntimeDatastoreReplicationStrategy | str) -> object:
        return parse_runtime_enum_or_var(v, RuntimeDatastoreReplicationStrategy, field_name="replication_strategy")

    @field_validator(
        "shard_count",
        "replica_count",
        "doc_count",
        "doc_count_deleted",
        "store_size_bytes",
        "replication_factor",
        mode="before",
    )
    @classmethod
    def parse_counts(cls, v: object, info: ValidationInfo) -> int | str | None:
        return parse_int_or_var(v, minimum=0, field_name=info.field_name) if v is not None else v

    @field_validator("durable_writes", mode="before")
    @classmethod
    def parse_durable_writes(cls, v: object) -> bool | str | None:
        return parse_optional_bool_or_var(v, field_name="durable_writes")

    @field_validator("per_dc_factor_map", "datatype_census", mode="before")
    @classmethod
    def parse_int_maps(cls, v: object, info: ValidationInfo) -> object:
        if not isinstance(v, dict):
            return v
        return {key: parse_int_or_var(value, minimum=0, field_name=info.field_name) for key, value in v.items()}


class RuntimeDatastoreMapping(SDLModel):
    """A bounded manifest of an observed search-index mapping/schema.

    Carries schema geometry and digest/evidence facts, never the raw
    OpenSearch/Elasticsearch ``_mapping`` response body.
    """

    mapping_id: str
    name: str = ""
    partition_ref: str = ""
    top_level_field_count: int | str | None = None
    leaf_field_count: int | str | None = None
    field_type_census: dict[str, int | str] = Field(default_factory=dict)
    dynamic_policy: str = ""
    dynamic_template_count: int | str | None = None
    date_detection: bool | str | None = None
    schema_digest: str = ""
    evidence_refs: list[str] = Field(default_factory=list)
    description: str = ""

    @field_validator("mapping_id")
    @classmethod
    def validate_mapping_id(cls, v: str) -> str:
        return require_symbol(v, field_name="mapping_id")

    @field_validator("top_level_field_count", "leaf_field_count", "dynamic_template_count", mode="before")
    @classmethod
    def parse_counts(cls, v: object, info: ValidationInfo) -> int | str | None:
        return parse_int_or_var(v, minimum=0, field_name=info.field_name) if v is not None else v

    @field_validator("field_type_census", mode="before")
    @classmethod
    def parse_field_type_census(cls, v: object) -> object:
        if not isinstance(v, dict):
            return v
        return {key: parse_int_or_var(value, minimum=0, field_name="field_type_census") for key, value in v.items()}

    @field_validator("date_detection", mode="before")
    @classmethod
    def parse_date_detection(cls, v: object) -> bool | str | None:
        return parse_optional_bool_or_var(v, field_name="date_detection")

    @field_validator("evidence_refs", mode="before")
    @classmethod
    def coerce_evidence_refs(cls, v: object) -> object:
        return coerce_string_list(v)

    @model_validator(mode="after")
    def validate_mapping(self) -> "RuntimeDatastoreMapping":
        _reject_duplicate_values(self.evidence_refs, field_name="evidence_refs", owner=self.mapping_id)
        return self


class RuntimeDatastoreTemplate(SDLModel):
    """A bounded manifest of an observed index template body.

    The template captures patterns, selected settings, optional mapping linkage,
    digest, and evidence refs without embedding the backend's raw template JSON.
    """

    template_id: str
    name: str = ""
    index_patterns: list[str] = Field(default_factory=list)
    settings_summary: dict[str, str | int | bool] = Field(default_factory=dict)
    mapping_ref: str = ""
    template_digest: str = ""
    evidence_refs: list[str] = Field(default_factory=list)
    description: str = ""

    @field_validator("template_id")
    @classmethod
    def validate_template_id(cls, v: str) -> str:
        return require_symbol(v, field_name="template_id")

    @field_validator("index_patterns", "evidence_refs", mode="before")
    @classmethod
    def coerce_string_fields(cls, v: object) -> object:
        return coerce_string_list(v)

    @model_validator(mode="after")
    def validate_template(self) -> "RuntimeDatastoreTemplate":
        _reject_duplicate_values(self.index_patterns, field_name="index_patterns", owner=self.template_id)
        _reject_duplicate_values(self.evidence_refs, field_name="evidence_refs", owner=self.template_id)
        return self


class RuntimeDatastorePersistence(SDLModel):
    """The single observed persistence posture of a key-value datastore.

    Captures Redis-style persistence: RDB save points, AOF on/off, the eviction
    policy, and the maxmemory ceiling. Its presence is the defining profile a
    ``key_value`` data model must carry.
    """

    persistence_id: str
    rdb_save_points: list[str] = Field(default_factory=list)
    aof: bool | str | None = None
    eviction: GovernedVocabulary[RuntimeDatastoreEvictionPolicy] = RuntimeDatastoreEvictionPolicy.UNKNOWN
    maxmemory: str = ""
    description: str = ""

    @field_validator("persistence_id")
    @classmethod
    def validate_persistence_id(cls, v: str) -> str:
        return require_symbol(v, field_name="persistence_id")

    @field_validator("rdb_save_points", mode="before")
    @classmethod
    def coerce_save_points(cls, v: object) -> object:
        return coerce_string_list(v)

    @field_validator("aof", mode="before")
    @classmethod
    def parse_aof(cls, v: object) -> bool | str | None:
        return parse_optional_bool_or_var(v, field_name="aof")

    @field_validator("eviction", mode="before")
    @classmethod
    def normalize_eviction(cls, v: RuntimeDatastoreEvictionPolicy | str) -> object:
        return parse_runtime_enum_or_var(v, RuntimeDatastoreEvictionPolicy, field_name="eviction")


class RuntimeDatastoreTransportSecurity(SDLModel):
    """The single observed transport-security posture of a datastore service.

    Records the intra-cluster transport TLS mode and whether client/node
    certificate verification is enforced — the observable ``xpack.security`` /
    ``SKIPSSL_VERIFY`` posture, never the certificate material itself.
    """

    transport_security_id: str
    mode: GovernedVocabulary[RuntimeDatastoreTransportSecurityMode] = RuntimeDatastoreTransportSecurityMode.NONE
    client_verification: bool | str | None = None
    node_verification: bool | str | None = None
    description: str = ""

    @field_validator("transport_security_id")
    @classmethod
    def validate_transport_security_id(cls, v: str) -> str:
        return require_symbol(v, field_name="transport_security_id")

    @field_validator("mode", mode="before")
    @classmethod
    def normalize_mode(cls, v: RuntimeDatastoreTransportSecurityMode | str) -> object:
        return parse_runtime_enum_or_var(v, RuntimeDatastoreTransportSecurityMode, field_name="mode")

    @field_validator("client_verification", "node_verification", mode="before")
    @classmethod
    def parse_verifications(cls, v: object) -> bool | str | None:
        return parse_optional_bool_or_var(v, field_name="verification")


class RuntimeDatastoreSetting(SDLModel):
    """An observed datastore runtime setting with scope, provenance, and class.

    Explicit ``redacted`` / ``operator_secret`` classifications omit raw values;
    names that look credential-bearing remain scenario content unless the
    author marks the value withheld.
    """

    setting_id: str
    scope: GovernedVocabulary[RuntimeDatastoreSettingScope] = RuntimeDatastoreSettingScope.ENGINE
    provenance: GovernedVocabulary[RuntimeDatastoreSettingProvenance] = RuntimeDatastoreSettingProvenance.UNKNOWN
    classification: GovernedVocabulary[RuntimeSensitivityClassification] = RuntimeSensitivityClassification.UNKNOWN
    name: str = ""
    value: str = ""
    description: str = ""

    @field_validator("setting_id")
    @classmethod
    def validate_setting_id(cls, v: str) -> str:
        return require_symbol(v, field_name="setting_id")

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        return _require_object_name(v, field_name="setting name") if v else v

    @field_validator("scope", mode="before")
    @classmethod
    def normalize_scope(cls, v: RuntimeDatastoreSettingScope | str) -> object:
        return parse_runtime_enum_or_var(v, RuntimeDatastoreSettingScope, field_name="scope")

    @field_validator("provenance", mode="before")
    @classmethod
    def normalize_provenance(cls, v: RuntimeDatastoreSettingProvenance | str) -> object:
        return parse_runtime_enum_or_var(v, RuntimeDatastoreSettingProvenance, field_name="provenance")

    @field_validator("classification", mode="before")
    @classmethod
    def normalize_classification(cls, v: RuntimeSensitivityClassification | str) -> object:
        return parse_runtime_enum_or_var(v, RuntimeSensitivityClassification, field_name="classification")

    @model_validator(mode="after")
    def validate_setting(self) -> "RuntimeDatastoreSetting":
        enforce_observed_value_redaction(
            owner_label=f"datastore setting '{self.setting_id}'",
            value=self.value,
            classification=self.classification,
            redacted_classifications=_REDACTED_SENSITIVITIES,
        )
        return self
