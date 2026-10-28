"""Obligation-specific evidence for fail-closed runtime cases."""

from raes_contracts.contracts.participant_control_applicability import control_digest


def negative_condition(case, measured):
    parents = {
        item.commit.receipt.ref: item
        for item in measured.evaluations
        if item.commit.receipt is not None and item.commit.receipt.ref in measured.parent_operation_ids
    }
    if case.obligation == "strict-denial":
        return any(
            item.composition.disposition in {"deny", "withhold"}
            and any(
                result.payload is not None
                and result.payload.kind == "decision"
                and result.payload.disposition in {"deny", "withhold"}
                for result in item.results
            )
            for item in parents.values()
        )
    if case.obligation == "authority":
        return any(
            not event.allowed
            and event.action == "dispatch_participant_control_effects"
            and event.target == case.participant_address
            for event in measured.audit
        )
    if case.obligation == "stale-cut":
        return any(
            event.reason == "control-stale-cut" and event.operation_id in measured.parent_operation_ids
            for event in measured.audit
        )
    if case.obligation == "mandatory-coverage":
        for identity, resolution in measured.resolutions:
            if identity not in measured.parent_operation_ids:
                continue
            if resolution is None:
                return any(
                    event.operation_id == identity and event.reason == "control-context-invalid"
                    for event in measured.audit
                )
            request = resolution.request
            required = {item.obligation_id for item in request.selection.obligations}
            coverage = {item.obligation_id for item in request.applicability.coverage}
            if required - coverage or any(item.status == "unresolved" for item in request.applicability.coverage):
                return True
        return False
    if case.obligation == "conflict":
        return any(
            item.composition.disposition == "conflict"
            or {"permit", "deny"}
            <= {
                result.payload.disposition
                for result in item.results
                if result.payload is not None and result.payload.kind == "decision"
            }
            for item in parents.values()
        )
    if case.obligation == "integrity":
        return any(
            item.composition.disposition == "failed"
            and any(
                result.status == "failed"
                and result.slot_id in item.request.applicability.required_slot_ids
                and (control_digest(item.request.context), result.slot_id) in measured.integrity_slots
                for result in item.results
            )
            for item in parents.values()
        )
    return False
