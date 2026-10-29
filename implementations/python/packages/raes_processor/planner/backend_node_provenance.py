"""Shared value-free concern records for backend-introduced portable nodes."""

from raes.explicitness import ExplicitnessClass, ExplicitnessProvenance
from raes_contracts.runtime_state import RealizationProvenanceEntry

from ..compiler.realization_value_domains import nested_authored_value
from ..semantics.realization_concerns import realization_concern_descriptors
from ..semantics.realization_requirement import CompiledRealizationRequirement
from ..semantics.realization_runtime_common import realization_provenance_entry


def backend_node_concern_provenance(
    address: str,
    node_name: str,
    node: object,
    supplied: dict[str, object],
    *,
    governing_scope: str = "/nodes",
) -> list[RealizationProvenanceEntry]:
    """Describe supplied concerns without converting backend choices into author intent."""

    records = []
    for descriptor in realization_concern_descriptors():
        if descriptor.section != "nodes":
            continue
        selected: object = supplied
        for token in descriptor.authored_path:
            selected = selected.get(token) if isinstance(selected, dict) else None
        value = nested_authored_value(node, descriptor.authored_path)
        if selected is None or value is None or not descriptor.includes_authored_value(value):
            continue
        requirement = CompiledRealizationRequirement(
            address=address,
            field_path=f"nodes.{node_name}.{descriptor.authored_suffix}",
            domain="runtime-realization",
            requirement_kind=descriptor.concern_kind,
            explicitness=ExplicitnessClass.OPEN,
            provenance=ExplicitnessProvenance.BACKEND_REALIZED,
            governing_scope=governing_scope,
        )
        records.append(realization_provenance_entry(requirement, False))
    return records
