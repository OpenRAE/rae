"""Resource ownership and policy descriptions attached to identity authorities.

Provider strings and conditions are inert data. These models never decide access.
"""

from typing import Annotated, Literal

from pydantic import AfterValidator, ConfigDict, Field, model_validator
from raes_contracts.identifiers import PortableIdentifier
from raes_contracts.runtime_values import reject_duplicates, require_non_empty
from raes_contracts.sdl_model import SDLModel
from raes_contracts.variable_references import WholeFieldVariableReference

__all__ = [
    "RuntimeIdentityResourceScope",
    "RuntimeIdentityUse",
    "RuntimeIdentityPolicyCondition",
    "RuntimeIdentityPermissionBinding",
    "RuntimeIdentityResourceAccess",
    "RuntimeIdentityAccessObservation",
]

ResourceReference = Annotated[
    str,
    Field(min_length=1, max_length=2048),
    AfterValidator(lambda value: require_non_empty(value, field_name="reference")),
]
NativeIdentity = Annotated[
    str,
    Field(min_length=1, max_length=2048),
    AfterValidator(lambda value: require_non_empty(value, field_name="native identity")),
]


class RuntimeIdentityResourceScope(SDLModel):
    """A provider-qualified ownership scope, independent of node placement."""

    scope_id: PortableIdentifier
    provider: NativeIdentity
    scope_kind: NativeIdentity
    name: str = ""
    native_id: str = ""
    incarnation_id: str = ""
    parent_ref: str = ""
    description: str = ""


class RuntimeIdentityUse(SDLModel):
    """A workload's identity use, without implying permission or disclosure."""

    use_id: PortableIdentifier
    workload_ref: ResourceReference
    principal_ref: ResourceReference
    mode: Literal["attached", "impersonated", "federated"] | WholeFieldVariableReference
    source_principal_ref: str = ""
    description: str = ""


class RuntimeIdentityPolicyCondition(SDLModel):
    """An uninterpreted provider expression, never executable SDL."""

    language: NativeIdentity
    expression: Annotated[str, Field(min_length=1, max_length=16384)]


class RuntimeIdentityPermissionBinding(SDLModel):
    """A policy's declared principals, actions and targets, not effective access."""

    model_config = ConfigDict(
        json_schema_extra={
            "anyOf": [
                {"required": ["actions"], "properties": {"actions": {"minItems": 1}}},
                {"required": ["role_ref"], "properties": {"role_ref": {"minLength": 1}}},
            ]
        }
    )

    binding_id: PortableIdentifier
    principal_refs: list[ResourceReference] = Field(min_length=1)
    resource_refs: list[ResourceReference] = Field(min_length=1)
    actions: list[NativeIdentity] = Field(default_factory=list)
    role_ref: str = ""
    effect: Literal["allow", "deny"] | WholeFieldVariableReference
    condition: RuntimeIdentityPolicyCondition | None = None
    description: str = ""

    @model_validator(mode="after")
    def validate_binding(self) -> RuntimeIdentityPermissionBinding:
        if not self.actions and not self.role_ref:
            raise ValueError("A permission binding requires actions or an explicit role reference")
        for name in ("principal_refs", "resource_refs", "actions"):
            reject_duplicates(getattr(self, name), label=name, container_label="permission binding")
        return self


class RuntimeIdentityResourceAccess(SDLModel):
    """A resource policy attachment or an explicitly sourced inherited view."""

    model_config = ConfigDict(
        json_schema_extra={
            "if": {"required": ["inherited_from_ref"], "properties": {"inherited_from_ref": {"minLength": 1}}},
            "then": {"properties": {"bindings": {"maxItems": 0}}},
        }
    )

    attachment_ref: ResourceReference
    bindings: list[RuntimeIdentityPermissionBinding] = Field(default_factory=list)
    inherited_from_ref: str = ""

    @model_validator(mode="after")
    def validate_source(self) -> RuntimeIdentityResourceAccess:
        if self.inherited_from_ref and self.bindings:
            raise ValueError("An inherited policy view must reference its source without copying bindings")
        reject_duplicates((item.binding_id for item in self.bindings), label="binding id", container_label="policy")
        return self


class RuntimeIdentityAccessObservation(SDLModel):
    """One reported attempt; evidence admission remains independently governed."""

    model_config = ConfigDict(
        json_schema_extra={
            "allOf": [
                {
                    "if": {"properties": {"outcome": {"enum": ["allowed", "denied"]}}, "required": ["outcome"]},
                    "then": {"required": ["evidence_refs"], "properties": {"evidence_refs": {"minItems": 1}}},
                }
            ]
        }
    )

    observation_id: PortableIdentifier
    principal_ref: ResourceReference
    action: NativeIdentity
    resource_ref: ResourceReference
    outcome: Literal["allowed", "denied", "unknown", "unsupported"]
    evidence_refs: list[NativeIdentity] = Field(default_factory=list)
    context_refs: list[ResourceReference] = Field(default_factory=list)
    description: str = ""

    @model_validator(mode="after")
    def validate_evidence(self) -> RuntimeIdentityAccessObservation:
        if self.outcome in {"allowed", "denied"} and not self.evidence_refs:
            raise ValueError("A decided access observation requires evidence references")
        for name in ("evidence_refs", "context_refs"):
            reject_duplicates(getattr(self, name), label=name, container_label="access observation")
        return self


def reject_identity_resource_duplicates(authority: object) -> None:
    """Keep the existing authority-local namespace, including new child records."""

    entries = [("identity_authority_id", authority.identity_authority_id)]
    for collection, identity in (
        ("services", "service_id"),
        ("subjects", "subject_id"),
        ("policies", "policy_id"),
        ("relationships", "relationship_id"),
        ("resource_scopes", "scope_id"),
        ("identity_uses", "use_id"),
        ("access_observations", "observation_id"),
    ):
        entries.extend((identity, getattr(item, identity)) for item in getattr(authority, collection))
    reject_duplicates(
        (value for _label, value in entries),
        label="stable id",
        container_label="identity authority",
        duplicate_template="Duplicate runtime identity {label} '{value}' in {container_label}",
    )
