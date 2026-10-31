"""Realization-envelope expression contract (ADR-070, envelope-semantics.md).

A realization envelope is a closed, versioned expression that denotes a *set* of
SDL scenario instances. The same expression is used in both directions: an author
describes an acceptable scenario family, and a backend describes the family it can
realize. The membership / subsumption / witness / negative-probe relation over
this contract lives in :mod:`raes.realization_envelope`.

The model is deliberately *closed* (``extra="forbid"`` plus a finite discriminated
union of domain kinds). That closedness is the portability guarantee of
``envelope-semantics.md`` R3 / ADR-070 §3: arbitrary Python predicates, backend
callbacks, external queries, unbounded regex, recursion, and non-linear arithmetic
are simply not representable, which keeps membership and subsumption reducible to
local structural checks and witness generation deterministic.

Issue #100 publishes the expression inside a configuration-bound backend carrier
at ``contracts/schemas/realization-envelope/realization-envelope-v1.json``. The carrier
adds typed material-configuration, transformation, support, and observation
disclosures while the relation continues to operate on the same expression.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from enum import Enum
from typing import Annotated, Any, Literal

from pydantic import Field, GetJsonSchemaHandler, model_validator
from pydantic.json_schema import JsonSchemaValue
from pydantic_core import CoreSchema

from raes_contracts._base import ContractModel, NonEmptyString
from raes_contracts.bounded_domains import (
    BooleanDomain,
    DomainDescriptor,
    DomainScalar,
    EnumDomain,
    ExactDomain,
    GovernedReferenceDomain,
    NumericIntervalDomain,
    NumericType,
    RecordDomain,
    scalar_in_domain,
    scalar_matches_numeric_type,
)
from raes_contracts.contracts.capabilities import (
    OperatingSystemCompatibilityModel,
    ProcessResourceLimitCapabilityModel,
)
from raes_contracts.contracts.realization_plans import RealizationEnvelopeIdentityModel
from raes_contracts.controlled_vocabularies import validate_controlled_vocabulary_value
from raes_contracts.versions import REALIZATION_ENVELOPE_SCHEMA_VERSION
from raes_contracts.vocabulary import Closure, ObservationStrength

from .json_serialization import sorted_json_digest

_ENVELOPE_PATH_RE = re.compile(r"^[^.\[\]]+(?:\.[^.\[\]]+|\[\d+\])*$")


def _require_envelope_path(path: str, *, allow_root: bool) -> None:
    if allow_root and path == "":
        return
    if _ENVELOPE_PATH_RE.fullmatch(path) is None:
        raise ValueError("path must use the complete canonical SDL path grammar")


class EnvelopeScope(str, Enum):
    """Semantic extent where a posture or closure applies (most local first)."""

    FIELD = "field"
    NODE = "node"
    TOPOLOGY = "topology"
    APP = "app"
    SCENARIO = "scenario"


_SCOPE_SPECIFICITY = {
    EnvelopeScope.SCENARIO: 0,
    EnvelopeScope.TOPOLOGY: 1,
    EnvelopeScope.APP: 1,
    EnvelopeScope.NODE: 2,
    EnvelopeScope.FIELD: 3,
}


def scope_specificity(scope: EnvelopeScope) -> int:
    """Return semantic specificity; topology and app are sibling scopes."""

    return _SCOPE_SPECIFICITY[scope]


class Posture(str, Enum):
    """Author/backend intent for a bound value or child scope."""

    OPEN = "open"
    CONSTRAINED = "constrained"
    EXACT = "exact"


class EnvelopeBinding(ContractModel):
    """Binds an SDL path (or governed scope ref) to a domain at a scope.

    ``domain`` names a descriptor in the envelope's ``domains`` map and is required
    for ``constrained`` / ``exact`` posture and forbidden for ``open`` posture (an
    open value is left to a downstream realizer). ``overrideable`` allows a
    more-specific binding to widen a value an enclosing closed scope fixed
    (``envelope-semantics.md`` R2).
    """

    path: NonEmptyString
    scope: EnvelopeScope
    posture: Posture
    domain: str | None = None
    overrideable: bool = False

    @model_validator(mode="after")
    def _validate_posture_domain(self) -> EnvelopeBinding:
        _require_envelope_path(self.path, allow_root=False)
        if self.posture is Posture.OPEN and self.domain is not None:
            raise ValueError("open posture binding must not name a domain")
        if self.posture in (Posture.CONSTRAINED, Posture.EXACT) and not self.domain:
            raise ValueError(f"{self.posture.value} posture binding must name a domain")
        return self


class ClosureOverlay(ContractModel):
    """Declares open-world or closed-world closure at a scope path."""

    path: str = ""
    scope: EnvelopeScope
    closure: Closure

    @model_validator(mode="after")
    def _validate_path(self) -> ClosureOverlay:
        _require_envelope_path(self.path, allow_root=True)
        return self


class WitnessPolicy(ContractModel):
    """Deterministic default-selection policy for witness generation.

    ``selections`` overrides the default choice for named domains (each value must
    be a member of the referenced domain); ``seed`` records the selection basis for
    reproducibility. Neither introduces randomness: witness generation stays a pure
    function of ``(envelope, policy)``.
    """

    seed: str | None = None
    selections: dict[NonEmptyString, DomainScalar] = Field(default_factory=dict)


class RealizationEnvelopeModel(ContractModel):
    """A versioned expression denoting a set of SDL scenario instances."""

    schema_version: Literal["realization-envelope/v1"] = "realization-envelope/v1"
    id: NonEmptyString
    scope: EnvelopeScope
    domains: dict[NonEmptyString, DomainDescriptor] = Field(default_factory=dict)
    bindings: list[EnvelopeBinding] = Field(default_factory=list)
    closure: list[ClosureOverlay] = Field(default_factory=list)
    witness_policy: WitnessPolicy | None = None
    source_ref: str | None = None
    contract_id: str | None = None
    digest: str | None = None

    @model_validator(mode="after")
    def _validate_envelope(self) -> RealizationEnvelopeModel:
        self._validate_domain_references()
        self._validate_acyclic_records()
        self._validate_bindings()
        self._validate_witness_policy()
        return self

    def _validate_domain_references(self) -> None:
        for name, descriptor in self.domains.items():
            if isinstance(descriptor, RecordDomain):
                for field_name, domain_name in descriptor.fields.items():
                    if domain_name not in self.domains:
                        raise ValueError(
                            f"record domain '{name}' field '{field_name}' references unknown domain '{domain_name}'"
                        )

    def _validate_acyclic_records(self) -> None:
        # DFS over record field references; ADR-070 §3 admits only acyclic
        # record/product structure.
        visiting: set[str] = set()
        done: set[str] = set()

        def visit(name: str) -> None:
            if name in done:
                return
            if name in visiting:
                raise ValueError(f"record domain reference cycle through '{name}'")
            descriptor = self.domains.get(name)
            visiting.add(name)
            if isinstance(descriptor, RecordDomain):
                for domain_name in descriptor.fields.values():
                    visit(domain_name)
            visiting.discard(name)
            done.add(name)

        for name in self.domains:
            visit(name)

    def _validate_bindings(self) -> None:
        self._validate_binding_entries()
        self._validate_closure_entries()

    def _validate_binding_entries(self) -> None:
        seen: dict[tuple[str, int], EnvelopeBinding] = {}
        for binding in self.bindings:
            if binding.domain is not None and binding.domain not in self.domains:
                raise ValueError(f"binding path '{binding.path}' references unknown domain '{binding.domain}'")
            if binding.posture is Posture.EXACT and binding.domain is not None:
                if not _is_singleton_domain(self.domains[binding.domain]):
                    raise ValueError(f"exact posture binding path '{binding.path}' requires a singleton domain")
            key = (binding.path, scope_specificity(binding.scope))
            existing = seen.get(key)
            if existing is not None and (
                existing.domain,
                existing.posture,
                existing.overrideable,
            ) != (
                binding.domain,
                binding.posture,
                binding.overrideable,
            ):
                # Equal-specificity, incompatible binding is invalid, not
                # merge-order dependent (envelope-semantics.md R2).
                raise ValueError(
                    f"conflicting equal-specificity bindings for path '{binding.path}' "
                    f"at equivalent scopes '{existing.scope.value}' and '{binding.scope.value}'"
                )
            seen[key] = binding

    def _validate_closure_entries(self) -> None:
        seen_closure: dict[tuple[str, int], tuple[EnvelopeScope, Closure]] = {}
        for overlay in self.closure:
            key = (overlay.path, scope_specificity(overlay.scope))
            existing_closure = seen_closure.get(key)
            if existing_closure is not None and existing_closure[1] is not overlay.closure:
                raise ValueError(
                    f"conflicting equal-specificity closure overlays for path '{overlay.path}' "
                    f"at equivalent scopes '{existing_closure[0].value}' and '{overlay.scope.value}'"
                )
            seen_closure[key] = (overlay.scope, overlay.closure)

    def _validate_witness_policy(self) -> None:
        if self.witness_policy is None:
            return
        for domain_name, value in self.witness_policy.selections.items():
            descriptor = self.domains.get(domain_name)
            if descriptor is None:
                raise ValueError(f"witness policy selects unknown domain '{domain_name}'")
            if not scalar_in_domain(value, descriptor):
                raise ValueError(f"witness policy selection for domain '{domain_name}' is not a domain member")


# Per-domain-kind predicates, dispatched by type to keep the public entry points
# flat (SonarCloud caps returns/complexity per function; type-dispatch chains
# otherwise trip S1142 / cognitive-complexity).
_SINGLETON_DOMAIN_CHECKS: dict[type, Callable[..., bool]] = {
    ExactDomain: lambda descriptor: True,
    EnumDomain: lambda descriptor: len(descriptor.values) == 1,
    BooleanDomain: lambda descriptor: descriptor.value is not None,
    NumericIntervalDomain: lambda descriptor: descriptor.lower == descriptor.upper,
    GovernedReferenceDomain: lambda descriptor: len(descriptor.allowed_refs) == 1,
}


def _is_singleton_domain(descriptor: DomainDescriptor) -> bool:
    check = _SINGLETON_DOMAIN_CHECKS.get(type(descriptor))
    return bool(check(descriptor)) if check is not None else False


# Import after the expression types are defined: the carrier embeds
# RealizationEnvelopeModel and this module preserves the original public API.


_NODE_ARCHITECTURE_VOCABULARY = "provisioner-node-architectures"
_COMPUTE_SUBSTRATE_VOCABULARY = "compute-substrates"

DigestString = Annotated[str, Field(pattern=r"^sha256:[a-f0-9]{64}$")]


class ConcernDisposition(str, Enum):
    """How the selected realizer treats a governed concern."""

    REALIZED = "realized"
    TRANSFORMED = "transformed"
    DESCRIPTOR_ONLY = "descriptor-only"
    UNSUPPORTED = "unsupported"


class RealizationConcern(str, Enum):
    """Closed concern taxonomy shared by backend envelope artifacts."""

    TOPOLOGY = "topology"
    ARCHITECTURE = "architecture"
    IMAGE = "image"
    RESOURCE_ALLOCATION = "resource-allocation"
    NETWORK = "network"
    CONTENT_PLACEMENT = "content-placement"
    ACCOUNT_PLACEMENT = "account-placement"
    FEATURE_BINDING = "feature-binding"
    SERVICE = "service"
    ACL = "acl"
    COMPUTE_SUBSTRATE = "compute-substrate"
    OPERATING_SYSTEM = "operating-system"


class TransformationKind(str, Enum):
    """Portable disclosure of a material realization transformation."""

    BOUNDED_NORMALIZATION = "bounded-normalization"
    DEFAULT_SUBSTITUTION = "default-substitution"
    DESCRIPTOR_SUBSTITUTION = "descriptor-substitution"
    IMAGE_SUBSTITUTION = "image-substitution"
    SERVICE_SYNTHESIS = "service-synthesis"


class IntegerBoundsModel(ContractModel):
    """Closed positive integer interval used by realizer resource claims."""

    minimum: int = Field(ge=1)
    maximum: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def _validate_bounds(self) -> IntegerBoundsModel:
        if self.maximum is not None and self.maximum < self.minimum:
            raise ValueError("maximum must not be less than minimum")
        return self


class RealizerConfigurationModel(ContractModel):
    """Secret-free material configuration identity for one realizer mode."""

    mode: NonEmptyString
    configuration_digest: DigestString
    architecture: NonEmptyString
    image_policy: NonEmptyString
    network_policy: NonEmptyString
    supported_node_types: list[NonEmptyString] = Field(min_length=1)
    supported_os_families: list[NonEmptyString] = Field(min_length=1)
    operating_systems: list[OperatingSystemCompatibilityModel] = Field(default_factory=list)
    supported_content_types: list[NonEmptyString] = Field(default_factory=list)
    supported_account_features: list[NonEmptyString] = Field(default_factory=list)
    supported_domain_profiles: list[NonEmptyString] = Field(default_factory=list)
    process_resource_limits: list[ProcessResourceLimitCapabilityModel] = Field(default_factory=list)
    supports_acls: bool = False
    memory_mib: IntegerBoundsModel
    vcpus: IntegerBoundsModel

    @model_validator(mode="after")
    def _validate_unique_terms(self) -> RealizerConfigurationModel:
        for field_name in (
            "supported_node_types",
            "supported_os_families",
            "supported_content_types",
            "supported_account_features",
            "supported_domain_profiles",
        ):
            values = getattr(self, field_name)
            if len(values) != len(set(values)):
                raise ValueError(f"{field_name} must not contain duplicates")
        resources = [capability.resource for capability in self.process_resource_limits]
        if len(resources) != len(set(resources)):
            raise ValueError("process_resource_limits must not contain duplicate resource terms")
        os_keys = [(entry.family, entry.distribution) for entry in self.operating_systems]
        if len(os_keys) != len(set(os_keys)):
            raise ValueError("operating_systems must not contain duplicate family/distribution rows")
        undeclared_families = {
            entry.family for entry in self.operating_systems if entry.family not in self.supported_os_families
        }
        if undeclared_families:
            raise ValueError(
                "operating_systems families must be present in supported_os_families: "
                + ", ".join(sorted(undeclared_families))
            )
        # The configuration-bound realized target architecture is a governed
        # canonical CPU-architecture term (issue #674), so a backend's declared
        # realization architecture stays in the same portable vocabulary as the
        # authored SDL requirement it must agree with.
        try:
            validate_controlled_vocabulary_value(_NODE_ARCHITECTURE_VOCABULARY, self.architecture)
        except ValueError as exc:
            # The vocabulary error text repeats the rejected term; keep it out of the message (E7).
            raise ValueError("architecture must be a governed node CPU architecture term") from exc
        return self

    @classmethod
    def __get_pydantic_json_schema__(
        cls,
        core_schema: CoreSchema,
        handler: GetJsonSchemaHandler,
    ) -> JsonSchemaValue:
        json_schema = handler.resolve_ref_schema(handler(core_schema))
        properties = json_schema.get("properties", {})
        for field_name in (
            "supported_node_types",
            "supported_os_families",
            "supported_content_types",
            "supported_account_features",
            "supported_domain_profiles",
        ):
            properties[field_name]["uniqueItems"] = True
        properties["process_resource_limits"]["uniqueItems"] = True
        properties["operating_systems"]["uniqueItems"] = True
        return json_schema


def _validate_transformation_coupling(model: RealizationConcernDisclosureModel) -> None:
    if len(model.transformations) != len(set(model.transformations)):
        raise ValueError("transformations must not contain duplicates")
    if model.disposition is ConcernDisposition.TRANSFORMED and not model.transformations:
        raise ValueError("transformed disposition requires transformations")
    if model.disposition is not ConcernDisposition.TRANSFORMED and model.transformations:
        raise ValueError("transformations require transformed disposition")


def _validate_observation_coupling(model: RealizationConcernDisclosureModel) -> None:
    if model.disposition is ConcernDisposition.UNSUPPORTED:
        if model.observation_strength is not ObservationStrength.NONE or model.mechanism is not None:
            raise ValueError("unsupported disposition cannot claim observation or mechanism")
    elif model.observation_strength is ObservationStrength.NONE or model.mechanism is None:
        raise ValueError("supported dispositions require observation and mechanism")


class RealizationConcernDisclosureModel(ContractModel):
    """Typed support, transformation, and observation claim for one concern."""

    concern: RealizationConcern
    disposition: ConcernDisposition
    observation_strength: ObservationStrength
    mechanism: NonEmptyString | None = None
    transformations: list[TransformationKind] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_disposition(self) -> RealizationConcernDisclosureModel:
        _validate_transformation_coupling(self)
        _validate_observation_coupling(self)
        if self.concern is RealizationConcern.COMPUTE_SUBSTRATE and self.mechanism is not None:
            try:
                validate_controlled_vocabulary_value(_COMPUTE_SUBSTRATE_VOCABULARY, self.mechanism)
            except ValueError as exc:
                # The vocabulary error text repeats the rejected term; keep it out of the message (E7).
                raise ValueError("compute-substrate mechanism must be a governed term") from exc
        return self

    @classmethod
    def __get_pydantic_json_schema__(
        cls,
        core_schema: CoreSchema,
        handler: GetJsonSchemaHandler,
    ) -> JsonSchemaValue:
        json_schema = handler.resolve_ref_schema(handler(core_schema))
        json_schema["properties"]["transformations"]["uniqueItems"] = True
        json_schema.setdefault("allOf", []).extend(
            [
                {
                    "if": {"properties": {"disposition": {"const": "transformed"}}},
                    "then": {"properties": {"transformations": {"minItems": 1}}},
                    "else": {"properties": {"transformations": {"maxItems": 0}}},
                },
                {
                    "if": {"properties": {"disposition": {"const": "unsupported"}}},
                    "then": {
                        "properties": {
                            "observation_strength": {"const": "none"},
                            "mechanism": {"type": "null"},
                        }
                    },
                    "else": {
                        "properties": {
                            "observation_strength": {"not": {"const": "none"}},
                            "mechanism": {"type": "string", "minLength": 1},
                        }
                    },
                },
            ]
        )
        return json_schema


def _realizer_configuration_payload(
    payload: Mapping[str, Any] | RealizerConfigurationModel,
) -> dict[str, Any]:
    model = (
        payload
        if isinstance(payload, RealizerConfigurationModel)
        else RealizerConfigurationModel.model_validate(payload)
    )
    material = model.model_dump(mode="json")
    if not material["process_resource_limits"]:
        material.pop("process_resource_limits")
    return material


def realizer_configuration_digest(payload: Mapping[str, Any] | RealizerConfigurationModel) -> str:
    """Digest the closed, secret-free material configuration projection."""

    material = _realizer_configuration_payload(payload)
    material.pop("configuration_digest", None)
    return sorted_json_digest(material)


def realization_envelope_digest(payload: Mapping[str, Any] | ContractModel) -> str:
    """Return the canonical digest of a published envelope, excluding its self-digest."""

    if isinstance(payload, BackendRealizationEnvelopeModel):
        material = payload.model_dump(mode="json")
        material["configuration"] = _realizer_configuration_payload(payload.configuration)
    elif isinstance(payload, Mapping) and {"id", "expression", "configuration", "concerns"} <= payload.keys():
        material = {
            "schema_version": payload.get("schema_version", "realization-envelope/v1"),
            "contract_id": payload.get("contract_id", "realization-envelope-v1"),
            "id": payload["id"],
            "expression": RealizationEnvelopeModel.model_validate(payload["expression"]).model_dump(mode="json"),
            "configuration": _realizer_configuration_payload(payload["configuration"]),
            "concerns": [
                RealizationConcernDisclosureModel.model_validate(claim).model_dump(mode="json")
                for claim in payload["concerns"]
            ],
        }
    else:
        material = payload.model_dump(mode="json") if isinstance(payload, ContractModel) else dict(payload)
    material.pop("digest", None)
    return sorted_json_digest(material)


class BackendRealizationEnvelopeModel(ContractModel):
    """Published backend carrier: shared set expression plus truthful realization claims."""

    schema_version: Literal["realization-envelope/v1"] = "realization-envelope/v1"
    contract_id: Literal["realization-envelope-v1"] = "realization-envelope-v1"
    id: NonEmptyString
    expression: RealizationEnvelopeModel
    configuration: RealizerConfigurationModel
    concerns: list[RealizationConcernDisclosureModel] = Field(min_length=1)
    digest: DigestString

    @model_validator(mode="after")
    def _validate_carrier(self) -> BackendRealizationEnvelopeModel:
        concern_values = [claim.concern for claim in self.concerns]
        if len(concern_values) != len(set(concern_values)):
            raise ValueError("concerns must not contain duplicate concern values")
        missing_concerns = set(RealizationConcern) - set(concern_values)
        if missing_concerns:
            missing = ", ".join(sorted(concern.value for concern in missing_concerns))
            raise ValueError(f"concerns must disclose every governed concern; missing: {missing}")
        operating_system_claim = next(
            claim for claim in self.concerns if claim.concern is RealizationConcern.OPERATING_SYSTEM
        )
        if self.configuration.operating_systems:
            if (
                operating_system_claim.disposition is not ConcernDisposition.REALIZED
                or operating_system_claim.observation_strength is not ObservationStrength.GUEST_OBSERVED
            ):
                raise ValueError(
                    "operating_systems capability rows require a realized guest-observed operating-system concern"
                )
        elif operating_system_claim.disposition is not ConcernDisposition.UNSUPPORTED:
            raise ValueError("operating-system concern support requires coupled operating_systems capability rows")
        if self.configuration.configuration_digest != realizer_configuration_digest(self.configuration):
            raise ValueError("realizer configuration digest does not match canonical content")
        expected = realization_envelope_digest(self)
        if self.digest != expected:
            raise ValueError("realization envelope digest does not match canonical content")
        return self

    @property
    def identity(self) -> RealizationEnvelopeIdentityModel:
        return RealizationEnvelopeIdentityModel(
            contract_id=self.contract_id,
            envelope_id=self.id,
            schema_version=self.schema_version,
            digest=self.digest,
            configuration_digest=self.configuration.configuration_digest,
        )

    @classmethod
    def __get_pydantic_json_schema__(
        cls,
        core_schema: CoreSchema,
        handler: GetJsonSchemaHandler,
    ) -> JsonSchemaValue:
        json_schema = handler.resolve_ref_schema(handler(core_schema))
        concerns = json_schema["properties"]["concerns"]
        concern_count = len(RealizationConcern)
        concerns["minItems"] = concern_count
        concerns["maxItems"] = concern_count
        concerns["allOf"] = [
            {
                "contains": {
                    "type": "object",
                    "required": ["concern"],
                    "properties": {"concern": {"const": concern.value}},
                },
                "minContains": 1,
                "maxContains": 1,
            }
            for concern in RealizationConcern
        ]
        json_schema["x-raes-invariants"] = [
            {
                "id": "realization-envelope-canonical-semantics-valid",
                "description": (
                    "Configuration bounds, expression references, canonical configuration and envelope digests, "
                    "and all cross-field realization disclosure semantics must validate together."
                ),
                "level": "error",
                "validator": "raes_contracts.realization_envelope.validate_backend_realization_envelope",
                "inputs": [{"contract_id": "realization-envelope-v1", "instance_path": "#"}],
            }
        ]
        return json_schema


def validate_backend_realization_envelope(payload: Mapping[str, Any]) -> BackendRealizationEnvelopeModel:
    """Apply the semantic-invariant validator named by the published schema."""

    return BackendRealizationEnvelopeModel.model_validate(payload)


__all__ = [
    "BackendRealizationEnvelopeModel",
    "BooleanDomain",
    "Closure",
    "ClosureOverlay",
    "ConcernDisposition",
    "DomainDescriptor",
    "EnumDomain",
    "EnvelopeBinding",
    "EnvelopeScope",
    "ExactDomain",
    "GovernedReferenceDomain",
    "IntegerBoundsModel",
    "NumericIntervalDomain",
    "NumericType",
    "ObservationStrength",
    "Posture",
    "REALIZATION_ENVELOPE_SCHEMA_VERSION",
    "RealizationConcern",
    "RealizationConcernDisclosureModel",
    "RealizationEnvelopeIdentityModel",
    "RealizationEnvelopeModel",
    "RealizerConfigurationModel",
    "RecordDomain",
    "TransformationKind",
    "WitnessPolicy",
    "realization_envelope_digest",
    "realizer_configuration_digest",
    "scalar_in_domain",
    "scalar_matches_numeric_type",
    "scope_specificity",
    "validate_backend_realization_envelope",
]
