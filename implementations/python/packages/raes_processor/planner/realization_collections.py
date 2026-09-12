"""Compile enclosing portable node membership through the shared normalizer."""

from dataclasses import replace

from raes.identifiers import QualifiedName
from raes.realization_designation import resolve_realization_designation
from raes_contracts.planning import ChangeAction, ProvisioningPlan, ProvisionOp, RuntimeDomain
from raes_contracts.realization_collections import (
    PORTABLE_NODE_COLLECTION_PROFILE,
    PreparedNodeCollectionAuthority,
    node_collection_members,
)
from raes_contracts.realization_structure import (
    RealizationClosure,
    RealizationCollectionProfile,
    RealizationRelationStatus,
    evaluate_realization_constraint,
    normalize_realization_literal,
    realization_constraint_binding,
)
from raes_contracts.runtime_state import RuntimeSnapshot
from raes_contracts.vocabulary import Closure

from ..models import RuntimeModel


def planned_node_collection(model: RuntimeModel, plan: ProvisioningPlan) -> PreparedNodeCollectionAuthority | None:
    """A child's designation cannot open its containing portable inventory."""

    if model.realization_instance is None:
        return None
    provenance = model.realization_instance.instantiation_provenance
    namespaces = {
        (),
        *(record.namespace for record in provenance.imports),
        *(QualifiedName.parse(name).parts[:-1] for name in model.realization_instance.nodes),
    }
    resolutions = {
        ".".join(namespace): resolve_realization_designation(
            provenance.realization_designations,
            field_pointer="/nodes",
            owner_namespace=namespace,
        )
        for namespace in sorted(namespaces)
    }
    if any(resolution.delegated for resolution in resolutions.values()):
        # Unresolved apparatus policy is not positive additional-resource authority.
        return None
    closure = RealizationClosure(
        posture="closed",
        universe="portable-node",
        profile=PORTABLE_NODE_COLLECTION_PROFILE,
    )
    members = node_collection_members(plan.operations, namespaces=resolutions)
    built = normalize_realization_literal(
        members,
        semantic_profile=PORTABLE_NODE_COLLECTION_PROFILE,
        default_closure=closure,
        collection_profiles=tuple(
            RealizationCollectionProfile(
                field_pointer=f"/{namespace}",
                collection_kind="portable-node",
                identity_fields=("address",),
                closure=RealizationClosure(
                    posture="open" if resolution.closure is Closure.OPEN_WORLD else "closed",
                    universe="portable-node",
                    profile=PORTABLE_NODE_COLLECTION_PROFILE,
                ),
            )
            for namespace, resolution in resolutions.items()
        ),
    )
    if built.status is not RealizationRelationStatus.CONFORMANT:
        raise ValueError("portable node collection exceeds the admitted recursive membership bounds")
    assert built.document is not None
    resolution = resolutions[""]
    return PreparedNodeCollectionAuthority(
        source="authored-scope" if resolution.source == "scope" else "legacy-default",
        governing_scope=resolution.governing_scope,
        constraint_document=built.document,
        constraint_binding=realization_constraint_binding(built.document, members),
    )


def retain_open_collection_nodes(plan: ProvisioningPlan) -> ProvisioningPlan:
    """Absence from authored nodes is not deletion under positive collection authority."""

    authority = plan.preparation.node_collection if plan.preparation is not None else None
    if authority is None:
        return plan
    kept = []
    for operation in plan.operations:
        if operation.action is ChangeAction.DELETE and operation.resource_type in {"node", "network"}:
            proposed = [*plan.operations, replace(operation, action=ChangeAction.UNCHANGED)]
            if evaluate_realization_constraint(
                authority.constraint_document,
                node_collection_members(proposed, namespaces=authority.constraint_document.root.fields),
            ).conformant:
                continue
        kept.append(operation)
    return replace(plan, operations=kept)


def prepared_node_collection_binding_violation(plan: ProvisioningPlan) -> str | None:
    authority = plan.preparation.node_collection if plan.preparation is not None else None
    if authority is not None and authority.constraint_binding != realization_constraint_binding(
        authority.constraint_document,
        node_collection_members(plan.operations, namespaces=authority.constraint_document.root.fields),
    ):
        return "Backend preparation collection authority is not bound to the original membership."
    return None


def prepared_node_collection_violation(
    original: ProvisioningPlan, selected: ProvisioningPlan, previous: RuntimeSnapshot
) -> str | None:
    """Authorize extra operations from the enclosing relation, never its absence."""

    original_addresses = {operation.address for operation in original.operations}
    extra = [operation for operation in selected.operations if operation.address not in original_addresses]
    authority = original.preparation.node_collection if original.preparation is not None else None
    if authority is None:
        return "Backend preparation has no enclosing collection authority." if extra else None
    if any(operation.resource_type not in {"node", "network"} for operation in extra):
        return "Backend preparation exceeded its portable node collection universe."
    invalid_binding = prepared_node_collection_binding_violation(original)
    if invalid_binding:
        return invalid_binding
    submitted = {operation.address for operation in selected.operations}
    retained = [
        ProvisionOp(ChangeAction.UNCHANGED, entry.address, entry.resource_type, entry.payload)
        for entry in previous.entries.values()
        if entry.domain == RuntimeDomain.PROVISIONING and entry.address not in submitted
    ]
    if not evaluate_realization_constraint(
        authority.constraint_document,
        node_collection_members(
            [*selected.operations, *retained], namespaces=authority.constraint_document.root.fields
        ),
    ).conformant:
        return "Backend preparation does not satisfy enclosing node collection authority."
    return None
