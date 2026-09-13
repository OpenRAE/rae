"""Lower source metadata through the shared recursive constraint normalizer."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum

from pydantic_core import to_jsonable_python
from raes.explicitness import ExplicitnessClass, ExplicitnessProvenance, ExplicitnessRecord
from raes.scenario import InstantiatedScenario
from raes_contracts.bounded_domains import EnumDomain
from raes_contracts.canonical import jsonable_fallback
from raes_contracts.realization_structure import (
    RealizationClosure,
    RealizationCollectionProfile,
    RealizationConstraintDocument,
    RealizationDelegatedValue,
    RealizationDomainValue,
    RealizationKnowledgeValue,
    RealizationNormalizationMetadata,
    RealizationOrigin,
    RealizationRelationStatus,
    RealizationScope,
    RealizationStructure,
    RecursiveRealizationStructure,
    normalize_realization_literal,
    realization_constraint_binding,
    validate_realization_value,
)
from raes_contracts.vocabulary import Closure

from ..semantics.realization_concerns import RegisteredRealizationConcern
from ..semantics.realization_specialized_projection import source_occurrences, specialized_collection_identity
from .realization_authority_posture import designated_registered_posture
from .realization_scalar_sets import bind_scalar_set_choices
from .realization_structure import compile_realization_structure
from .realization_value_domains import compiled_architecture_value_domain


class _PendingRecursiveClosure(Exception):
    """The source is retained by RuntimeModel until apparatus resolution."""


def compile_registered_constraint(
    scenario: InstantiatedScenario,
    registered: RegisteredRealizationConcern,
    records: Mapping[str, ExplicitnessRecord],
    *,
    authored_value: object,
    field_pointer: str,
    value_domain: EnumDomain | None = None,
    apparatus_closure: Closure | None = None,
) -> tuple[RealizationStructure | None, RealizationConstraintDocument | None, str | None, bool, bool, bool]:
    descriptor = registered.descriptor
    record = records.get(registered.field_path)
    if (
        descriptor.concern_kind in {"os-family", "os-distribution", "os-version"}
        and value_domain is None
        and record is not None
        and record.classification is ExplicitnessClass.CONSTRAINED
    ):
        # Unbounded public OS variables retain the incumbent configured-row
        # narrowing in the planner. Its finite scalar authority is lossless;
        # there is no nested source constraint to discard here.
        return None, None, None, False, False, False
    if descriptor.concern_kind == "node-architecture" and value_domain is None:
        value_domain = compiled_architecture_value_domain(scenario, field_pointer=field_pointer)
    if descriptor.recursive_projector is None and descriptor.projector is not None:
        structure, error, opened = compile_realization_structure(
            scenario, registered, records, authored_value=authored_value, field_pointer=field_pointer
        )
        return structure, None, None, error, opened, False
    return _compiled_recursive_constraint(
        scenario,
        registered,
        records,
        authored_value=authored_value,
        field_pointer=field_pointer,
        value_domain=value_domain,
        apparatus_closure=apparatus_closure,
    )


def _compiled_recursive_constraint(
    scenario: InstantiatedScenario,
    registered: RegisteredRealizationConcern,
    records: Mapping[str, ExplicitnessRecord],
    *,
    authored_value: object,
    field_pointer: str,
    value_domain: EnumDomain | None,
    apparatus_closure: Closure | None,
) -> tuple[RealizationStructure | None, RealizationConstraintDocument | None, str | None, bool, bool, bool]:
    """Compile one recursive concern, deferring an unresolved apparatus closure."""

    try:
        document, error, opened = compile_recursive_realization_constraint(
            scenario,
            registered,
            records,
            authored_value=authored_value,
            field_pointer=field_pointer,
            value_domain=value_domain,
            apparatus_closure=apparatus_closure,
        )
    except _PendingRecursiveClosure:
        return None, None, None, False, False, True
    binding = (
        realization_constraint_binding(
            document,
            to_jsonable_python(
                registered.descriptor.project(authored_value, recursive=True), fallback=jsonable_fallback
            ),
        )
        if document is not None
        else None
    )
    return None, document, binding, error, opened, False


def _escape(token: str) -> str:
    return token.replace("~", "~0").replace("/", "~1")


def _source_child(source: object, key: str) -> object:
    if isinstance(source, Mapping):
        return source.get(key)
    return getattr(source, key, None)


@dataclass
class _SourceMetadata:
    scenario: InstantiatedScenario
    registered: RegisteredRealizationConcern
    records: Mapping[str, ExplicitnessRecord]
    root_pointer: str
    root_domain: EnumDomain | None
    apparatus_closure: Closure | None = None
    scopes: list[RealizationScope] = field(default_factory=list)
    origins: dict[str, RealizationOrigin] = field(default_factory=dict)
    optional_fields: set[str] = field(default_factory=set)
    leaf_constraints: dict[str, RecursiveRealizationStructure] = field(default_factory=dict)
    collection_profiles: list[RealizationCollectionProfile] = field(default_factory=list)

    @property
    def profile(self) -> str:
        return f"raes/{self.registered.descriptor.concern_kind}/v1"

    def closure(self, pointer: str) -> RealizationClosure:
        posture = designated_registered_posture(
            self.scenario,
            field_pointer=f"{self.root_pointer}{pointer}",
            declaration_name=self.registered.declaration_name,
        )
        if posture.delegated:
            if self.apparatus_closure is None:
                raise _PendingRecursiveClosure
            opened = self.apparatus_closure is Closure.OPEN_WORLD
        else:
            opened = posture.explicitness is ExplicitnessClass.OPEN
        return RealizationClosure(
            posture="open" if opened else "closed",
            universe=self.registered.descriptor.concern_kind,
            profile=self.profile,
        )

    @staticmethod
    def _origin(record: ExplicitnessRecord | None) -> RealizationOrigin:
        """Attribute one projected pointer to the authority that supplied it."""

        if record is None:
            return RealizationOrigin.DEFAULT
        if record.provenance is ExplicitnessProvenance.PROCESSOR_DERIVED:
            return RealizationOrigin.PROCESSOR
        return RealizationOrigin.AUTHOR

    def _collect_mapping(
        self, projected: dict[str, object], source: object, pointer: str, path: str, source_pointer: str
    ) -> None:
        """Walk one projected record, retaining its source pointer alignment."""

        self.scopes.append(RealizationScope(field_pointer=pointer, closure=self.closure(source_pointer)))
        scalar_alias = set(projected) == {"_identity", "value"} and not isinstance(source, (dict, list))
        for key, child in projected.items():
            source_key = key.removesuffix("_present").removesuffix("_commitment")
            if scalar_alias:
                self.collect(child, source, f"{pointer}/{_escape(key)}", path, source_pointer)
                continue
            self.collect(
                child,
                _source_child(source, source_key),
                f"{pointer}/{_escape(key)}",
                f"{path}.{source_key}",
                f"{source_pointer}/{_escape(source_key)}",
            )

    def _collection_identity(self, pointer: str) -> tuple[str, ...]:
        """Name the identity fields one projected collection level carries."""

        if not pointer:
            return self.registered.descriptor.collection_identity_fields
        return specialized_collection_identity(self.registered.descriptor.concern_kind, pointer)

    def _collect_sequence(
        self, projected: list[object], source: object, pointer: str, path: str, source_pointer: str
    ) -> None:
        """Walk one projected collection, preserving every source occurrence."""

        closure = self.closure(source_pointer)
        self.scopes.append(RealizationScope(field_pointer=pointer, closure=closure))
        identity = self._collection_identity(pointer)
        if identity:
            self.collection_profiles.append(
                RealizationCollectionProfile(
                    field_pointer=pointer,
                    collection_kind=self.registered.descriptor.concern_kind,
                    identity_fields=identity,
                    closure=closure,
                )
            )
        if not isinstance(source, list):
            raise ValueError("recursive projection must preserve source occurrences")
        occurrences = source_occurrences(self.registered.descriptor.concern_kind, source_pointer, projected, source)
        if len(occurrences) != len(projected):
            raise ValueError("recursive projection must preserve source occurrences")
        for index, (child, (source_index, source_child)) in enumerate(zip(projected, occurrences, strict=True)):
            self.collect(
                child,
                source_child,
                f"{pointer}/{index}",
                f"{path}[{source_index}]",
                f"{source_pointer}/{source_index}",
            )

    def collect(self, projected: object, source: object, pointer: str, path: str, source_pointer: str = "") -> None:
        record = self.records.get(path)
        self.origins[pointer] = self._origin(record)
        if record is None and pointer:
            self.optional_fields.add(pointer)
        if isinstance(projected, dict):
            self._collect_mapping(projected, source, pointer, path, source_pointer)
        elif isinstance(projected, list):
            self._collect_sequence(projected, source, pointer, path, source_pointer)
        else:
            self.leaf(source, pointer, record, source_pointer)

    def _constrained_domain(self, pointer: str, source_pointer: str) -> EnumDomain:
        """Resolve the publication-safe domain one constrained leaf narrows to."""

        domain = self.root_domain if not pointer else None
        if domain is None and not pointer.endswith(("_present", "_commitment")):
            constraint = next(
                (
                    item
                    for item in self.scenario.instantiation_provenance.capability_constraints
                    if item.field_pointer == f"{self.root_pointer}{source_pointer}"
                ),
                None,
            )
            if constraint is not None:
                domain = EnumDomain(values=list(constraint.allowed_values))
        if domain is None:
            raise ValueError("constrained leaf requires a publication-safe domain")
        return domain

    def leaf(self, source: object, pointer: str, record: ExplicitnessRecord | None, source_pointer: str) -> None:
        classification = None if record is None else record.classification
        if classification is ExplicitnessClass.OPEN:
            # Legacy authoring specificity calls taxonomy sentinels "open".
            # They report unrecovered knowledge, not an enumerated permission
            # to substitute one of the products known to this core release.
            # DNS numeric extensions already mark their discriminator exact.
            if not isinstance(source, Enum) or source.value not in ("unknown", "other"):
                raise ValueError("taxonomy knowledge must retain its typed source")
            self.leaf_constraints[pointer] = RealizationKnowledgeValue(kind="knowledge", state="unknown")
        elif classification is ExplicitnessClass.CONSTRAINED:
            self.leaf_constraints[pointer] = RealizationDomainValue(
                kind="domain", domain=self._constrained_domain(pointer, source_pointer)
            )
        elif record is None and self.closure(source_pointer).posture.value == "open":
            self.leaf_constraints[pointer] = RealizationDelegatedValue(kind="delegated")


def compile_recursive_realization_constraint(
    scenario: InstantiatedScenario,
    registered: RegisteredRealizationConcern,
    records: Mapping[str, ExplicitnessRecord],
    *,
    authored_value: object,
    field_pointer: str,
    value_domain: EnumDomain | None = None,
    apparatus_closure: Closure | None = None,
) -> tuple[RealizationConstraintDocument | None, bool, bool]:
    """Retain source presence/provenance, safe leaves and local collection closure."""

    metadata = _SourceMetadata(scenario, registered, records, field_pointer, value_domain, apparatus_closure)
    try:
        projected = to_jsonable_python(
            registered.descriptor.project(authored_value, recursive=True), fallback=jsonable_fallback
        )
        if validate_realization_value(projected).status is not RealizationRelationStatus.CONFORMANT:
            raise ValueError("recursive projection exceeds the admitted value bounds")
        metadata.collect(projected, authored_value, "", registered.field_path)
        # Scalar literals/domains have no member universe to close. An exact
        # scalar does not create a separate apparatus-default decision.
        closure = metadata.closure("") if isinstance(projected, (dict, list)) else RealizationClosure()
        built = normalize_realization_literal(
            projected,
            semantic_profile=metadata.profile,
            default_closure=closure,
            metadata=RealizationNormalizationMetadata(
                scopes=tuple(metadata.scopes),
                collection_profiles=tuple(metadata.collection_profiles),
                origins=metadata.origins,
                leaf_constraints=metadata.leaf_constraints,
                optional_fields=frozenset(metadata.optional_fields),
            ),
        )
        if built.status is not RealizationRelationStatus.CONFORMANT:
            raise ValueError("recursive normalization could not preserve the source authority")
        document = bind_scalar_set_choices(built.document)
    except (TypeError, ValueError, KeyError):
        return None, True, False
    return document, False, any(scope.closure.posture.value == "open" for scope in metadata.scopes)


__all__ = ["compile_registered_constraint", "compile_recursive_realization_constraint"]
