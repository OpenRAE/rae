"""Typed data contracts for portable standard and private domain profiles."""

from __future__ import annotations

from enum import Enum
from typing import Annotated, Literal

from pydantic import (
    ConfigDict,
    Field,
    SerializationInfo,
    SerializerFunctionWrapHandler,
    model_serializer,
    model_validator,
)
from pydantic import JsonValue as PydanticJsonValue

from ._base import ContractModel, NonEmptyString, PrefixedDigestString
from ._domain_profile_schema_identity import _validate_inert_uri, _validate_schema_vocabularies
from .canonical import JsonValue, canonical_json_digest
from .versions import (
    DOMAIN_PROFILE_ADMISSION_POLICY_SCHEMA_VERSION,
    DOMAIN_PROFILE_BINDING_SCHEMA_VERSION,
    DOMAIN_PROFILE_DEFINITION_SCHEMA_VERSION,
    DOMAIN_PROFILE_RESOLUTION_CONTEXT_SCHEMA_VERSION,
    DOMAIN_PROFILE_SUPPORT_DECLARATION_SCHEMA_VERSION,
)

_DRAFT_2020_12 = "https://json-schema.org/draft/2020-12/schema"
_NAMESPACE_PATTERN = r"^[a-z][a-z0-9]*(?:[.-][a-z0-9]+)*$"
_IDENTIFIER_PATTERN = r"^[a-z][a-z0-9]*(?:[-.][a-z0-9]+)*$"

DomainProfileNamespace = Annotated[str, Field(pattern=_NAMESPACE_PATTERN, max_length=253)]
DomainProfileIdentifier = Annotated[str, Field(pattern=_IDENTIFIER_PATTERN, max_length=128)]
DomainProfileRevision = Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._+-]*$", max_length=128)]


class _FrozenContractModel(ContractModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class DomainProfileIdentityModel(_FrozenContractModel):
    """Authority-qualified logical identity at one exact revision."""

    namespace: DomainProfileNamespace
    authority: NonEmptyString
    profile_id: DomainProfileIdentifier
    revision: DomainProfileRevision

    @model_validator(mode="after")
    def _validate_authority(self) -> DomainProfileIdentityModel:
        _validate_inert_uri(self.authority, field_name="domain profile authority")
        return self


class DomainProfileCoordinateModel(DomainProfileIdentityModel):
    """Exact immutable definition coordinate."""

    definition_digest: PrefixedDigestString


class DomainProfileSemanticContractModel(_FrozenContractModel):
    """Exact identity of pre-installed semantic behavior, never executable data."""

    authority: NonEmptyString
    contract_id: DomainProfileIdentifier
    revision: DomainProfileRevision
    digest: PrefixedDigestString

    @model_validator(mode="after")
    def _validate_authority(self) -> DomainProfileSemanticContractModel:
        _validate_inert_uri(self.authority, field_name="domain profile semantic-contract authority")
        return self


class DomainProfileSchemaModel(_FrozenContractModel):
    """Pinned inert JSON Schema carried by a profile definition."""

    dialect: Literal[_DRAFT_2020_12] = _DRAFT_2020_12
    schema_id: NonEmptyString
    revision: DomainProfileRevision
    schema_digest: PrefixedDigestString
    required_vocabularies: tuple[NonEmptyString, ...] = ()
    schema_document: dict[str, PydanticJsonValue]

    @model_validator(mode="before")
    @classmethod
    def _seal_schema_digest(cls, value: object) -> object:
        if not isinstance(value, dict):
            return value
        payload: dict[str, object] = dict(value)
        document = payload.get("schema_document")
        if payload.get("schema_digest") is None and isinstance(document, dict):
            payload["schema_digest"] = canonical_json_digest(document)
        return payload

    @model_validator(mode="after")
    def _validate_schema_identity(self) -> DomainProfileSchemaModel:
        _validate_inert_uri(self.schema_id, field_name="domain profile schema_id")
        if self.schema_document.get("$schema") != self.dialect:
            raise ValueError("domain profile schema document must declare the selected dialect")
        if self.schema_document.get("$id") != self.schema_id:
            raise ValueError("domain profile schema document id must match schema_id")
        if self.schema_digest != canonical_json_digest(self.schema_document):
            raise ValueError("domain profile schema digest does not match the schema document")
        _validate_schema_vocabularies(self.schema_document, self.required_vocabularies)
        return self


class DomainProfileDefinitionDraftModel(_FrozenContractModel):
    """Unsealed definition payload used only as input to the digest helper."""

    identity: DomainProfileIdentityModel
    profile_schema: DomainProfileSchemaModel
    semantic_contract: DomainProfileSemanticContractModel
    allowed_contexts: tuple[NonEmptyString, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _validate_contexts(self) -> DomainProfileDefinitionDraftModel:
        if self.allowed_contexts != tuple(sorted(set(self.allowed_contexts))):
            raise ValueError("domain profile allowed contexts must be sorted and unique")
        return self


class DomainProfileDefinitionModel(_FrozenContractModel):
    """Immutable standard-or-private definition using the shared contract."""

    schema_version: Literal[DOMAIN_PROFILE_DEFINITION_SCHEMA_VERSION] = DOMAIN_PROFILE_DEFINITION_SCHEMA_VERSION
    coordinate: DomainProfileCoordinateModel
    profile_schema: DomainProfileSchemaModel
    semantic_contract: DomainProfileSemanticContractModel
    allowed_contexts: tuple[NonEmptyString, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _validate_definition(self) -> DomainProfileDefinitionModel:
        if self.allowed_contexts != tuple(sorted(set(self.allowed_contexts))):
            raise ValueError("domain profile allowed contexts must be sorted and unique")
        if self.coordinate.definition_digest != canonical_domain_profile_definition_digest(self):
            raise ValueError("domain profile definition digest does not match its semantic projection")
        return self


class DomainProfileDefinitionProvenanceModel(_FrozenContractModel):
    """Source and trust decision for one locally admitted definition."""

    source_locator: NonEmptyString
    source_digest: PrefixedDigestString
    trust_decision_id: DomainProfileIdentifier

    @model_validator(mode="after")
    def _validate_source(self) -> DomainProfileDefinitionProvenanceModel:
        _validate_inert_uri(self.source_locator, field_name="domain profile definition source_locator")
        return self


class AdmittedDomainProfileDefinitionModel(_FrozenContractModel):
    """A definition paired with its separate local admission provenance."""

    definition: DomainProfileDefinitionModel
    provenance: DomainProfileDefinitionProvenanceModel

    @model_validator(mode="after")
    def _validate_source_digest(self) -> AdmittedDomainProfileDefinitionModel:
        if self.provenance.source_digest != self.definition.coordinate.definition_digest:
            raise ValueError("admitted domain profile source digest must match the definition digest")
        return self


class DomainProfileNamespaceAdmissionModel(_FrozenContractModel):
    """Local trust decision binding a namespace to one authority."""

    namespace: DomainProfileNamespace
    authority: NonEmptyString
    trust_decision_id: DomainProfileIdentifier

    @model_validator(mode="after")
    def _validate_authority(self) -> DomainProfileNamespaceAdmissionModel:
        _validate_inert_uri(self.authority, field_name="domain profile namespace authority")
        return self


class DomainProfileOperation(str, Enum):
    STRUCTURAL_VALIDATION = "structural-validation"
    SEMANTIC_VALIDATION = "semantic-validation"
    REFINEMENT = "refinement"
    COMPARISON = "comparison"
    INTERPRETATION = "interpretation"
    EXECUTION = "execution"
    TYPED_REPORT = "typed-report"


class DomainProfileLimitsModel(_FrozenContractModel):
    max_definitions: int = Field(default=256, ge=1, le=4096)
    max_bindings: int = Field(default=256, ge=1, le=4096)
    max_depth: int = Field(default=16, ge=1, le=64)
    max_nodes: int = Field(default=4096, ge=1, le=65536)
    max_scalar_bytes: int = Field(default=1_048_576, ge=1, le=16_777_216)
    max_references: int = Field(default=128, ge=0, le=4096)
    max_evaluations: int = Field(default=65_536, ge=1, le=1_048_576)
    max_diagnostics: int = Field(default=64, ge=1, le=256)


class DomainProfileSupportDeclarationModel(_FrozenContractModel):
    """Exact operation-specific support; never a handler or plugin record."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        json_schema_extra={
            "allOf": [
                {
                    "if": {
                        "properties": {"operations": {"contains": {"const": "structural-validation"}}},
                        "required": ["operations"],
                    },
                    "then": {
                        "properties": {
                            "supported_schema_dialects": {"minItems": 1},
                            "supported_schema_keywords": {"minItems": 1},
                        },
                        "required": [
                            "supported_schema_dialects",
                            "supported_schema_keywords",
                        ],
                    },
                }
            ]
        },
    )

    schema_version: Literal[DOMAIN_PROFILE_SUPPORT_DECLARATION_SCHEMA_VERSION] = (
        DOMAIN_PROFILE_SUPPORT_DECLARATION_SCHEMA_VERSION
    )
    coordinate: DomainProfileCoordinateModel
    semantic_contract: DomainProfileSemanticContractModel
    operations: tuple[DomainProfileOperation, ...] = Field(min_length=1)
    supported_schema_dialects: tuple[NonEmptyString, ...] = ()
    supported_vocabularies: tuple[NonEmptyString, ...] = ()
    supported_schema_keywords: tuple[NonEmptyString, ...] = ()

    @model_validator(mode="after")
    def _validate_support_sets(self) -> DomainProfileSupportDeclarationModel:
        for label, values in (
            ("operations", self.operations),
            ("supported_schema_dialects", self.supported_schema_dialects),
            ("supported_vocabularies", self.supported_vocabularies),
            ("supported_schema_keywords", self.supported_schema_keywords),
        ):
            if values != tuple(sorted(set(values), key=str)):
                raise ValueError(f"domain profile {label} must be sorted and unique")
        for dialect in self.supported_schema_dialects:
            _validate_inert_uri(dialect, field_name="supported domain profile schema dialect")
        for vocabulary in self.supported_vocabularies:
            _validate_inert_uri(vocabulary, field_name="supported domain profile schema vocabulary")
        if DomainProfileOperation.STRUCTURAL_VALIDATION in self.operations and (
            not self.supported_schema_dialects or not self.supported_schema_keywords
        ):
            raise ValueError("structural domain profile support requires explicit dialects and keywords")
        return self


class DomainProfileResolutionContextModel(_FrozenContractModel):
    """Immutable caller-supplied local definitions, trust, and support."""

    schema_version: Literal[DOMAIN_PROFILE_RESOLUTION_CONTEXT_SCHEMA_VERSION] = (
        DOMAIN_PROFILE_RESOLUTION_CONTEXT_SCHEMA_VERSION
    )
    namespace_admissions: tuple[DomainProfileNamespaceAdmissionModel, ...]
    definitions: tuple[AdmittedDomainProfileDefinitionModel, ...]
    support_declarations: tuple[DomainProfileSupportDeclarationModel, ...] = ()
    limits: DomainProfileLimitsModel = DomainProfileLimitsModel()

    @model_validator(mode="after")
    def _validate_counts(self) -> DomainProfileResolutionContextModel:
        if len(self.definitions) > self.limits.max_definitions:
            raise ValueError("domain profile definition count exceeds the configured limit")
        if len(self.namespace_admissions) > self.limits.max_definitions:
            raise ValueError("domain profile namespace-admission count exceeds the configured limit")
        if len(self.support_declarations) > self.limits.max_definitions:
            raise ValueError("domain profile support-declaration count exceeds the configured limit")
        return self


class DomainProfileResolutionOutcome(str, Enum):
    RESOLVED = "resolved"
    NAMESPACE_UNADMITTED = "namespace-unadmitted"
    NAMESPACE_COLLISION = "namespace-collision"
    DEFINITION_UNAVAILABLE = "definition-unavailable"
    INCOMPATIBLE_REVISION = "incompatible-revision"
    DIGEST_MISMATCH = "digest-mismatch"
    COORDINATE_COLLISION = "coordinate-collision"


class DomainProfileBindingUse(str, Enum):
    CONSTRAINT = "constraint"
    TYPED_REPORT = "typed-report"
    ANNOTATION = "annotation"
    OPAQUE_EXCHANGE = "opaque-exchange"


class DomainProfileBindingBasis(str, Enum):
    AUTHOR_SUPPLIED = "author-supplied"
    BACKEND_SELECTED = "backend-selected"
    OBSERVED = "observed"


class DomainProfileBindingProvenanceModel(_FrozenContractModel):
    """Basis of a bound value, separate from definition trust provenance."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        json_schema_extra={
            "allOf": [
                {
                    "if": {
                        "properties": {"basis": {"const": "observed"}},
                        "required": ["basis"],
                    },
                    "then": {
                        "properties": {"evidence_refs": {"minItems": 1}},
                        "required": ["evidence_refs"],
                    },
                },
                {
                    "if": {
                        "properties": {"basis": {"enum": ["author-supplied", "backend-selected"]}},
                        "required": ["basis"],
                    },
                    "then": {"properties": {"evidence_refs": {"maxItems": 0}}},
                },
            ]
        },
    )

    basis: DomainProfileBindingBasis
    source_ref: NonEmptyString
    evidence_refs: tuple[NonEmptyString, ...] = ()

    @model_validator(mode="after")
    def _validate_evidence_basis(self) -> DomainProfileBindingProvenanceModel:
        if self.evidence_refs != tuple(sorted(set(self.evidence_refs))):
            raise ValueError("domain profile binding evidence refs must be sorted and unique")
        if self.basis is DomainProfileBindingBasis.OBSERVED and not self.evidence_refs:
            raise ValueError("observed domain profile bindings require evidence refs")
        if self.basis is not DomainProfileBindingBasis.OBSERVED and self.evidence_refs:
            raise ValueError("non-observed domain profile bindings must not claim observation evidence")
        return self


class DomainProfileBindingOwnerModel(_FrozenContractModel):
    """Explicit core owner, phase, context, and use for profile data."""

    owning_contract_id: NonEmptyString
    canonical_address: str = Field(pattern=r"^#(?:/(?:[^~/]|~[01])*)*$", max_length=4096)
    concept_family: NonEmptyString
    lifecycle_phase: NonEmptyString
    context: NonEmptyString
    use: DomainProfileBindingUse


class DomainProfileBindingModel(_FrozenContractModel):
    """Typed profile data attached to one explicit host owner."""

    schema_version: Literal[DOMAIN_PROFILE_BINDING_SCHEMA_VERSION] = DOMAIN_PROFILE_BINDING_SCHEMA_VERSION
    binding_id: DomainProfileIdentifier
    coordinate: DomainProfileCoordinateModel
    owner: DomainProfileBindingOwnerModel
    value: PydanticJsonValue
    provenance: DomainProfileBindingProvenanceModel
    children: tuple[DomainProfileBindingModel, ...] = ()

    @model_serializer(mode="wrap")
    def _retain_explicit_null(
        self, handler: SerializerFunctionWrapHandler, info: SerializationInfo
    ) -> dict[str, object]:
        result = handler(self)
        if (
            self.value is None
            and not (info.exclude and "value" in info.exclude)
            and (info.include is None or "value" in info.include)
        ):
            result["value"] = None
        return result

    @model_validator(mode="after")
    def _validate_child_ids(self) -> DomainProfileBindingModel:
        child_ids = [child.binding_id for child in self.children]
        if len(child_ids) != len(set(child_ids)):
            raise ValueError("nested domain profile binding ids must be unique among siblings")
        return self


class DomainProfileAdmissionPolicyModel(_FrozenContractModel):
    """Host-owned use policy; profile data cannot grant opaque carriage."""

    schema_version: Literal[DOMAIN_PROFILE_ADMISSION_POLICY_SCHEMA_VERSION] = (
        DOMAIN_PROFILE_ADMISSION_POLICY_SCHEMA_VERSION
    )
    required_operations: tuple[DomainProfileOperation, ...] = ()
    allow_opaque_exchange: bool = False

    @model_validator(mode="after")
    def _validate_operations(self) -> DomainProfileAdmissionPolicyModel:
        if self.required_operations != tuple(sorted(set(self.required_operations), key=str)):
            raise ValueError("required domain profile operations must be sorted and unique")
        return self


class DomainProfileAdmissionOutcome(str, Enum):
    VALIDATED = "validated"
    OPAQUE_PRESERVED = "opaque-preserved"
    RESOLUTION_REFUSED = "resolution-refused"
    CONTEXT_REFUSED = "context-refused"
    UNSUPPORTED_OPERATION = "unsupported-operation"
    UNSUPPORTED_VOCABULARY = "unsupported-vocabulary"
    UNSUPPORTED_KEYWORD = "unsupported-keyword"
    SCHEMA_INVALID = "schema-invalid"
    VALUE_INVALID = "value-invalid"
    LIMIT_EXCEEDED = "limit-exceeded"


def draft_domain_profile_definition(
    *,
    namespace: str,
    authority: str,
    profile_id: str,
    revision: str,
    schema: DomainProfileSchemaModel,
    semantic_contract: DomainProfileSemanticContractModel,
    allowed_contexts: tuple[str, ...],
) -> DomainProfileDefinitionDraftModel:
    """Build a validated digest-free definition draft."""

    return DomainProfileDefinitionDraftModel(
        identity=DomainProfileIdentityModel(
            namespace=namespace,
            authority=authority,
            profile_id=profile_id,
            revision=revision,
        ),
        profile_schema=schema,
        semantic_contract=semantic_contract,
        allowed_contexts=allowed_contexts,
    )


def _definition_digest_payload(
    value: DomainProfileDefinitionDraftModel | DomainProfileDefinitionModel,
) -> dict[str, JsonValue]:
    identity = value.identity if isinstance(value, DomainProfileDefinitionDraftModel) else value.coordinate
    return {
        "schema_version": DOMAIN_PROFILE_DEFINITION_SCHEMA_VERSION,
        "identity": {
            "namespace": identity.namespace,
            "authority": identity.authority,
            "profile_id": identity.profile_id,
            "revision": identity.revision,
        },
        "profile_schema": value.profile_schema.model_dump(mode="json"),
        "semantic_contract": value.semantic_contract.model_dump(mode="json"),
        "allowed_contexts": list(value.allowed_contexts),
    }


def canonical_domain_profile_definition_digest(
    value: DomainProfileDefinitionDraftModel | DomainProfileDefinitionModel,
) -> str:
    """Digest the definition projection without self-reference."""

    return canonical_json_digest(_definition_digest_payload(value))


def seal_domain_profile_definition(
    draft: DomainProfileDefinitionDraftModel,
) -> DomainProfileDefinitionModel:
    """Bind a validated draft to its immutable RFC 8785 definition digest."""

    digest = canonical_domain_profile_definition_digest(draft)
    return DomainProfileDefinitionModel(
        coordinate=DomainProfileCoordinateModel(
            **draft.identity.model_dump(mode="python"),
            definition_digest=digest,
        ),
        profile_schema=draft.profile_schema,
        semantic_contract=draft.semantic_contract,
        allowed_contexts=draft.allowed_contexts,
    )
