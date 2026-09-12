"""Compile the addressed substrate concern independently of node-kind authority."""

from raes.explicitness import ExplicitnessClass, ExplicitnessProvenance
from raes.nodes import NodeType
from raes.realization_designation import RealizationConstraintPosture
from raes.scenario import InstantiatedScenario

from ..semantics.realization import REALIZATION_DOMAIN, CompiledRealizationRequirement
from .addresses import _node_address


def append_compute_substrate_requirements(
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
