"""Canonical observation results prepared for one terminal operation commit."""

from __future__ import annotations

import json
from dataclasses import dataclass

from raes_backend_protocols.capabilities import BackendManifest
from raes_contracts.contracts import (
    ExperimentEvidenceRecordReferenceModel,
    ExperimentRealizedFormDisclosureModel,
    ExperimentReferenceModel,
)
from raes_contracts.observation_demand import (
    ObservationBasis,
    ObservationLifecycleItem,
    ObservationLifecycleResult,
)
from raes_contracts.observation_reporting import RealizationDescriptionItem


@dataclass(frozen=True)
class ObservationExecution:
    """Committed lifecycle metadata and protected realized-form disclosures."""

    lifecycle: ObservationLifecycleResult
    realized_form_disclosures: tuple[ExperimentRealizedFormDisclosureModel, ...]


@dataclass(frozen=True)
class PreparedObservationExecution:
    """Private prepared result split into public metadata and atomic payload."""

    metadata: ObservationExecution
    result_payload: dict[str, object]


def prepare_observation_execution(
    lifecycle: ObservationLifecycleResult,
    description: tuple[RealizationDescriptionItem, ...],
    manifest: BackendManifest,
    *,
    operation_id: str | None,
) -> PreparedObservationExecution:
    """Prepare protected values for the control-plane terminal transaction."""

    disclosures = tuple(_realized_form_disclosure(item, manifest) for item in description)
    metadata = ObservationExecution(
        lifecycle=ObservationLifecycleResult(
            collected=tuple(_item_metadata(item) for item in lifecycle.collected),
            retained=tuple(_item_metadata(item) for item in lifecycle.retained),
            exported=tuple(_item_metadata(item) for item in lifecycle.exported),
            operational_count=lifecycle.operational_count,
        ),
        realized_form_disclosures=disclosures,
    )
    if lifecycle.exported:
        raise ValueError("observation export requires a governed delivery owner")
    retained_disclosures = tuple(
        disclosure for item, disclosure in zip(description, disclosures, strict=True) if item.retention_required
    )
    if (lifecycle.retained or retained_disclosures) and (operation_id is None or not operation_id.strip()):
        raise ValueError("durable observation lifecycle requires an operation identity")
    payload = {
        "schema_version": "observation-operation-result/v1",
        "operation_id": operation_id,
        "lifecycle": {
            "collected": [_item_payload(item, include_values=False) for item in metadata.lifecycle.collected],
            "retained": [_item_payload(item, include_values=False) for item in metadata.lifecycle.retained],
            "exported": [_item_payload(item, include_values=False) for item in metadata.lifecycle.exported],
            "operational_count": metadata.lifecycle.operational_count,
        },
        "retained": [_item_payload(item) for item in lifecycle.retained],
        "realized_form_disclosures": [item.model_dump(mode="json", exclude_none=True) for item in retained_disclosures],
    }
    return PreparedObservationExecution(metadata, payload)


def _item_metadata(item: ObservationLifecycleItem) -> ObservationLifecycleItem:
    return ObservationLifecycleItem(item.selector_key, (), item.integrity_ref)


def observation_execution_from_payload(payload: object) -> ObservationExecution | None:
    """Recover public observation results from one committed operation payload."""

    execution = None
    if isinstance(payload, dict) and payload.get("schema_version") == "observation-operation-result/v1":
        lifecycle = payload.get("lifecycle")
        disclosures = payload.get("realized_form_disclosures")
        if isinstance(lifecycle, dict) and isinstance(disclosures, list):
            try:
                execution = ObservationExecution(
                    lifecycle=ObservationLifecycleResult(
                        collected=_metadata_items(lifecycle.get("collected")),
                        retained=_metadata_items(lifecycle.get("retained")),
                        exported=_metadata_items(lifecycle.get("exported")),
                        operational_count=int(lifecycle.get("operational_count", 0)),
                    ),
                    realized_form_disclosures=tuple(
                        ExperimentRealizedFormDisclosureModel.model_validate(item) for item in disclosures
                    ),
                )
            except (TypeError, ValueError):
                execution = None
    return execution


def _metadata_items(value: object) -> tuple[ObservationLifecycleItem, ...]:
    if not isinstance(value, list):
        raise TypeError("observation lifecycle metadata must be a list")
    items = []
    for item in value:
        if not isinstance(item, dict) or not isinstance(item.get("selector_key"), str):
            raise TypeError("observation lifecycle metadata item is invalid")
        integrity_ref = item.get("integrity_ref")
        if integrity_ref is not None and not isinstance(integrity_ref, str):
            raise TypeError("observation lifecycle integrity reference is invalid")
        items.append(ObservationLifecycleItem(item["selector_key"], (), integrity_ref))
    return tuple(items)


def _item_payload(item: ObservationLifecycleItem, *, include_values: bool = True) -> dict[str, object]:
    return {
        "selector_key": item.selector_key,
        **({"values": _json_value(list(item.values))} if include_values else {}),
        **({"integrity_ref": item.integrity_ref} if item.integrity_ref is not None else {}),
    }


def _realized_form_disclosure(
    item: RealizationDescriptionItem,
    manifest: BackendManifest,
) -> ExperimentRealizedFormDisclosureModel:
    selector_key, value, basis, evidence_ref, integrity_ref, _retention_required = item
    evidence_refs = (
        []
        if evidence_ref is None
        else [ExperimentEvidenceRecordReferenceModel(ref_kind="evidence-record", ref_id=evidence_ref)]
    )
    integrity = "" if integrity_ref is None else f" Integrity reference: {integrity_ref}."
    return ExperimentRealizedFormDisclosureModel(
        concern_id=selector_key,
        concern_kind="other",
        basis=("backend-realized" if basis is ObservationBasis.BACKEND_SELECTED else "observed"),
        realized_by_ref=ExperimentReferenceModel(
            ref_kind="backend",
            ref_id=manifest.identity.name,
            ref_version=manifest.identity.version,
        ),
        realized_value_summary=_json_text(value),
        disclosure=f"Requested realization description achieved with basis '{basis.value}'.{integrity}",
        evidence_refs=evidence_refs,
    )


def _json_value(value: object) -> object:
    try:
        encoded = json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":"))
        return json.loads(encoded)
    except (TypeError, ValueError) as exc:
        raise ValueError("observation result must be JSON-compatible") from exc


def _json_text(value: object) -> str:
    encoded = json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":"))
    if len(encoded.encode("utf-8")) > 16_384:
        raise ValueError("realization description exceeds the bounded report size")
    return encoded


__all__ = [
    "ObservationExecution",
    "PreparedObservationExecution",
    "observation_execution_from_payload",
    "prepare_observation_execution",
]
