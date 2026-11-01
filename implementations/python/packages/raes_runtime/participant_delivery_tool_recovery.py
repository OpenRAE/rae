"""Classify interrupted delivery tools from retained core bindings, without replay."""

from pydantic import TypeAdapter
from raes_contracts.contracts.participant_action_admission import ParticipantActionAdmissionRequest
from raes_contracts.operation_lifecycle import OperationState
from raes_contracts.participant_tool_actions import ParticipantToolActionRequest, ParticipantToolActionSettlement

from .participant_delivery_invocation_records import delivery_invocation_binding, delivery_tool_origin_matches
from .participant_invocation_tool_actions import InvocationToolEntry
from .participant_invocation_tool_claims import tool_action_claim_payload


def reconcile_delivery_tool(plane, record, *, port_type):
    payload = record.result_payload or {}
    retained = payload.get("delivery_tool")
    if retained is None:
        return False
    claim = tool_action_claim_payload(payload)
    parent = plane.delivery_operations.get(record.status.context.parent_operation_id)
    invocation = None if parent is None else delivery_invocation_binding(parent)
    if invocation is None or not delivery_tool_origin_matches(invocation, claim):
        raise ValueError("delivery tool recovery requires its retained invocation")
    admission = TypeAdapter(ParticipantActionAdmissionRequest).validate_python(retained["admission"])
    request = ParticipantToolActionRequest(
        **{
            **{key: value for key, value in claim.items() if key != "kind"},
            "target_addresses": tuple(claim["target_addresses"]),
        }
    )
    port = port_type.recovery_port(plane, invocation, parent)
    entry = InvocationToolEntry(
        request,
        record.receipt.operation_id,
        retained["admission_ordinal"],
        record.receipt.submitted_at,
        record,
        admission=admission,
    )
    settlement = (
        ParticipantToolActionSettlement.WITHHELD
        if record.status.state is OperationState.ACCEPTED
        else ParticipantToolActionSettlement.INDETERMINATE
    )
    port.settle_interrupted_tool(entry, settlement, "interrupted")
    return True
