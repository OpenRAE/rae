"""Derive descendant state from SDL under the original enclosing authority."""

from dataclasses import replace

from raes import MaterializedScenario, admit_instantiated_scenario, parse_sdl
from raes.explicitness import ExplicitnessClass, ExplicitnessProvenance
from raes_backend_protocols.manifest import backend_manifest_v2_model
from raes_contracts.augmentation_preparation import AugmentationEffect, AugmentationPreparation
from raes_contracts.json_ingress import parse_bounded_json_object
from raes_contracts.materialization import MATERIALIZATION_MAX_BYTES, MaterializationSubmission
from raes_contracts.materialization_inventory import RUNTIME_DESCENDANTS_CONTRACT, InventoryInvariant
from raes_contracts.planning import ChangeAction, RuntimeDomain, require_plan_operation_identity
from raes_contracts.realization_collections import node_collection_members
from raes_contracts.realization_structure import evaluate_realization_constraint
from raes_contracts.runtime_state import SnapshotEntry

from ..compiler import compile_runtime_model, materialization_differences, validate_materialization_origins
from ..compiler.realization_value_domains import nested_authored_value
from ..semantics.realization_concerns import realization_concern_descriptors
from ..semantics.realization_requirement import CompiledRealizationRequirement
from ..semantics.realization_runtime_common import realization_provenance_entry
from .augmentation_admission import admit_augmentation_preparation
from .materialization_admission import _inventory_resources, _validate_binding, admit_materialization_submission
from .materialization_lineage import admitted_inventory_predecessor, validate_inventory_lineage
from .prepared_node_admission import validate_portable_node_inventory
from .prepared_node_projection import prepared_node_payload_projection
from .realization_collections import planned_node_collection


def admit_runtime_inventory(submission, request, manifest, previous, accepted, archive):
    """Return admitted SDL and runtime-owned projections; never mint execution plans."""
    if RUNTIME_DESCENDANTS_CONTRACT not in manifest.supported_contract_versions:
        raise ValueError("runtime descendant reporting was not negotiated")
    submission = MaterializationSubmission.model_validate(submission.model_dump(mode="json"))
    materialized = parse_sdl(submission.sdl)
    if not isinstance(materialized, MaterializedScenario):
        raise ValueError("runtime inventory requires descriptive SDL")
    report = materialized.materialization_provenance.inventory
    source = request.materialization_source
    if (
        report is None
        or not request.inventory_attempt_id
        or source.target_scope is None
        or (report.attempt_id, report.run_id, report.source_digest, report.target_scope)
        != (request.inventory_attempt_id, source.run_id, source.instantiated_digest, source.target_scope)
    ):
        raise ValueError(InventoryInvariant.BINDING)
    try:
        _validate_binding(materialized, source, request, manifest, previous)
    except ValueError:
        raise ValueError(InventoryInvariant.BINDING) from None
    original = admit_instantiated_scenario(
        parse_bounded_json_object(source.snapshot, max_bytes=MATERIALIZATION_MAX_BYTES)["scenario"]
    )
    validate_materialization_origins(original, materialized)
    original_model = compile_runtime_model(original)
    original_resources = _inventory_resources(original_model, request, previous)
    originals = {address for address, entry in original_resources.items() if entry.domain == RuntimeDomain.PROVISIONING}
    resources = _inventory_resources(compile_runtime_model(materialized), request, previous)
    preceding = admitted_inventory_predecessor(request, manifest, previous, archive)
    if request.inventory_refresh and preceding is None:
        raise ValueError("inventory refresh requires an accepted predecessor report")
    validate_inventory_lineage(
        report, preceding, originals, previous, operation_id=request.operation_id, resources=resources
    )
    entries = _project_entries(report, preceding, resources, originals, accepted)
    authority = planned_node_collection(original_model, request)
    if (
        authority is None
        or not evaluate_realization_constraint(
            authority.constraint_document,
            node_collection_members(
                (entry for entry in entries.values() if entry.domain == RuntimeDomain.PROVISIONING),
                namespaces=authority.constraint_document.root.fields,
            ),
        ).conformant
    ):
        raise ValueError(InventoryInvariant.MEMBERSHIP)
    live = {address: entry for address, entry in entries.items() if entry.domain == RuntimeDomain.PROVISIONING}
    try:
        validate_portable_node_inventory(live, originals, manifest)
    except (AttributeError, KeyError, TypeError, ValueError):
        raise ValueError(InventoryInvariant.CAPABILITY) from None
    _validate_addition_permission(original, materialized, request, manifest, previous)
    candidate = accepted.with_entries(entries)
    admitted = admit_materialization_submission(submission, request, manifest, previous, candidate)
    provenance = _descendant_provenance(report, materialized)
    current = {entry.address for entry in report.descendants}
    ledger = {
        (entry.address, entry.field_path, entry.domain, entry.requirement_kind): entry
        for entry in (*previous.realization_provenance, *accepted.realization_provenance)
        if entry.address not in current
    }
    ledger.update(
        {(entry.address, entry.field_path, entry.domain, entry.requirement_kind): entry for entry in provenance}
    )
    unchanged = {operation.address for operation in request.operations if operation.action is ChangeAction.UNCHANGED}
    for entry in previous.realization_provenance:
        if entry.address in unchanged:
            ledger[(entry.address, entry.field_path, entry.domain, entry.requirement_kind)] = entry
    identities = {(entry.address, entry.field_path, entry.requirement_kind): key for key, entry in ledger.items()}
    admitted_choices = {
        (entry.address, entry.field_path, entry.requirement_kind)
        for entry in request.realization_authority
        if entry.mode.value in {"open", "constrained"}
    }
    admitted_choices.update(
        (entry.address, entry.field_path, entry.concern)
        for entry in request.realization_constraints
        if entry.posture in {"open", "constrained"}
    )
    for selection in report.backend_selections:
        selected = (selection.address, selection.field_path, selection.requirement_kind)
        identity = identities.get(selected)
        if (
            identity is None
            or ledger[identity].explicitness is ExplicitnessClass.EXACT
            or (selected not in admitted_choices and selection.address not in current)
        ):
            raise ValueError(InventoryInvariant.PROVENANCE)
        ledger[identity] = replace(ledger[identity], provenance=ExplicitnessProvenance.BACKEND_REALIZED)
    return admitted, candidate.with_entries(dict(candidate.entries), realization_provenance=tuple(ledger.values()))


def _project_entries(report, preceding, resources, originals, accepted):
    entries = dict(accepted.entries)
    old = {entry.address for entry in preceding.descendants} if preceding is not None else set()
    declared = {entry.address for entry in report.descendants if entry.state != "autoremoved"}
    foreign = {
        address
        for address, entry in entries.items()
        if entry.domain == RuntimeDomain.PROVISIONING and address not in originals and address not in old
    }
    described = {address for address, entry in resources.items() if entry.domain == RuntimeDomain.PROVISIONING}
    if described - originals != declared | foreign:
        raise ValueError("descriptive inventory does not cover its descendants exactly")
    for record in report.descendants:
        if record.state == "autoremoved":
            if record.address in resources:
                raise ValueError("autoremoved descendant still appears in live SDL")
            entries.pop(record.address, None)
            continue
        resource = resources.get(record.address)
        if (
            resource is None
            or resource.domain != RuntimeDomain.PROVISIONING
            or resource.resource_type not in {"node", "network"}
        ):
            raise ValueError("descendant has no admitted portable SDL resource")
        require_plan_operation_identity(resource.domain, resource.address, resource.resource_type)
        if (resource.payload.get("count") or 1) != 1 or resource.profile_bindings:
            raise ValueError("descendant requires its own single portable identity and native profile admission")
        entries[record.address] = SnapshotEntry(
            resource.address,
            resource.domain,
            resource.resource_type,
            prepared_node_payload_projection(resource.payload),
            resource.ordering_dependencies,
            resource.refresh_dependencies,
            status="terminated" if record.state == "terminated" else "ready",
        )
    return entries


def _validate_addition_permission(original, materialized, request, manifest, previous):
    """Check existing author policy; this read-only report cannot grant permission."""
    differences = materialization_differences(original, materialized)
    content = materialized.model_dump_json(exclude={"materialization_provenance"})
    prospective = AugmentationPreparation.for_request(
        request,
        backend_manifest_v2_model(manifest),
        previous,
        content=content,
        effects=tuple(
            AugmentationEffect(
                field_pointer=difference.field_pointer,
                requirement_refs=("backend-operational",),
                affected_scopes=(difference.field_pointer,),
            )
            for difference in differences
        ),
    )
    if not admit_augmentation_preparation(prospective, request, manifest, previous).is_valid:
        raise ValueError("reported descendant effects exceed the original augmentation permission")


def _descendant_provenance(report, materialized):
    records = []
    bindings = {
        binding.address: binding.node_name for binding in materialized.materialization_provenance.resource_bindings
    }
    for entry in report.descendants:
        if entry.state == "autoremoved":
            continue
        node_name = bindings[entry.address]
        node = materialized.nodes[node_name]
        supplied = node.model_dump(mode="json", exclude_unset=True)
        for descriptor in realization_concern_descriptors():
            if descriptor.section != "nodes":
                continue
            present = supplied
            for token in descriptor.authored_path:
                present = present.get(token) if isinstance(present, dict) else None
            value = nested_authored_value(node, descriptor.authored_path)
            if present is None or value is None or not descriptor.includes_authored_value(value):
                continue
            requirement = CompiledRealizationRequirement(
                address=entry.address,
                field_path=f"nodes.{node_name}.{descriptor.authored_suffix}",
                domain="runtime-realization",
                requirement_kind=descriptor.concern_kind,
                explicitness=ExplicitnessClass.OPEN,
                provenance=ExplicitnessProvenance.BACKEND_REALIZED,
                governing_scope="/nodes",
            )
            records.append(realization_provenance_entry(requirement, False))
    return tuple(records)
