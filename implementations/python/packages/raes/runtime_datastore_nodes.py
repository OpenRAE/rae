"""Engine-plugin, node-endpoint, and node child models for the
``runtime.datastore_services`` family (DSL-141 node provenance/topology).

Split out of ``runtime_datastore_partitions.py`` (ADR-015 file-size governance).
"""

from pydantic import Field, field_validator, model_validator

from raes.runtime_vocabulary import GovernedVocabulary

from ._base import SDLModel, parse_int_or_var
from ._runtime_datastore_support import _reject_duplicate_values, _require_object_name
from .runtime_datastore_vocab import (
    RuntimeDatastoreNodeEndpointRole,
    RuntimeDatastoreNodeRole,
)
from .runtime_values import (
    coerce_string_list,
    parse_optional_bool_or_var,
    parse_ram,
    parse_runtime_enum_or_var,
    require_symbol,
)


class RuntimeDatastoreEnginePlugin(SDLModel):
    """An engine extension/plugin/module installed on a datastore node.

    Per-node installed-capability inventory (OpenSearch plugins, Redis modules,
    …). Carries the per-plugin ``version`` the name-only service-level list could
    not. ``plugin_id`` is a stable symbol; ``name`` is the observed engine name.
    """

    plugin_id: str
    name: str = ""
    version: str = ""
    description: str = ""

    @field_validator("plugin_id")
    @classmethod
    def validate_plugin_id(cls, v: str) -> str:
        return require_symbol(v, field_name="plugin_id")

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        return _require_object_name(v, field_name="plugin name") if v else v


class RuntimeDatastoreNodeEndpoint(SDLModel):
    """An observed published listener on a datastore node.

    Product-neutral node listener topology: ``role`` distinguishes the
    participant-facing ``client`` listener from the inter-node ``peer`` listener
    without encoding engine-native names. ``address`` and ``port`` stay split,
    matching every other runtime listener surface. A node endpoint records
    published topology, not proof of an OS bind or host publication (ADR-058).
    """

    endpoint_id: str
    role: GovernedVocabulary[RuntimeDatastoreNodeEndpointRole] = RuntimeDatastoreNodeEndpointRole.UNKNOWN
    protocol: str = ""
    address: str = ""
    port: int | str | None = None
    description: str = ""

    @field_validator("endpoint_id")
    @classmethod
    def validate_endpoint_id(cls, v: str) -> str:
        return require_symbol(v, field_name="endpoint_id")

    @field_validator("role", mode="before")
    @classmethod
    def normalize_role(cls, v: object) -> object:
        return parse_runtime_enum_or_var(v, RuntimeDatastoreNodeEndpointRole, field_name="role")

    @field_validator("port", mode="before")
    @classmethod
    def parse_port(cls, v: object) -> int | str | None:
        return parse_int_or_var(v, minimum=1, maximum=65535, field_name="port") if v is not None else v


class RuntimeDatastoreNode(SDLModel):
    """An observed node participating in a datastore cluster.

    Beyond cluster membership and roles, a node carries product-neutral engine
    provenance (version, build hash/type), JVM/process memory posture (initial
    and maximum heap byte bounds, memory-lock state), a typed per-node engine
    plugin inventory, and typed published endpoints (client vs peer listeners).
    All are observed runtime facts — never host policy or software-component
    identity (ADR-058 amending ADR-048).
    """

    node_id: str
    name: str = ""
    roles: list[GovernedVocabulary[RuntimeDatastoreNodeRole]] = Field(default_factory=list)
    is_coordinator: bool | str | None = None
    engine_version: str = ""
    build_hash: str = ""
    build_type: str = ""
    heap_init_bytes: int | str | None = None
    heap_max_bytes: int | str | None = None
    memory_locked: bool | str | None = None
    endpoints: list[RuntimeDatastoreNodeEndpoint] = Field(default_factory=list)
    plugins: list[RuntimeDatastoreEnginePlugin] = Field(default_factory=list)
    description: str = ""

    @field_validator("node_id")
    @classmethod
    def validate_node_id(cls, v: str) -> str:
        return require_symbol(v, field_name="node_id")

    @field_validator("roles", mode="before")
    @classmethod
    def normalize_roles(cls, v: object) -> object:
        values = coerce_string_list(v)
        if isinstance(values, list):
            return [parse_runtime_enum_or_var(item, RuntimeDatastoreNodeRole, field_name="roles") for item in values]
        return values

    @field_validator("is_coordinator", mode="before")
    @classmethod
    def parse_is_coordinator(cls, v: object) -> bool | str | None:
        return parse_optional_bool_or_var(v, field_name="is_coordinator")

    @field_validator("heap_init_bytes", "heap_max_bytes", mode="before")
    @classmethod
    def parse_heap_bytes(cls, v: object) -> int | str | None:
        return parse_ram(v) if v is not None else v

    @field_validator("memory_locked", mode="before")
    @classmethod
    def parse_memory_locked(cls, v: object) -> bool | str | None:
        return parse_optional_bool_or_var(v, field_name="memory_locked")

    @model_validator(mode="after")
    def validate_node(self) -> "RuntimeDatastoreNode":
        _reject_duplicate_values(self.roles, field_name="roles", owner=self.node_id)
        _reject_duplicate_values(
            [plugin.plugin_id for plugin in self.plugins], field_name="plugin_id", owner=self.node_id
        )
        _reject_duplicate_values(
            [endpoint.endpoint_id for endpoint in self.endpoints], field_name="endpoint_id", owner=self.node_id
        )
        self._reject_heap_inversion()
        return self

    def _reject_heap_inversion(self) -> None:
        init_bytes = self.heap_init_bytes
        max_bytes = self.heap_max_bytes
        if isinstance(init_bytes, int) and isinstance(max_bytes, int) and init_bytes > max_bytes:
            raise ValueError(
                f"datastore node '{self.node_id}' heap_init_bytes ({init_bytes}) "
                f"must not exceed heap_max_bytes ({max_bytes})"
            )
