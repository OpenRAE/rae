"""Application-owned secret metadata, versions and value-free consumer selection."""

from typing import Annotated, Literal

from pydantic import ConfigDict, Field, model_validator
from raes_contracts.identifiers import PortableIdentifier
from raes_contracts.runtime_values import reject_duplicates
from raes_contracts.sdl_model import SDLModel
from raes_contracts.variable_references import WholeFieldVariableReference, is_variable_ref

from .runtime_identity_resources import NativeIdentity, ResourceReference

__all__ = [
    "RuntimeServiceSecret",
    "RuntimeSecretReplication",
    "RuntimeSecretReplica",
    "RuntimeSecretVersion",
    "RuntimeSecretConsumer",
    "RuntimeSecretSelector",
    "RuntimeCloudServiceLimit",
]


class RuntimeSecretVersion(SDLModel):
    """Immutable version identity with optional lifecycle and content source."""

    model_config = ConfigDict(
        json_schema_extra={
            "allOf": [
                {
                    "if": {"properties": {"state": {"const": "destroyed"}}, "required": ["state"]},
                    "then": {"properties": {"payload_content_ref": {"const": ""}}},
                }
            ]
        }
    )

    version_id: PortableIdentifier
    native_id: str = ""
    state: Literal["enabled", "disabled", "destroyed"] | WholeFieldVariableReference | None = None
    native_state: str = ""
    payload_content_ref: str = ""
    description: str = ""

    @model_validator(mode="after")
    def validate_destroyed(self) -> RuntimeSecretVersion:
        if self.state == "destroyed" and self.payload_content_ref:
            raise ValueError("A destroyed version cannot have a live payload content reference")
        return self


class RuntimeSecretSelector(SDLModel):
    """Inert provider selector identity, kept separate from its resolution."""

    kind: NativeIdentity
    value: NativeIdentity


class RuntimeSecretConsumer(SDLModel):
    """A consumer's exact version or provider selector; no automatic fallback."""

    model_config = ConfigDict(
        json_schema_extra={
            "oneOf": [
                {
                    "required": ["version_ref"],
                    "properties": {"version_ref": {"minLength": 1}, "selector": {"type": "null"}},
                },
                {
                    "required": ["selector"],
                    "properties": {"selector": {"type": "object"}, "version_ref": {"const": ""}},
                },
            ],
            "allOf": [
                {
                    "if": {
                        "required": ["resolved_version_ref"],
                        "properties": {"resolved_version_ref": {"minLength": 1}},
                    },
                    "then": {
                        "required": ["resolution_basis"],
                        "properties": {"resolution_basis": {"enum": ["declared", "backend-selected", "observed"]}},
                    },
                    "else": {
                        "properties": {
                            "resolution_basis": {"type": "null"},
                            "resolution_evidence_refs": {"maxItems": 0},
                        }
                    },
                },
                {
                    "if": {"required": ["resolution_basis"], "properties": {"resolution_basis": {"const": "observed"}}},
                    "then": {
                        "required": ["resolution_evidence_refs"],
                        "properties": {"resolution_evidence_refs": {"minItems": 1}},
                    },
                },
            ],
        }
    )

    selection_id: PortableIdentifier
    consumer_ref: ResourceReference
    version_ref: str = ""
    selector: RuntimeSecretSelector | None = None
    resolved_version_ref: str = ""
    resolution_basis: Literal["declared", "backend-selected", "observed"] | None = None
    resolution_evidence_refs: list[NativeIdentity] = Field(default_factory=list)
    description: str = ""

    @model_validator(mode="after")
    def validate_selection(self) -> RuntimeSecretConsumer:
        if bool(self.version_ref) == (self.selector is not None):
            raise ValueError("A consumer requires exactly one exact version or provider selector")
        if self.resolved_version_ref:
            if (
                self.version_ref
                and self.resolved_version_ref != self.version_ref
                and not any(is_variable_ref(ref) for ref in (self.version_ref, self.resolved_version_ref))
            ):
                raise ValueError("An exact version selection cannot resolve to another version")
            if self.resolution_basis is None:
                raise ValueError("A resolved version requires its resolution basis")
            if self.resolution_basis == "observed" and not self.resolution_evidence_refs:
                raise ValueError("An observed version resolution requires evidence references")
        elif self.resolution_basis is not None or self.resolution_evidence_refs:
            raise ValueError("Resolution evidence requires a resolved version")
        reject_duplicates(self.resolution_evidence_refs, label="evidence reference", container_label="selection")
        return self


_KmsKeyName = (
    Annotated[
        str,
        Field(pattern=r"^projects/[^/\s]+/locations/[^/\s]+/keyRings/[^/\s]+/cryptoKeys/[^/\s]+$"),
    ]
    | WholeFieldVariableReference
)


def _validate_replication_key(key: str | None, location: str) -> None:
    if key is None or is_variable_ref(key) or is_variable_ref(location):
        return
    if key.split("/")[3] != location:
        raise ValueError("Secret replication encryption key must use the replication location")


class RuntimeSecretReplica(SDLModel):
    """One GCP Secret Manager replica with optional native encryption key identity."""

    location: Annotated[NativeIdentity, Field(pattern=r"^\S+$", json_schema_extra={"pattern": r"^\S+$"})]
    kms_key_name: _KmsKeyName | None = None

    @model_validator(mode="after")
    def validate_key_location(self) -> RuntimeSecretReplica:
        _validate_replication_key(self.kms_key_name, self.location)
        return self


class RuntimeSecretReplication(SDLModel):
    """Provider-qualified replication intent; never inferred from missing locations."""

    model_config = ConfigDict(
        json_schema_extra={
            "allOf": [
                {
                    "if": {"properties": {"mode": {"const": "automatic"}}, "required": ["mode"]},
                    "then": {"properties": {"replicas": {"maxItems": 0}}},
                },
                {
                    "if": {"properties": {"mode": {"const": "user-managed"}}, "required": ["mode"]},
                    "then": {
                        "required": ["replicas"],
                        "properties": {"replicas": {"minItems": 1}, "kms_key_name": {"type": "null"}},
                    },
                },
            ],
            "x-raes-invariants": [
                {
                    "id": "secret-replication-location-agreement",
                    "description": "Replica locations must be unique and encryption keys must match their location; "
                    "automatic encryption requires global. Typed replication excludes legacy placement fields.",
                    "level": "error",
                    "validator": "raes.scenario.Scenario.model_validate",
                    "inputs": [{"contract_id": "sdl-authoring-input-v1", "instance_path": "#"}],
                }
            ],
        }
    )

    provider: Literal["gcp-secret-manager"]
    mode: Literal["automatic", "user-managed"] | WholeFieldVariableReference
    replicas: list[RuntimeSecretReplica] = Field(default_factory=list, max_length=1024)
    kms_key_name: _KmsKeyName | None = None

    @model_validator(mode="after")
    def validate_policy(self) -> RuntimeSecretReplication:
        if self.mode == "automatic":
            if self.replicas:
                raise ValueError("Automatic secret replication cannot declare replicas")
            _validate_replication_key(self.kms_key_name, "global")
        elif self.mode == "user-managed":
            if not self.replicas or self.kms_key_name is not None:
                raise ValueError("User-managed secret replication requires replicas and only per-replica keys")
        reject_duplicates(
            (replica.location for replica in self.replicas if not is_variable_ref(replica.location)),
            label="replica location",
            container_label="secret replication",
        )
        return self


class RuntimeServiceSecret(SDLModel):
    """A service-owned secret resource; payload bytes belong to content."""

    model_config = ConfigDict(
        json_schema_extra={
            "allOf": [
                {
                    "if": {"required": ["replication"], "properties": {"replication": {"type": "object"}}},
                    "then": {
                        "properties": {
                            "location": {"const": ""},
                            "replica_locations": {"maxItems": 0},
                            "encryption_key_ref": {"const": ""},
                        }
                    },
                }
            ]
        }
    )

    secret_id: PortableIdentifier
    replication: RuntimeSecretReplication | None = None
    resource_scope_ref: str = ""
    native_id: str = ""
    versions: list[RuntimeSecretVersion] = Field(default_factory=list)
    consumers: list[RuntimeSecretConsumer] = Field(default_factory=list)
    location: str = ""
    replica_locations: list[NativeIdentity] = Field(default_factory=list)
    encryption_key_ref: str = ""
    reset_owner_ref: str = ""
    deletion_owner_ref: str = ""
    description: str = ""

    @model_validator(mode="after")
    def validate_identities(self) -> RuntimeServiceSecret:
        if self.replication is not None and (self.location or self.replica_locations or self.encryption_key_ref):
            raise ValueError("Typed secret replication cannot combine with legacy location or encryption fields")
        for collection, identity in ((self.versions, "version_id"), (self.consumers, "selection_id")):
            reject_duplicates(
                (getattr(item, identity) for item in collection), label=identity, container_label="secret"
            )
        reject_duplicates(self.replica_locations, label="replica location", container_label="secret")
        return self


class RuntimeCloudServiceLimit(SDLModel):
    """An optional native service limit, with explicit quantity and scope."""

    limit_id: PortableIdentifier
    name: NativeIdentity
    maximum: Annotated[int, Field(strict=True, ge=0)]
    unit: NativeIdentity
    resource_scope_ref: str = ""
    description: str = ""
