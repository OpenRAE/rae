"""Realization-requirement compilation (SEM-218)."""

from collections.abc import Mapping
from dataclasses import replace

from raes.explicitness import ExplicitnessClass, ExplicitnessProvenance, ExplicitnessRecord
from raes.nodes import NodeType
from raes.realization_designation import RealizationConstraintPosture
from raes.runtime_resource_limits import (
    RuntimeProcessResourceLimit,
    process_resource_limit_identity_digest,
)
from raes.scenario import InstantiatedScenario
from raes.semantics.domain_topology import DomainTopologyAnalysis
from raes_contracts.planning import RealizationAuthorityMode, RealizationResolutionSource
from raes_contracts.vocabulary import ProcessResourceLimitScope

from ..semantics.realization import (
    REALIZATION_DOMAIN,
    CompiledRealizationAuthority,
    CompiledRealizationRequirement,
    ProcessResourceLimitDemand,
    RealizationValueConstraint,
    registered_realization_concern_descriptors,
)
from ..semantics.realization_concerns import CONCERN_PAYLOAD_PATH, RegisteredRealizationConcern
from ..semantics.realization_operational_verification import operational_verification_requirement
from .addresses import (
    _account_address,
    _condition_binding_address,
    _content_address,
    _domain_controller_address,
    _event_address,
    _feature_binding_address,
    _generated_artifact_address,
    _inject_address,
    _network_address,
    _node_address,
    _persistent_volume_address,
)
from .realization_authority_posture import designated_registered_posture, explicit_registered_posture
from .realization_concern_binding import realization_requirement_address
from .realization_concern_explicitness import semantic_explicitness_record
from .realization_structure import compile_realization_structure
from .realization_value_domains import compiled_os_value_domain, nested_authored_value


def _append_source_artifact_requirement(
    requirements: list[CompiledRealizationRequirement],
    *,
    source: object,
    field_path: str,
    address: str,
    governing_scope: str,
) -> None:
    artifact_requirement = getattr(source, "artifact_requirement", None)
    if artifact_requirement is None:
        return
    requirements.append(
        CompiledRealizationRequirement(
            field_path=field_path,
            address=address,
            domain=REALIZATION_DOMAIN,
            requirement_kind="source-artifact",
            explicitness=artifact_requirement.explicitness,
            provenance=ExplicitnessProvenance.AUTHOR_DECLARED,
            governing_scope=governing_scope,
            artifact_requirement=artifact_requirement,
        )
    )


def _append_source_artifact_requirements(
    requirements: list[CompiledRealizationRequirement],
    scenario: InstantiatedScenario,
) -> None:
    _append_resource_source_artifact_requirements(requirements, scenario)
    _append_bound_source_artifact_requirements(requirements, scenario)
    _append_action_source_artifact_requirements(requirements, scenario)


def _append_resource_source_artifact_requirements(
    requirements: list[CompiledRealizationRequirement],
    scenario: InstantiatedScenario,
) -> None:
    for name, node in scenario.nodes.items():
        if node.source is not None:
            _append_source_artifact_requirement(
                requirements,
                source=node.source,
                field_path=f"nodes.{name}.source.artifact_requirement",
                address=_network_address(name) if node.type == NodeType.SWITCH else _node_address(name),
                governing_scope=f"#/nodes/{name}/source/artifact_requirement",
            )
    for name, content in scenario.content.items():
        if content.source is not None:
            _append_source_artifact_requirement(
                requirements,
                source=content.source,
                field_path=f"content.{name}.source.artifact_requirement",
                address=_content_address(name),
                governing_scope=f"#/content/{name}/source/artifact_requirement",
            )


def _append_bound_source_artifact_requirements(
    requirements: list[CompiledRealizationRequirement],
    scenario: InstantiatedScenario,
) -> None:
    for node_name, node in scenario.nodes.items():
        _append_feature_source_artifact_requirements(requirements, scenario, node_name, node.features)
        _append_condition_source_artifact_requirements(requirements, scenario, node_name, node.conditions)


def _append_feature_source_artifact_requirements(
    requirements: list[CompiledRealizationRequirement],
    scenario: InstantiatedScenario,
    node_name: str,
    feature_names: list[str],
) -> None:
    for feature_name in feature_names:
        feature = scenario.features.get(feature_name)
        if feature is not None and feature.source is not None:
            _append_source_artifact_requirement(
                requirements,
                source=feature.source,
                field_path=f"features.{feature_name}.source.artifact_requirement",
                address=_feature_binding_address(node_name, feature_name),
                governing_scope=f"#/features/{feature_name}/source/artifact_requirement",
            )


def _append_condition_source_artifact_requirements(
    requirements: list[CompiledRealizationRequirement],
    scenario: InstantiatedScenario,
    node_name: str,
    condition_names: list[str],
) -> None:
    for condition_name in condition_names:
        condition = scenario.conditions.get(condition_name)
        if condition is not None and condition.source is not None:
            _append_source_artifact_requirement(
                requirements,
                source=condition.source,
                field_path=f"conditions.{condition_name}.source.artifact_requirement",
                address=_condition_binding_address(node_name, condition_name),
                governing_scope=f"#/conditions/{condition_name}/source/artifact_requirement",
            )


def _append_action_source_artifact_requirements(
    requirements: list[CompiledRealizationRequirement],
    scenario: InstantiatedScenario,
) -> None:
    for section, declarations, address_factory in (
        ("injects", scenario.injects, _inject_address),
        ("events", scenario.events, _event_address),
    ):
        for name, declaration in declarations.items():
            if declaration.source is not None:
                _append_source_artifact_requirement(
                    requirements,
                    source=declaration.source,
                    field_path=f"{section}.{name}.source.artifact_requirement",
                    address=address_factory(name),
                    governing_scope=f"#/{section}/{name}/source/artifact_requirement",
                )


def _append_domain_topology_requirements(
    requirements: list[CompiledRealizationRequirement],
    domain_analysis: DomainTopologyAnalysis,
) -> None:
    """Append processor-derived requirements for domain-bound resources."""

    domain_carriers = [
        *(
            (_node_address(node_name), binding.domain_name)
            for node_name, binding in domain_analysis.node_bindings.items()
        ),
        *(
            (_account_address(account_name), binding.domain_name)
            for account_name, binding in domain_analysis.account_bindings.items()
        ),
        *(
            (_domain_controller_address(node_name, binding.domain_name), binding.domain_name)
            for node_name, binding in domain_analysis.node_bindings.items()
            if binding.role.value == "controller"
        ),
    ]
    for address, domain_name in domain_carriers:
        requirements.append(
            CompiledRealizationRequirement(
                field_path=f"identity_domains.{domain_name}.topology",
                address=address,
                domain=REALIZATION_DOMAIN,
                requirement_kind="domain-topology",
                explicitness=ExplicitnessClass.EXACT,
                provenance=ExplicitnessProvenance.PROCESSOR_DERIVED,
            )
        )


def _append_stateful_resource_requirements(
    requirements: list[CompiledRealizationRequirement],
    scenario: InstantiatedScenario,
) -> None:
    """Append exact requirements for authored stateful resources."""

    for section_name, resources, address_factory, requirement_kind in (
        (
            "generated_artifacts",
            scenario.generated_artifacts,
            _generated_artifact_address,
            "generated-artifact",
        ),
        (
            "persistent_volumes",
            scenario.persistent_volumes,
            _persistent_volume_address,
            "persistent-volume",
        ),
    ):
        for name in resources:
            requirements.append(
                CompiledRealizationRequirement(
                    field_path=f"{section_name}.{name}",
                    address=address_factory(name),
                    domain=REALIZATION_DOMAIN,
                    requirement_kind=requirement_kind,
                    explicitness=ExplicitnessClass.EXACT,
                    provenance=ExplicitnessProvenance.AUTHOR_DECLARED,
                    governing_scope=f"#/{section_name}/{name}",
                )
            )


def _append_service_materialization_requirements(
    requirements: list[CompiledRealizationRequirement],
    scenario: InstantiatedScenario,
) -> None:
    for name, content in scenario.content.items():
        binding = content.service_materialization
        if binding is None:
            continue
        requirement_kind = (
            "service-search-index-schema-materialization"
            if binding.interface_profile == "service-search-index-schema"
            else "service-content-materialization"
        )
        requirements.append(
            CompiledRealizationRequirement(
                field_path=f"content.{name}.service_materialization",
                address=_content_address(name),
                domain=REALIZATION_DOMAIN,
                requirement_kind=requirement_kind,
                explicitness=ExplicitnessClass.EXACT,
                provenance=ExplicitnessProvenance.AUTHOR_DECLARED,
                governing_scope=f"#/content/{name}/service_materialization",
            )
        )


def _compiled_registered_realization(
    scenario: InstantiatedScenario,
    registered: RegisteredRealizationConcern,
    explicitness: Mapping[str, ExplicitnessRecord],
) -> tuple[CompiledRealizationRequirement | None, CompiledRealizationAuthority | None]:
    descriptor = registered.descriptor
    section_name = descriptor.section
    declaration_name = registered.declaration_name
    encoded_name = declaration_name.replace("~", "~0").replace("/", "~1")
    field_pointer = f"/{section_name}/{encoded_name}/{'/'.join(descriptor.authored_path)}"
    record = semantic_explicitness_record(
        explicitness,
        field_path=registered.field_path,
        excluded_fields=descriptor.explicitness_excluded_fields,
    )
    declarations = getattr(scenario, section_name)
    authored_value = nested_authored_value(
        declarations[declaration_name],
        descriptor.authored_path,
    )
    value_constraints: tuple[RealizationValueConstraint, ...] = ()
    process_resource_limits: tuple[ProcessResourceLimitDemand, ...] = ()
    value_domain = None
    constraint_provenance = None
    if descriptor.concern_kind == "process-resource-limits":
        value_constraints, process_resource_limits = _compiled_process_resource_limits(
            scenario,
            field_pointer=field_pointer,
            authored_value=authored_value,
        )
    elif descriptor.concern_kind in {"os-family", "os-distribution", "os-version"}:
        value_domain, constraint_provenance = compiled_os_value_domain(
            scenario,
            field_pointer=field_pointer,
        )
    if record is not None and not descriptor.includes_authored_value(authored_value):
        return None, None
    posture = (
        explicit_registered_posture(record, field_pointer)
        if record is not None
        else designated_registered_posture(
            scenario,
            field_pointer=field_pointer,
            declaration_name=declaration_name,
        )
    )
    address = realization_requirement_address(
        scenario,
        section_name=section_name,
        declaration_name=declaration_name,
    )
    structure = None
    structure_error = False
    if record is not None:
        structure, structure_error, root_open = compile_realization_structure(
            scenario, registered, explicitness, authored_value=authored_value, field_pointer=field_pointer
        )
        if root_open and structure is not None:
            posture = replace(posture, explicitness=ExplicitnessClass.OPEN, mode=RealizationAuthorityMode.OPEN)
    verification_scope, observation_strength = operational_verification_requirement(
        descriptor.concern_kind, authored_value
    )
    authority = CompiledRealizationAuthority(
        field_path=registered.field_path,
        address=address,
        domain=REALIZATION_DOMAIN,
        requirement_kind=descriptor.concern_kind,
        payload_path=descriptor.payload_path,
        mode=posture.mode,
        source=posture.source,
        provenance=posture.provenance,
        governing_scope=posture.governing_scope,
        delegated=posture.delegated,
        verification_scope=verification_scope,
        required_observation_strength=observation_strength,
    )
    if posture.explicitness is None and not posture.delegated:
        return None, authority
    requirement = CompiledRealizationRequirement(
        field_path=registered.field_path,
        address=address,
        domain=REALIZATION_DOMAIN,
        requirement_kind=descriptor.concern_kind,
        explicitness=posture.explicitness,
        provenance=posture.provenance,
        governing_scope=posture.governing_scope,
        delegated=posture.delegated,
        verification_scope=verification_scope,
        required_observation_strength=observation_strength,
        value_domain=value_domain,
        constraint_provenance=constraint_provenance,
        value_constraints=value_constraints,
        process_resource_limits=process_resource_limits,
        structure=structure,
        structure_error=structure_error,
    )
    return requirement, authority


def _compiled_process_resource_limits(
    scenario: InstantiatedScenario,
    *,
    field_pointer: str,
    authored_value: object,
) -> tuple[tuple[RealizationValueConstraint, ...], tuple[ProcessResourceLimitDemand, ...]]:
    limits = tuple(authored_value) if isinstance(authored_value, list) else ()
    typed_limits = tuple(
        value if isinstance(value, RuntimeProcessResourceLimit) else RuntimeProcessResourceLimit.model_validate(value)
        for value in limits
    )
    constraints: list[RealizationValueConstraint] = []
    prefix = f"{field_pointer}/"
    for constraint in scenario.instantiation_provenance.capability_constraints:
        if not constraint.field_pointer.startswith(prefix):
            continue
        suffix = constraint.field_pointer.removeprefix(prefix).split("/")
        if len(suffix) != 2 or not suffix[0].isdigit() or suffix[1] not in {"soft", "hard"}:
            continue
        index = int(suffix[0])
        if index >= len(typed_limits):
            continue
        constraints.append(
            RealizationValueConstraint(
                identity_digest=process_resource_limit_identity_digest(typed_limits[index]),
                leaf=suffix[1],
                parameter=constraint.parameter,
                allowed_values=constraint.allowed_values,
            )
        )
    demands = tuple(
        ProcessResourceLimitDemand(
            identity_digest=process_resource_limit_identity_digest(value),
            resource=value.resource,
            scope=ProcessResourceLimitScope(value.scope.value),
            soft=value.soft,
            hard=value.hard,
        )
        for value in typed_limits
    )
    return tuple(constraints), demands


def _compile_realization(
    scenario: InstantiatedScenario,
    domain_analysis: DomainTopologyAnalysis,
) -> tuple[tuple[CompiledRealizationRequirement, ...], tuple[CompiledRealizationAuthority, ...]]:
    """Lower explicit leaves before typed fallbacks; omitted stays closed and explicit root delegation stays typed."""

    requirements: list[CompiledRealizationRequirement] = []
    _append_compute_substrate_requirements(requirements, scenario)
    authority: list[CompiledRealizationAuthority] = []
    explicitness = scenario.explicitness
    for registered in registered_realization_concern_descriptors(
        declaration_names={"nodes": scenario.nodes, "content": scenario.content}
    ):
        requirement, authority_entry = _compiled_registered_realization(scenario, registered, explicitness)
        if requirement is not None:
            requirements.append(requirement)
        if authority_entry is not None:
            authority.append(authority_entry)
    _append_domain_topology_requirements(requirements, domain_analysis)
    _append_stateful_resource_requirements(requirements, scenario)
    _append_service_materialization_requirements(requirements, scenario)
    _append_source_artifact_requirements(requirements, scenario)
    existing = {(entry.address, entry.field_path, entry.requirement_kind) for entry in authority}
    authority.extend(
        CompiledRealizationAuthority(
            field_path=requirement.field_path,
            address=requirement.address,
            domain=requirement.domain,
            requirement_kind=requirement.requirement_kind,
            payload_path=CONCERN_PAYLOAD_PATH[requirement.requirement_kind],
            mode=RealizationAuthorityMode.EXACT,
            source=RealizationResolutionSource.PROCESSOR_DERIVED,
            provenance=requirement.provenance,
            governing_scope=requirement.governing_scope,
            verification_scope=requirement.verification_scope,
            required_observation_strength=requirement.required_observation_strength,
        )
        for requirement in requirements
        if requirement.requirement_kind in CONCERN_PAYLOAD_PATH
        if (requirement.address, requirement.field_path, requirement.requirement_kind) not in existing
    )
    return tuple(requirements), tuple(authority)


def _compile_realization_requirements(
    scenario: InstantiatedScenario,
    domain_analysis: DomainTopologyAnalysis,
) -> tuple[CompiledRealizationRequirement, ...]:
    """Compatibility view over the SEM-218 realization demand graph."""

    return _compile_realization(scenario, domain_analysis)[0]


def _append_compute_substrate_requirements(
    requirements: list[CompiledRealizationRequirement],
    scenario: InstantiatedScenario,
) -> None:
    """Lower addressed substrate intent independently of structural node kind."""

    explicitness_by_posture = {
        RealizationConstraintPosture.EXACT: ExplicitnessClass.EXACT,
        RealizationConstraintPosture.CONSTRAINED: ExplicitnessClass.CONSTRAINED,
        RealizationConstraintPosture.OPEN: ExplicitnessClass.OPEN,
    }
    records_by_pointer = {
        record.field_pointer: record
        for record in scenario.instantiation_provenance.realization_constraints
        if record.concern.value == "compute-substrate"
    }
    for node_name, node in scenario.nodes.items():
        if node.type is NodeType.SWITCH:
            continue
        pointer_name = node_name.replace("~", "~0").replace("/", "~1")
        field_pointer = f"/nodes/{pointer_name}"
        record = records_by_pointer.get(field_pointer)
        posture = record.posture if record is not None else RealizationConstraintPosture.OPEN
        requirements.append(
            CompiledRealizationRequirement(
                field_path=f"nodes.{node_name}.realization.compute-substrate",
                address=_node_address(node_name),
                domain=REALIZATION_DOMAIN,
                requirement_kind="compute-substrate",
                explicitness=explicitness_by_posture[posture],
                provenance=ExplicitnessProvenance.AUTHOR_DECLARED,
                governing_scope=record.governing_scope if record is not None else f"#{field_pointer}",
                verification_scope=None,
                required_observation_strength=None,
                value_domain=record.domain if record is not None else None,
                constraint_provenance=record.provenance if record is not None else "author-declared",
            )
        )
