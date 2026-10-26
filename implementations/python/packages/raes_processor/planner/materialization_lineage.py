"""Causal and lifecycle admission over a bounded descendant inventory."""

from raes.materialization_provenance import MaterializationProvenance
from raes_backend_protocols.capabilities import BackendManifest
from raes_backend_protocols.manifest import backend_manifest_v2_model
from raes_contracts.canonical import canonical_json_digest
from raes_contracts.materialization import MaterializationArchive, MaterializationSource
from raes_contracts.materialization_inventory import (
    InventoryInvariant,
    RuntimeDescendantBinding,
    RuntimeInventoryReport,
)
from raes_contracts.planning import PlannedResource, ProvisioningPlan
from raes_contracts.runtime_state import RuntimeSnapshot


def admitted_inventory_predecessor(
    request: ProvisioningPlan, manifest: BackendManifest, previous: RuntimeSnapshot, archive: MaterializationArchive
) -> RuntimeInventoryReport | None:
    """Read and authenticate the latest retained producer inventory and source."""
    from raes import parse_sdl

    from .materialization_admission import validate_materialization_archive_record

    source = request.materialization_source
    if source is None:
        raise ValueError(InventoryInvariant.BINDING)
    records = [
        record
        for record in previous.materialization_attestations
        if record.run_id == source.run_id and record.artifact.source == manifest.name and record.inventory is not None
    ]
    if not records:
        return None
    record = records[-1]
    try:
        submission = archive.read(record)
        validate_materialization_archive_record(submission, record)
        provenance = parse_sdl(submission.sdl).materialization_provenance
    except Exception:
        raise ValueError(InventoryInvariant.ARCHIVE) from None
    _validate_predecessor_binding(provenance, record.inventory, source, manifest)
    return record.inventory


def validate_inventory_lineage(
    report: RuntimeInventoryReport,
    preceding: RuntimeInventoryReport | None,
    original_addresses: set[str],
    previous: RuntimeSnapshot,
    *,
    operation_id: str | None,
    resources: dict[str, PlannedResource],
) -> None:
    """Preserve creation identities and require explicit fresh lifecycle changes."""
    if not report.complete or report.unavailable_evidence:
        raise ValueError(InventoryInvariant.COVERAGE)
    old = {entry.address: entry for entry in preceding.descendants} if preceding is not None else {}
    current = {entry.address: entry for entry in report.descendants}
    _validate_report_progress(report, preceding, old, current)
    for entry in report.descendants:
        before = _validate_descendant_identity(entry, old, previous, original_addresses)
        _validate_lifecycle_binding(entry, before, operation_id, report.attempt_id)
        _validate_ancestry(entry, current, original_addresses, resources)


def _validate_report_progress(
    report: RuntimeInventoryReport,
    preceding: RuntimeInventoryReport | None,
    old: dict[str, RuntimeDescendantBinding],
    current: dict[str, RuntimeDescendantBinding],
) -> None:
    if preceding is not None and report.sequence <= preceding.sequence:
        raise ValueError(InventoryInvariant.REPLAY)
    if old.keys() - current.keys():
        raise ValueError(InventoryInvariant.COVERAGE)


def _validate_descendant_identity(
    entry: RuntimeDescendantBinding,
    old: dict[str, RuntimeDescendantBinding],
    previous: RuntimeSnapshot,
    original_addresses: set[str],
) -> RuntimeDescendantBinding | None:
    if entry.address in original_addresses or entry.source_address not in original_addresses:
        raise ValueError(InventoryInvariant.LINEAGE)
    before = old.get(entry.address)
    if before is None and entry.address in previous.entries:
        raise ValueError(InventoryInvariant.IDENTITY)
    if before is not None:
        _validate_retained_identity(before, entry)
    return before


def _validate_lifecycle_binding(
    entry: RuntimeDescendantBinding, before: RuntimeDescendantBinding | None, operation_id: str | None, attempt_id: str
) -> None:
    if entry.lifecycle is not None and (before is None or entry != before):
        if (entry.lifecycle.operation_id, entry.lifecycle.attempt_id) != (operation_id, attempt_id):
            raise ValueError(InventoryInvariant.BINDING)


def _validate_retained_identity(before: RuntimeDescendantBinding, entry: RuntimeDescendantBinding) -> None:
    identity_fields = (
        "address",
        "parent_address",
        "parent_instance_index",
        "source_address",
        "native_identity_digest",
        "creation",
    )
    if any(getattr(before, field) != getattr(entry, field) for field in identity_fields):
        raise ValueError(InventoryInvariant.IDENTITY)
    allowed = {
        "active": {"active", "terminated", "autoremoved"},
        "terminated": {"terminated", "autoremoved"},
        "autoremoved": {"autoremoved"},
    }
    if entry.state not in allowed[before.state] or (
        entry.state == before.state and entry.lifecycle != before.lifecycle
    ):
        raise ValueError(InventoryInvariant.IDENTITY)


def _validate_ancestry(
    entry: RuntimeDescendantBinding,
    current: dict[str, RuntimeDescendantBinding],
    original_addresses: set[str],
    resources: dict[str, PlannedResource],
) -> None:
    seen = {entry.address}
    descendant = entry
    while descendant.parent_address not in original_addresses:
        parent = _causal_parent(descendant, entry.source_address, current, seen)
        seen.add(parent.address)
        descendant = parent
    if descendant.parent_address != entry.source_address:
        raise ValueError(InventoryInvariant.LINEAGE)
    source = resources.get(entry.source_address)
    if (
        source is None
        or source.resource_type not in {"node", "network"}
        or descendant.parent_instance_index >= (source.payload.get("count") or 1)
    ):
        raise ValueError(InventoryInvariant.LINEAGE)


def _causal_parent(
    descendant: RuntimeDescendantBinding,
    source_address: str,
    current: dict[str, RuntimeDescendantBinding],
    seen: set[str],
) -> RuntimeDescendantBinding:
    parent = current.get(descendant.parent_address)
    if parent is None or parent.address in seen or len(seen) >= 64:
        raise ValueError(InventoryInvariant.LINEAGE)
    if parent.source_address != source_address or descendant.parent_instance_index != 0:
        raise ValueError(InventoryInvariant.LINEAGE)
    return parent


def _validate_predecessor_binding(
    provenance: MaterializationProvenance,
    inventory: RuntimeInventoryReport | None,
    source: MaterializationSource,
    manifest: BackendManifest,
) -> None:
    envelope = manifest.realization_envelope
    if inventory is None or envelope is None:
        raise ValueError(InventoryInvariant.BINDING)
    if (
        provenance.instantiated_digest.value != source.instantiated_digest
        or provenance.producer.configuration_digest != envelope.configuration.configuration_digest
        or inventory.target_scope != source.target_scope
        or provenance.producer.manifest_digest
        != canonical_json_digest(backend_manifest_v2_model(manifest).model_dump(mode="json"))
    ):
        raise ValueError(InventoryInvariant.BINDING)
