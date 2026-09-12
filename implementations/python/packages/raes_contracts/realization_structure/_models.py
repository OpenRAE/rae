"""Data contracts for recursive realization authority."""

from __future__ import annotations

from enum import Enum
from typing import Annotated, Literal

from pydantic import (
    ConfigDict,
    Field,
    SerializerFunctionWrapHandler,
    StrictBool,
    StrictFloat,
    StrictInt,
    StrictStr,
    model_serializer,
    model_validator,
)

from .._base import ContractModel
from ..bounded_domains import GovernedReferenceDomain, NullableDomainDescriptor
from ..canonical import canonical_json_digest

JSON_POINTER_PATTERN = r"^(?:/(?:[^~/]|~[01])*)*$"


class StructureModel(ContractModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class RealizationPresence(str, Enum):
    """Whether the addressed member must, may, or must not exist."""

    REQUIRED = "required"
    OPTIONAL = "optional"
    FORBIDDEN = "forbidden"


class RealizationOrigin(str, Enum):
    """Authority origin retained independently of the represented value."""

    AUTHOR = "author"
    DEFAULT = "default"
    PROCESSOR = "processor"
    BACKEND = "backend"
    OBSERVATION = "observation"


class RealizationClosurePosture(str, Enum):
    """Local collection or record posture before lexical inheritance."""

    OPEN = "open"
    CLOSED = "closed"
    UNDEFINED = "undefined"


class RealizationRelationStatus(str, Enum):
    """Diagnostic-bearing result of a recursive semantic relation."""

    CONFORMANT = "conformant"
    NONCONFORMANT = "nonconformant"
    UNRESOLVED = "unresolved"
    INVALID = "invalid"
    UNSUPPORTED = "unsupported"
    LIMIT_EXCEEDED = "limit-exceeded"


class RealizationClosure(StructureModel):
    """One local posture in an explicitly named semantic universe."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        json_schema_extra={
            "allOf": [
                {
                    "if": {
                        "properties": {"posture": {"enum": ["open", "closed"]}},
                        "required": ["posture"],
                    },
                    "then": {"required": ["universe", "profile"]},
                },
                {
                    "if": {"properties": {"posture": {"const": "undefined"}}, "required": ["posture"]},
                    "then": {"properties": {"universe": {"type": "null"}, "profile": {"type": "null"}}},
                },
            ]
        },
    )

    posture: RealizationClosurePosture = RealizationClosurePosture.UNDEFINED
    universe: str | None = Field(default=None, min_length=1, max_length=256)
    profile: str | None = Field(default=None, min_length=1, max_length=256)

    @model_validator(mode="after")
    def _validate_named_posture(self) -> RealizationClosure:
        defined = self.posture is not RealizationClosurePosture.UNDEFINED
        if defined != (self.universe is not None and self.profile is not None):
            raise ValueError("defined closure requires both universe and profile; undefined closure requires neither")
        return self


class RecursiveStructureModel(StructureModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)

    presence: RealizationPresence = RealizationPresence.REQUIRED
    origin: RealizationOrigin = RealizationOrigin.AUTHOR


class RealizationLiteral(RecursiveStructureModel):
    """A type-sensitive exact JSON value, including explicit JSON null."""

    kind: Literal["literal"]
    value: Annotated[
        StrictStr | StrictInt | StrictFloat | StrictBool | None,
        Field(
            json_schema_extra={
                "anyOf": [
                    {"type": "boolean"},
                    {"type": "integer"},
                    {"type": "number"},
                    {"type": "string"},
                    {"type": "null"},
                ]
            }
        ),
    ]

    @model_serializer(mode="wrap")
    def _retain_explicit_null(self, handler: SerializerFunctionWrapHandler) -> dict[str, object]:
        result = handler(self)
        # Excluding absent optional metadata must never erase a literal null.
        result["value"] = self.value
        return result


class RealizationKnowledgeValue(RecursiveStructureModel):
    """A value-free knowledge state that never grants realization authority."""

    kind: Literal["knowledge"]
    state: Literal["unknown", "redacted", "not-applicable"]


class RealizationDelegatedValue(RecursiveStructureModel):
    """A deliberately backend-selected value, distinct from unknown knowledge."""

    kind: Literal["delegated"]


class RealizationDomainValue(RecursiveStructureModel):
    """A scalar restricted by the shared bounded-domain algebra."""

    kind: Literal["domain"]
    domain: NullableDomainDescriptor


class RealizationRecordConstraint(RecursiveStructureModel):
    """A recursive record whose closure is independent of child precision."""

    kind: Literal["recursive-record"]
    fields: dict[str, RecursiveRealizationStructure] = Field(max_length=4096)
    closure: RealizationClosure = RealizationClosure()


class RealizationCollectionMember(StructureModel):
    """One semantic member identity and its recursive constraint."""

    identity: tuple[str | int | bool, ...] = Field(min_length=1, max_length=8)
    constraint: RecursiveRealizationStructure


class RealizationIdentityAlias(StructureModel):
    """One explicit alternate identity mapped to a canonical member identity."""

    identity: tuple[str | int | bool, ...] = Field(min_length=1, max_length=8)
    target: tuple[str | int | bool, ...] = Field(min_length=1, max_length=8)


def identity_key(identity: tuple[object, ...]) -> str:
    """Return the canonical digest for a semantic collection identity."""

    return canonical_json_digest(list(identity))


class RealizationKeyedCollectionConstraint(RecursiveStructureModel):
    """A set-like collection matched by profile-owned semantic identity."""

    kind: Literal["keyed-collection"]
    collection_kind: str = Field(min_length=1, max_length=128)
    identity_fields: tuple[str, ...] = Field(min_length=1, max_length=8)
    members: tuple[RealizationCollectionMember, ...] = Field(max_length=4096)
    aliases: tuple[RealizationIdentityAlias, ...] = Field(default=(), max_length=4096)
    closure: RealizationClosure = RealizationClosure()
    min_items: int = Field(default=0, ge=0, le=4096)
    max_items: int = Field(default=4096, ge=0, le=4096)

    @model_validator(mode="after")
    def _validate_collection(self) -> RealizationKeyedCollectionConstraint:
        if len(self.identity_fields) != len(set(self.identity_fields)):
            raise ValueError("collection identity_fields must be unique")
        if self.min_items > self.max_items:
            raise ValueError("collection min_items must not exceed max_items")
        if any(len(member.identity) != len(self.identity_fields) for member in self.members):
            raise ValueError("collection member identity arity must match identity_fields")
        identities = [identity_key(member.identity) for member in self.members]
        if len(identities) != len(set(identities)):
            raise ValueError("collection members must have unique semantic identities")
        if any(
            len(alias.identity) != len(self.identity_fields) or len(alias.target) != len(self.identity_fields)
            for alias in self.aliases
        ):
            raise ValueError("collection alias identity arity must match identity_fields")
        alias_identities = [identity_key(alias.identity) for alias in self.aliases]
        if len(alias_identities) != len(set(alias_identities)):
            raise ValueError("collection alias identities must be unique")
        if set(alias_identities) & set(identities):
            raise ValueError("collection alias identities must not collide with canonical member identities")
        if any(identity_key(alias.target) not in identities for alias in self.aliases):
            raise ValueError("collection aliases must target declared canonical member identities")
        return self


class RealizationSequenceConstraint(RecursiveStructureModel):
    """An ordered collection; position remains meaningful and duplicates survive."""

    kind: Literal["sequence"]
    items: tuple[RecursiveRealizationStructure, ...] = Field(max_length=4096)
    closure: RealizationClosure = RealizationClosure()
    min_items: int = Field(default=0, ge=0, le=4096)
    max_items: int = Field(default=4096, ge=0, le=4096)

    @model_validator(mode="after")
    def _validate_cardinality(self) -> RealizationSequenceConstraint:
        if self.min_items > self.max_items:
            raise ValueError("sequence min_items must not exceed max_items")
        return self


class RealizationDefinitionReference(RecursiveStructureModel):
    """A bounded acyclic reference to another constraint definition."""

    kind: Literal["definition-reference"]
    target: str = Field(min_length=1, max_length=256)


class RealizationGraphReference(RecursiveStructureModel):
    """A graph identity edge; it is compared, never recursively expanded."""

    kind: Literal["graph-reference"]
    domain: GovernedReferenceDomain
    cycle_policy: Literal["allow", "forbid"]


class RealizationAllOf(RecursiveStructureModel):
    """A canonical conjunction used when constraints cannot be safely folded."""

    kind: Literal["all-of"]
    constraints: tuple[RecursiveRealizationStructure, ...] = Field(min_length=2, max_length=256)


RecursiveRealizationStructure = Annotated[
    RealizationLiteral
    | RealizationKnowledgeValue
    | RealizationDelegatedValue
    | RealizationDomainValue
    | RealizationRecordConstraint
    | RealizationKeyedCollectionConstraint
    | RealizationSequenceConstraint
    | RealizationDefinitionReference
    | RealizationGraphReference
    | RealizationAllOf,
    Field(discriminator="kind"),
]
RealizationRecordConstraint.model_rebuild()
RealizationCollectionMember.model_rebuild()
RealizationKeyedCollectionConstraint.model_rebuild()
RealizationSequenceConstraint.model_rebuild()
RealizationAllOf.model_rebuild()


class RealizationScope(StructureModel):
    """A lexical closure override inherited by otherwise-undefined descendants."""

    field_pointer: str = Field(max_length=4096, pattern=JSON_POINTER_PATTERN)
    closure: RealizationClosure
    origin: RealizationOrigin = RealizationOrigin.AUTHOR

    @model_validator(mode="after")
    def _validate_defined_closure(self) -> RealizationScope:
        if self.closure.posture is RealizationClosurePosture.UNDEFINED:
            raise ValueError("realization scope closure must be open or closed")
        return self


class RealizationCollectionProfile(StructureModel):
    """Pinned shape metadata for one core or selected extension collection."""

    field_pointer: str = Field(max_length=4096, pattern=JSON_POINTER_PATTERN)
    collection_kind: str = Field(min_length=1, max_length=128)
    identity_fields: tuple[str, ...] = Field(min_length=1, max_length=8)
    closure: RealizationClosure

    @model_validator(mode="after")
    def _validate_profile(self) -> RealizationCollectionProfile:
        if len(self.identity_fields) != len(set(self.identity_fields)):
            raise ValueError("collection profile identity_fields must be unique")
        if self.closure.posture is RealizationClosurePosture.UNDEFINED:
            raise ValueError("collection profile closure must be open or closed")
        return self


class RealizationConstraintDocument(StructureModel):
    """Versioned recursive authority independent of backend choice and evidence."""

    contract_id: Literal["recursive-realization-constraint-v1"] = "recursive-realization-constraint-v1"
    semantic_profile: str = Field(min_length=1, max_length=256)
    default_closure: RealizationClosure = RealizationClosure()
    scopes: tuple[RealizationScope, ...] = ()
    root: RecursiveRealizationStructure
    definitions: dict[str, RecursiveRealizationStructure] = Field(default_factory=dict, max_length=256)

    @model_validator(mode="after")
    def _validate_unique_scopes(self) -> RealizationConstraintDocument:
        pointers = [scope.field_pointer for scope in self.scopes]
        if len(pointers) != len(set(pointers)):
            raise ValueError("realization scopes must have unique field_pointer values")
        return self


RealizationConstraintDocument.model_rebuild()


class RealizationConstraintLimits(StructureModel):
    """Portable finite-work limits applied to every recursive relation."""

    max_depth: int = Field(default=32, ge=1, le=1024)
    max_nodes: int = Field(default=4096, ge=1, le=1_000_000)
    max_operations: int = Field(default=16_384, ge=1, le=4_000_000)
    max_members: int = Field(default=4096, ge=1, le=100_000)
    max_identity_checks: int = Field(default=4096, ge=1, le=1_000_000)
    max_reference_hops: int = Field(default=256, ge=1, le=4096)
    max_scalar_bytes: int = Field(default=4096, ge=1, le=8 * 1024 * 1024)
    max_total_scalar_bytes: int = Field(default=1024 * 1024, ge=1, le=64 * 1024 * 1024)
    max_diagnostics: int = Field(default=16, ge=1, le=256)


DEFAULT_REALIZATION_CONSTRAINT_LIMITS = RealizationConstraintLimits()
DEFAULT_UNDEFINED_REALIZATION_CLOSURE = RealizationClosure()
