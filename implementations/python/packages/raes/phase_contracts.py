"""Portable records for SDL phase derivation claims and replay context."""

from __future__ import annotations

import re
from collections.abc import Hashable, Iterable
from enum import Enum
from typing import Annotated, Literal

from pydantic import ConfigDict, Field, JsonValue, SerializerFunctionWrapHandler, model_serializer, model_validator
from raes_contracts.canonical import canonical_json_digest

from ._base import SDLModel
from ._identifiers import PortableIdentifier, QualifiedName, require_module_identifier
from .explicitness import ExplicitnessClass, ExplicitnessProvenance
from .realization_designation import RealizationConstraintRecord, RealizationDesignationRecord

_DIGEST_PATTERN = r"^sha256:[a-f0-9]{64}$"
_JSON_POINTER_RE = re.compile(r"^(?:/(?:[^~/]|~[01])*)*$")
JSONScalar = str | int | float | bool


class FrozenPhaseModel(SDLModel):
    """Closed immutable value object used inside portable phase artifacts."""

    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)


class SemanticDigest(FrozenPhaseModel):
    """Profile-labelled digest of one expanded authoring scenario."""

    profile: Literal["raes-sdl-semantic/v1"]
    algorithm: Literal["sha256"]
    value: Annotated[str, Field(pattern=_DIGEST_PATTERN)]


class TrialCoordinateProvenance(FrozenPhaseModel):
    """Logical coordinate copied from one admitted plan entry."""

    condition_id: str | None = None
    block_id: str | None = None
    replicate_id: str | None = None


class AdmittedSelectionProvenance(FrozenPhaseModel):
    """Canonical admitted selection record carried into snapshot identity."""

    variation_point_id: str = Field(min_length=1)
    record_digest: Annotated[str, Field(pattern=_DIGEST_PATTERN)]
    record: dict[str, JsonValue]

    @model_validator(mode="after")
    def _validate_record(self) -> AdmittedSelectionProvenance:
        if self.record.get("variation_point_id") != self.variation_point_id:
            raise ValueError("admitted selection record identity must match variation_point_id")
        if canonical_json_digest(self.record) != self.record_digest:
            raise ValueError("admitted selection record digest must match its canonical payload")
        return self


class AdmittedBindingProvenance(FrozenPhaseModel):
    """Canonical admitted binding record carried into snapshot identity."""

    binding_id: str = Field(min_length=1)
    record_digest: Annotated[str, Field(pattern=_DIGEST_PATTERN)]
    record: dict[str, JsonValue]

    @model_validator(mode="after")
    def _validate_record(self) -> AdmittedBindingProvenance:
        descriptor = self.record.get("descriptor")
        if not isinstance(descriptor, dict) or descriptor.get("binding_id") != self.binding_id:
            raise ValueError("admitted binding record identity must match binding_id")
        if canonical_json_digest(self.record) != self.record_digest:
            raise ValueError("admitted binding record digest must match its canonical payload")
        return self


class TrialInstantiationProvenance(FrozenPhaseModel):
    """Exact sealed plan/entry lineage for one admitted trial instantiation."""

    scenario_family_id: str = Field(min_length=1)
    scenario_family_digest: Annotated[str, Field(pattern=_DIGEST_PATTERN)]
    plan_id: str = Field(min_length=1)
    plan_digest: Annotated[str, Field(pattern=_DIGEST_PATTERN)]
    plan_entry_id: str = Field(min_length=1)
    entry_digest: Annotated[str, Field(pattern=_DIGEST_PATTERN)]
    run_id: str = Field(min_length=1)
    coordinate: TrialCoordinateProvenance
    selections: tuple[AdmittedSelectionProvenance, ...] = ()
    bindings: tuple[AdmittedBindingProvenance, ...] = ()

    @model_validator(mode="after")
    def _validate_record_identities(self) -> TrialInstantiationProvenance:
        selection_ids = [selection.variation_point_id for selection in self.selections]
        if len(selection_ids) != len(set(selection_ids)):
            raise ValueError("trial instantiation selections must have unique variation_point_id values")
        binding_ids = [binding.binding_id for binding in self.bindings]
        if len(binding_ids) != len(set(binding_ids)):
            raise ValueError("trial instantiation bindings must have unique binding_id values")
        return self


class BindingOrigin(str, Enum):
    """Why a concrete parameter value was selected."""

    PROVIDED = "provided"
    DEFAULT = "default"


class ParameterBinding(FrozenPhaseModel):
    """One selected parameter value with an unambiguous qualified identity."""

    parameter: tuple[PortableIdentifier, ...] = Field(min_length=1, max_length=32)
    origin: BindingOrigin
    value: JSONScalar


class ResolvedImportProvenance(FrozenPhaseModel):
    """Portable evidence emitted after one trusted module resolution."""

    namespace: tuple[PortableIdentifier, ...] = Field(min_length=1, max_length=31)
    requested_source: str = Field(min_length=1, max_length=2048)
    requested_version: str = Field(default="*", min_length=1, max_length=256)
    requested_digest: str = Field(default="", max_length=71)
    module_id: str = Field(max_length=129)
    module_version: str = Field(min_length=1, max_length=256)
    resolved_source: str = Field(min_length=1, max_length=4096)
    manifest_digest: str = Field(default="", max_length=71)
    content_digest: str = Field(default="", max_length=71)
    export_hash: str = Field(default="", max_length=71)
    signer_id: str = Field(default="", max_length=256)
    bindings: tuple[ParameterBinding, ...] = ()

    @model_validator(mode="after")
    def _validate_record(self) -> ResolvedImportProvenance:
        QualifiedName.parse(".".join(self.namespace))
        require_module_identifier(self.module_id, field_name="module_id")
        identities = [binding.parameter for binding in self.bindings]
        if len(identities) != len(set(identities)):
            raise ValueError("resolved import bindings must have unique parameter identities")
        if any(len(identity) != 1 for identity in identities):
            raise ValueError("resolved import bindings must use module-local parameter identities")
        for field_name in ("requested_digest", "manifest_digest", "content_digest", "export_hash"):
            digest = getattr(self, field_name)
            if digest and re.fullmatch(_DIGEST_PATTERN, digest) is None:
                raise ValueError(f"{field_name} must be empty or a sha256 digest")
        for field_name in ("requested_source", "resolved_source"):
            source = getattr(self, field_name)
            if _is_absolute_host_source(source):
                raise ValueError(f"{field_name} must not contain an absolute host path")
            if _contains_registry_userinfo(source):
                raise ValueError(f"{field_name} must not contain registry credentials")
        return self


def _is_ordinary_constraint_pointer(parts: list[str]) -> bool:
    return len(parts) == 4 and (parts[1], parts[3]) in {
        ("nodes", "os"),
        ("nodes", "os_distribution"),
        ("nodes", "os_version"),
        ("nodes", "architecture"),
        ("infrastructure", "count"),
    }


def _is_runtime_constraint_pointer(parts: list[str]) -> bool:
    return len(parts) >= 5 and parts[1] == "nodes" and parts[3] == "runtime" and all(parts[4:])


class CapabilityConstraint(FrozenPhaseModel):
    """Pre-instantiation constraint retained for one concrete field."""

    kind: Literal["allowed-values"] = "allowed-values"
    field_pointer: str = Field(max_length=4096)
    parameter: tuple[PortableIdentifier, ...] = Field(min_length=1, max_length=32)
    allowed_values: tuple[JSONScalar, ...] = Field(
        min_length=1,
        json_schema_extra={"uniqueItems": True},
    )

    @model_validator(mode="after")
    def _validate_constraint(self) -> CapabilityConstraint:
        if not self.field_pointer.startswith("/") or _JSON_POINTER_RE.fullmatch(self.field_pointer) is None:
            raise ValueError("field_pointer must be a non-root RFC 6901 JSON Pointer")
        parts = self.field_pointer.split("/")
        if not _is_ordinary_constraint_pointer(parts) and not _is_runtime_constraint_pointer(parts):
            raise ValueError(
                "field_pointer must address /nodes/<id>/(os|os_distribution|os_version|architecture), "
                "/infrastructure/<id>/count, or "
                "a concrete scalar below /nodes/<id>/runtime"
            )
        declaration = parts[2].replace("~1", "/").replace("~0", "~")
        QualifiedName.parse(declaration)
        for index, value in enumerate(self.allowed_values):
            if any(_json_value_equal(value, prior) for prior in self.allowed_values[:index]):
                raise ValueError("allowed_values must not contain duplicates")
        return self


class ExplicitnessProvenanceRecord(FrozenPhaseModel):
    """Serializable SEM-218 classification for one instantiated model path."""

    model_path: str = Field(min_length=1, max_length=4096)
    classification: ExplicitnessClass
    provenance: ExplicitnessProvenance = ExplicitnessProvenance.AUTHOR_DECLARED
    reason: str = Field(default="", max_length=1024)
    parameters: tuple[tuple[PortableIdentifier, ...], ...] = ()

    @model_validator(mode="after")
    def _validate_parameters(self) -> ExplicitnessProvenanceRecord:
        if len(self.parameters) != len(set(self.parameters)):
            raise ValueError("explicitness parameters must be unique")
        return self


class ExpansionProvenance(FrozenPhaseModel):
    """Trusted import-resolution facts attached to an expanded authoring object."""

    imports: tuple[ResolvedImportProvenance, ...] = ()
    capability_constraints: tuple[CapabilityConstraint, ...] = ()
    explicitness: tuple[ExplicitnessProvenanceRecord, ...] = ()
    realization_designations: tuple[RealizationDesignationRecord, ...] = ()
    realization_constraints: tuple[RealizationConstraintRecord, ...] = ()

    @model_validator(mode="after")
    def _validate_unique_identities(self) -> ExpansionProvenance:
        _validate_derivation_collections(
            imports=self.imports,
            constraints=self.capability_constraints,
            explicitness=self.explicitness,
            realization_designations=self.realization_designations,
            realization_constraints=self.realization_constraints,
        )
        return self


class InstantiationProvenance(FrozenPhaseModel):
    """Complete portable derivation context for an instantiated scenario."""

    authored_digest: SemanticDigest
    selected_profile: str | None = Field(default=None, max_length=256)
    bindings: tuple[ParameterBinding, ...] = ()
    imports: tuple[ResolvedImportProvenance, ...] = ()
    capability_constraints: tuple[CapabilityConstraint, ...] = ()
    explicitness: tuple[ExplicitnessProvenanceRecord, ...] = ()
    realization_designations: tuple[RealizationDesignationRecord, ...] = ()
    realization_constraints: tuple[RealizationConstraintRecord, ...] = ()
    trial: TrialInstantiationProvenance | None = Field(default=None, repr=False)

    @model_serializer(mode="wrap")
    def _serialize_optional_trial(self, handler: SerializerFunctionWrapHandler) -> object:
        payload = handler(self)
        if self.trial is None and isinstance(payload, dict):
            payload.pop("trial", None)
        return payload

    @model_validator(mode="after")
    def _validate_unique_identities(self) -> InstantiationProvenance:
        binding_ids = [binding.parameter for binding in self.bindings]
        if len(binding_ids) != len(set(binding_ids)):
            raise ValueError("instantiation bindings must have unique parameter identities")
        if any(len(identity) != 1 for identity in binding_ids):
            raise ValueError("root bindings must use local parameter identities")
        _validate_derivation_collections(
            imports=self.imports,
            constraints=self.capability_constraints,
            explicitness=self.explicitness,
            realization_designations=self.realization_designations,
            realization_constraints=self.realization_constraints,
            root_bindings=self.bindings,
        )
        return self

    @property
    def root_binding_values(self) -> dict[str, JSONScalar]:
        """Selected root bindings; imported bindings remain on import records."""

        return {".".join(binding.parameter): binding.value for binding in self.bindings}


def _validate_derivation_collections(
    *,
    imports: tuple[ResolvedImportProvenance, ...],
    constraints: tuple[CapabilityConstraint, ...],
    explicitness: tuple[ExplicitnessProvenanceRecord, ...],
    realization_designations: tuple[RealizationDesignationRecord, ...],
    realization_constraints: tuple[RealizationConstraintRecord, ...],
    root_bindings: tuple[ParameterBinding, ...] = (),
) -> None:
    _require_unique(
        (record.namespace for record in imports),
        "resolved imports must have unique namespace paths",
    )
    _require_unique(
        (constraint.field_pointer for constraint in constraints),
        "capability constraints must address unique concrete fields",
    )
    _require_unique(
        (record.model_path for record in explicitness),
        "explicitness records must have unique model paths",
    )
    _require_unique(
        ((record.namespace, record.field_pointer) for record in realization_designations),
        "realization designation records must have unique scope identities",
    )
    _require_unique(
        ((record.namespace, record.field_pointer, record.concern) for record in realization_constraints),
        "realization constraint records must have unique concern identities",
    )

    binding_values = _binding_environment(imports, root_bindings)
    _validate_constraint_bindings(constraints, binding_values)
    _validate_explicitness_bindings(explicitness, binding_values)


def _require_unique(values: Iterable[Hashable], message: str) -> None:
    materialized = tuple(values)
    if len(materialized) != len(set(materialized)):
        raise ValueError(message)


def _binding_environment(
    imports: tuple[ResolvedImportProvenance, ...],
    root_bindings: tuple[ParameterBinding, ...],
) -> dict[tuple[str, ...], JSONScalar]:
    binding_values = {binding.parameter: binding.value for binding in root_bindings}
    for record in imports:
        for binding in record.bindings:
            identity = (*record.namespace, *binding.parameter)
            if identity in binding_values:
                raise ValueError("resolved parameter identities must be globally unique")
            binding_values[identity] = binding.value
    return binding_values


def _validate_constraint_bindings(
    constraints: tuple[CapabilityConstraint, ...],
    binding_values: dict[tuple[str, ...], JSONScalar],
) -> None:
    constraints_by_parameter: dict[tuple[str, ...], tuple[JSONScalar, ...]] = {}
    for constraint in constraints:
        if constraint.parameter not in binding_values:
            raise ValueError("capability constraint references an unresolved parameter identity")
        if not any(
            _json_value_equal(binding_values[constraint.parameter], allowed) for allowed in constraint.allowed_values
        ):
            raise ValueError("resolved parameter value does not satisfy its capability constraint")
        prior_values = constraints_by_parameter.setdefault(constraint.parameter, constraint.allowed_values)
        if not _json_domain_equal(prior_values, constraint.allowed_values):
            raise ValueError("one parameter identity must not carry conflicting capability constraints")


def _validate_explicitness_bindings(
    explicitness: tuple[ExplicitnessProvenanceRecord, ...],
    binding_values: dict[tuple[str, ...], JSONScalar],
) -> None:
    for record in explicitness:
        unknown = [identity for identity in record.parameters if identity not in binding_values]
        if unknown:
            raise ValueError("explicitness record references an unresolved parameter identity")


def _json_value_equal(left: JSONScalar, right: JSONScalar) -> bool:
    """Compare scalar JSON values without Python's ``True == 1`` collapse."""

    if isinstance(left, bool) or isinstance(right, bool):
        return isinstance(left, bool) and isinstance(right, bool) and left == right
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return left == right
    return type(left) is type(right) and left == right


def _json_domain_equal(
    left: tuple[JSONScalar, ...],
    right: tuple[JSONScalar, ...],
) -> bool:
    return len(left) == len(right) and all(
        any(_json_value_equal(candidate, other) for other in right) for candidate in left
    )


def _is_absolute_host_source(source: str) -> bool:
    candidate = source
    for prefix in ("local:", "file:"):
        if candidate.startswith(prefix):
            candidate = candidate.removeprefix(prefix)
            break
    return candidate.startswith(("/", "\\", "~/", "~\\")) or re.match(r"^[A-Za-z]:[\\/]", candidate) is not None


def _contains_registry_userinfo(source: str) -> bool:
    if not source.startswith("oci:") and "@sha256:" not in source:
        return False
    candidate = source.removeprefix("oci:")
    if "://" in candidate:
        candidate = candidate.split("://", 1)[1]
    authority = candidate.split("/", 1)[0]
    return "@" in authority


__all__ = [
    "BindingOrigin",
    "CapabilityConstraint",
    "ExpansionProvenance",
    "ExplicitnessProvenanceRecord",
    "InstantiationProvenance",
    "ParameterBinding",
    "ResolvedImportProvenance",
    "RealizationDesignationRecord",
    "RealizationConstraintRecord",
    "SemanticDigest",
]
