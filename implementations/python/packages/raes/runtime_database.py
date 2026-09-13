"""Observed database logical-state runtime inventory models for SDL nodes.

These models express the participant-observable database logical state of a
node's database service (see ADR-029): the database engine, wire protocol and
version; listener observations; logical objects (databases, schemas, tables);
database-local roles; privilege grants; and provenance-bearing runtime
settings.

This is observed runtime state attached to ``Node.runtime``. It is distinct
from ``Node.services`` (transport bindings), ``runtime.network.published_ports``
(host/OS publication), ``runtime.applications`` (the HTTP application surface),
the top-level ``accounts`` provisioning surface, and ``runtime.local_identity``
(OS-local users). A database service may *reference* the owning transport
service but never duplicates or mutates those surfaces. Database roles are
database-local authorization principals — they are not OS accounts.

``RelationshipDatabaseAccess`` is the typed access detail a top-level
``relationships`` edge carries when an application connects to a database; it
keeps ``role_ref``/``auth_method`` structurally validated rather than buried in
prose (ADR-029 §4).
"""

import ipaddress
import re
from typing import Any

from pydantic import Field, ValidationInfo, field_validator, model_validator

from raes.runtime_vocabulary import GovernedVocabulary

from ._base import (
    SDLModel,
    is_variable_ref,
    parse_bool_or_var,
    parse_int_or_var,
)
from .runtime_database_vocab import (
    ENGINE_TO_PROTOCOLS as _ENGINE_TO_PROTOCOLS,
)
from .runtime_database_vocab import (
    DatabaseAuthMethod,
    DatabaseEngine,
    DatabaseObjectOrigin,
    DatabaseObjectType,
    DatabaseProtocol,
    DatabaseRoleType,
    DatabaseSettingProvenance,
)
from .runtime_filesystem import RuntimeSensitivityClassification
from .runtime_values import (
    coerce_string_list,
    enforce_observed_value_redaction,
    parse_optional_bool_or_var,
    parse_runtime_enum_or_var,
    reject_duplicates,
    require_symbol,
)

__all__ = [
    "Database",
    "DatabaseAuthMethod",
    "DatabaseEngine",
    "DatabaseGrant",
    "DatabaseListener",
    "DatabaseObjectOrigin",
    "DatabaseObjectType",
    "DatabaseProtocol",
    "DatabaseRole",
    "DatabaseRoleType",
    "DatabaseSchema",
    "DatabaseSetting",
    "DatabaseSettingProvenance",
    "DatabaseTable",
    "RelationshipDatabaseAccess",
    "RuntimeDatabaseService",
]

_MIN_PORT = 1
_MAX_PORT = 65535

# A single DNS label: alphanumerics and internal hyphens, 1-63 chars.
_HOSTNAME_LABEL = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?$")

# Sensitivity classes whose raw value must never be recorded.
_REDACTED_SENSITIVITIES = (
    RuntimeSensitivityClassification.REDACTED,
    RuntimeSensitivityClassification.OPERATOR_SECRET,
)


def _db_listen_address_or_var(value: str, *, field_name: str) -> str:
    """Validate a database listener address, allowing ``${var}`` placeholders.

    Database listeners are not host-published ports and not filesystem paths:
    a value may be the wildcard ``*``, an IPv4/IPv6 address, a hostname, or a
    Unix socket path. Forcing it through an IP-only or absolute-path validator
    would wrongly reject legitimate PostgreSQL ``listen_addresses`` values
    (ADR-029 §3).
    """
    if is_variable_ref(value):
        return value
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    if any(ch.isspace() for ch in value):
        raise ValueError(f"{field_name} must not contain whitespace")
    if value == "*" or value.startswith("/"):
        return value
    try:
        ipaddress.ip_address(value)
        return value
    except ValueError:
        pass
    if all(_HOSTNAME_LABEL.match(label) for label in value.split(".")):
        return value
    raise ValueError(f"{field_name} must be '*', an IP address, a hostname, or a Unix socket path")


def _require_object_name(value: str, *, field_name: str) -> str:
    """Validate an observed object name: non-empty, ``${var}`` allowed.

    Object names are data, never reference path segments, so a name may carry
    a variable placeholder; the stable ``*_id`` symbol is what identifies it.
    """
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value


class DatabaseListener(SDLModel):
    """An observed listener of a database service.

    This records what the database process itself listens on. It is not host
    publication — ``runtime.network.published_ports`` remains the host-exposure
    fact (ADR-029 §3).
    """

    address: str
    port: int | str | None = None
    description: str = ""

    @field_validator("address")
    @classmethod
    def validate_address(cls, v: str) -> str:
        return _db_listen_address_or_var(v, field_name="listener address")

    @field_validator("port", mode="before")
    @classmethod
    def parse_port(cls, v: int | str | None) -> int | str | None:
        if v is None:
            return v
        return parse_int_or_var(v, minimum=_MIN_PORT, maximum=_MAX_PORT, field_name="listener port")


class DatabaseTable(SDLModel):
    """An observed table in a database schema.

    ``table_id`` is the stable identity; ``name`` is the observed table name
    and is data, never a mapping key or reference segment.
    """

    table_id: str
    name: str
    description: str = ""

    @field_validator("table_id")
    @classmethod
    def validate_table_id(cls, v: str) -> str:
        return require_symbol(v, field_name="table_id")

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        return _require_object_name(v, field_name="table name")


class DatabaseSchema(SDLModel):
    """An observed schema (namespace) within a database."""

    schema_id: str
    name: str
    origin: GovernedVocabulary[DatabaseObjectOrigin] = DatabaseObjectOrigin.UNKNOWN
    tables: list[DatabaseTable] = Field(default_factory=list)
    description: str = ""

    @field_validator("schema_id")
    @classmethod
    def validate_schema_id(cls, v: str) -> str:
        return require_symbol(v, field_name="schema_id")

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        return _require_object_name(v, field_name="schema name")

    @field_validator("origin", mode="before")
    @classmethod
    def normalize_origin(cls, v: DatabaseObjectOrigin | str) -> DatabaseObjectOrigin | str:
        return parse_runtime_enum_or_var(v, DatabaseObjectOrigin, field_name="origin")

    @model_validator(mode="after")
    def validate_schema(self) -> "DatabaseSchema":
        seen: set[str] = set()
        for table in self.tables:
            if table.table_id in seen:
                raise ValueError(f"Duplicate database table_id '{table.table_id}' in schema '{self.schema_id}'")
            seen.add(table.table_id)
        return self


class Database(SDLModel):
    """An observed logical database within a database service."""

    database_id: str
    name: str
    origin: GovernedVocabulary[DatabaseObjectOrigin] = DatabaseObjectOrigin.UNKNOWN
    schemas: list[DatabaseSchema] = Field(default_factory=list)
    description: str = ""

    @field_validator("database_id")
    @classmethod
    def validate_database_id(cls, v: str) -> str:
        return require_symbol(v, field_name="database_id")

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        return _require_object_name(v, field_name="database name")

    @field_validator("origin", mode="before")
    @classmethod
    def normalize_origin(cls, v: DatabaseObjectOrigin | str) -> DatabaseObjectOrigin | str:
        return parse_runtime_enum_or_var(v, DatabaseObjectOrigin, field_name="origin")

    @model_validator(mode="after")
    def validate_database(self) -> "Database":
        seen: set[str] = set()
        for schema in self.schemas:
            if schema.schema_id in seen:
                raise ValueError(f"Duplicate database schema_id '{schema.schema_id}' in database '{self.database_id}'")
            seen.add(schema.schema_id)
        return self


class DatabaseRole(SDLModel):
    """An observed database-local role — an authorization principal.

    Database roles are not OS accounts, ``runtime.local_identity`` users, or
    top-level scenario ``accounts`` (ADR-029 §4).
    """

    role_id: str
    name: str
    role_type: GovernedVocabulary[DatabaseRoleType] = DatabaseRoleType.OTHER
    origin: GovernedVocabulary[DatabaseObjectOrigin] = DatabaseObjectOrigin.UNKNOWN
    can_login: bool | str | None = None
    description: str = ""

    @field_validator("role_id")
    @classmethod
    def validate_role_id(cls, v: str) -> str:
        return require_symbol(v, field_name="role_id")

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        return _require_object_name(v, field_name="role name")

    @field_validator("role_type", mode="before")
    @classmethod
    def normalize_role_type(cls, v: DatabaseRoleType | str) -> DatabaseRoleType | str:
        return parse_runtime_enum_or_var(v, DatabaseRoleType, field_name="role_type")

    @field_validator("origin", mode="before")
    @classmethod
    def normalize_origin(cls, v: DatabaseObjectOrigin | str) -> DatabaseObjectOrigin | str:
        return parse_runtime_enum_or_var(v, DatabaseObjectOrigin, field_name="origin")

    @field_validator("can_login", mode="before")
    @classmethod
    def parse_can_login(cls, v: bool | str | None) -> bool | str | None:
        return parse_optional_bool_or_var(v, field_name="can_login")


class DatabaseGrant(SDLModel):
    """An observed privilege grant to a database role.

    The grant is structured by grantee, target object, and privileges; raw
    ``GRANT`` statements are not the portable model (ADR-029 §4). ``object_ref``
    is the stable ``*_id`` of a database/schema/table in the same service.
    """

    grantee_role_ref: str
    object_type: GovernedVocabulary[DatabaseObjectType]
    object_ref: str
    privileges: list[str] = Field(default_factory=list)
    with_grant_option: bool | str = False
    description: str = ""

    @field_validator("grantee_role_ref", "object_ref")
    @classmethod
    def validate_refs(cls, v: str, info: ValidationInfo) -> str:
        if not isinstance(v, str) or not v.strip():
            raise ValueError(f"{info.field_name} must be a non-empty string")
        return v

    @field_validator("object_type", mode="before")
    @classmethod
    def normalize_object_type(cls, v: DatabaseObjectType | str) -> DatabaseObjectType | str:
        return parse_runtime_enum_or_var(v, DatabaseObjectType, field_name="object_type")

    @field_validator("privileges", mode="before")
    @classmethod
    def coerce_privileges(cls, v: Any) -> list[str]:
        return coerce_string_list(v)

    @field_validator("privileges")
    @classmethod
    def validate_privileges(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("grant privileges must not be empty")
        for privilege in v:
            if not isinstance(privilege, str) or not privilege.strip():
                raise ValueError("grant privilege must be a non-empty string")
        if len(v) != len(set(v)):
            raise ValueError("Duplicate grant privilege")
        return v

    @field_validator("with_grant_option", mode="before")
    @classmethod
    def parse_with_grant_option(cls, v: bool | str) -> bool | str:
        return parse_bool_or_var(v, field_name="with_grant_option")


class DatabaseSetting(SDLModel):
    """An observed database runtime setting with provenance and sensitivity.

    Explicit ``redacted``/``operator_secret`` classifications omit raw values;
    credential-shaped names remain scenario content unless the author marks the
    value withheld.
    """

    name: str
    value: str = ""
    value_classification: GovernedVocabulary[RuntimeSensitivityClassification] = (
        RuntimeSensitivityClassification.UNKNOWN
    )
    provenance: GovernedVocabulary[DatabaseSettingProvenance] = DatabaseSettingProvenance.UNKNOWN
    description: str = ""

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        return _require_object_name(v, field_name="setting name")

    @field_validator("value_classification", mode="before")
    @classmethod
    def normalize_value_classification(
        cls,
        v: RuntimeSensitivityClassification | str,
    ) -> RuntimeSensitivityClassification | str:
        return parse_runtime_enum_or_var(v, RuntimeSensitivityClassification, field_name="value_classification")

    @field_validator("provenance", mode="before")
    @classmethod
    def normalize_provenance(cls, v: DatabaseSettingProvenance | str) -> DatabaseSettingProvenance | str:
        return parse_runtime_enum_or_var(v, DatabaseSettingProvenance, field_name="provenance")

    @model_validator(mode="after")
    def validate_redacted_value(self) -> "DatabaseSetting":
        # Explicit redaction classifications omit raw values; credential-shaped
        # names remain scenario content unless the author marks them withheld.
        enforce_observed_value_redaction(
            owner_label=f"database setting '{self.name}'",
            value=self.value,
            classification=self.value_classification,
            redacted_classifications=_REDACTED_SENSITIVITIES,
        )
        return self


class RuntimeDatabaseService(SDLModel):
    """An observed database service hosted by a transport service on a node.

    ``service`` references the owning same-node ``Node.services[].name`` (bare
    name or the qualified ``nodes.<node>.services.<name>`` form). The inventory
    is observation metadata; it never mutates ``Node.services``.
    """

    database_service_id: str
    service: str = ""
    engine: GovernedVocabulary[DatabaseEngine] = DatabaseEngine.OTHER
    protocol: GovernedVocabulary[DatabaseProtocol] = DatabaseProtocol.OTHER
    version: str = ""
    name: str = ""
    description: str = ""
    listeners: list[DatabaseListener] = Field(default_factory=list)
    databases: list[Database] = Field(default_factory=list)
    roles: list[DatabaseRole] = Field(default_factory=list)
    grants: list[DatabaseGrant] = Field(default_factory=list)
    settings: list[DatabaseSetting] = Field(default_factory=list)

    @field_validator("database_service_id")
    @classmethod
    def validate_database_service_id(cls, v: str) -> str:
        return require_symbol(v, field_name="database_service_id")

    @field_validator("engine", mode="before")
    @classmethod
    def normalize_engine(cls, v: DatabaseEngine | str) -> DatabaseEngine | str:
        return parse_runtime_enum_or_var(v, DatabaseEngine, field_name="engine")

    @field_validator("protocol", mode="before")
    @classmethod
    def normalize_protocol(cls, v: DatabaseProtocol | str) -> DatabaseProtocol | str:
        return parse_runtime_enum_or_var(v, DatabaseProtocol, field_name="protocol")

    @model_validator(mode="after")
    def validate_service(self) -> "RuntimeDatabaseService":
        self._reject_duplicate_top_level_ids()
        self._reject_duplicate_nested_object_ids()
        self._reject_duplicate_setting_names()
        self._enforce_engine_protocol_pairing()
        return self

    def _reject_duplicate_top_level_ids(self) -> None:
        for field_name, attr in (("database", "database_id"), ("role", "role_id")):
            reject_duplicates(
                (getattr(item, attr) for item in getattr(self, f"{field_name}s")),
                label=f"{field_name} {attr}",
                container_label=f"database service '{self.database_service_id}'",
            )

    def _reject_duplicate_nested_object_ids(self) -> None:
        # Service-wide uniqueness for every object type used by ``grants``.
        # Without this, two databases can share ``schema_id: public`` or two
        # schemas can share ``table_id: users``, and a grant ``object_ref``
        # resolves ambiguously against the service-wide set the semantic
        # validator builds (ADR-029 §4/§6).
        schema_ids = [schema.schema_id for db in self.databases for schema in db.schemas]
        table_ids = [table.table_id for db in self.databases for schema in db.schemas for table in schema.tables]
        suffix = f"database service '{self.database_service_id}'; grant object_ref needs unambiguous resolution"
        reject_duplicates(schema_ids, label="schema schema_id", container_label=suffix)
        reject_duplicates(table_ids, label="table table_id", container_label=suffix)

    def _reject_duplicate_setting_names(self) -> None:
        reject_duplicates(
            (setting.name for setting in self.settings),
            label="database setting",
            container_label=f"database service '{self.database_service_id}'",
            duplicate_template="Duplicate {label} '{value}' in {container_label}",
        )

    def _enforce_engine_protocol_pairing(self) -> None:
        # An engine with a canonical wire protocol may not carry
        # ``protocol: other`` (ADR-029 §3). ``${var}`` engines or protocols are
        # deferred to instantiation revalidation.
        if not isinstance(self.engine, DatabaseEngine):
            return
        expected = _ENGINE_TO_PROTOCOLS.get(self.engine)
        if expected is None or is_variable_ref(self.protocol):
            return
        if self.protocol in expected:
            return
        allowed = ", ".join(sorted(p.value for p in expected))
        raise ValueError(f"database engine '{self.engine.value}' requires protocol to be one of: {allowed}")


class RelationshipDatabaseAccess(SDLModel):
    """Typed database-access detail carried by a top-level relationship edge.

    When an application connects to a database, the relationship's ``target``
    resolves to the database (service or logical database) and this block keeps
    the ``role_ref`` (a ``role_id`` in that service) and ``auth_method``
    structurally validated rather than recorded as prose (ADR-029 §4).
    """

    role_ref: str = ""
    auth_method: GovernedVocabulary[DatabaseAuthMethod] = DatabaseAuthMethod.OTHER
    description: str = ""

    @field_validator("auth_method", mode="before")
    @classmethod
    def normalize_auth_method(cls, v: DatabaseAuthMethod | str) -> DatabaseAuthMethod | str:
        return parse_runtime_enum_or_var(v, DatabaseAuthMethod, field_name="auth_method")
