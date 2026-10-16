"""Occurrence identity and order invariants inside the incumbent store transactions."""

from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING

from raes_backend_protocols.inject_execution import InjectExecutionEvidence
from raes_contracts.canonical import canonical_json_digest
from raes_contracts.contracts import (
    InjectOccurrenceModel,
    InjectOccurrenceOutcomeModel,
    OperationArtifactReferenceModel,
    inject_trigger_request_digest,
    require_inject_occurrence_invocation,
    validate_inject_occurrence_claims,
    validate_inject_occurrence_outcome,
)
from raes_contracts.planning import RuntimeDomain
from raes_contracts.runtime_state import OperationState

if TYPE_CHECKING:
    from .control_plane_store import ControlPlaneOperationRecord
    from .operation_invocation_ledger import InvocationLedger

INJECT_GENESIS_HEAD = "inject-order:genesis"


def inject_order_head(occurrence: InjectOccurrenceModel) -> str:
    """Produce an opaque head that the trusted order issuer can bind in the next permit."""

    return canonical_json_digest(
        {
            "domain": "raes.inject-order-head/v1",
            "request": inject_trigger_request_digest(occurrence.request),
            "position": occurrence.order.position,
        }
    )


def require_inject_record(record: ControlPlaneOperationRecord) -> None:
    occurrence = record.inject_occurrence
    if occurrence is None:
        _require_no_unbound_inject_evidence(record)
        return
    invocation = _require_occurrence_record(record, occurrence)
    outcome = record.inject_outcome
    if outcome is not None:
        _require_outcome_record(record, occurrence, invocation, outcome)
    elif record.inject_evidence is not None:
        raise ValueError("inject artifact evidence requires its validated occurrence outcome")


def _require_no_unbound_inject_evidence(record: ControlPlaneOperationRecord) -> None:
    invocation = record.invocation
    if (
        record.inject_outcome is not None
        or record.inject_evidence is not None
        or (invocation is not None and invocation.request.command.contract_id == "inject-occurrence-v1")
    ):
        raise ValueError("inject invocation requires its retained occurrence")


def _require_occurrence_record(
    record: ControlPlaneOperationRecord, occurrence: InjectOccurrenceModel
) -> InvocationLedger:
    InjectOccurrenceModel.model_validate(occurrence.model_dump(mode="json"))
    invocation = record.invocation
    if invocation is None:
        raise ValueError("inject occurrence requires its invocation ledger")
    if invocation.native or record.receipt.domain is not RuntimeDomain.ORCHESTRATION:
        raise ValueError("inject occurrence requires its orchestration provider invocation")
    require_inject_occurrence_invocation(occurrence, invocation.request)
    if (
        record.idempotency_key != occurrence.request.request_key
        or record.request_fingerprint != occurrence.admission.request_commitment
    ):
        raise ValueError("inject occurrence must retain its retry claim and admission commitment")
    if record.status.state is OperationState.SUCCEEDED and record.inject_outcome is None:
        raise ValueError("inject success requires its independently validated outcome")
    return invocation


def _require_outcome_record(
    record: ControlPlaneOperationRecord,
    occurrence: InjectOccurrenceModel,
    invocation: InvocationLedger,
    outcome: InjectOccurrenceOutcomeModel,
) -> None:
    InjectOccurrenceOutcomeModel.model_validate(outcome.model_dump(mode="json"))
    validate_inject_occurrence_outcome(occurrence, invocation.request, outcome)
    if outcome.response not in invocation.responses:
        raise ValueError("inject outcome requires retained backend evidence")
    expected = getattr(outcome.response.message, "proposed_state", OperationState.FAILED)
    if record.status.state is not expected:
        raise ValueError("inject outcome disagrees with terminal operation state")
    evidence = record.inject_evidence
    if evidence is None:
        raise ValueError("inject outcome requires its durable artifact evidence")
    InjectExecutionEvidence.model_validate(evidence.model_dump(mode="json"))
    _require_evidence_parent(evidence, occurrence)
    _require_evidence_references(evidence, outcome)


def _require_evidence_parent(evidence: InjectExecutionEvidence, occurrence: InjectOccurrenceModel) -> None:
    parent = evidence.manifest.parent_ref
    if (
        evidence.manifest.scope != "scenario"
        or parent.ref_kind != "scenario"
        or parent.ref_id != occurrence.scenario.artifact_id
    ):
        raise ValueError("inject artifact parent does not match the admitted occurrence scenario")


def _require_evidence_references(evidence: InjectExecutionEvidence, outcome: InjectOccurrenceOutcomeModel) -> None:
    reference = OperationArtifactReferenceModel(
        contract_id="associated-artifact-manifest-v1",
        artifact_id=evidence.manifest.manifest_id,
        digest=canonical_json_digest(evidence.manifest.model_dump(mode="json")),
    )
    message_effects = getattr(outcome.response.message, "effects", None)
    produced = [] if message_effects is None else [*message_effects.evidence_refs]
    result_reference = getattr(outcome.response.message, "result", None)
    if result_reference is not None:
        produced.append(result_reference)
    for item in outcome.bindings:
        produced.extend(item.effects.evidence_refs)
        if item.readback is not None:
            produced.append(item.readback)
    if not produced or any(item != reference for item in produced):
        raise ValueError("inject readback must resolve to its independently validated durable evidence")


def require_inject_transition(prior: ControlPlaneOperationRecord, replacement: ControlPlaneOperationRecord) -> None:
    if prior.inject_occurrence != replacement.inject_occurrence:
        raise ValueError("inject occurrence pins are immutable")
    if prior.inject_outcome is not None and prior.inject_outcome != replacement.inject_outcome:
        raise ValueError("inject outcome is immutable")
    if prior.inject_evidence is not None and prior.inject_evidence != replacement.inject_evidence:
        raise ValueError("inject artifact evidence is immutable")


def require_inject_history(records: Iterable[ControlPlaneOperationRecord]) -> None:
    claims = sorted(
        (record.inject_occurrence for record in records if record.inject_occurrence is not None),
        key=lambda item: item.order.position,
    )
    validate_inject_occurrence_claims(claims)
    head = INJECT_GENESIS_HEAD
    for position, claim in enumerate(claims, 1):
        if claim.order.position != position:
            raise ValueError("inject order position does not follow the admitted chain")
        if claim.order.predecessor != head:
            raise ValueError("inject order head does not follow the preceding admitted claim")
        head = inject_order_head(claim)


def require_inject_claim(
    record: ControlPlaneOperationRecord, records: Iterable[ControlPlaneOperationRecord], *, revision: int
) -> None:
    """Called under the store lock/transaction, never as a preflight-only lookup."""

    if record.inject_occurrence is None:
        return
    existing = tuple(records)
    if any(item.receipt.operation_id == record.receipt.operation_id for item in existing):
        return
    if record.inject_occurrence.store_revision != str(revision):
        raise ValueError("inject claim snapshot revision is stale")
    require_inject_history((*existing, record))
