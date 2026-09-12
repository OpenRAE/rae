"""Lower optional authored software profiles into the existing plan host.

Author-supplied definitions are exchange data. The target's independent pinned
resolution context and installed semantic validator still admit every use.
"""

from collections.abc import Iterator
from dataclasses import dataclass

from raes.explicitness import ExplicitnessClass
from raes.runtime_software_profiles import RuntimeSoftwareRefinement
from raes.scenario import InstantiatedScenario
from raes_contracts.canonical import canonical_json_digest
from raes_contracts.domain_profiles import (
    AdmittedDomainProfileDefinitionModel,
    DomainProfileBindingModel,
    DomainProfileBindingOwnerModel,
    DomainProfileBindingProvenanceModel,
    DomainProfileDefinitionProvenanceModel,
)
from raes_contracts.realization_profiles import PLAN_PROFILE_CONTRACT, PlanProfileAuthority, ProfileBindingConstraint
from raes_contracts.realization_structure import (
    RealizationClosure,
    RealizationNormalizationMetadata,
    RealizationScope,
    normalize_realization_literal,
    realization_constraint_binding,
)

from .addresses import _node_address
from .realization_authority_posture import designated_registered_posture

_CONTEXTS = {
    "acquisition": "artifact-acquisition",
    "version-correspondence": "software-version-correspondence",
    "repository-state": "software-repository-state",
    "repository-trust": "software-repository-trust",
}


@dataclass(frozen=True)
class _Attachment:
    node: str
    identity: str
    pointer: str
    refinement: RuntimeSoftwareRefinement


def _software_refinements(scenario: InstantiatedScenario) -> Iterator[_Attachment]:
    for node_name, node in scenario.nodes.items():
        if node.runtime is None:
            continue
        groups = [("software_components", "component_id", node.runtime.software_components)]
        state = node.runtime.repository_state
        if state is not None:
            groups.extend(
                (
                    ("repository_state/repositories", "repository_id", state.repositories),
                    ("repository_state/trust_bindings", "trust_id", state.trust_bindings),
                )
            )
        for path, id_field, items in groups:
            for index, item in enumerate(items):
                for refinement_index, refinement in enumerate(item.refinements):
                    yield _Attachment(
                        node_name,
                        f"{id_field}:{getattr(item, id_field)}",
                        f"/nodes/{_escape(node_name)}/runtime/{path}/{index}/refinements/{refinement_index}/profile_value",
                        refinement,
                    )


def _escape(value: str) -> str:
    return value.replace("~", "~0").replace("/", "~1")


def _value_metadata(scenario: InstantiatedScenario, attachment: _Attachment) -> RealizationNormalizationMetadata:
    scopes = []
    pending = [("", attachment.refinement.profile_value)]
    while pending:
        pointer, value = pending.pop()
        if not isinstance(value, (dict, list)):
            continue
        posture = designated_registered_posture(
            scenario, field_pointer=attachment.pointer + pointer, declaration_name=attachment.node
        )
        if posture.delegated:
            raise ValueError("Software profile values require a resolved enclosing realization posture")
        scopes.append(
            RealizationScope(
                field_pointer=pointer,
                closure=RealizationClosure(
                    posture="open" if posture.explicitness is ExplicitnessClass.OPEN else "closed",
                    universe="profile-value",
                    profile=attachment.refinement.definition.coordinate.definition_digest,
                ),
            )
        )
        children = value.items() if isinstance(value, dict) else enumerate(value) if isinstance(value, list) else ()
        pending.extend((f"{pointer}/{_escape(str(key))}", child) for key, child in children)
    return RealizationNormalizationMetadata(scopes=tuple(scopes))


def compile_software_profiles(
    scenario: InstantiatedScenario, existing: PlanProfileAuthority | None
) -> PlanProfileAuthority | None:
    """Conjoin all authored attachments; reject duplicate or conflicting identity."""

    definitions = (
        {}
        if existing is None
        else {item.definition.coordinate.definition_digest: item for item in existing.definitions}
    )
    bindings = [] if existing is None else list(existing.bindings)
    constraints = [] if existing is None else list(existing.constraints)
    for attachment in _software_refinements(scenario):
        node_name, component_id, refinement = attachment.node, attachment.identity, attachment.refinement
        definition = refinement.definition
        digest = definition.coordinate.definition_digest
        definitions.setdefault(
            digest,
            AdmittedDomainProfileDefinitionModel(
                definition=definition,
                provenance=DomainProfileDefinitionProvenanceModel(
                    source_locator="urn:raes:authored-software-refinement",
                    source_digest=digest,
                    trust_decision_id="author-constraint-only",
                ),
            ),
        )
        binding_id = (
            "software-" + canonical_json_digest([node_name, component_id, refinement.refinement_id]).split(":")[1]
        )
        binding = DomainProfileBindingModel(
            binding_id=binding_id,
            coordinate=definition.coordinate,
            owner=DomainProfileBindingOwnerModel(
                owning_contract_id=PLAN_PROFILE_CONTRACT,
                canonical_address=f"#/resources/{_node_address(node_name)}",
                concept_family="resource-realization",
                lifecycle_phase="planning",
                context=_CONTEXTS[refinement.purpose],
                use="constraint",
            ),
            value=refinement.profile_value,
            provenance=DomainProfileBindingProvenanceModel(
                basis="author-supplied",
                source_ref=f"software:{component_id}/{refinement.refinement_id}",
            ),
        )
        built = normalize_realization_literal(
            binding.value,
            semantic_profile=digest,
            metadata=_value_metadata(scenario, attachment),
        )
        if built.status.value != "conformant":
            raise ValueError("Software profile constraint exceeds the supported recursive fragment")
        bindings.append(binding)
        constraints.append(
            ProfileBindingConstraint(
                binding_path=(binding_id,),
                document=built.document,
                source_binding=realization_constraint_binding(built.document, binding.value),
            )
        )
    if not bindings:
        return None
    if len({binding.binding_id for binding in bindings}) != len(bindings):
        raise ValueError("Software profile binding identities conflict")
    return PlanProfileAuthority(
        definitions=tuple(definitions.values()), bindings=tuple(bindings), constraints=tuple(constraints)
    )
